"""Ingest Crown Estate Scotland ScotWind / INTOG option polygons into PostGIS.

Fetches the open CES Spatial Hub FeatureServers (or a local GeoJSON) and loads
``ces_scotwind_intog``. Polygons + award descriptors only.

Option-fee £ are HOLD — see ``data/config/scotwind_option_fees.yaml``. They are
never stored as layer attributes.

Raw downloads may be written under ``data/external/ces/`` (gitignored). Never
commit that directory.

Usage:
  export DATABASE_URL=postgresql://...
  python -m etl.ingest_scotwind_intog --from-api
  python -m etl.ingest_scotwind_intog --input ../data/external/ces/scotwind_intog.geojson
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
import psycopg2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE = "ces_scotwind_intog"
CES_ROOT = "https://services3.arcgis.com/nGV4jiurzcahJ9LV/ArcGIS/rest/services"

SOURCES = (
    {
        "leasing_round": "scotwind",
        "url": f"{CES_ROOT}/ScotWind_Offers_Crown_Estate_Scotland/FeatureServer/0/query",
        "award_field": "Id",
        "capacity_field": "Total_Cap",
    },
    {
        "leasing_round": "intog",
        "url": f"{CES_ROOT}/INTOG_Application_Areas/FeatureServer/0/query",
        "award_field": "ID",
        "capacity_field": "Capacity",
    },
)

EVIDENCE_TAG = "market"
PUBLICATION_STATUS = "ok"
SOURCE_ID = "ces_spatial_hub_scotwind_intog"
LICENCE = "OGL-3.0"
# Dropped if an earlier draft created them — fees are not layer attributes.
_LEGACY_FEE_COLUMNS = (
    "option_fee_gbp",
    "option_fee_per_km2_gbp",
    "fee_status",
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
                id TEXT PRIMARY KEY,
                leasing_round TEXT NOT NULL,
                award_id INTEGER,
                lead_applicant TEXT,
                technology TEXT,
                category TEXT,
                innovation_category TEXT,
                capacity_mw DOUBLE PRECISION,
                area_km2 DOUBLE PRECISION,
                evidence_tag TEXT NOT NULL DEFAULT '{EVIDENCE_TAG}',
                publication_status TEXT NOT NULL DEFAULT '{PUBLICATION_STATUS}',
                source_id TEXT,
                licence TEXT,
                geom GEOMETRY(MultiPolygon, 4326) NOT NULL
            );
            """
        )
        for col in _LEGACY_FEE_COLUMNS:
            cur.execute(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS {col};")
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_geom "
            f"ON {TABLE} USING GIST (geom);"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_round "
            f"ON {TABLE} (leasing_round);"
        )
    conn.commit()


def _fetch_layer(url: str) -> list[dict[str, Any]]:
    """GeoJSON features in WGS84 (outSR=4326) — INTOG native CRS is 27700."""
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "geojson",
    }
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    if payload.get("type") != "FeatureCollection":
        raise RuntimeError(f"Expected FeatureCollection from {url}")
    return list(payload.get("features") or [])


def _row_from_feature(
    feature: dict[str, Any],
    *,
    leasing_round: str,
    award_field: str,
    capacity_field: str,
) -> dict[str, Any] | None:
    geometry = feature.get("geometry")
    if not geometry:
        return None
    props = dict(feature.get("properties") or feature.get("attributes") or {})
    award_raw = props.get(award_field) or props.get("award_id") or props.get("Id") or props.get("ID")
    if award_raw is None:
        return None
    award_id = int(award_raw)
    row_id = f"{leasing_round}:{award_id}"
    category = props.get("Category")
    in_cat = props.get("IN_Cat")
    if isinstance(in_cat, str) and not in_cat.strip():
        in_cat = None
    return {
        "id": row_id,
        "leasing_round": leasing_round,
        "award_id": award_id,
        "lead_applicant": props.get("Lead_App") or props.get("lead_applicant"),
        "technology": props.get("Technology") or props.get("technology"),
        "category": category,
        "innovation_category": in_cat,
        "capacity_mw": props.get(capacity_field) or props.get("capacity_mw"),
        "area_km2": props.get("Area_km2") or props.get("area_km2"),
        "evidence_tag": EVIDENCE_TAG,
        "publication_status": PUBLICATION_STATUS,
        "source_id": SOURCE_ID,
        "licence": LICENCE,
        "geometry": geometry,
    }


