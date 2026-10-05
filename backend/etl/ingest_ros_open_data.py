import logging
import pandas as pd
import psycopg2
from psycopg2 import extras
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DB Configuration
DB_CONFIG = {
    "dbname": "scotland_wealth",
    "user": "wealth_user",
    "password": "wealth_password",
    "host": "localhost",
    "port": "5432"
}

# Path to the free RoS CSV provided by statistics.gov.scot
# In production, this would be the path to the downloaded dataset
ROS_DATA_PATH = Path("data/processed/ros_house_prices_zones.csv")

def ingest_ros_data():
    """
    Ingests free RoS residential property sales data into PostGIS.
    Expects a CSV with columns: zone_id, median_price, mean_price, sales_count
    """
    if not ROS_DATA_PATH.exists():
        logger.error(f"RoS data file not found at {ROS_DATA_PATH}. Please download the Small Area Statistics from statistics.gov.scot.")
        return

    logger.info(f"Ingesting free RoS data from {ROS_DATA_PATH}...")

    try:
        df = pd.read_csv(ROS_DATA_PATH)

        conn = psycopg2.connect(**DB_CONFIG)
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
        logger.info("RoS data ingestion completed successfully.")
    except Exception as e:
        logger.error(f"Failed to ingest RoS data: {e}")

if __name__ == "__main__":
    ingest_ros_data()
