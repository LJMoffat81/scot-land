"""Ingest NFI / Native Woodland Survey GeoJSON into PostGIS.

Large raw downloads stay under data/external/ (gitignored). This script
never commits geometry — it only loads a local extract into PostGIS.

Usage:
  export DATABASE_URL=postgresql://...
  python -m etl.ingest_woodland_layers --layer nfi \\
    --input ../data/external/woodland/nfi_woodland.geojson --replace
  python -m etl.ingest_woodland_layers --layer native_woodland \\
    --input ../data/external/woodland/native_woodland.geojson --replace

Fixtures for CI/local smoke tests:
  data/fixtures/gis/nfi_woodland_sample.geojson
  data/fixtures/gis/native_woodland_sample.geojson
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

LAYERS = {
    "nfi": {
        "table": "nfi_woodland",
        "default": REPO_ROOT / "data" / "external" / "woodland" / "nfi_woodland.geojson",
        "fixture": REPO_ROOT
        / "data"
        / "fixtures"
        / "gis"
        / "nfi_woodland_sample.geojson",
    },
    "native_woodland": {
        "table": "native_woodland",
        "default": REPO_ROOT
        / "data"
        / "external"
        / "woodland"
        / "native_woodland.geojson",
        "fixture": REPO_ROOT
        / "data"
        / "fixtures"
        / "gis"
        / "native_woodland_sample.geojson",
    },
}


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


def ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS nfi_woodland (
                feature_id TEXT PRIMARY KEY,
                category TEXT,
                ift_ioa TEXT,
                country TEXT,
                area_ha DOUBLE PRECISION,
                geom GEOMETRY(MultiPolygon, 4326) NOT NULL
            );
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_nfi_woodland_geom "
            "ON nfi_woodland USING GIST (geom);"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS native_woodland (
                feature_id TEXT PRIMARY KEY,
                object_id INTEGER,
                scptdata_i INTEGER,
                woodland_type TEXT,
                canopy_pct INTEGER,
                native_pct INTEGER,
                dom_habitat TEXT,
                hectares DOUBLE PRECISION,
                maturity TEXT,
                geom GEOMETRY(MultiPolygon, 4326) NOT NULL
            );
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_native_woodland_geom "
            "ON native_woodland USING GIST (geom);"
        )
    conn.commit()


def _feature_id(layer: str, props: dict[str, Any], feature: dict[str, Any], index: int) -> str:
    if layer == "nfi":
        for key in ("id", "OBJECTID", "objectid", "fid"):
            if feature.get(key):
                return f"nfi-{feature[key]}"
        cat = props.get("CATEGORY") or props.get("category") or "x"
        ift = props.get("IFT_IOA") or props.get("ift_ioa") or "x"
        area = props.get("Area_ha") or props.get("area_ha") or index
        return f"nfi-{cat}-{ift}-{area}-{index}"
    for key in ("OBJECTID", "object_id", "SCPTDATA_I", "scptdata_i", "id"):
        value = props.get(key) if key in props else feature.get(key)
        if value is not None and value != "":
            return f"nwss-{value}"
    return f"nwss-row-{index}"


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_nfi(path: Path, conn, replace: bool) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features") or []
    with conn.cursor() as cur:
        if replace:
            cur.execute("TRUNCATE TABLE nfi_woodland;")
        inserted = 0
        for index, feature in enumerate(features):
            geometry = feature.get("geometry")
            if not geometry:
                continue
            props = dict(feature.get("properties") or {})
            fid = _feature_id("nfi", props, feature, index)
            cur.execute(
                """
                INSERT INTO nfi_woodland
                    (feature_id, category, ift_ioa, country, area_ha, geom)
                VALUES (
                    %s, %s, %s, %s, %s,
                    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                )
                ON CONFLICT (feature_id) DO UPDATE SET
                    category = EXCLUDED.category,
                    ift_ioa = EXCLUDED.ift_ioa,
                    country = EXCLUDED.country,
                    area_ha = EXCLUDED.area_ha,
                    geom = EXCLUDED.geom
                """,
                (
                    fid,
                    props.get("CATEGORY") or props.get("category"),
                    props.get("IFT_IOA") or props.get("ift_ioa"),
                    props.get("COUNTRY") or props.get("country"),
                    _as_float(props.get("Area_ha") or props.get("area_ha")),
                    json.dumps(geometry),
                ),
            )
            inserted += 1
    conn.commit()
    return inserted


def load_native(path: Path, conn, replace: bool) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features") or []
    with conn.cursor() as cur:
        if replace:
            cur.execute("TRUNCATE TABLE native_woodland;")
        inserted = 0
        for index, feature in enumerate(features):
            geometry = feature.get("geometry")
            if not geometry:
                continue
            props = dict(feature.get("properties") or {})
            fid = _feature_id("native_woodland", props, feature, index)
            cur.execute(
                """
                INSERT INTO native_woodland (
                    feature_id, object_id, scptdata_i, woodland_type,
                    canopy_pct, native_pct, dom_habitat, hectares, maturity, geom
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                )
                ON CONFLICT (feature_id) DO UPDATE SET
                    object_id = EXCLUDED.object_id,
                    scptdata_i = EXCLUDED.scptdata_i,
                    woodland_type = EXCLUDED.woodland_type,
                    canopy_pct = EXCLUDED.canopy_pct,
                    native_pct = EXCLUDED.native_pct,
                    dom_habitat = EXCLUDED.dom_habitat,
                    hectares = EXCLUDED.hectares,
                    maturity = EXCLUDED.maturity,
                    geom = EXCLUDED.geom
                """,
                (
                    fid,
                    _as_int(props.get("OBJECTID") or props.get("object_id")),
                    _as_int(props.get("SCPTDATA_I") or props.get("scptdata_i")),
                    props.get("TYPE") or props.get("woodland_type"),
                    _as_int(props.get("CANOPY_PCT") or props.get("canopy_pct")),
                    _as_int(props.get("NATIVE_PCT") or props.get("native_pct")),
                    props.get("DOM_HABITA") or props.get("dom_habitat"),
                    _as_float(props.get("HECTARES") or props.get("hectares")),
                    props.get("MATURITY") or props.get("maturity"),
                    json.dumps(geometry),
                ),
            )
            inserted += 1
    conn.commit()
    return inserted


def write_stamp(path: Path, layer: str, count: int) -> None:
    stamp = path.with_suffix(path.suffix + ".ingest.json")
    stamp.write_text(
        json.dumps(
            {
                "layer": layer,
                "input": str(path),
                "rows": count,
                "ingested_on": date.today().isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--layer",
        choices=sorted(LAYERS),
        required=True,
        help="Which woodland layer to load",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="GeoJSON FeatureCollection (default: data/external path)",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Load the small redistributable fixture instead of data/external",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="TRUNCATE the target table before load",
    )
    args = parser.parse_args()
    spec = LAYERS[args.layer]
    path = args.input
    if path is None:
        path = spec["fixture"] if args.fixture else spec["default"]
    if not path.is_file():
        raise SystemExit(f"Input not found: {path}")

    conn = connect()
    try:
        ensure_tables(conn)
        if args.layer == "nfi":
            count = load_nfi(path, conn, args.replace)
        else:
            count = load_native(path, conn, args.replace)
    finally:
        conn.close()
    write_stamp(path, args.layer, count)
    logger.info("Loaded %s rows into %s from %s", count, spec["table"], path)


if __name__ == "__main__":
    main()
