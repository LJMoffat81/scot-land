"""Crown Estate Scotland offshore lease polygons (OGL Spatial Hub).

Served from local PostGIS `crown_estate_leases` after
`python -m etl.ingest_crown_estate_leases`. Themes: offshore wind, wave,
tidal, CCS (lease agreements). Offshore only — aquaculture/onshore omitted.
No modelled rent.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import psycopg2
import yaml
from psycopg2 import extras

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
TABLE = "crown_estate_leases"
MAX_FEATURES = 80


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
    row = sources.get("crown_estate_leases") or {}
    return {
        "source": row.get("name")
        or "Crown Estate Scotland leases (Spatial Hub)",
        "licence": row.get("licence") or "OGL-3.0",
        "licence_url": row.get("licence_url")
        or (
            "https://www.nationalarchives.gov.uk/doc/"
            "open-government-licence/version/3/"
        ),
        "attribution": row.get("attribution")
        or (
            "Contains public sector information, licensed under the Open "
            "Government Licence v3.0, from Crown Estate Scotland."
        ),
        "source_url": row.get("source_url")
        or "https://crown-estate-scotland-spatial-hub-coregis.hub.arcgis.com/",
        "hub_url": row.get("hub_url")
        or "https://crown-estate-scotland-spatial-hub-coregis.hub.arcgis.com/",
        "gaps": row.get("gaps")
        or [
            "Lease polygons as published by CES — not a title sheet",
            "Themes ingested: offshore wind, wave, tidal, CCS (offshore only)",
            "Aquaculture and onshore estate are not mirrored here",
            "Cables/pipelines and non-lease recreational layers are not mirrored here",
        ],
    }


def is_loaded() -> bool:
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("Crown Estate leases PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{TABLE}",))
            if not cur.fetchone()[0]:
                return False
            cur.execute(f"SELECT 1 FROM {TABLE} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("Crown Estate leases load check failed: %s", exc)
        return False
    finally:
        conn.close()


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """CES lease polygons in the viewport as GeoJSON (WGS84)."""
    meta = source_meta()
    if not is_loaded():
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": (
                    f"{TABLE} is missing or empty. Run "
                    "`python -m etl.ingest_crown_estate_leases` from the OGL Spatial Hub."
                ),
                "loaded": False,
                **{
                    k: meta[k]
                    for k in ("source", "licence", "attribution", "source_url", "gaps")
                },
            },
        }

    cap = max(1, min(int(max_features), MAX_FEATURES))
    # Simplify for map speed; keep topology soft.
    span = max(abs(north - south), abs(east - west))
    simplify = max(span / 400.0, 0.0002)
    sql = f"""
        SELECT id, lease_theme, description, tenant_name, agreement_type,
               property_classification, project_phase, capacity_mw,
               ST_AsGeoJSON(
                 ST_SimplifyPreserveTopology(
                   ST_MakeValid(geom), %s
                 )
               )::json AS geometry
        FROM {TABLE}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY capacity_mw DESC NULLS LAST, lease_theme
        LIMIT %s
    """
    try:
        conn = _connect()
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (
                    simplify,
                    west,
                    south,
                    east,
                    north,
                    west,
                    south,
                    east,
                    north,
                    cap,
                ),
            )
            rows = cur.fetchall()
    except Exception as exc:
        logger.warning("Crown Estate leases bbox query failed: %s", exc)
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": str(exc),
                "loaded": False,
                **{k: meta[k] for k in ("source", "licence", "attribution", "source_url")},
            },
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass

    features = []
    for row in rows:
        geom = row.pop("geometry")
        if geom is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "id": row.get("id"),
                    "lease_theme": row.get("lease_theme"),
                    "name": row.get("description"),
                    "tenant": row.get("tenant_name"),
                    "agreement_type": row.get("agreement_type"),
                    "classification": row.get("property_classification"),
                    "phase": row.get("project_phase"),
                    "capacity_mw": row.get("capacity_mw"),
                    "source": meta["attribution"],
                    "licence": meta["licence"],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "loaded": True,
            "count": len(features),
            "max_features": cap,
            "as_of": date.today().isoformat(),
            **{
                k: meta[k]
                for k in ("source", "licence", "attribution", "source_url", "gaps")
            },
        },
    }
