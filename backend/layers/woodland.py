"""National Forest Inventory and Native Woodland Survey overlays (PostGIS).

Sources (open): NatureScot Scottish Forestry GeoServer / Forestry Commission /
Scottish Forestry — Open Government Licence v3.0. Map layers are land-use
context, not a rent and not a title.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import psycopg2
import yaml
from psycopg2 import extras

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
MAX_FEATURES = 80


class LayerUnavailable(Exception):
    """Raised when a woodland PostGIS table is missing, empty, or unreachable."""


@dataclass(frozen=True)
class WoodlandLayer:
    layer_id: str
    table: str
    sources_key: str
    select_cols: tuple[str, ...]
    props_from_row: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def _db_config() -> dict[str, Any]:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        return {"dsn": url}
    return {
        "dbname": os.getenv("WEALTH_DB_NAME", "scotland_wealth"),
        "user": os.getenv("WEALTH_DB_USER", "wealth_user"),
        "password": os.getenv("WEALTH_DB_PASSWORD", ""),
        "host": os.getenv("WEALTH_DB_HOST", "localhost"),
        "port": os.getenv("WEALTH_DB_PORT", "5432"),
    }


def _connect():
    cfg = _db_config()
    if "dsn" in cfg:
        return psycopg2.connect(cfg["dsn"])
    return psycopg2.connect(**cfg)


@lru_cache(maxsize=1)
def _sources() -> dict[str, Any]:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def source_meta(sources_key: str) -> dict[str, Any]:
    block = (_sources().get(sources_key) or {}) if isinstance(_sources(), dict) else {}
    return {
        "source": block.get("name") or sources_key,
        "licence": block.get("licence") or "Open Government Licence v3.0",
        "attribution": block.get("attribution") or "",
        "source_url": block.get("source_url") or "",
        "wfs_url": block.get("wfs_url") or "",
        "wfs_type_name": block.get("wfs_type_name") or "",
        "vintage": block.get("vintage") or "see local ingest stamp",
        "gaps": block.get("gaps") or [],
    }


def _nfi_props(row: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "feature_id": row.get("feature_id"),
        "category": row.get("category"),
        "ift_ioa": row.get("ift_ioa"),
        "country": row.get("country"),
        "area_ha": row.get("area_ha"),
        "layer": "nfi",
        "source": meta["source"],
        "licence": meta["licence"],
    }


def _nwss_props(row: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "feature_id": row.get("feature_id"),
        "object_id": row.get("object_id"),
        "scptdata_i": row.get("scptdata_i"),
        "woodland_type": row.get("woodland_type"),
        "canopy_pct": row.get("canopy_pct"),
        "native_pct": row.get("native_pct"),
        "dom_habitat": row.get("dom_habitat"),
        "hectares": row.get("hectares"),
        "maturity": row.get("maturity"),
        "layer": "native_woodland",
        "source": meta["source"],
        "licence": meta["licence"],
    }


NFI = WoodlandLayer(
    layer_id="nfi",
    table="nfi_woodland",
    sources_key="nfi",
    select_cols=("feature_id", "category", "ift_ioa", "country", "area_ha"),
    props_from_row=_nfi_props,
)

NATIVE_WOODLAND = WoodlandLayer(
    layer_id="native_woodland",
    table="native_woodland",
    sources_key="native_woodland",
    select_cols=(
        "feature_id",
        "object_id",
        "scptdata_i",
        "woodland_type",
        "canopy_pct",
        "native_pct",
        "dom_habitat",
        "hectares",
        "maturity",
    ),
    props_from_row=_nwss_props,
)

LAYERS = {NFI.layer_id: NFI, NATIVE_WOODLAND.layer_id: NATIVE_WOODLAND}


def is_loaded(layer: WoodlandLayer) -> bool:
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("Woodland PostGIS unavailable (%s): %s", layer.layer_id, exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (f"public.{layer.table}",),
            )
            if not bool(cur.fetchone()[0]):
                return False
            cur.execute(f"SELECT 1 FROM {layer.table} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("Woodland load check failed (%s): %s", layer.layer_id, exc)
        return False
    finally:
        conn.close()


def require_loaded(layer: WoodlandLayer) -> None:
    if not is_loaded(layer):
        raise LayerUnavailable(
            f"{layer.layer_id} is not available: {layer.table} is missing or empty. "
            "Ingest open woodland GeoJSON "
            "(python -m etl.ingest_woodland_layers) before publishing this layer."
        )


def query_bbox(
    layer: WoodlandLayer,
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport woodland polygons as GeoJSON (WGS84)."""
    require_loaded(layer)
    cap = max(1, min(int(max_features), MAX_FEATURES))
    meta = source_meta(layer.sources_key)
    cols = ", ".join(layer.select_cols)
    order_col = "area_ha" if "area_ha" in layer.select_cols else "hectares"
    sql = f"""
        SELECT
            {cols},
            ST_AsGeoJSON(geom)::json AS geometry
        FROM {layer.table}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY {order_col} DESC NULLS LAST
        LIMIT %s
    """
    try:
        conn = _connect()
    except Exception as exc:
        raise LayerUnavailable(
            f"{layer.layer_id} PostGIS unavailable: {exc}"
        ) from exc
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (west, south, east, north, west, south, east, north, cap),
            )
            rows = cur.fetchall()
    except Exception as exc:
        raise LayerUnavailable(f"{layer.layer_id} query failed: {exc}") from exc
    finally:
        conn.close()

    features = []
    for row in rows:
        geom = row.get("geometry")
        if not geom:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": layer.props_from_row(dict(row), meta),
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "layer": layer.layer_id,
            "count": len(features),
            "capped": len(features) >= cap,
            **meta,
        },
    }


def query_nfi_bbox(
    south: float, west: float, north: float, east: float, max_features: int = MAX_FEATURES
) -> dict[str, Any]:
    return query_bbox(NFI, south, west, north, east, max_features=max_features)


def query_native_woodland_bbox(
    south: float, west: float, north: float, east: float, max_features: int = MAX_FEATURES
) -> dict[str, Any]:
    return query_bbox(
        NATIVE_WOODLAND, south, west, north, east, max_features=max_features
    )
