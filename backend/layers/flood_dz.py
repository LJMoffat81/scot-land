"""Data Zone choropleth of SEPA Flood Maps v3.0 medium present-day extents.

Returns 2022 Data Zone outlines only. Properties are the share whitelist.
No flood polygons and nothing finer than a Data Zone. 503 when the table
is empty — never invents shares.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import psycopg2
from psycopg2 import extras

logger = logging.getLogger(__name__)

TABLE = "sepa_flood_dz"
PROPERTY_KEYS = (
    "data_zone",
    "pct_area_river",
    "pct_area_coastal",
    "pct_area_surface",
    "source_version",
)
KINDS = frozenset({"river", "coastal", "surface"})
LICENCE = "OGL-3.0"
LICENCE_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)
ATTRIBUTION = "© SEPA 2025. Licensed under the Open Government Licence 3.0."
BBOX_ENDPOINT = "/layers/open/flood-dz"
NOT_LOADED = "SEPA flood Data Zone table is not loaded yet."


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
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("SEPA flood Data Zone PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{TABLE}",))
            if not cur.fetchone()[0]:
                return False
            cur.execute(f"SELECT 1 FROM {TABLE} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("SEPA flood Data Zone load check failed: %s", exc)
        return False
    finally:
        conn.close()


def clamp_pct(value: Any) -> int:
    number = int(value)
    if number < 0 or number > 100:
        raise ValueError(f"share {number} is outside 0 to 100")
    return number


def public_properties(row: dict[str, Any]) -> dict[str, Any]:
    """Exact key whitelist. Extra keys, including any other geometry, are dropped."""
    return {
        "data_zone": str(row["data_zone"]),
        "pct_area_river": clamp_pct(row["pct_area_river"]),
        "pct_area_coastal": clamp_pct(row["pct_area_coastal"]),
        "pct_area_surface": clamp_pct(row["pct_area_surface"]),
        "source_version": str(row["source_version"]),
    }


def feature_collection(rows: list[dict[str, Any]], *, kind: str) -> dict[str, Any]:
    features = []
    for row in rows:
        geometry = row.get("geometry")
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": public_properties(row),
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "loaded": True,
            "kind": kind,
            "count": len(features),
            "licence": LICENCE,
            "licence_url": LICENCE_URL,
            "attribution": ATTRIBUTION,
        },
    }


def unloaded_payload() -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [],
        "meta": {
            "ok": False,
            "loaded": False,
            "error": NOT_LOADED,
            "licence": LICENCE,
            "licence_url": LICENCE_URL,
            "attribution": ATTRIBUTION,
        },
    }


def fetch_rows(
    west: float,
    south: float,
    east: float,
    north: float,
) -> list[dict[str, Any]]:
    """Data Zone outlines in the bbox. Geometry is the zone, never a flood polygon."""
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT
                    z.data_zone,
                    z.pct_area_river,
                    z.pct_area_coastal,
                    z.pct_area_surface,
                    z.source_version,
                    ST_AsGeoJSON(
                        ST_Transform(
                            ST_SimplifyPreserveTopology(b.geom, 25),
                            4326
                        )
                    ) AS geometry
                FROM {TABLE} z
                JOIN dz_boundaries b
                  ON b.code = z.data_zone AND b.vintage = 2022
                WHERE ST_Intersects(
                    b.geom,
                    ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), 27700)
                )
                ORDER BY z.data_zone
                """,
                (west, south, east, north),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def query_bbox(
    west: float,
    south: float,
    east: float,
    north: float,
    *,
    kind: str,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(kind)
    if not is_loaded():
        return unloaded_payload()
    try:
        rows = fetch_rows(west, south, east, north)
    except Exception as exc:
        logger.info("SEPA flood Data Zone query failed: %s", exc)
        return unloaded_payload()
    return feature_collection(rows, kind=kind)
