"""Housing Land Audit / Housing Land Supply overlay (OGL).

Authoritative open product: Spatial Hub *Housing Land Supply – Scotland*
(UK Open Government Licence v3.0) — local-authority Housing Land Audit sites
amalgamated by the Improvement Service.

Live anonymous Spatial Hub WFS returns 403 from this host. Operators may set
``SPATIALHUB_AUTHKEY`` (gitignored ``.env``, passed by ``docker-compose.home.yml``)
and run ``python -m etl.ingest_hla_sites --from-wfs``. The national SG ArcGIS
FeatureServer is PSGA/Digimap-restricted and is **not** used. This module
serves site polygons from PostGIS ``planning_sites`` (source='hla') after
ingest of a local OGL extract or authenticated WFS pull. When the table has
no HLA rows (or the authkey is missing for a WFS refresh), callers return
HTTP 503 with ``not loaded yet`` — never invent sites.
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

from spatial.geoserver_auth import is_configured as spatialhub_auth_configured
from spatial.geoserver_auth import not_loaded_message

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
TABLE = "planning_sites"
SOURCE = "hla"
MAX_FEATURES = 80

SPATIAL_HUB_URL = "https://data.spatialhub.scot/dataset/housing_land_supply-is"
METADATA_URL = (
    "https://spatialdata.gov.scot/geonetwork/srv/api/records/"
    "911d7102-d5bc-4de9-bbfd-6e0abd429d01"
)
LICENCE = "OGL-3.0"
ATTRIBUTION = (
    "Housing Land Supply – Scotland (Housing Land Audit amalgamation). "
    "Contains public sector information licensed under the Open Government "
    "Licence v3.0. Contains data from Improvement Service under OGL, supplied "
    "by Scotland's local planning authorities. © Improvement Service / "
    "Scottish Government. Audit site polygons, not a title."
)


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
def hla_source_meta() -> dict[str, Any]:
    """Licence / attribution / gaps from the committed source registry."""
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    hla = sources.get("hla") or {}
    return {
        "source": hla.get("name") or "Housing Land Supply / Housing Land Audit",
        "licence": hla.get("licence") or LICENCE,
        "attribution": hla.get("attribution") or ATTRIBUTION,
        "spatial_hub_url": hla.get("spatial_hub_url") or SPATIAL_HUB_URL,
        "metadata_url": hla.get("metadata_url") or METADATA_URL,
        "gaps": hla.get("gaps")
        or [
            "Spatial Hub anonymous WFS returns 403; set SPATIALHUB_AUTHKEY "
            "for --from-wfs, or load a local OGL extract",
            "Without SPATIALHUB_AUTHKEY the overlay stays not loaded yet",
            "National ArcGIS FeatureServer is PSGA/Digimap — not used here",
        ],
        "api_env": hla.get("api_env") or "SPATIALHUB_AUTHKEY",
        "authkey_configured": spatialhub_auth_configured(),
    }


def is_loaded() -> bool:
    """True when PostGIS has at least one public HLA planning_sites row."""
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("HLA PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (f"public.{TABLE}",),
            )
            exists = bool(cur.fetchone()[0])
            if not exists:
                return False
            cur.execute(
                f"""
                SELECT 1 FROM {TABLE}
                WHERE source = %s
                  AND publish_level IN ('public_site', 'public_zone')
                LIMIT 1
                """,
                (SOURCE,),
            )
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("HLA load check failed: %s", exc)
        return False
    finally:
        conn.close()


def _row_props(row: dict[str, Any]) -> dict[str, Any]:
    hectares = row.get("hectares")
    try:
        size_ha = float(hectares) if hectares is not None else None
    except (TypeError, ValueError):
        size_ha = None
    capacity = row.get("capacity_homes")
    try:
        capacity_homes = int(capacity) if capacity is not None else None
    except (TypeError, ValueError):
        capacity_homes = None
    return {
        "site_id": row.get("site_id"),
        "name": row.get("site_id"),
        "site_refer": row.get("site_id"),
        "local_authority": row.get("plan_authority"),
        "planning_status": row.get("planning_status"),
        "permitted_use": row.get("permitted_use") or "housing",
        "size_ha": size_ha,
        "capacity_homes": capacity_homes,
        "hla_year": row.get("source_vintage"),
        "geometry_source": row.get("geom_source"),
        "layer": "hla",
        "source": ATTRIBUTION,
        "licence": LICENCE,
    }


def _unloaded_error() -> str:
    """Honest note when PostGIS has no HLA rows (authkey missing or not ingested)."""
    base = not_loaded_message("Housing land audit overlay")
    if spatialhub_auth_configured():
        return (
            f"{base}. Run python -m etl.ingest_hla_sites --from-wfs "
            "(or load a local OGL extract)."
        )
    return (
        f"{base}. Set SPATIALHUB_AUTHKEY in .env for Spatial Hub WFS, "
        "or ingest a local OGL extract (python -m etl.ingest_hla_sites)."
    )


def query_point(lat: float, lng: float) -> dict[str, Any]:
    """Sites whose polygon contains the clicked point (WGS84 in, BNGrid store)."""
    meta = hla_source_meta()
    if not is_loaded():
        return {
            "ok": False,
            "error": _unloaded_error(),
            "intersects": False,
            "sites": [],
            "source": meta["attribution"],
            "spatial_hub_url": meta["spatial_hub_url"],
            "licence": meta["licence"],
        }
    sql = f"""
        SELECT
            site_id, plan_authority, planning_status, permitted_use,
            hectares, capacity_homes, source_vintage, geom_source
        FROM {TABLE}
        WHERE source = %s
          AND publish_level IN ('public_site', 'public_zone')
          AND ST_Intersects(
                geom,
                ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 27700)
          )
        ORDER BY hectares DESC NULLS LAST
        LIMIT 5
    """
    conn = None
    try:
        conn = _connect()
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(sql, (SOURCE, lng, lat))
            rows = cur.fetchall()
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "intersects": False,
            "sites": [],
            "source": meta["attribution"],
            "licence": meta["licence"],
        }
    finally:
        if conn is not None:
            conn.close()

    sites = []
    for row in rows:
        props = _row_props(dict(row))
        sites.append(
            {
                "site_id": props["site_id"],
                "local_authority": props["local_authority"],
                "planning_status": props["planning_status"],
                "size_ha": props["size_ha"],
                "capacity_homes": props["capacity_homes"],
                "hla_year": props["hla_year"],
                "geometry_source": props["geometry_source"],
            }
        )
    return {
        "ok": True,
        "intersects": bool(sites),
        "sites": sites,
        "source": meta["attribution"],
        "spatial_hub_url": meta["spatial_hub_url"],
        "metadata_url": meta["metadata_url"],
        "licence": meta["licence"],
        "note": (
            "Housing Land Audit / Housing Land Supply sites. Audit polygons, "
            "not a legal title. Confirm ownership on ScotLIS."
        ),
    }


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport HLA polygons as GeoJSON (WGS84) from PostGIS planning_sites."""
    meta = hla_source_meta()
    if not is_loaded():
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": _unloaded_error(),
                "layer": "hla",
                "spatial_hub_url": meta["spatial_hub_url"],
                "licence": meta["licence"],
                "authkey_configured": meta["authkey_configured"],
            },
        }

    cap = max(1, min(int(max_features), MAX_FEATURES))
    sql = f"""
        SELECT
            site_id, plan_authority, planning_status, permitted_use,
            hectares, capacity_homes, source_vintage, geom_source,
            ST_AsGeoJSON(ST_Transform(geom, 4326))::json AS geometry
        FROM {TABLE}
        WHERE source = %s
          AND publish_level IN ('public_site', 'public_zone')
          AND geom && ST_Transform(
                ST_MakeEnvelope(%s, %s, %s, %s, 4326), 27700
              )
          AND ST_Intersects(
                geom,
                ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), 27700)
              )
        ORDER BY hectares DESC NULLS LAST
        LIMIT %s
    """
    conn = None
    try:
        conn = _connect()
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (SOURCE, west, south, east, north, west, south, east, north, cap),
            )
            rows = cur.fetchall()
    except Exception as exc:
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": str(exc),
                "layer": "hla",
                "licence": meta["licence"],
            },
        }
    finally:
        if conn is not None:
            conn.close()

    features = []
    for row in rows[:cap]:
        row_dict = dict(row)
        geometry = row_dict.pop("geometry", None)
        if not geometry:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": _row_props(row_dict),
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "layer": "hla",
            "count": len(features),
            "capped": len(rows) >= cap,
            "source": meta["attribution"],
            "spatial_hub_url": meta["spatial_hub_url"],
            "metadata_url": meta["metadata_url"],
            "licence": meta["licence"],
            "gaps": list(meta["gaps"]),
        },
    }
