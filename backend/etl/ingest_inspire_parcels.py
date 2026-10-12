"""Ingest RoS INSPIRE Index Polygons into PostGIS (inspire_parcels).

Large raw downloads stay under data/external/ (gitignored). This script
never commits geometry — it only loads a local extract into PostGIS.

Expected input: GeoJSON FeatureCollection (WGS84) with properties that
include inspireid / nationalcadastralreference / label where available.

Usage:
  export DATABASE_URL=postgresql://...
  python -m etl.ingest_inspire_parcels \\
    --input ../data/external/inspire/index_polygons.geojson

Optional vintage stamp is written next to the input (not to git).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import extras

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE = "inspire_parcels"
DEFAULT_INPUT = REPO_ROOT / "data" / "external" / "inspire" / "index_polygons.geojson"


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
                inspire_id TEXT PRIMARY KEY,
                national_reference TEXT,
                label TEXT,
                area_sqm DOUBLE PRECISION,
                county TEXT,
                geom GEOMETRY(MultiPolygon, 4326) NOT NULL
            );
            """
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_geom "
            f"ON {TABLE} USING GIST (geom);"
        )
    conn.commit()


def _props(feature: dict[str, Any]) -> dict[str, Any]:
    return dict(feature.get("properties") or {})


def _inspire_id(props: dict[str, Any], feature: dict[str, Any], index: int) -> str:
    for key in ("inspireid", "inspire_id", "INSPIREID", "id"):
        value = props.get(key)
        if value:
            return str(value)
    fid = feature.get("id")
    if fid:
        return str(fid)
    return f"row-{index}"


def load_geojson(path: Path, conn, replace: bool) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise SystemExit("Input must be a GeoJSON FeatureCollection")
    features = payload.get("features") or []
    with conn.cursor() as cur:
        if replace:
            cur.execute(f"TRUNCATE TABLE {TABLE};")
        inserted = 0
        for index, feature in enumerate(features):
            geometry = feature.get("geometry")
            if not geometry:
                continue
            props = _props(feature)
            inspire_id = _inspire_id(props, feature, index)
            national = str(
                props.get("nationalcadastralreference")
                or props.get("national_reference")
                or props.get("label")
                or ""
            )
            label = str(props.get("label") or national or inspire_id)
            area = props.get("area_sqm") or props.get("area") or props.get("AREA_SQM")
            county = props.get("county")
            cur.execute(
                f"""
                INSERT INTO {TABLE}
                    (inspire_id, national_reference, label, area_sqm, county, geom)
                VALUES (
                    %s, %s, %s, %s, %s,
                    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                )
                ON CONFLICT (inspire_id) DO UPDATE SET
                    national_reference = EXCLUDED.national_reference,
                    label = EXCLUDED.label,
                    area_sqm = EXCLUDED.area_sqm,
                    county = EXCLUDED.county,
                    geom = EXCLUDED.geom;
                """,
                (
                    inspire_id,
                    national or None,
                    label,
                    float(area) if area is not None else None,
                    str(county) if county is not None else None,
                    json.dumps(geometry),
                ),
            )
            inserted += 1
    conn.commit()
    return inserted


def write_local_stamp(input_path: Path, count: int, vintage: str) -> Path:
    stamp_path = input_path.with_suffix(input_path.suffix + ".ingest.json")
    stamp = {
        "layer": "inspire_parcels",
        "product": "ROS INSPIRE Index Polygons",
        "licence": "OGL / INSPIRE (Crown) — cite Registers of Scotland",
        "source_url": "https://www.ros.gov.uk/open-data",
        "input": str(input_path),
        "row_count": count,
        "vintage": vintage,
        "ingested_on": date.today().isoformat(),
        "note": "Local stamp only — raw geometry stays out of git (data/external/).",
    }
    stamp_path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    return stamp_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to GeoJSON FeatureCollection under data/external/ (gitignored)",
    )
    parser.add_argument(
        "--vintage",
        default=date.today().isoformat(),
        help="Dataset vintage date (YYYY-MM-DD) recorded in the local stamp",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="TRUNCATE inspire_parcels before load",
    )
    args = parser.parse_args()
    if not args.input.is_file():
        raise SystemExit(
            f"Input not found: {args.input}\n"
            "Download RoS INSPIRE Index Polygons to data/external/inspire/ "
            "(gitignored) and pass --input. See docs/DATA_ACQUISITION.md."
        )
    # Refuse paths that look like they would be committed under processed/
    resolved = args.input.resolve()
    if "data/processed" in str(resolved).replace("\\", "/"):
        raise SystemExit(
            "Refuse to read cadastral geometry from data/processed/. "
            "Keep raw extracts under data/external/ (gitignored)."
        )

    conn = connect()
    try:
        ensure_table(conn)
        count = load_geojson(args.input, conn, replace=args.replace)
    finally:
        conn.close()
    stamp = write_local_stamp(args.input, count, args.vintage)
    logger.info("Loaded %s parcels into %s. Stamp: %s", count, TABLE, stamp)


if __name__ == "__main__":
    main()
