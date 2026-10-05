import logging
import httpx
import pandas as pd
import psycopg2
from psycopg2 import extras
from pathlib import Path
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# Configuration
DB_CONFIG = {
    "dbname": "scotland_wealth",
    "user": "wealth_user",
    "password": "wealth_password",
    "host": "localhost",
    "port": "5432"
}

# CKAN API Constants for Scottish Government Open Data
CKAN_API_URL = "https://opendata.scot/api/3/action/package_show"
# This ID corresponds to the "Residential Properties Sales and Price" dataset
ROS_RESOURCE_ID = "685c6a7b-e58d-4d6f-a3b1-7d8b2c9a1b2c" # Example ID - will be verified

class RosSyncService:
    """
    Automatically synchronizes the la-calc engine with the latest
    Registers of Scotland open data via the CKAN API.
    """

    def __init__(self, db_config: dict = DB_CONFIG):
        self.db_config = db_config

    def check_for_updates(self) -> bool:
        """
        Queries the CKAN API to see if the dataset has been updated
        since the last sync.
        """
        try:
            response = httpx.get(f"{CKAN_API_URL}?id=ros-house-prices")
            response.raise_for_status()
            data = response.json()

            # Find the specific resource for Data Zones
            resources = data.get("result", {}).get("resources", [])
            target_res = next((r for r in resources if "data-zones" in r.get("name", "").lower()), None)

            if not target_res:
                logger.error("Could not find the Data Zone resource in the dataset.")
                return False

            last_modified = target_res.get("last_modified")
            # In a real app, compare this with a 'last_sync' timestamp in the DB
            logger.info(f"Latest dataset modified on: {last_modified}")
            return True
        except Exception as e:
            logger.error(f"Update check failed: {e}")
            return False

    def sync_data(self):
        """
        Downloads the latest CSV from CKAN and updates PostGIS.
        """
        logger.info("Syncing RoS data from Open Data portal...")

        try:
            # 1. Get the download URL
            response = httpx.get(f"{CKAN_API_URL}?id=ros-house-prices")
            response.raise_for_status()
            data = response.json()
            resources = data.get("result", {}).get("resources", [])
            target_res = next((r for r in resources if "data-zones" in r.get("name", "").lower()), None)

            if not target_res:
                raise ValueError("Resource not found.")

            download_url = target_res.get("url")

            # 2. Download and Load into Pandas
            df = pd.read_csv(download_url)

            # 3. Push to PostGIS
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    cur.execute("""
                        INSERT INTO ros_sales_data (zone_id, median_price, mean_price, sales_count)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (zone_id) DO UPDATE SET
                            median_price = EXCLUDED.median_price,
                            mean_price = EXCLUDED.mean_price,
                            sales_count = EXCLUDED.sales_count,
                            updated_at = CURRENT_TIMESTAMP;
                    """, (
                        str(row['zone_id']),
                        float(row['median_price']) if not pd.isna(row['median_price']) else None,
                        float(row['mean_price']) if not pd.isna(row['mean_price']) else None,
                        int(row['sales_count']) if not pd.isna(row['sales_count']) else 0
                    ))
            conn.commit()
            conn.close()
            logger.info("Automatic RoS sync completed successfully.")
            return True
        except Exception as e:
            logger.error(f"Auto-sync failed: {e}")
            return False

# Singleton instance
ros_sync_service = RosSyncService()
