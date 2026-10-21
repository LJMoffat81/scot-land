import logging
import pandas as pd
from pathlib import Path

from georgist import db
from paths import PROCESSED_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Path to the free RoS CSV from data.gov.scot
# (https://data.gov.scot/dataset/house_prices___residential_properties_sales_and_price).
# In production, this would be the path to the downloaded dataset
ROS_DATA_PATH = PROCESSED_DIR / "ros_house_prices_zones.csv"  # DATA_DIR-aware

def ingest_ros_data():
    """
    LEGACY: targets `ros_sales_data`, which the new schema does not define.
    The surface pipeline reads the pinned RoS file via georgist/surface_harvester.py.

    Ingests free RoS residential property sales data into PostGIS.
    Expects a CSV with columns: zone_id, median_price, mean_price, sales_count
    """
    if not ROS_DATA_PATH.exists():
        logger.error(
            f"RoS data file not found at {ROS_DATA_PATH}. Please download the "
            "Small Area Statistics from data.gov.scot "
            "(https://data.gov.scot/dataset/house_prices___residential_properties_sales_and_price)."
        )
        return

    logger.info(f"Ingesting free RoS data from {ROS_DATA_PATH}...")

    try:
        df = pd.read_csv(ROS_DATA_PATH)

        conn = db.connect()  # env-configured; raises DatabaseUnavailable
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
                    int(row['sales_count']) if not pd.isna(row['sales_count']) else None  # suppressed is missing, not 0
                ))
        conn.commit()
        conn.close()
        logger.info("RoS data ingestion completed successfully.")
    except Exception as e:
        logger.error(f"Failed to ingest RoS data: {e}")

if __name__ == "__main__":
    ingest_ros_data()
