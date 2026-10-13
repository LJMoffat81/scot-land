"""Ingest Spatial Hub Housing Land Supply (HLA) into PostGIS planning_sites.

The open product is Spatial Hub *Housing Land Supply – Scotland* under
UK Open Government Licence v3.0. Raw downloads stay under data/external/
(gitignored). This script never commits geometry — it only loads a local
GeoJSON extract into ``planning_sites`` with ``source='hla'``.

Usage:
  export DATABASE_URL=postgresql://...
  python -m etl.ingest_hla_sites \\
    --input ../data/external/spatialhub/hls/pub_hls.geojson \\
    --replace

Convert a Spatial Hub shapefile (EPSG:27700) first if needed:
  ogr2ogr -f GeoJSON -t_srs EPSG:4326 pub_hls.geojson pub_hls.shp
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
DEFAULT_INPUT = (
    REPO_ROOT / "data" / "external" / "spatialhub" / "hls" / "pub_hls.geojson"
)
SOURCE = "hla"
LICENCE = "OGL-3.0"
SPATIAL_HUB_URL = "https://data.spatialhub.scot/dataset/housing_land_supply-is"


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


def _props(feature: dict[str, Any]) -> dict[str, Any]:
    return dict(feature.get("properties") or {})


def site_id_for(props: dict[str, Any], index: int) -> str:
    """Stable public site id from Spatial Hub fields (or synthetic fixture)."""
    for key in ("hls_uid", "site_id", "SITE_ID"):
        value = props.get(key)
        if value not in (None, ""):
            return str(value)
    la = props.get("la_s_code") or props.get("local_auth") or props.get("local_authority")
    refer = props.get("site_refer") or props.get("site_reference") or props.get("site_code")
    year = props.get("hla_year") or props.get("current_ye") or props.get("updtyear")
    parts = [p for p in (la, refer, year) if p not in (None, "")]
    if parts:
        return "|".join(str(p) for p in parts) + f"|{index}"
    return f"HLA-ROW-{index}"


def _optional_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _optional_int(raw: Any) -> int | None:
    value = _optional_float(raw)
    if value is None:
        return None
    return int(round(value))


def hectares_for(props: dict[str, Any], geometry: dict[str, Any] | None) -> float | None:
    for key in ("ha_geometry", "site_size", "SiteArea_ha", "hectares", "ha"):
        value = _optional_float(props.get(key))
        if value is not None:
            return value
    return None


def capacity_for(props: dict[str, Any]) -> int | None:
    for key in ("remaining", "Rem_Cap", "rem_cap", "capacity", "Capa", "capacity_homes"):
        value = _optional_int(props.get(key))
        if value is not None:
            return max(0, value)
    return None


def vintage_for(props: dict[str, Any]) -> str | None:
    for key in ("hla_year", "current_ye", "updtyear", "period", "source_vintage"):
        value = props.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def authority_for(props: dict[str, Any]) -> str | None:
    for key in ("local_auth", "local_authority", "la_s_code", "authorit"):
        value = props.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def geom_source_for(geometry: dict[str, Any] | None, props: dict[str, Any]) -> str:
    gtype = (geometry or {}).get("type")
    if gtype == "Point":
        return "point"
    if props.get("is_buffer") in (True, "true", "True", 1, "1"):
        # Buffer-on-XY is still a polygon in the open product; tag surveyed
        # with planning_status note rather than inventing a new geom_source.
        return "surveyed"
    return "surveyed"


def load_geojson(path: Path, conn, replace: bool) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise SystemExit("Input must be a GeoJSON FeatureCollection (WGS84)")
    features = payload.get("features") or []
    with conn.cursor() as cur:
        if replace:
            cur.execute("DELETE FROM planning_sites WHERE source = %s", (SOURCE,))
        inserted = 0
        for index, feature in enumerate(features):
            geometry = feature.get("geometry")
            if not geometry:
                continue
            props = _props(feature)
            site_id = site_id_for(props, index)
            gtype = geometry.get("type")
            geom_source = geom_source_for(geometry, props)
            if gtype == "Point":
                if geom_source != "point":
                    geom_source = "point"
                geom_sql = (
                    "ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 27700)"
                )
            else:
                geom_sql = (
                    "ST_Multi(ST_Transform("
                    "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 27700))"
                )
                geom_source = "surveyed"
            hectares = hectares_for(props, geometry)
            capacity = capacity_for(props)
            vintage = vintage_for(props)
            authority = authority_for(props)
            status = (
                props.get("planning_status")
                or props.get("Stat")
                or props.get("effective_")
                or props.get("eff_cat")
            )
            cur.execute(
                f"""
                INSERT INTO planning_sites (
                    site_id, source, permitted_use, planning_status,
                    plan_authority, geom_source, geom, hectares,
                    capacity_homes, publish_level, licence, source_vintage
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, {geom_sql}, %s, %s, %s, %s, %s
                )
                ON CONFLICT (source, site_id) DO UPDATE SET
                    permitted_use = EXCLUDED.permitted_use,
                    planning_status = EXCLUDED.planning_status,
                    plan_authority = EXCLUDED.plan_authority,
                    geom_source = EXCLUDED.geom_source,
                    geom = EXCLUDED.geom,
                    hectares = EXCLUDED.hectares,
                    capacity_homes = EXCLUDED.capacity_homes,
                    publish_level = EXCLUDED.publish_level,
                    licence = EXCLUDED.licence,
                    source_vintage = EXCLUDED.source_vintage,
                    updated_at = now();
                """,
                (
                    site_id,
                    SOURCE,
                    "housing",
                    str(status) if status not in (None, "") else None,
                    authority,
                    geom_source,
                    json.dumps(geometry),
                    hectares,
                    capacity,
                    "public_site",
                    LICENCE,
                    vintage,
                ),
            )
            inserted += 1
    conn.commit()
    return inserted


def write_local_stamp(input_path: Path, count: int, vintage: str) -> Path:
    stamp_path = input_path.with_suffix(input_path.suffix + ".ingest.json")
    stamp = {
        "layer": "hla",
        "product": "Spatial Hub Housing Land Supply – Scotland",
        "licence": LICENCE,
        "source_url": SPATIAL_HUB_URL,
        "input": str(input_path),
        "row_count": count,
        "vintage": vintage,
        "ingested_on": date.today().isoformat(),
        "postgis_table": "planning_sites",
        "postgis_source": SOURCE,
        "note": (
            "Local stamp only — raw geometry stays out of git (data/external/). "
            "Synthetic fixtures under data/fixtures/hla/ are for tests only."
        ),
    }
    stamp_path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    return stamp_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to WGS84 GeoJSON under data/external/ (gitignored)",
    )
    parser.add_argument(
        "--vintage",
        default=date.today().isoformat(),
        help="Dataset vintage date (YYYY-MM-DD) recorded in the local stamp",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="DELETE existing source='hla' rows before load",
    )
    args = parser.parse_args()
    if not args.input.is_file():
        raise SystemExit(
            f"Input not found: {args.input}\n"
            "Download Spatial Hub Housing Land Supply (OGL) to "
            "data/external/spatialhub/hls/ (gitignored), convert to WGS84 "
            "GeoJSON, and pass --input. See docs/DATA_ACQUISITION.md."
        )
    resolved = args.input.resolve()
    path_str = str(resolved).replace("\\", "/")
    if "data/processed" in path_str:
        raise SystemExit(
            "Refuse to read HLA geometry from data/processed/. "
            "Keep raw extracts under data/external/ (gitignored)."
        )

    conn = connect()
    try:
        count = load_geojson(args.input, conn, replace=args.replace)
    finally:
        conn.close()
    stamp = write_local_stamp(args.input, count, args.vintage)
    logger.info("Loaded %s HLA sites into planning_sites. Stamp: %s", count, stamp)


if __name__ == "__main__":
    main()
