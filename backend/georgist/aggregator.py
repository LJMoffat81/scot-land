"""National Wealth aggregation via PostGIS spatial intersections.

Missing database or tables → DatabaseUnavailable (API maps to HTTP 503).
Never invent zeros or placeholder rents when the store is unavailable.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import psycopg2
from psycopg2 import extras

logger = logging.getLogger(__name__)


class DatabaseUnavailable(Exception):
    """Raised when wealth aggregation cannot reach PostGIS or required tables."""


def _db_config() -> dict[str, Any]:
    """Prefer DATABASE_URL; fall back to discrete env vars (no hard-coded passwords)."""
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


class WealthAggregator:
    """Aggregates Georgist economic rent using PostGIS spatial queries."""

    def __init__(self, db_config: dict[str, Any] | None = None):
        self.db_config = db_config if db_config is not None else _db_config()

    def get_connection(self):
        cfg = self.db_config
        if "dsn" in cfg:
            return psycopg2.connect(cfg["dsn"])
        return psycopg2.connect(**cfg)

    def get_total_wealth(self, zone_id: str, lat: float, lng: float) -> dict[str, Any]:
        """Sum surface, resource, and eco rents for a location.

        Raises DatabaseUnavailable when PostGIS cannot be queried — callers must
        surface that as HTTP 503 rather than inventing zero totals.
        """
        total_wealth: dict[str, Any] = {
            "surface_rent": 0.0,
            "resource_rent": 0.0,
            "eco_rent": 0.0,
            "total_annual_rent": 0.0,
            "breakdown": {},
        }

        try:
            conn = self.get_connection()
        except Exception as exc:
            logger.error("Database connection failed in aggregator: %s", exc)
            raise DatabaseUnavailable(str(exc)) from exc

        try:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT rent_per_ha FROM surface_wealth WHERE zone_id = %s",
                    (zone_id,),
                )
                row = cur.fetchone()
                if row:
                    total_wealth["surface_rent"] = float(row["rent_per_ha"] or 0)

                cur.execute(
                    """
                    SELECT name, annual_rent_gbp
                    FROM resource_wealth
                    WHERE ST_Intersects(geom, ST_SetSRID(ST_Point(%s, %s), 4326))
                    """,
                    (lng, lat),
                )
                for row in cur.fetchall():
                    rent = float(row["annual_rent_gbp"] or 0)
                    total_wealth["resource_rent"] += rent
                    total_wealth["breakdown"][row["name"]] = rent

                cur.execute(
                    """
                    SELECT name, annual_rent_gbp
                    FROM eco_wealth
                    WHERE ST_Intersects(geom, ST_SetSRID(ST_Point(%s, %s), 4326))
                    """,
                    (lng, lat),
                )
                for row in cur.fetchall():
                    rent = float(row["annual_rent_gbp"] or 0)
                    total_wealth["eco_rent"] += rent
                    total_wealth["breakdown"][row["name"]] = rent
        except DatabaseUnavailable:
            raise
        except Exception as exc:
            logger.error("Database error in aggregator: %s", exc)
            raise DatabaseUnavailable(str(exc)) from exc
        finally:
            conn.close()

        total_wealth["total_annual_rent"] = (
            total_wealth["surface_rent"]
            + total_wealth["resource_rent"]
            + total_wealth["eco_rent"]
        )
        return total_wealth


aggregator = WealthAggregator()
