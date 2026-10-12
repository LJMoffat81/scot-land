"""Natural capital — DESNZ REPD onshore wind (Scotland).

PostGIS ``repd_onshore_wind`` after ``python -m etl.ingest_repd_onshore_wind``.
Publishes MW and development status only — **no £ rent figures**. Overlay never
adds to Surface Rent or AGR. Evidence tagged ``value_tier`` market|proxy|shadow;
``publication_status`` withholds thin rows.
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
TABLE = "repd_onshore_wind"
MAX_FEATURES = 80
LICENCE_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)


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
    row = sources.get("repd_onshore_wind") or {}
    return {
        "source": row.get("name")
        or "REPD onshore wind (natural capital)",
        "licence": row.get("licence") or "OGL-3.0",
        "licence_url": row.get("licence_url") or LICENCE_URL,
        "attribution": row.get("attribution")
        or (
            "Contains public sector information licensed under the Open "
            "Government Licence v3.0. Renewable Energy Planning Database "
            "© DESNZ / Crown copyright. Onshore wind planning-site points — "
            "not a lease, not a rent, not a title."
        ),
        "source_url": row.get("source_url")
        or (
            "https://www.gov.uk/government/publications/"
            "renewable-energy-planning-database-quarterly-extract"
        ),
        "publisher": row.get("publisher") or "DESNZ",
        "value_tier": row.get("value_tier") or "market",
        "adds_to_surface_rent": False,
        "gaps": row.get("gaps")
        or [
            "UK-wide register — map shows Scotland onshore wind only",
            "Coordinates are planning-site points, not lease polygons",
            "No £ rent on this layer — natural-capital evidence only",
            "Status and capacity change with each quarterly extract",
        ],
    }


def is_loaded() -> bool:
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("REPD onshore wind PostGIS unavailable: %s", exc)
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
                  AND publish_level IN ('public_site', 'public_zone')
                LIMIT 1
                """
            )
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("REPD onshore wind load check failed: %s", exc)
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
    """Scotland onshore-wind REPD points in the viewport as GeoJSON (no rent)."""
    meta = source_meta()
    if not is_loaded():
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": (
                    f"{TABLE} is missing or empty. Run "
                    "`python -m etl.ingest_repd_onshore_wind` against the OGL "
                    "quarterly CSV."
                ),
                "loaded": False,
                "layer": "repd_onshore_wind",
                "value_tier": meta["value_tier"],
                "adds_to_surface_rent": False,
                **{
                    k: meta[k]
                    for k in (
                        "source",
                        "licence",
                        "licence_url",
                        "attribution",
                        "source_url",
                        "gaps",
                    )
                },
            },
        }

    cap = max(1, min(int(max_features), MAX_FEATURES))
    sql = f"""
        SELECT ref_id, site_name, operator_name, technology_type,
               development_status, development_status_short,
               installed_capacity_mw, postcode, planning_authority,
               value_tier, publication_status, publish_level,
               ST_AsGeoJSON(geom)::json AS geometry
        FROM {TABLE}
        WHERE publication_status = 'ok'
          AND publish_level IN ('public_site', 'public_zone')
          AND geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY installed_capacity_mw DESC NULLS LAST
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
        logger.warning("REPD onshore wind bbox query failed: %s", exc)
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": str(exc),
                "loaded": False,
                "layer": "repd_onshore_wind",
                "adds_to_surface_rent": False,
                **{
                    k: meta[k]
                    for k in ("source", "licence", "licence_url", "source_url")
                },
            },
        }
    finally:
        if conn is not None:
            conn.close()

    features = []
    for row in rows:
        geom = row.pop("geometry")
        props = {
            "ref_id": row.get("ref_id"),
            "name": row.get("site_name"),
            "operator": row.get("operator_name"),
            "technology": row.get("technology_type"),
            "status": row.get("development_status_short")
            or row.get("development_status"),
            "capacity_mw": row.get("installed_capacity_mw"),
            "postcode": row.get("postcode"),
            "planning_authority": row.get("planning_authority"),
            "value_tier": row.get("value_tier"),
            "publication_status": row.get("publication_status"),
            "layer": "repd_onshore_wind",
            "adds_to_surface_rent": False,
            "source": meta["attribution"],
            "licence": meta["licence"],
            "licence_url": meta["licence_url"],
        }
        features.append(
            {"type": "Feature", "geometry": geom, "properties": props}
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "loaded": True,
            "layer": "repd_onshore_wind",
            "count": len(features),
            "max_features": cap,
            "as_of": date.today().isoformat(),
            "value_tier": meta["value_tier"],
            "adds_to_surface_rent": False,
            "note": (
                "Natural-capital evidence (MW + status). Not Surface Rent, "
                "not AGR, not a lease polygon, not a tax bill."
            ),
            **{
                k: meta[k]
                for k in (
                    "source",
                    "licence",
                    "licence_url",
                    "attribution",
                    "source_url",
                    "gaps",
                )
            },
        },
    }
