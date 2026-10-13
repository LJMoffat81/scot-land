"""NRS Census 2022 Settlements and Localities from local PostGIS.

Source: National Records of Scotland via maps.gov.scot Census2022 WFS
(CEN2022:Settlement2022, CEN2022:Locality2022). Open Government Licence.
When tables are missing or empty, callers must return HTTP 503 — never invent
settlement or locality polygons.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from psycopg2 import extras

from georgist.db import DatabaseUnavailable, connect

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"

PlaceKind = Literal["settlements", "localities"]

TABLES: dict[PlaceKind, str] = {
    "settlements": "nrs_settlements",
    "localities": "nrs_localities",
}
MAX_FEATURES = 200


class LayerUnavailable(Exception):
    """Raised when NRS place polygons are not loaded or PostGIS is unreachable."""


@lru_cache(maxsize=1)
def _source_block() -> dict[str, Any]:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    return dict(sources.get("nrs_settlements_localities") or {})


def source_meta(kind: PlaceKind) -> dict[str, Any]:
    block = _source_block()
    layer = (block.get("layers") or {}).get(kind) or {}
    return {
        "source": layer.get("name")
        or block.get("name")
        or "NRS Census 2022 Settlements and Localities",
        "licence": block.get("licence") or "OGL-3.0",
        "attribution": block.get("attribution")
        or (
            "Contains National Records of Scotland data © Crown copyright "
            "and database right. Contains Ordnance Survey data © Crown "
            "copyright and database right."
        ),
        "source_url": block.get("source_url")
        or "https://www.nrscotland.gov.uk/statistics-and-data/geography",
        "wfs_url": block.get("wfs_url"),
        "wfs_type": layer.get("wfs_type"),
        "vintage": block.get("vintage") or "Census 2022",
        "product": layer.get("product") or kind,
        "gaps": list(block.get("gaps") or []),
    }


def is_loaded(kind: PlaceKind) -> bool:
    table = TABLES[kind]
    try:
        conn = connect()
    except DatabaseUnavailable as exc:
        logger.info("NRS %s PostGIS unavailable: %s", kind, exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{table}",))
            if not cur.fetchone()[0]:
                return False
            cur.execute(f"SELECT 1 FROM {table} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("NRS %s load check failed: %s", kind, exc)
        return False
    finally:
        conn.close()


def require_loaded(kind: PlaceKind) -> None:
    if not is_loaded(kind):
        table = TABLES[kind]
        raise LayerUnavailable(
            f"NRS {kind} are not available: {table} is missing or empty. "
            "Ingest Census 2022 polygons "
            "(python -m etl.ingest_nrs_settlements) before publishing this layer."
        )


def query_bbox(
    kind: PlaceKind,
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport place polygons as GeoJSON (WGS84)."""
    require_loaded(kind)
    table = TABLES[kind]
    cap = max(1, min(int(max_features), MAX_FEATURES))
    meta = source_meta(kind)
    sql = f"""
        SELECT
            code,
            name,
            popcount,
            area_m2,
            ST_AsGeoJSON(geom)::json AS geometry
        FROM {table}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY popcount DESC NULLS LAST
        LIMIT %s
    """
    try:
        conn = connect()
    except DatabaseUnavailable as exc:
        raise LayerUnavailable(f"NRS {kind} PostGIS unavailable: {exc}") from exc
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (west, south, east, north, west, south, east, north, cap),
            )
            rows = cur.fetchall()
    except Exception as exc:
        raise LayerUnavailable(f"NRS {kind} query failed: {exc}") from exc
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
                "properties": {
                    "code": row.get("code"),
                    "name": row.get("name"),
                    "popcount": row.get("popcount"),
                    "area_m2": row.get("area_m2"),
                    "layer": kind,
                    "source": meta["source"],
                    "licence": meta["licence"],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "layer": kind,
            "count": len(features),
            "capped": len(features) >= cap,
            **meta,
        },
    }


def lookup_at(kind: PlaceKind, lat: float, lng: float) -> dict[str, Any] | None:
    """Containing place under a point, or None when unloaded / no hit."""
    if not is_loaded(kind):
        return None
    table = TABLES[kind]
    try:
        conn = connect()
    except DatabaseUnavailable:
        return None
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT code, name, popcount, area_m2
                FROM {table}
                WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY popcount ASC NULLS LAST
                LIMIT 1
                """,
                (lng, lat),
            )
            row = cur.fetchone()
    except Exception:
        return None
    finally:
        conn.close()
    if not row:
        return None
    return {
        "code": row["code"],
        "name": row["name"],
        "popcount": row["popcount"],
        "area_m2": row["area_m2"],
        "layer": kind,
        **source_meta(kind),
    }
