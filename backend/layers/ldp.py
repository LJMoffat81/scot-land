"""Local Development Plan (LDP) allocations — PostGIS-backed open overlay.

National Spatial Hub pack is fragmented (per-authority ZIPs / portal links;
City of Edinburgh unavailable). Live map geometry is loaded into PostGIS from
OGL sources only (see ``data/config/sources.yaml`` → ``ldp_allocations`` and
``python -m etl.ingest_ldp_allocations``). Never invents missing authorities.
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
TABLE = "ldp_allocations"
MAX_FEATURES = 80

SPATIAL_HUB_URL = "https://data.spatialhub.scot/dataset/local_development_plans-is"
SPATIALDATA_METADATA_URL = (
    "https://spatialdata.gov.scot/geonetwork/srv/api/records/"
    "8e13ad58-41f2-4308-a3a8-5ffe8593e731"
)
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"

ATTRIBUTION = (
    "Local Development Plan allocations. Contains public sector information "
    "licensed under the Open Government Licence v3.0. Spatial Hub / Improvement "
    "Service amalgamated pack (fragmented per planning authority). Where authority "
    "portals publish OGL FeatureServers (e.g. Highland Council), those are ingested "
    "into PostGIS. Planning allocations, not a title sheet. Review with the adopted "
    "LDP and National Planning Framework 4."
)


class LayerUnavailable(Exception):
    """Raised when LDP allocations are not loaded or PostGIS is unreachable."""


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
    cfg = sources.get("ldp_allocations") or {}
    return {
        "source": cfg.get("name") or "Local Development Plan allocations (Scotland)",
        "licence": cfg.get("licence") or "OGL-3.0",
        "attribution": cfg.get("attribution") or ATTRIBUTION,
        "source_url": cfg.get("spatial_hub_url") or SPATIAL_HUB_URL,
        "spatial_hub_url": cfg.get("spatial_hub_url") or SPATIAL_HUB_URL,
        "metadata_url": cfg.get("spatialdata_metadata_url") or SPATIALDATA_METADATA_URL,
        "licence_url": cfg.get("licence_url") or OGL_URL,
        "vintage": cfg.get("vintage") or "Spatial Hub quarterly pack; PostGIS ingest stamp",
        "gaps": cfg.get("gaps")
        or [
            "City of Edinburgh LDP spatial data is unavailable in the Spatial Hub pack",
            "National coverage is fragmented — per-authority ZIPs or portal links, not one seamless layer",
            "Some authorities publish portal links only; those are not mirrored until an OGL download/FeatureServer is ingested",
            "Allocations are planning policy extents — not a title sheet or ownership layer",
        ],
    }


def is_loaded() -> bool:
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("LDP PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{TABLE}",))
            if not cur.fetchone()[0]:
                return False
            cur.execute(f"SELECT 1 FROM {TABLE} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("LDP load check failed: %s", exc)
        return False
    finally:
        conn.close()


def coverage_summary() -> dict[str, Any]:
    """Authorities present in PostGIS — honest national gap view."""
    meta = source_meta()
    if not is_loaded():
        return {
            "ok": False,
            "loaded": False,
            "authorities": [],
            "n_features": 0,
            "gaps": meta["gaps"],
            **{k: meta[k] for k in ("source", "licence", "source_url", "spatial_hub_url", "metadata_url")},
        }
    conn = None
    try:
        conn = _connect()
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT authority, COUNT(*)::int AS n
                FROM {TABLE}
                GROUP BY authority
                ORDER BY authority
                """
            )
            rows = cur.fetchall()
            cur.execute(f"SELECT COUNT(*)::int AS n FROM {TABLE}")
            total = int(cur.fetchone()["n"])
    except Exception as exc:
        return {"ok": False, "loaded": False, "error": str(exc), "authorities": [], "gaps": meta["gaps"]}
    finally:
        if conn is not None:
            conn.close()
    return {
        "ok": True,
        "loaded": True,
        "n_features": total,
        "authorities": [{"authority": r["authority"], "n": r["n"]} for r in rows],
        "gaps": meta["gaps"],
        "attribution": meta["attribution"],
        **{k: meta[k] for k in ("source", "licence", "source_url", "spatial_hub_url", "metadata_url", "licence_url", "vintage")},
    }


def catalog_layer() -> dict[str, Any]:
    meta = source_meta()
    return {
        "id": "ldp_allocations",
        "group": "spatial",
        "status": "live",
        "label": "LDP allocations",
        "description": (
            "Local Development Plan allocation polygons from OGL Spatial Hub / "
            "authority portals, loaded into PostGIS. National coverage is fragmented "
            "(Edinburgh missing; some authorities portal-only). Natural capital ledger "
            "row 1a (planning uplift, already included in surface) — not a "
            "LayersPanel toggle. Planning extents, not a title. No public AGR £."
        ),
        "endpoint": "/layers/open/ldp",
        "licence": meta["licence"],
        "minzoom": 8,
        "source_url": meta["source_url"],
        "spatial_hub_url": meta["spatial_hub_url"],
        "gaps": meta["gaps"],
        "ledger_role": "ledger-row",
        "ledger_row": "1a",
        "ui_surface": "ledger",
    }


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport LDP allocation polygons as GeoJSON (WGS84)."""
    meta = source_meta()
    if not is_loaded():
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": (
                    "ldp_allocations is missing or empty. Ingest OGL LDP allocation "
                    "GeoJSON (python -m etl.ingest_ldp_allocations) before publishing."
                ),
                "layer": "ldp_allocations",
                "gaps": meta["gaps"],
                **{k: meta[k] for k in ("source", "licence", "source_url", "spatial_hub_url")},
            },
        }

    cap = max(1, min(int(max_features), MAX_FEATURES))
    sql = f"""
        SELECT
            site_id,
            authority,
            allocation,
            code,
            plan_source,
            hectares,
            ST_AsGeoJSON(geom)::json AS geometry
        FROM {TABLE}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY hectares DESC NULLS LAST
        LIMIT %s
    """
    try:
        conn = _connect()
    except Exception as exc:
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": f"PostGIS unavailable: {exc}",
                "layer": "ldp_allocations",
                "gaps": meta["gaps"],
            },
        }
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(sql, (west, south, east, north, west, south, east, north, cap))
            rows = cur.fetchall()
    except Exception as exc:
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": f"LDP query failed: {exc}",
                "layer": "ldp_allocations",
                "gaps": meta["gaps"],
            },
        }
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
                    "authority": row.get("authority"),
                    "allocation": row.get("allocation"),
                    "code": row.get("code"),
                    "plan_source": row.get("plan_source"),
                    "hectares": float(row["hectares"]) if row.get("hectares") is not None else None,
                    "layer": "ldp_allocations",
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
            "layer": "ldp_allocations",
            "count": len(features),
            "capped": len(features) >= cap,
            "gaps": meta["gaps"],
            "attribution": meta["attribution"],
            **{k: meta[k] for k in ("source", "licence", "source_url", "spatial_hub_url", "metadata_url", "vintage")},
        },
    }
