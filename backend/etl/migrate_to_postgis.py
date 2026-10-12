"""Apply the Wealth schema (via Alembic) and load processed outputs into PostGIS.

Connection comes only from the environment (DATABASE_URL or PG*), via
georgist.db. Files come from DATA_DIR/processed (paths.py).

    cd backend
    alembic upgrade head                     # preferred schema path
    python -m etl.migrate_to_postgis --schema-only
    python -m etl.migrate_to_postgis              # schema + placeholder resource/eco

Schema DDL lives in `db/schema/*.sql` and is applied by the Alembic baseline
migration (`alembic/versions/20261012_0001_*.py`). Prefer `alembic upgrade head`
for new databases. Existing DBs already created by the old CREATE IF NOT EXISTS
path should run `alembic stamp head` once (see docs/DB_MIGRATIONS.md).

The pre-spec `surface_wealth` table (rent_per_ha, SIMD ranks) is no longer
created or loaded: surface rent now goes to `surface_rent_dz` via
`upsert_surface_rent`, from Valuation's surface pipeline rows.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Iterable, Mapping

from alembic import command
from alembic.config import Config

from georgist import db
from georgist.wealth_schema import SURFACE_DB_COLUMNS
from paths import PROCESSED_DIR

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = BACKEND_ROOT / "db" / "schema"
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def apply_schema(conn=None) -> list[str]:
    """Run `alembic upgrade head` (ignores conn; Alembic opens its own connection)."""
    del conn  # kept for call-site compatibility with older tests
    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")
    applied = [p.name for p in sorted(SCHEMA_DIR.glob("*.sql"))]
    logger.info("Alembic upgrade head (schema files: %s)", ", ".join(applied))
    return applied


def migrate_geojson_data(conn, file_name: str, table_name: str) -> int:
    """Load a resource/eco GeoJSON (EPSG:4326) into a 27700 MultiPolygon table.

    Rows keep the file's quality tag; anything untagged is loaded as
    'placeholder' so it can never reach totals by accident.
    """
    if table_name not in ("resource_wealth", "eco_wealth"):
        raise ValueError(table_name)
    file_path = PROCESSED_DIR / file_name
    if not file_path.exists():
        logger.warning("No %s found in %s; skipping.", file_name, PROCESSED_DIR)
        return 0
    data = json.loads(file_path.read_text(encoding="utf-8"))
    features = data.get("features", [])
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table_name} WHERE quality = 'placeholder'")
        for feat in features:
            props = feat["properties"]
            cur.execute(
                f"""
                INSERT INTO {table_name} (resource_type, name, annual_rent_gbp, price_year,
                    commons_class, value_tier, quality, crosswalk_method, source_id,
                    licence, publish_level, geom)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 27700)))
                """,
                (
                    props.get("resource_type"),
                    props.get("name"),
                    props.get("annual_rent_gbp"),
                    props.get("price_year"),
                    props.get("commons_class") or ("extractive" if table_name == "resource_wealth" else "eco"),
                    props.get("value_tier") or "proxy",
                    props.get("quality") or "placeholder",
                    props.get("crosswalk_method") or "footprint_area",
                    props.get("source_id") or file_name,
                    props.get("licence"),
                    props.get("publish_level") or "internal",
                    json.dumps(feat["geometry"]),
                ),
            )
    conn.commit()
    logger.info("Loaded %d features into %s.", len(features), table_name)
    return len(features)


def upsert_surface_rent(conn, rows: Iterable[Mapping]) -> int:
    """Upsert `surface_rent_dz` rows produced by georgist.wealth_schema.to_db_row."""
    cols = SURFACE_DB_COLUMNS
    pk = ("code", "vintage", "valuation_date")
    sql = (
        f"INSERT INTO surface_rent_dz ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
        f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET "
        + ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in pk)
        + ", updated_at = now()"
    )
    n = 0
    with conn.cursor() as cur:
        for row in rows:
            if tuple(row) != cols:
                raise ValueError("row does not match SURFACE_DB_COLUMNS; build it with to_db_row")
            values = [
                json.dumps(v) if c in ("brma_mix", "source_sha256", "drc_swing_gbp") and v is not None else v
                for c, v in row.items()
            ]
            cur.execute(sql, values)
            n += 1
    conn.commit()
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema-only", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        conn = db.connect()
    except db.DatabaseUnavailable as exc:
        logger.error("Database unavailable: %s", exc)
        return 2
    try:
        apply_schema(conn)
        if not args.schema_only:
            migrate_geojson_data(conn, "resource_wealth.geojson", "resource_wealth")
            migrate_geojson_data(conn, "eco_wealth.geojson", "eco_wealth")
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.exception("Migration failed")
        return 1
    finally:
        conn.close()
    logger.info("Migration completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
