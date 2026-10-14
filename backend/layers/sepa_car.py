"""SEPA CAR licences — PostGIS only (MapServer ingest, never client proxy).

Load with one command::

    python -m etl.ingest_sepa_car

That fetches Open/SEPA_Reference MapServer layers 194/195 into PostGIS.
This module never calls MapServer at request time. OGL-3.0. No £ rent.
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
TABLE = "sepa_car_licences"
MAX_FEATURES = 80
OGL_V3_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)
SEPA_ENV_DATA = "https://www.sepa.org.uk/environment/environmental-data/"
MAPSERVER = (
    "https://map.sepa.org.uk/server/rest/services/Open/SEPA_Reference/MapServer"
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
def source_meta() -> dict[str, Any]:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    row = sources.get("sepa_car") or {}
    return {
        "source": row.get("name") or "SEPA CAR licences",
        "licence": row.get("licence") or "OGL-3.0",
        "licence_url": row.get("licence_url") or OGL_V3_URL,
        "attribution": row.get("attribution")
        or (
            "Contains public sector information licensed under the Open "
            "Government Licence v3.0. © Scottish Environment Protection Agency. "
            "CAR Simple (194) and Registration (195) from SEPA_Reference "
            "MapServer — ingested to PostGIS; not proxied live. Not a title."
        ),
        "source_url": row.get("source_url") or SEPA_ENV_DATA,
        "mapserver_url": row.get("mapserver_url") or MAPSERVER,
        "publisher": row.get("publisher") or "SEPA",
        "commons_class": row.get("commons_class") or "extractive",
        "value_tier": row.get("value_tier") or "market",
        "publication_status": row.get("publication_status") or "ok",
        "adds_to_surface_rent": False,
        "gaps": row.get("gaps")
        or [
            "Served from PostGIS after ingest — MapServer is never proxied to clients",
            "Layers 194 (simple) and 195 (registration) only",
            "No money figures — licence inventory only",
            "Load with: python -m etl.ingest_sepa_car",
        ],
    }


def is_loaded() -> bool:
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("SEPA CAR PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{TABLE}",))
            if not cur.fetchone()[0]:
                return False
            cur.execute(
                f"""
                SELECT 1 FROM {TABLE}
                WHERE geom IS NOT NULL AND publication_status = 'ok'
                LIMIT 1
                """
            )
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("SEPA CAR load check failed: %s", exc)
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
    """CAR licence points from PostGIS only (never MapServer at request time)."""
    meta = source_meta()
    tier_keys = (
        "source",
        "licence",
        "licence_url",
        "attribution",
        "source_url",
        "mapserver_url",
        "commons_class",
        "value_tier",
        "publication_status",
        "adds_to_surface_rent",
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
                    "`python -m etl.ingest_sepa_car` to load MapServer "
                    "layers 194/195 into PostGIS (API never proxies MapServer)."
                ),
                "loaded": False,
                **{k: meta[k] for k in tier_keys},
            },
        }

    cap = max(1, min(int(max_features), MAX_FEATURES))
    sql = f"""
        SELECT authorisation_no, car_layer, authorisation_holder,
               authorisation_description, authorisation_level,
               authorisation_status, regulatory_area, authorisation_activity,
               category, ngr, commons_class, value_tier, publication_status,
               ST_AsGeoJSON(geom)::json AS geometry
        FROM {TABLE}
        WHERE geom IS NOT NULL
          AND publication_status = 'ok'
          AND geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY authorisation_no
        LIMIT %s
    """
    conn = None
    try:
        conn = _connect()
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (west, south, east, north, west, south, east, north, cap),
            )
            rows = cur.fetchall()
    except Exception as exc:
        logger.warning("SEPA CAR bbox query failed: %s", exc)
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": str(exc),
                "loaded": False,
                **{k: meta[k] for k in tier_keys if k != "gaps"},
            },
        }
    finally:
        if conn is not None:
            conn.close()

    features = []
    for row in rows:
        geom = row.pop("geometry")
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "authorisation_no": row.get("authorisation_no"),
                    "car_layer": row.get("car_layer"),
                    "holder": row.get("authorisation_holder"),
                    "description": row.get("authorisation_description"),
                    "level": row.get("authorisation_level"),
                    "status": row.get("authorisation_status"),
                    "regulatory_area": row.get("regulatory_area"),
                    "activity": row.get("authorisation_activity"),
                    "category": row.get("category"),
                    "ngr": row.get("ngr"),
                    "commons_class": row.get("commons_class") or meta["commons_class"],
                    "value_tier": row.get("value_tier") or meta["value_tier"],
                    "publication_status": row.get("publication_status")
                    or meta["publication_status"],
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
            "note": (
                "Natural-capital CAR inventory from PostGIS only — "
                "no MapServer proxy; no money figures; not surface rent"
            ),
            **{k: meta[k] for k in tier_keys},
        },
    }
