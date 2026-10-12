"""SEPA Hydropower Sites — CAR-licensed water abstractions for hydropower.

OGL ATOM shapefile → PostGIS `hydro_sites` after `python -m etl.ingest_hydro_sites`.
Natural-capital evidence only: value_tier=proxy, commons_class=extractive.
No £ rent figures. Overlay never adds value to surface rent.
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
TABLE = "hydro_sites"
MAX_FEATURES = 80
OGL_V3_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)


class LayerUnavailable(Exception):
    """Raised when hydro PostGIS table is missing/empty or DB unreachable."""


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
    row = sources.get("hydro_sites") or {}
    return {
        "source": row.get("name") or "SEPA Hydropower Sites",
        "licence": row.get("licence") or "OGL-3.0",
        "licence_url": row.get("licence_url") or OGL_V3_URL,
        "attribution": row.get("attribution")
        or (
            "Contains public sector information licensed under the Open "
            "Government Licence v3.0. © SEPA. Hydropower CAR sites — not a title."
        ),
        "source_url": row.get("source_url")
        or "https://www.data.gov.uk/dataset/5750f8e5-d51b-4e75-a8d6-403a0d1ded81/hydropower_sites",
        "atom_url": row.get("atom_url")
        or "https://map.sepa.org.uk/atom/SEPA_Hydropower_Sites.atom",
        "publisher": row.get("publisher") or "SEPA",
        "commons_class": row.get("commons_class") or "extractive",
        "value_tier": row.get("value_tier") or "proxy",
        "publication_status": row.get("publication_status") or "ok",
        "gaps": row.get("gaps")
        or [
            "CAR hydropower abstractions only — not the full CAR register",
            "Points are licensed sites, not lease polygons or titles",
            "Vintage follows the SEPA ATOM package (last feed update 2018)",
            "Full extract is not committed; load via ingest into PostGIS",
        ],
    }


def is_loaded() -> bool:
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("Hydro PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{TABLE}",))
            if not cur.fetchone()[0]:
                return False
            cur.execute(f"SELECT 1 FROM {TABLE} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("Hydro load check failed: %s", exc)
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
    """Hydropower CAR site points in the viewport as GeoJSON (no rent)."""
    meta = source_meta()
    tier_keys = (
        "source",
        "licence",
        "licence_url",
        "attribution",
        "source_url",
        "commons_class",
        "value_tier",
        "publication_status",
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
                    "`python -m etl.ingest_hydro_sites` against the OGL ATOM shapefile."
                ),
                "loaded": False,
                **{k: meta[k] for k in tier_keys},
            },
        }

    cap = max(1, min(int(max_features), MAX_FEATURES))
    sql = f"""
        SELECT lic_no, auth_id, site_name, licence_start_date,
               commons_class, value_tier, publication_status,
               ST_AsGeoJSON(geom)::json AS geometry
        FROM {TABLE}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY site_name NULLS LAST
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
        logger.warning("Hydro bbox query failed: %s", exc)
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
                    "lic_no": row.get("lic_no"),
                    "auth_id": row.get("auth_id"),
                    "name": row.get("site_name"),
                    "licence_start_date": (
                        row["licence_start_date"].isoformat()
                        if row.get("licence_start_date")
                        else None
                    ),
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
            "note": "Natural-capital site inventory only — no £ rent; not surface rent",
            **{k: meta[k] for k in tier_keys},
        },
    }
