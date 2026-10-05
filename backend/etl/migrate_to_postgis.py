import json
import logging
import psycopg2
from psycopg2 import extras
from pathlib import Path
from typing import Any

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

PROCESSED_DIR = Path("scot-land/data/processed")

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def setup_database():
    """Initialize the PostGIS extension and create tables."""
    logger.info("Initializing PostGIS database schema...")
    conn = get_connection()
    with conn.cursor() as cur:
        # Enable PostGIS
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

        # 1. Surface Wealth Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS surface_wealth (
                zone_id TEXT PRIMARY KEY,
                pop_density FLOAT,
                simd_income_rank INT,
                simd_access_rank INT,
                rent_per_ha FLOAT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Resource Wealth Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS resource_wealth (
                id SERIAL PRIMARY KEY,
                resource_type TEXT,
                name TEXT,
                annual_rent_gbp FLOAT,
                rent_per_ha FLOAT,
                geom GEOMETRY(Polygon, 4326)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_res_geom ON resource_wealth USING GIST (geom);")

        # 3. Eco Wealth Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS eco_wealth (
                id SERIAL PRIMARY KEY,
                resource_type TEXT,
                name TEXT,
                annual_rent_gbp FLOAT,
                rent_per_ha FLOAT,
                geom GEOMETRY(Polygon, 4326)
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_eco_geom ON eco_wealth USING GIST (geom);")

    conn.commit()
    conn.close()
    logger.info("Database schema initialized successfully.")

def migrate_surface_data():
    """Migrate zone_wealth.json to PostGIS."""
    file_path = PROCESSED_DIR / "zone_wealth.json"
    if not file_path.exists():
        logger.warning("No surface data found to migrate.")
        return

    logger.info("Migrating surface wealth data...")
    with open(file_path, "r") as f:
        data = json.load(f)

    conn = get_connection()
    with conn.cursor() as cur:
        for zone_id, info in data.items():
            stats = info.get("stats", {})
            cur.execute("""
                INSERT INTO surface_wealth (zone_id, pop_density, simd_income_rank, simd_access_rank, rent_per_ha)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (zone_id) DO UPDATE SET
                    pop_density = EXCLUDED.pop_density,
                    simd_income_rank = EXCLUDED.simd_income_rank,
                    simd_access_rank = EXCLUDED.simd_access_rank,
                    rent_per_ha = EXCLUDED.rent_per_ha;
            """, (
                zone_id,
                stats.get("pop_density"),
                stats.get("simd_income_rank"),
                stats.get("simd_access_rank"),
                info.get("rent_per_ha")
            ))
    conn.commit()
    conn.close()
    logger.info(f"Migrated {len(data)} surface zones.")

def migrate_geojson_data(file_name: str, table_name: str):
    """Generic migrator for Resource and Eco GeoJSON files."""
    file_path = PROCESSED_DIR / file_name
    if not file_path.exists():
        logger.warning(f"No {file_name} found to migrate.")
        return

    logger.info(f"Migrating {file_name} to {table_name}...")
    with open(file_path, "r") as f:
        data = json.load(f)

    conn = get_connection()
    with conn.cursor() as cur:
        for feat in data.get("features", []):
            props = feat["properties"]
            # Convert GeoJSON geometry to WKT for PostGIS
            # For the MVP, we use ST_GeomFromGeoJSON
            geom_json = json.dumps(feat["geometry"])

            cur.execute(f"""
                INSERT INTO {table_name} (resource_type, name, annual_rent_gbp, rent_per_ha, geom)
                VALUES (%s, %s, %s, %s, ST_GeomFromGeoJSON(%s))
            """, (
                props.get("resource_type"),
                props.get("name"),
                props.get("annual_rent_gbp"),
                props.get("rent_per_ha"),
                geom_json
            ))
    conn.commit()
    conn.close()
    logger.info(f"Migrated {len(data.get('features', []))} features into {table_name}.")

if __name__ == "__main__":
    try:
        setup_database()
        migrate_surface_data()
        migrate_geojson_data("resource_wealth.geojson", "resource_wealth")
        migrate_geojson_data("eco_wealth.geojson", "eco_wealth")
        logger.info("Full migration completed successfully!")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
