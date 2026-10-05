import logging
import psycopg2
from psycopg2 import extras
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# DB Configuration
DB_CONFIG = {
    "dbname": "scotland_wealth",
    "user": "wealth_user",
    "password": "wealth_password",
    "host": "localhost",
    "port": "5432"
}

class WealthAggregator:
    """
    Aggregates all forms of Georgist economic rent using PostGIS spatial queries.
    """

    def __init__(self, db_config: dict = DB_CONFIG):
        self.db_config = db_config

    def get_connection(self):
        return psycopg2.connect(**self.db_config)

    def get_total_wealth(self, zone_id: str, lat: float, lng: float) -> dict[str, Any]:
        """
        Sums the rents from Surface, Resource, and Eco layers using spatial SQL.
        """
        total_wealth = {
            "surface_rent": 0.0,
            "resource_rent": 0.0,
            "eco_rent": 0.0,
            "total_annual_rent": 0.0,
            "breakdown": {}
        }

        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                # 1. Surface Rent (Data Zone lookup)
                cur.execute(
                    "SELECT rent_per_ha FROM surface_wealth WHERE zone_id = %s",
                    (zone_id,)
                )
                row = cur.fetchone()
                if row:
                    total_wealth["surface_rent"] = float(row["rent_per_ha"] or 0)

                # 2. Resource Rent (Spatial Intersection)
                # ST_Intersects checks if the point is inside the resource polygon
                cur.execute("""
                    SELECT name, annual_rent_gbp
                    FROM resource_wealth
                    WHERE ST_Intersects(geom, ST_SetSRID(ST_Point(%s, %s), 4326))
                """, (lng, lat))
                res_rows = cur.fetchall()
                for row in res_rows:
                    rent = float(row["annual_rent_gbp"] or 0)
                    total_wealth["resource_rent"] += rent
                    total_wealth["breakdown"][row["name"]] = rent

                # 3. Eco Rent (Spatial Intersection)
                cur.execute("""
                    SELECT name, annual_rent_gbp
                    FROM eco_wealth
                    WHERE ST_Intersects(geom, ST_SetSRID(ST_Point(%s, %s), 4326))
                """, (lng, lat))
                eco_rows = cur.fetchall()
                for row in eco_rows:
                    rent = float(row["annual_rent_gbp"] or 0)
                    total_wealth["eco_rent"] += rent
                    total_wealth["breakdown"][row["name"]] = rent

            conn.close()
        except Exception as e:
            logger.error(f"Database error in aggregator: {e}")
            # Fallback to 0s on error to prevent API crash

        total_wealth["total_annual_rent"] = (
            total_wealth["surface_rent"] +
            total_wealth["resource_rent"] +
            total_wealth["eco_rent"]
        )

        return total_wealth

# Singleton instance
aggregator = WealthAggregator()
