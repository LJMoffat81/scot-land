"""Ingest Community Ownership in Scotland 2024 points into PostGIS.

Processed GeoJSON (postcodes.io centroids of the SG OGL asset dataset) lives
under data/processed/gis/. Never writes to data/external.

Usage:
  export DATABASE_URL=postgresql://...
  python -m etl.ingest_community_ownership
  python -m etl.ingest_community_ownership --input ../data/processed/gis/community_ownership_assets.geojson
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import extras

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE = "community_ownership_assets"
DEFAULT_INPUT = (
    REPO_ROOT / "data" / "processed" / "gis" / "community_ownership_assets.geojson"
)


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


def connect():
    cfg = _db_config()
    if "dsn" in cfg:
        return psycopg2.connect(cfg["dsn"])
    return psycopg2.connect(**cfg)


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                asset_id TEXT PRIMARY KEY,
                group_name TEXT NOT NULL,
                asset_name TEXT,
                postcode TEXT,
                local_authority TEXT,
                la_s_code TEXT,
                area_ha DOUBLE PRECISION,
                asset_type TEXT,
                year_of_ownership INTEGER,
                geometry_source TEXT NOT NULL DEFAULT 'postcode_centroid',
                geom GEOMETRY(Point, 4326) NOT NULL
            );
            """
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_geom "
            f"ON {TABLE} USING GIST (geom);"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_la "
            f"ON {TABLE} (la_s_code);"
        )
    conn.commit()


def load_geojson(path: Path, conn, replace: bool) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise SystemExit("Input must be a GeoJSON FeatureCollection")
    features = payload.get("features") or []
    rows: list[tuple[Any, ...]] = []
    for feat in features:
        props = dict(feat.get("properties") or {})
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            continue
        lng, lat = float(coords[0]), float(coords[1])
        asset_id = props.get("asset_id")
        group_name = props.get("group_name")
        if not asset_id or not group_name:
            continue
        year = props.get("year_of_ownership")
        try:
            year_i = int(year) if year is not None and year != "" else None
        except (TypeError, ValueError):
            year_i = None
        area = props.get("area_ha")
        try:
            area_f = float(area) if area is not None and area != "" else None
        except (TypeError, ValueError):
            area_f = None
        rows.append(
            (
                str(asset_id),
                str(group_name),
                props.get("asset_name"),
                props.get("postcode"),
                props.get("local_authority"),
                props.get("la_s_code"),
                area_f,
                props.get("asset_type"),
                year_i,
                props.get("geometry_source") or "postcode_centroid",
                lng,
                lat,
            )
        )
    with conn.cursor() as cur:
        if replace:
            cur.execute(f"TRUNCATE TABLE {TABLE};")
        extras.execute_batch(
            cur,
            f"""
            INSERT INTO {TABLE} (
                asset_id, group_name, asset_name, postcode, local_authority,
                la_s_code, area_ha, asset_type, year_of_ownership,
                geometry_source, geom
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)
            )
            ON CONFLICT (asset_id) DO UPDATE SET
                group_name = EXCLUDED.group_name,
                asset_name = EXCLUDED.asset_name,
                postcode = EXCLUDED.postcode,
                local_authority = EXCLUDED.local_authority,
                la_s_code = EXCLUDED.la_s_code,
                area_ha = EXCLUDED.area_ha,
                asset_type = EXCLUDED.asset_type,
                year_of_ownership = EXCLUDED.year_of_ownership,
                geometry_source = EXCLUDED.geometry_source,
                geom = EXCLUDED.geom
            """,
            rows,
            page_size=200,
        )
    conn.commit()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Processed GeoJSON FeatureCollection (WGS84 points)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="TRUNCATE community_ownership_assets before load",
    )
    args = parser.parse_args(argv)
    if not args.input.is_file():
        raise SystemExit(f"Input not found: {args.input}")
    conn = connect()
    try:
        ensure_table(conn)
        count = load_geojson(args.input, conn, replace=args.replace)
    finally:
        conn.close()
    logger.info("Loaded %s community ownership assets into %s", count, TABLE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
