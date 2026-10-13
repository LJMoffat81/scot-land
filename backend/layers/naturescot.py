"""NatureScot SSSI and protected-area designations from local PostGIS.

Sources are NatureScot OGL-3.0 open downloads / WFS. Raw geometry stays under
data/external/naturescot/ (gitignored). BBox endpoints return 503 when tables
are missing or empty — never invent designations.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import psycopg2
import yaml
from psycopg2 import extras

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"

SSSI_TABLE = "naturescot_sssi"
DESIGNATIONS_TABLE = "naturescot_designations"
MAX_FEATURES = 80

DESIGNATION_TYPES = ("spa", "sac", "nnr")

ATTRIBUTION = (
    "Contains NatureScot information licensed under the Open Government "
    "Licence v3.0. Protected-area boundaries are indicative — confirm legal "
    "status with NatureScot / ScotLIS as appropriate."
)


class LayerUnavailable(Exception):
    """Raised when NatureScot tables are not loaded or PostGIS is unreachable."""


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


def sssi_source_meta() -> dict[str, Any]:
    cfg = (_sources().get("naturescot_sssi") or {})
    return {
        "source": cfg.get("name") or "NatureScot Sites of Special Scientific Interest",
        "licence": cfg.get("licence") or "OGL-3.0",
        "attribution": cfg.get("attribution") or ATTRIBUTION,
        "source_url": cfg.get("source_url")
        or "https://opendata.nature.scot/maps/sites-of-special-scientific-interest",
        "download_url": cfg.get("download_url")
        or "https://gis-downloads.nature.scot/SSSI_SCOTLAND_GEOJSON_4326.zip",
        "vintage": cfg.get("vintage") or "see local ingest stamp",
        "gaps": cfg.get("gaps")
        or [
            "Indicative NatureScot boundaries — not a title plan",
            "Status and extent can change after the download vintage",
        ],
    }


def designations_source_meta() -> dict[str, Any]:
    cfg = (_sources().get("naturescot_designations") or {})
    return {
        "source": cfg.get("name")
        or "NatureScot designations (SPA, SAC, NNR)",
        "licence": cfg.get("licence") or "OGL-3.0",
        "attribution": cfg.get("attribution") or ATTRIBUTION,
        "source_url": cfg.get("source_url")
        or "https://opendata.nature.scot/",
        "designation_types": list(cfg.get("designation_types") or DESIGNATION_TYPES),
        "downloads": cfg.get("downloads")
        or {
            "spa": "https://gis-downloads.nature.scot/SPA_SCOTLAND_GEOJSON_4326.zip",
            "sac": "https://gis-downloads.nature.scot/SAC_SCOTLAND_GEOJSON_4326.zip",
            "nnr": "https://gis-downloads.nature.scot/NNR_SCOTLAND_GEOJSON_4326.zip",
        },
        "vintage": cfg.get("vintage") or "see local ingest stamp",
        "gaps": cfg.get("gaps")
        or [
            "Indicative NatureScot boundaries — not a title plan",
            "SSSI is a separate layer; this overlay is SPA / SAC / NNR",
            "Status and extent can change after the download vintage",
        ],
    }


def _table_loaded(table: str) -> bool:
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("NatureScot PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (f"public.{table}",),
            )
            exists = bool(cur.fetchone()[0])
            if not exists:
                return False
            cur.execute(f"SELECT 1 FROM {table} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("NatureScot load check failed (%s): %s", table, exc)
        return False
    finally:
        conn.close()


def sssi_is_loaded() -> bool:
    return _table_loaded(SSSI_TABLE)


def designations_is_loaded() -> bool:
    return _table_loaded(DESIGNATIONS_TABLE)


def require_sssi_loaded() -> None:
    if not sssi_is_loaded():
        raise LayerUnavailable(
            "SSSI designations are not available: naturescot_sssi is missing "
            "or empty. Ingest NatureScot SSSI "
            "(python -m etl.ingest_naturescot --layer sssi) before publishing."
        )


def require_designations_loaded() -> None:
    if not designations_is_loaded():
        raise LayerUnavailable(
            "NatureScot designations are not available: naturescot_designations "
            "is missing or empty. Ingest SPA/SAC/NNR "
            "(python -m etl.ingest_naturescot --layer designations) before publishing."
        )


def query_sssi_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport SSSI polygons as GeoJSON (WGS84)."""
    require_sssi_loaded()
    cap = max(1, min(int(max_features), MAX_FEATURES))
    meta = sssi_source_meta()
    sql = f"""
        SELECT
            pa_code,
            name,
            status,
            site_type,
            site_ha,
            european_code,
            ST_AsGeoJSON(geom)::json AS geometry
        FROM {SSSI_TABLE}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY site_ha DESC NULLS LAST
        LIMIT %s
    """
    try:
        conn = _connect()
    except Exception as exc:
        raise LayerUnavailable(f"NatureScot PostGIS unavailable: {exc}") from exc
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(sql, (west, south, east, north, west, south, east, north, cap))
            rows = cur.fetchall()
    except Exception as exc:
        raise LayerUnavailable(f"SSSI query failed: {exc}") from exc
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
                    "pa_code": row.get("pa_code"),
                    "name": row.get("name"),
                    "status": row.get("status"),
                    "site_type": row.get("site_type"),
                    "site_ha": row.get("site_ha"),
                    "european_code": row.get("european_code"),
                    "designation_type": "sssi",
                    "layer": "sssi",
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
            "layer": "sssi",
            "count": len(features),
            "capped": len(features) >= cap,
            **meta,
        },
    }


def query_designations_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport SPA / SAC / NNR polygons as GeoJSON (WGS84)."""
    require_designations_loaded()
    cap = max(1, min(int(max_features), MAX_FEATURES))
    meta = designations_source_meta()
    sql = f"""
        SELECT
            site_key,
            designation_type,
            pa_code,
            name,
            status,
            site_type,
            site_ha,
            european_code,
            ST_AsGeoJSON(geom)::json AS geometry
        FROM {DESIGNATIONS_TABLE}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY site_ha DESC NULLS LAST
        LIMIT %s
    """
    try:
        conn = _connect()
    except Exception as exc:
        raise LayerUnavailable(f"NatureScot PostGIS unavailable: {exc}") from exc
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(sql, (west, south, east, north, west, south, east, north, cap))
            rows = cur.fetchall()
    except Exception as exc:
        raise LayerUnavailable(f"NatureScot designations query failed: {exc}") from exc
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
                    "site_key": row.get("site_key"),
                    "designation_type": row.get("designation_type"),
                    "pa_code": row.get("pa_code"),
                    "name": row.get("name"),
                    "status": row.get("status"),
                    "site_type": row.get("site_type"),
                    "site_ha": row.get("site_ha"),
                    "european_code": row.get("european_code"),
                    "layer": "naturescot_designations",
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
            "layer": "naturescot_designations",
            "count": len(features),
            "capped": len(features) >= cap,
            **meta,
        },
    }
