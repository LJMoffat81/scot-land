"""Ingest NFI / Native Woodland Survey into PostGIS.

Large raw downloads stay under data/external/ (gitignored). This script
never commits geometry — it only loads a local extract or a live WFS pull
into PostGIS. Mixed geometries keep polygon parts only.

Usage:
  export DATABASE_URL=postgresql://...

  # One-command WFS → PostGIS (NatureScot scottishforestry workspace)
  python -m etl.ingest_woodland_layers --layer nfi --from-wfs --replace
  python -m etl.ingest_woodland_layers --layer native_woodland --from-wfs --replace

  # Or load a local GeoJSON (after WFS conversion / open-data download)
  python -m etl.ingest_woodland_layers --layer nfi \\
    --input ../data/external/woodland/nfi_woodland.geojson --replace
  python -m etl.ingest_woodland_layers --layer native_woodland \\
    --input ../data/external/woodland/native_woodland.geojson --replace

Fixtures for CI/local smoke tests:
  data/fixtures/gis/nfi_woodland_sample.geojson
  data/fixtures/gis/native_woodland_sample.geojson

See scripts/data/README-woodland.md.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import psycopg2
import yaml
from shapely.geometry import MultiPolygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
DEFAULT_WFS = "https://ogc.nature.scot/geoserver/scottishforestry/ows"
WFS_PAGE_SIZE = 1000
COUNT_TOLERANCE = 0.001  # ~0.1% vs #57 / WFS numberMatched baseline

LAYERS = {
    "nfi": {
        "table": "nfi_woodland",
        "default": REPO_ROOT / "data" / "external" / "woodland" / "nfi_woodland.geojson",
        "fixture": REPO_ROOT
        / "data"
        / "fixtures"
        / "gis"
        / "nfi_woodland_sample.geojson",
        "wfs_type_name": "scottishforestry:National_Forest_Inventory_Woodland_Scotland",
        "expected_rows": 207_640,
        "sources_key": "nfi",
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
        "wfs_type_name": "scottishforestry:Native_Woodland_Survey_of_Scotland",
        "expected_rows": 95_814,
        "sources_key": "native_woodland",
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


def keep_polygons(geom: BaseGeometry) -> dict[str, Any] | None:
    """Keep polygon / multipolygon parts from mixed WFS geometries."""
    if geom.is_empty:
        return None
    if geom.geom_type == "Polygon":
        return mapping(MultiPolygon([geom]))
    if geom.geom_type == "MultiPolygon":
        return mapping(geom)
    if geom.geom_type == "GeometryCollection":
        parts = [
            g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty
        ]
        if not parts:
            return None
        return keep_polygons(unary_union(parts))
    return None


def _feature_id(layer: str, props: dict[str, Any], feature: dict[str, Any], index: int) -> str:
    if layer == "nfi":
        for key in ("id", "OBJECTID", "objectid", "fid"):
            if feature.get(key):
                return f"nfi-{feature[key]}"
        for key in ("OBJECTID", "objectid", "fid"):
            if props.get(key) is not None and props.get(key) != "":
                return f"nfi-{props[key]}"
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


def _geometry_json(feature: dict[str, Any]) -> str | None:
    geometry = feature.get("geometry")
    if not geometry:
        return None
    try:
        geom = shape(geometry)
    except Exception:
        return None
    multi = keep_polygons(geom)
    if multi is None:
        return None
    return json.dumps(multi)


def wfs_config(layer: str) -> tuple[str, str]:
    """Return (wfs_url, type_name) from sources.yaml with hard-coded fallbacks."""
    spec = LAYERS[layer]
    type_name = spec["wfs_type_name"]
    url = DEFAULT_WFS
    if SOURCES_PATH.is_file():
        with SOURCES_PATH.open(encoding="utf-8") as handle:
            sources = yaml.safe_load(handle) or {}
        block = sources.get(spec["sources_key"]) or {}
        url = (block.get("wfs_url") or url).rstrip("?")
        type_name = block.get("wfs_type_name") or type_name
    return url, type_name


def fetch_wfs_geojson(
    layer: str,
    *,
    page_size: int = WFS_PAGE_SIZE,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Page NatureScot WFS GetFeature (GeoJSON) for one woodland layer."""
    wfs_url, type_name = wfs_config(layer)
    features: list[dict[str, Any]] = []
    start = 0
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=120.0)
    assert client is not None
    try:
        while True:
            params = {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": type_name,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "count": str(page_size),
                "startIndex": str(start),
            }
            response = client.get(wfs_url, params=params)
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("features") or []
            features.extend(batch)
            matched = payload.get("numberMatched")
            logger.info(
                "WFS %s: fetched %s (startIndex=%s, numberMatched=%s)",
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


def check_count(layer: str, actual: int, *, tolerance: float = COUNT_TOLERANCE) -> None:
    expected = int(LAYERS[layer]["expected_rows"])
    delta = abs(actual - expected) / expected if expected else abs(actual - expected)
    if delta > tolerance:
        raise SystemExit(
            f"{layer}: got {actual:,}, expected {expected:,} "
            f"(Δ {delta:.4%} > {tolerance:.1%}) — #57 / WFS baseline"
        )
    logger.info(
        "Count check OK %s: %s (expected %s, Δ %.4f%%)",
        layer,
        f"{actual:,}",
        f"{expected:,}",
        delta * 100,
    )


def load_nfi(path: Path | None, conn, replace: bool, payload: dict[str, Any] | None = None) -> int:
    if payload is None:
        assert path is not None
        payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features") or []
    with conn.cursor() as cur:
        if replace:
            cur.execute("TRUNCATE TABLE nfi_woodland;")
        inserted = 0
        skipped = 0
        for index, feature in enumerate(features):
            geom_json = _geometry_json(feature)
            if not geom_json:
                skipped += 1
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
                    geom_json,
                ),
            )
            inserted += 1
    conn.commit()
    if skipped:
        logger.info("NFI: skipped %s non-polygon / empty features", skipped)
    return inserted


