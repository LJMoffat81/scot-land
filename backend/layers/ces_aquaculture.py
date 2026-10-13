"""Crown Estate Scotland aquaculture seabed leases (OGL Spatial Hub).

PostGIS ``ces_aquaculture_leases`` after ``python -m etl.ingest_ces_aquaculture``.
Natural-capital evidence only: ``value_tier`` market|proxy|shadow, no £ rent.
Overlay never adds value to Surface Rent or AGR.

Attribution (CES): Contains information from the Crown Estate Scotland
licensed under the Open Government Licence v3.0.
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
TABLE = "ces_aquaculture_leases"
LAYER_ID = "ces_aquaculture"
MAX_FEATURES = 80
OGL_V3_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)
CES_ATTRIBUTION = (
    "Contains information from the Crown Estate Scotland licensed under the "
    "Open Government Licence v3.0."
)
HUB_URL = "https://crown-estate-scotland-spatial-hub-coregis.hub.arcgis.com/"


class LayerUnavailable(Exception):
    """Raised when the PostGIS table is missing/empty or DB unreachable."""


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
    row = sources.get("ces_aquaculture") or {}
    return {
        "source": row.get("name") or "CES aquaculture seabed leases",
        "licence": row.get("licence") or "OGL-3.0",
        "licence_url": row.get("licence_url") or OGL_V3_URL,
        "attribution": row.get("attribution") or CES_ATTRIBUTION,
        "source_url": row.get("source_url") or HUB_URL,
        "publisher": row.get("publisher") or "Crown Estate Scotland",
        "value_tier": row.get("value_tier") or "market",
        "adds_to_surface_rent": False,
        "gaps": row.get("gaps")
        or [
            "Lease polygons as published by CES — not a Land Register title",
            "No £ rent on this layer — natural-capital evidence only",
            "Separate from offshore energy leases and context-tiles seabed proxy",
            "Full extract is not committed; load via ingest into PostGIS",
        ],
    }


def is_loaded() -> bool:
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("CES aquaculture PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{TABLE}",))
            if not cur.fetchone()[0]:
                return False
            cur.execute(
                f"""
                SELECT 1 FROM {TABLE}
                WHERE publication_status = 'ok'
                LIMIT 1
                """
            )
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("CES aquaculture load check failed: %s", exc)
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
    """CES aquaculture seabed lease polygons in the viewport (no rent £)."""
    meta = source_meta()
    tier_keys = (
        "source",
        "licence",
        "licence_url",
        "attribution",
        "source_url",
        "value_tier",
        "gaps",
    )
    if not is_loaded():
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": (
                    f"{TABLE} is missing or empty. Run "
                    "`python -m etl.ingest_ces_aquaculture` against the CES "
                    "Spatial Hub FeatureServer (OGL)."
                ),
                "loaded": False,
                "layer": LAYER_ID,
                "adds_to_surface_rent": False,
                **{k: meta[k] for k in tier_keys},
            },
        }

    cap = max(1, min(int(max_features), MAX_FEATURES))
    span = max(abs(north - south), abs(east - west))
    simplify = max(span / 400.0, 0.0002)
    sql = f"""
        SELECT id, site_id, lease_description, property_classification,
               value_tier, publication_status,
               ST_AsGeoJSON(
                 ST_SimplifyPreserveTopology(
                   ST_MakeValid(geom), %s
                 )
               )::json AS geometry
        FROM {TABLE}
        WHERE publication_status = 'ok'
          AND geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY property_classification NULLS LAST, site_id NULLS LAST
        LIMIT %s
    """
    conn = None
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
        logger.warning("CES aquaculture bbox query failed: %s", exc)
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": str(exc),
                "loaded": False,
                "layer": LAYER_ID,
                "adds_to_surface_rent": False,
                **{
                    k: meta[k]
                    for k in ("source", "licence", "licence_url", "source_url", "value_tier")
                },
            },
        }
    finally:
        if conn is not None:
            conn.close()

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
                    "site_id": row.get("site_id"),
                    "name": row.get("lease_description"),
                    "classification": row.get("property_classification"),
                    "value_tier": row.get("value_tier") or meta["value_tier"],
                    "publication_status": row.get("publication_status") or "ok",
                    "layer": LAYER_ID,
                    "adds_to_surface_rent": False,
                    "source": meta["attribution"],
                    "licence": meta["licence"],
                    "licence_url": meta["licence_url"],
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
            "capped": len(features) >= cap,
            "layer": LAYER_ID,
            "as_of": date.today().isoformat(),
            "adds_to_surface_rent": False,
            "note": (
                "CES aquaculture seabed lease polygons only — no £ rent; "
                "never added to Surface Rent or AGR; not a title."
            ),
            **{k: meta[k] for k in tier_keys},
        },
    }
