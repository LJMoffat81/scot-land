"""Common Good polygons from local PostGIS (OGL council open layers).

Ingest via ``python -m etl.ingest_common_good``. When the table is missing or
empty, callers must return HTTP 503 — never invent extents. Fife OS INSPIRE
EUL titles are **not** loaded here (linked only in ``common_good.yaml``).
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
CONFIG_PATH = REPO_ROOT / "data" / "config" / "common_good.yaml"
TABLE = "common_good_sites"
MAX_FEATURES = 80


class LayerUnavailable(Exception):
    """Raised when Common Good PostGIS data is not loaded or unreachable."""


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
def source_meta() -> dict[str, Any]:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    cg = sources.get("common_good") or {}
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    ogl = [
        s
        for s in (cfg.get("spatial_sources") or [])
        if isinstance(s, dict) and str(s.get("licence") or "").upper().startswith("OGL")
    ]
    catalog_url = None
    if ogl:
        catalog_url = ogl[0].get("catalog_url") or ogl[0].get("metadata_url")
    return {
        "source": cg.get("name") or "Common Good land (OGL council open layers)",
        "licence": cg.get("licence") or "OGL-3.0 (council open map data; partial coverage)",
        "attribution": cg.get("attribution")
        or (
            "Common Good sites from council open layers under the Open Government "
            "Licence v3.0. Indicative — not a title plan. Coverage is partial."
        ),
        "source_url": catalog_url
        or cg.get("guidance_url")
        or "https://www.gov.scot/publications/community-empowerment-common-good-property-guidance-local-authorities/",
        "gaps": cg.get("gaps")
        or [
            "No national open Common Good polygon layer",
            "Only OGL council open layers are ingested into PostGIS",
            "Fife OS INSPIRE EUL titles are linked, not loaded",
        ],
    }


def is_loaded() -> bool:
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("Common Good PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (f"public.{TABLE}",),
            )
            if not bool(cur.fetchone()[0]):
                return False
            cur.execute(f"SELECT 1 FROM {TABLE} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("Common Good load check failed: %s", exc)
        return False
    finally:
        conn.close()


def require_loaded() -> None:
    if not is_loaded():
        raise LayerUnavailable(
            "Common Good overlay is not available: common_good_sites is missing "
            "or empty. Ingest OGL council layers "
            "(python -m etl.ingest_common_good) before publishing this layer."
        )


def row_count() -> int:
    if not is_loaded():
        return 0
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def query_point(lat: float, lng: float) -> dict[str, Any]:
    """Sites whose polygon contains the clicked point (PostGIS)."""
    meta = source_meta()
    if not is_loaded():
        return {
            "ok": False,
            "intersects": False,
            "sites": [],
            "source": meta["attribution"],
            "note": "PostGIS Common Good table not loaded.",
        }
    sql = f"""
        SELECT site_id, council_code, council_name, name, site_kind,
               account, description, area_ha, source_id, licence, source_url
        FROM {TABLE}
        WHERE ST_Intersects(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        ORDER BY area_ha DESC NULLS LAST
        LIMIT 5
    """
    try:
        conn = _connect()
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(sql, (lng, lat))
            rows = cur.fetchall()
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "intersects": False,
            "sites": [],
            "source": meta["attribution"],
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass

    sites = [
        {
            "site_id": row.get("site_id"),
            "name": row.get("name"),
            "site_kind": row.get("site_kind"),
            "council_code": row.get("council_code"),
            "council_name": row.get("council_name"),
            "area_ha": row.get("area_ha"),
            "account": row.get("account"),
            "description": row.get("description"),
            "source_id": row.get("source_id"),
            "licence": row.get("licence"),
        }
        for row in rows
    ]
    return {
        "ok": True,
        "intersects": bool(sites),
        "sites": sites,
        "source": meta["attribution"],
        "licence": meta["licence"],
        "note": (
            "OGL council open layer — indicative Common Good holding, not a title. "
            "Confirm on ScotLIS / the council register."
        ),
    }


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport Common Good polygons as GeoJSON (WGS84)."""
    require_loaded()
    cap = max(1, min(int(max_features), MAX_FEATURES))
    meta = source_meta()
    sql = f"""
        SELECT
            site_id, council_code, council_name, name, site_kind,
            account, description, area_ha, source_id, licence, source_url,
            ST_AsGeoJSON(geom)::json AS geometry
        FROM {TABLE}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY area_ha DESC NULLS LAST
        LIMIT %s
    """
    try:
        conn = _connect()
    except Exception as exc:
        raise LayerUnavailable(f"Common Good PostGIS unavailable: {exc}") from exc
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(sql, (west, south, east, north, west, south, east, north, cap))
            rows = cur.fetchall()
    except Exception as exc:
        raise LayerUnavailable(f"Common Good query failed: {exc}") from exc
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
                    "site_id": row.get("site_id"),
                    "name": row.get("name"),
                    "site_kind": row.get("site_kind"),
                    "council_code": row.get("council_code"),
                    "council_name": row.get("council_name"),
                    "area_ha": row.get("area_ha"),
                    "account": row.get("account"),
                    "layer": "common_good",
                    "source_id": row.get("source_id"),
                    "licence": row.get("licence") or meta["licence"],
                    "source_url": row.get("source_url") or meta["source_url"],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "layer": "common_good",
            "count": len(features),
            "capped": len(features) >= cap,
            **meta,
        },
    }
