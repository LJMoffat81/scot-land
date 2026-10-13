"""SEPA Flood Maps overlay (OGL-3.0).

Present-day medium-likelihood river and coastal flood extents (200-year).
Geometry comes only from the OGL download at www2.sepa.org.uk/flooddata,
ingested into PostGIS. Never queries SEPA MapServer, viewer, or other web
services. Returns an honest unloaded payload (API → 503) when the table is
empty. Never invents extents.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import psycopg2
from psycopg2 import extras

logger = logging.getLogger(__name__)

TABLE = "sepa_flood"
MAX_FEATURES = 80

DOWNLOAD_URL = "https://www2.sepa.org.uk/flooddata/"
ATTRIBUTION_PDF = (
    "https://www.sepa.org.uk/media/5zidnja5/sepa_flood_maps_data_attribution_statements.pdf"
)
LICENCE = "OGL-3.0"
LICENCE_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)
ATTRIBUTION = (
    "© SEPA 2025; this SEPA product is licensed under the Open Government Licence v3.0. "
    "Flood Maps v3.0 — medium-likelihood river and coastal extents (present day). "
    "Indicative hazard extents, not a flood insurance quote or title."
)
BBOX_ENDPOINT = "/layers/open/flood"
MINZOOM = 8


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


def is_loaded() -> bool:
    """True when PostGIS has at least one SEPA flood row."""
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("SEPA flood PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (f"public.{TABLE}",),
            )
            if not cur.fetchone()[0]:
                return False
            cur.execute(f"SELECT 1 FROM {TABLE} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("SEPA flood load check failed: %s", exc)
        return False
    finally:
        conn.close()


def catalog_layer() -> dict[str, Any]:
    return {
        "id": "flood",
        "group": "spatial",
        "status": "live",
        "label": "SEPA flood extent",
        "description": (
            "Medium-likelihood (200-year) river and coastal flood extents, "
            "SEPA Flood Maps v3.0 present-day. OGL download from "
            "www2.sepa.org.uk/flooddata only — ingested to PostGIS "
            "(503 when unloaded). Natural capital Constraint (no ledger rent row, "
            "£0) — changes best permitted use only. No LayersPanel toggle; "
            "no MapServer, viewer, or live web services."
        ),
        "endpoint": BBOX_ENDPOINT,
        "licence": LICENCE,
        "licence_url": LICENCE_URL,
        "minzoom": MINZOOM,
        "source_url": DOWNLOAD_URL,
        "attribution_url": ATTRIBUTION_PDF,
        "ledger_role": "constraint",
        "ledger_row": None,
        "ui_surface": "ledger",
        "gaps": [
            "Surface-water and climate-change scenarios are in the OGL product "
            "but not in the default public constraint paint (medium river + coastal only).",
            "Extents are indicative hazard maps — not a property-level flood quote.",
            "Must ingest the OGL download into PostGIS; live SEPA services are not used.",
            "Constraint overlays are £0 and never a rent row (C-overlay).",
        ],
    }


def _query_postgis(
    south: float,
    west: float,
    north: float,
    east: float,
    *,
    max_features: int,
) -> dict[str, Any] | None:
    if not is_loaded():
        return None
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("SEPA flood PostGIS connect failed: %s", exc)
        return None
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT object_id, layer_id, source, probability, scenario,
                       map_type, reference, version,
                       ST_AsGeoJSON(geom)::json AS geometry
                FROM {TABLE}
                WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                  AND ST_Intersects(
                        geom,
                        ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                  )
                ORDER BY ST_Area(geom) DESC
                LIMIT %s
                """,
                (west, south, east, north, west, south, east, north, max_features),
            )
            rows = cur.fetchall()
    except Exception as exc:
        logger.info("SEPA flood PostGIS query failed: %s", exc)
        return None
    finally:
        conn.close()

    features = []
    for row in rows:
        props = {
            "object_id": row["object_id"],
            "layer_id": row["layer_id"],
            "source": row["source"],
            "probability": row["probability"],
            "scenario": row["scenario"],
            "map_type": row["map_type"],
            "reference": row["reference"],
            "version": row["version"],
            "layer": "flood",
            "source_label": ATTRIBUTION,
            "licence": LICENCE,
            "licence_url": LICENCE_URL,
            "geometry_source": "postgis",
        }
        features.append(
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": props,
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "backend": "postgis",
            "count": len(features),
            "max_features": max_features,
            "licence": LICENCE,
            "licence_url": LICENCE_URL,
            "source": ATTRIBUTION,
            "source_url": DOWNLOAD_URL,
            "note": (
                "PostGIS ingest of SEPA Flood Maps v3.0 OGL download "
                "(medium river + coastal). Source: www2.sepa.org.uk/flooddata."
            ),
        },
    }


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    *,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Flood polygons in the viewport from PostGIS only (OGL download ingest)."""
    limit = max(1, min(int(max_features), MAX_FEATURES))
    if south >= north or west >= east:
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": "invalid bbox",
                "licence": LICENCE,
                "licence_url": LICENCE_URL,
                "source": ATTRIBUTION,
            },
        }

    postgis = _query_postgis(south, west, north, east, max_features=limit)
    if postgis is not None:
        return postgis

    return {
        "type": "FeatureCollection",
        "features": [],
        "meta": {
            "ok": False,
            "error": (
                f"{TABLE} is missing or empty. Download SEPA Flood Maps (OGL) "
                f"from {DOWNLOAD_URL} and run `python -m etl.ingest_sepa_flood`. "
                "MapServer / viewer / live web services are not used."
            ),
            "backend": "postgis",
            "loaded": False,
            "licence": LICENCE,
            "licence_url": LICENCE_URL,
            "source": ATTRIBUTION,
            "source_url": DOWNLOAD_URL,
        },
    }