def features_from_api() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in SOURCES:
        features = _fetch_layer(source["url"])
        logger.info("Fetched %d features from %s", len(features), source["leasing_round"])
        for feature in features:
            row = _row_from_feature(
                feature,
                leasing_round=source["leasing_round"],
                award_field=source["award_field"],
                capacity_field=source["capacity_field"],
            )
            if row:
                rows.append(row)
    return rows


def features_from_geojson(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise SystemExit("Input must be a GeoJSON FeatureCollection")
    rows: list[dict[str, Any]] = []
    for feature in payload.get("features") or []:
        props = dict(feature.get("properties") or {})
        leasing_round = str(props.get("leasing_round") or "").lower()
        if leasing_round not in {"scotwind", "intog"}:
            raise SystemExit(
                "Local GeoJSON features need properties.leasing_round "
                "in {scotwind, intog}"
            )
        award_field = "award_id" if "award_id" in props else ("Id" if leasing_round == "scotwind" else "ID")
        capacity_field = (
            "capacity_mw"
            if "capacity_mw" in props
            else ("Total_Cap" if leasing_round == "scotwind" else "Capacity")
        )
        wrapped = {"geometry": feature.get("geometry"), "properties": props}
        row = _row_from_feature(
            wrapped,
            leasing_round=leasing_round,
            award_field=award_field,
            capacity_field=capacity_field,
        )
        if row:
            rows.append(row)
    return rows


def load_rows(conn, rows: list[dict[str, Any]], replace: bool) -> int:
    with conn.cursor() as cur:
        if replace:
            cur.execute(f"TRUNCATE TABLE {TABLE};")
        inserted = 0
        for row in rows:
            geom = json.dumps(row["geometry"])
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    id, leasing_round, award_id, lead_applicant, technology,
                    category, innovation_category, capacity_mw, area_km2,
                    evidence_tag, publication_status, source_id, licence, geom
                ) VALUES (
                    %(id)s, %(leasing_round)s, %(award_id)s, %(lead_applicant)s,
                    %(technology)s, %(category)s, %(innovation_category)s,
                    %(capacity_mw)s, %(area_km2)s, %(evidence_tag)s,
                    %(publication_status)s, %(source_id)s, %(licence)s,
                    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326))
                )
                ON CONFLICT (id) DO UPDATE SET
                    leasing_round = EXCLUDED.leasing_round,
                    award_id = EXCLUDED.award_id,
                    lead_applicant = EXCLUDED.lead_applicant,
                    technology = EXCLUDED.technology,
                    category = EXCLUDED.category,
                    innovation_category = EXCLUDED.innovation_category,
                    capacity_mw = EXCLUDED.capacity_mw,
                    area_km2 = EXCLUDED.area_km2,
                    evidence_tag = EXCLUDED.evidence_tag,
                    publication_status = EXCLUDED.publication_status,
                    source_id = EXCLUDED.source_id,
                    licence = EXCLUDED.licence,
                    geom = EXCLUDED.geom
                """,
                {**row, "geom": geom},
            )
            inserted += 1
    conn.commit()
    return inserted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-api",
        action="store_true",
        help="Fetch ScotWind Offers + INTOG Application Areas from CES FeatureServers",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Local GeoJSON FeatureCollection (WGS84) with leasing_round on each feature",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="TRUNCATE before load (always on for --from-api)",
    )
    parser.add_argument(
        "--save-raw",
        type=Path,
        help="Optional path under data/external/ to write combined GeoJSON (gitignored)",
    )
    args = parser.parse_args(argv)
    if not args.from_api and not args.input:
        parser.error("Provide --from-api and/or --input")

    if args.from_api:
        rows = features_from_api()
        replace = True
    else:
        rows = features_from_geojson(args.input)
        replace = args.replace

    if args.save_raw:
        raw_path = args.save_raw
        if "data/external" not in str(raw_path.resolve()):
            logger.warning(
                "save-raw path is outside data/external; prefer gitignored data/external/ces/"
            )
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {k: v for k, v in row.items() if k != "geometry"},
                    "geometry": row["geometry"],
                }
                for row in rows
            ],
        }
        raw_path.write_text(json.dumps(collection), encoding="utf-8")
        logger.info("Wrote raw extract to %s (%d features)", raw_path, len(rows))

    conn = connect()
    try:
        ensure_table(conn)
        n = load_rows(conn, rows, replace=replace)
    finally:
        conn.close()
    logger.info(
        "Loaded %d ScotWind/INTOG polygon rows into %s (evidence=%s, publication=%s; fees not on layer)",
        n,
        TABLE,
        EVIDENCE_TAG,
        PUBLICATION_STATUS,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
