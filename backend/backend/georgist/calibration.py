import logging
import psycopg2
from psycopg2 import extras
from pathlib import Path
import json
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# DB Configuration
DB_CONFIG = {
    "dbname": "scotland_wealth",
    "user": "wealth_user",
    "password": "wealth_password",
    "host": "localhost",
    "port": "5432"
}

class CalibrationEngine:
    """
    Calibrates the Georgist la-calc multipliers against actual market sales
    from Registers of Scotland (RoS).
    """

    def __init__(self, db_config: dict = DB_CONFIG):
        self.db_config = db_config

    def get_connection(self):
        return psycopg2.connect(**self.db_config)

    def calculate_error_margin(self, zone_id: str) -> Dict[str, Any]:
        """
        Compares la-calc predicted rent vs actual median sale price.
        """
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                # 1. Get la-calc estimated rent
                cur.execute(
                    "SELECT rent_per_ha FROM surface_wealth WHERE zone_id = %s",
                    (zone_id,)
                )
                prediction = cur.fetchone()
                if not prediction:
                    return {"error": "No prediction found for zone"}

                predicted_rent = float(prediction["rent_per_ha"] or 0)

                # 2. Get RoS Actual Median Sale Price for the same zone
                # Note: This assumes RoS data is also migrated to a 'sales_data' table
                cur.execute(
                    "SELECT median_price FROM ros_sales_data WHERE zone_id = %s",
                    (zone_id,)
                )
                actual = cur.fetchone()

                if not actual:
                    return {"status": "insufficient_data", "prediction": predicted_rent}

                actual_price = float(actual["median_price"] or 0)

                # In a real Georgist model, we convert Sale Price -> Land Rent
                # using a capitalization rate (e.g., 5% = 0.05)
                cap_rate = 0.05
                implied_rent = actual_price * cap_rate

                error = (implied_rent - predicted_rent) / implied_rent if implied_rent != 0 else 0

                return {
                    "zone_id": zone_id,
                    "predicted_rent": predicted_rent,
                    "implied_market_rent": implied_rent,
                    "error_margin": error,
                    "multiplier_suggestion": 1.0 + error
                }
        finally:
            conn.close()

    def apply_calibration(self, zone_id: str, multiplier: float):
        """
        Updates the la-calc rent for a zone based on calibration.
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE surface_wealth
                    SET rent_per_ha = rent_per_ha * %s
                    WHERE zone_id = %s
                """, (multiplier, zone_id))
            conn.commit()
        finally:
            conn.close()

# Singleton instance
calibration_engine = CalibrationEngine()
