"""Ingest Spatial Hub Housing Land Supply (HLA) into PostGIS planning_sites.

The open product is Spatial Hub *Housing Land Supply – Scotland* under
UK Open Government Licence v3.0. Raw downloads stay under data/external/
(gitignored). This script never commits geometry — it loads a local GeoJSON
extract or an authenticated Spatial Hub WFS pull into ``planning_sites``
with ``source='hla'``.

Usage:
  export DATABASE_URL=postgresql://...
  python -m etl.ingest_hla_sites \\
    --input ../data/external/spatialhub/hls/pub_hls.geojson \\
    --replace

  # Authenticated Spatial Hub WFS (requires SPATIALHUB_AUTHKEY in .env):
  python -m etl.ingest_hla_sites --from-wfs --replace

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
from urllib.parse import parse_qsl, urlsplit

import httpx
import psycopg2
import yaml

from etl.receipt_write import write_receipt
from spatial.geoserver_auth import ENV_NAME as SPATIALHUB_AUTHKEY_ENV
from spatial.geoserver_auth import is_configured as spatialhub_auth_configured
from spatial.geoserver_auth import not_loaded_message
from spatial.geoserver_auth import with_wfs_auth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
DEFAULT_INPUT = (
    REPO_ROOT / "data" / "external" / "spatialhub" / "hls" / "pub_hls.geojson"
)
SOURCE = "hla"
LICENCE = "OGL-3.0"
SPATIAL_HUB_URL = "https://data.spatialhub.scot/dataset/housing_land_supply-is"
DEFAULT_WFS = (
    "https://geo.spatialhub.scot/geoserver/sh_hls/wfs"
    "?service=wfs&typeName=sh_hls:pub_hls"
)
WFS_PAGE_SIZE = 1000


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


def wfs_endpoint() -> tuple[str, str]:
    """Return (base_wfs_url, type_name) from sources.yaml with hard-coded fallback."""
    url = DEFAULT_WFS
    type_name = "sh_hls:pub_hls"
    if SOURCES_PATH.is_file():
        with SOURCES_PATH.open(encoding="utf-8") as handle:
            sources = yaml.safe_load(handle) or {}
        block = sources.get("hla") or {}
        url = (block.get("wfs_url") or url).strip()
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    type_name = (
        query.get("typeName")
        or query.get("typeNames")
        or type_name
    )
    base = url.split("?", 1)[0]
    return base, type_name


def fetch_wfs_geojson(
    *,
    page_size: int = WFS_PAGE_SIZE,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Page Spatial Hub HLA WFS GetFeature (GeoJSON). Requires SPATIALHUB_AUTHKEY."""
    if not spatialhub_auth_configured():
        raise SystemExit(
            not_loaded_message("Housing land audit")
            + f" — set {SPATIALHUB_AUTHKEY_ENV} in the gitignored .env "
            "(see backend/.env.example), or pass a local --input extract."
        )
    base_url, type_name = wfs_endpoint()
    features: list[dict[str, Any]] = []
    start = 0
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=120.0)
    assert client is not None
    try:
        while True:
            request_url = with_wfs_auth(
                base_url,
                extra_params={
                    "service": "WFS",
                    "version": "2.0.0",
                    "request": "GetFeature",
                    "typeNames": type_name,
                    "outputFormat": "application/json",
                    "srsName": "EPSG:4326",
                    "count": str(page_size),
                    "startIndex": str(start),
                },
            )
            response = client.get(request_url)
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("features") or []
            features.extend(batch)
            matched = payload.get("numberMatched")
            logger.info(
                "Spatial Hub WFS %s: fetched %s (startIndex=%s, numberMatched=%s)",
                type_name,
                len(batch),
                start,
                matched,
            )
            if len(batch) < page_size:
                break
            start += len(batch)
            if matched not in (None, "unknown") and start >= int(matched):
                break
            if start > 1_000_000:
                raise RuntimeError(f"Unexpectedly large WFS layer {type_name}")
    finally:
        if own_client:
            client.close()
    return {"type": "FeatureCollection", "features": features}


def load_geojson(path: Path, conn, replace: bool) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return load_feature_collection(payload, conn, replace=replace)


def load_feature_collection(
    payload: dict[str, Any], conn, replace: bool
) -> int:
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


def write_local_stamp(input_path: Path, count: int, vintage: str) -> Path | None:
    """Write HLA receipt next to input; non-fatal when /app/data is read-only."""
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
    return write_receipt(
        stamp_path,
        stamp,
        fallback_name=stamp_path.name or "hla.ingest.json",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to WGS84 GeoJSON under data/external/ (gitignored)",
    )
    parser.add_argument(
        "--from-wfs",
        action="store_true",
        help=(
            "Fetch GeoJSON from Spatial Hub HLA WFS (requires "
            f"{SPATIALHUB_AUTHKEY_ENV} in .env)"
        ),
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
    if args.from_wfs:
        payload = fetch_wfs_geojson()
        stamp_path = DEFAULT_INPUT
        conn = connect()
        try:
            count = load_feature_collection(
                payload, conn, replace=args.replace
            )
        finally:
            conn.close()
        stamp = write_local_stamp(stamp_path, count, args.vintage)
        logger.info(
            "Loaded %s HLA sites from Spatial Hub WFS into planning_sites. "
            "Stamp: %s",
            count,
            stamp,
        )
        return

    if not args.input.is_file():
        raise SystemExit(
            f"Input not found: {args.input}\n"
            "Download Spatial Hub Housing Land Supply (OGL) to "
            "data/external/spatialhub/hls/ (gitignored), convert to WGS84 "
            "GeoJSON, and pass --input — or set "
            f"{SPATIALHUB_AUTHKEY_ENV} and use --from-wfs. "
            "See docs/DATA_ACQUISITION.md."
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