def load_native(
    path: Path | None, conn, replace: bool, payload: dict[str, Any] | None = None
) -> int:
    if payload is None:
        assert path is not None
        payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features") or []
    with conn.cursor() as cur:
        if replace:
            cur.execute("TRUNCATE TABLE native_woodland;")
        inserted = 0
        skipped = 0
        for index, feature in enumerate(features):
            geom_json = _geometry_json(feature)
            if not geom_json:
                skipped += 1
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
                    geom_json,
                ),
            )
            inserted += 1
    conn.commit()
    if skipped:
        logger.info("NWSS: skipped %s non-polygon / empty features", skipped)
    return inserted


def write_stamp(path: Path, layer: str, count: int, *, source: str) -> None:
    stamp = path.with_suffix(path.suffix + ".ingest.json")
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(
        json.dumps(
            {
                "layer": layer,
                "input": str(path),
                "rows": count,
                "source": source,
                "expected_rows": LAYERS[layer]["expected_rows"],
                "ingested_on": date.today().isoformat(),
                "note": "Local stamp only — raw geometry stays out of git.",
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
        "--from-wfs",
        action="store_true",
        help="Fetch GeoJSON from NatureScot scottishforestry WFS (paged) then load",
    )
    parser.add_argument(
        "--save-fetch",
        action="store_true",
        help="When --from-wfs, also write GeoJSON under data/external/woodland/",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="TRUNCATE the target table before load",
    )
    parser.add_argument(
        "--check-counts",
        action="store_true",
        help="Fail unless row count matches the #57 / WFS baseline within ~0.1%",
    )
    args = parser.parse_args()
    spec = LAYERS[args.layer]

    mode_flags = sum(
        [
            bool(args.from_wfs),
            bool(args.fixture),
            args.input is not None,
        ]
    )
    if mode_flags > 1:
        parser.error("Use only one of --from-wfs, --fixture, or --input")

    payload: dict[str, Any] | None = None
    path: Path | None = args.input
    source = "local-geojson"

    if args.from_wfs:
        source = "wfs"
        payload = fetch_wfs_geojson(args.layer)
        path = spec["default"]
        if args.save_fetch:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
            logger.info("Wrote WFS extract → %s", path)
    elif path is None:
        path = spec["fixture"] if args.fixture else spec["default"]
        source = "fixture" if args.fixture else "local-geojson"
        if not path.is_file():
            raise SystemExit(
                f"Input not found: {path}\n"
                "Use --from-wfs, --fixture, or place a GeoJSON under data/external/woodland/."
            )

    conn = connect()
    try:
        ensure_tables(conn)
        if args.layer == "nfi":
            count = load_nfi(path, conn, args.replace, payload=payload)
        else:
            count = load_native(path, conn, args.replace, payload=payload)
    finally:
        conn.close()

    if args.check_counts:
        check_count(args.layer, count)

    assert path is not None
    write_stamp(path, args.layer, count, source=source)
    logger.info("Loaded %s rows into %s from %s (%s)", count, spec["table"], path, source)


if __name__ == "__main__":
    main()
