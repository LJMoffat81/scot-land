"""Ingest NatureScot SSSI and designations into PostGIS.

Large raw downloads stay under data/external/naturescot/ (gitignored).
This script never commits geometry — it only loads a local extract.

Expected input: GeoJSON FeatureCollection (WGS84) with NatureScot fields
(NAME, PA_CODE, STATUS, TYPE, SITE_HA, EUROPEAN_CODE / EUROPEAN_C, …).

Usage:
  export DATABASE_URL=postgresql://...
  python -m etl.ingest_naturescot --layer sssi \\
    --input ../data/external/naturescot/sssi.geojson --replace
  python -m etl.ingest_naturescot --layer designations \\
    --input-dir ../data/external/naturescot --replace
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
DEFAULT_DIR = REPO_ROOT / "data" / "external" / "naturescot"
SSSI_TABLE = "naturescot_sssi"
DESIGNATIONS_TABLE = "naturescot_designations"
DESIGNATION_TYPES = ("spa", "sac", "nnr")

DESIGNATION_FILES = {
    "spa": "spa.geojson",
    "sac": "sac.geojson",
    "nnr": "nnr.geojson",
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
    schema = (
        Path(__file__).resolve().parents[1]
        / "db"
        / "schema"
        / "007_naturescot_designations.sql"
    )
    with conn.cursor() as cur:
        cur.execute(schema.read_text(encoding="utf-8"))
    conn.commit()


def _props(feature: dict[str, Any]) -> dict[str, Any]:
    return dict(feature.get("properties") or {})


def _pa_code(props: dict[str, Any], feature: dict[str, Any], index: int) -> str:
    for key in ("PA_CODE", "pa_code", "CODE", "code", "id"):
        value = props.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    fid = feature.get("id")
    if fid is not None:
        return str(fid)
    return f"row-{index}"


def _name(props: dict[str, Any], fallback: str) -> str:
    for key in ("NAME", "name", "SITE_NAME", "site_name"):
        value = props.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return fallback


def _optional_str(props: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = props.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _optional_float(props: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = props.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def load_sssi(path: Path, conn, replace: bool) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise SystemExit("Input must be a GeoJSON FeatureCollection")
    features = payload.get("features") or []
    with conn.cursor() as cur:
        if replace:
            cur.execute(f"TRUNCATE TABLE {SSSI_TABLE};")
        inserted = 0
        for index, feature in enumerate(features):
            geometry = feature.get("geometry")
            if not geometry:
                continue
            props = _props(feature)
            code = _pa_code(props, feature, index)
            cur.execute(
                f"""
                INSERT INTO {SSSI_TABLE}
                    (pa_code, name, status, site_type, site_ha, european_code, geom)
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                )
                ON CONFLICT (pa_code) DO UPDATE SET
                    name = EXCLUDED.name,
                    status = EXCLUDED.status,
                    site_type = EXCLUDED.site_type,
                    site_ha = EXCLUDED.site_ha,
                    european_code = EXCLUDED.european_code,
                    geom = EXCLUDED.geom;
                """,
                (
                    code,
                    _name(props, code),
                    _optional_str(props, "STATUS", "status"),
                    _optional_str(props, "TYPE", "site_type", "SITE_TYPE"),
                    _optional_float(props, "SITE_HA", "site_ha", "FEATURE_HA"),
                    _optional_str(
                        props, "EUROPEAN_CODE", "EUROPEAN_C", "european_code"
                    ),
                    json.dumps(geometry),
                ),
            )
            inserted += 1
    conn.commit()
    return inserted


def load_designation_type(
    path: Path, conn, designation_type: str, replace_type: bool
) -> int:
    if designation_type not in DESIGNATION_TYPES:
        raise SystemExit(f"Unknown designation type: {designation_type}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise SystemExit("Input must be a GeoJSON FeatureCollection")
    features = payload.get("features") or []
    with conn.cursor() as cur:
        if replace_type:
            cur.execute(
                f"DELETE FROM {DESIGNATIONS_TABLE} WHERE designation_type = %s;",
                (designation_type,),
            )
        inserted = 0
        for index, feature in enumerate(features):
            geometry = feature.get("geometry")
            if not geometry:
                continue
            props = _props(feature)
            code = _pa_code(props, feature, index)
            site_key = f"{designation_type}:{code}"
            cur.execute(
                f"""
                INSERT INTO {DESIGNATIONS_TABLE}
                    (site_key, designation_type, pa_code, name, status,
                     site_type, site_ha, european_code, geom)
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                )
                ON CONFLICT (site_key) DO UPDATE SET
                    pa_code = EXCLUDED.pa_code,
                    name = EXCLUDED.name,
                    status = EXCLUDED.status,
                    site_type = EXCLUDED.site_type,
                    site_ha = EXCLUDED.site_ha,
                    european_code = EXCLUDED.european_code,
                    geom = EXCLUDED.geom;
                """,
                (
                    site_key,
                    designation_type,
                    code,
                    _name(props, site_key),
                    _optional_str(props, "STATUS", "status"),
                    _optional_str(props, "TYPE", "site_type", "SITE_TYPE"),
                    _optional_float(props, "SITE_HA", "site_ha", "FEATURE_HA"),
                    _optional_str(
                        props, "EUROPEAN_CODE", "EUROPEAN_C", "european_code"
                    ),
                    json.dumps(geometry),
                ),
            )
            inserted += 1
    conn.commit()
    return inserted


def write_local_stamp(
    stamp_path: Path, *, layer: str, count: int, vintage: str, inputs: list[str]
) -> Path:
    stamp = {
        "layer": layer,
        "product": "NatureScot protected areas",
        "licence": "OGL-3.0",
        "source_url": "https://opendata.nature.scot/",
        "inputs": inputs,
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
        "--layer",
        choices=("sssi", "designations", "all"),
        default="all",
        help="Which NatureScot tables to load",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="GeoJSON path for --layer sssi (default: data/external/naturescot/sssi.geojson)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_DIR,
        help="Directory containing spa.geojson / sac.geojson / nnr.geojson",
    )
    parser.add_argument(
        "--vintage",
        default=date.today().isoformat(),
        help="Dataset vintage date (YYYY-MM-DD) recorded in the local stamp",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Truncate / replace existing rows for the selected layer",
    )
    args = parser.parse_args()

    conn = connect()
    try:
        ensure_tables(conn)
        total = 0
        inputs: list[str] = []
        if args.layer in ("sssi", "all"):
            sssi_path = args.input or (DEFAULT_DIR / "sssi.geojson")
            if not sssi_path.is_file():
                raise SystemExit(f"SSSI GeoJSON not found: {sssi_path}")
            n = load_sssi(sssi_path, conn, replace=args.replace)
            logger.info("Loaded %s SSSI features from %s", n, sssi_path)
            total += n
            inputs.append(str(sssi_path))
            write_local_stamp(
                sssi_path.with_suffix(sssi_path.suffix + ".ingest.json"),
                layer="naturescot_sssi",
                count=n,
                vintage=args.vintage,
                inputs=[str(sssi_path)],
            )
        if args.layer in ("designations", "all"):
            type_total = 0
            for dtype, filename in DESIGNATION_FILES.items():
                path = args.input_dir / filename
                if not path.is_file():
                    raise SystemExit(f"Designation GeoJSON not found: {path}")
                n = load_designation_type(
                    path, conn, dtype, replace_type=args.replace
                )
                logger.info("Loaded %s %s features from %s", n, dtype.upper(), path)
                type_total += n
                inputs.append(str(path))
            total += type_total
            write_local_stamp(
                args.input_dir / "designations.ingest.json",
                layer="naturescot_designations",
                count=type_total,
                vintage=args.vintage,
                inputs=inputs if args.layer == "designations" else inputs[1:],
            )
        logger.info("NatureScot ingest complete (%s features)", total)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
