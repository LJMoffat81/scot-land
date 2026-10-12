"""Ingest SEPA Flood Maps polygons into PostGIS (sepa_flood).

Raw geodatabases / national extracts stay under data/external/ (gitignored).
Prefer exporting medium-likelihood river + coastal layers to GeoJSON
(EPSG:4326) from the SEPA download or MapServer, then:

  python -m etl.ingest_sepa_flood \\
    --input ../data/external/sepa/flood_medium_river_coastal.geojson \\
    --replace

Each feature needs properties.layer_id (1=river medium, 7=coastal medium)
or SOURCE / PROB fields matching the MapServer schema.
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
from shapely.geometry import MultiPolygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("ingest_sepa_flood")

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE = "sepa_flood"
DEFAULT_INPUT = (
    REPO_ROOT / "data" / "external" / "sepa" / "flood_medium_river_coastal.geojson"
)

SOURCE_FROM_LAYER = {1: "River", 4: "Surface Water", 7: "Coastal"}


def connect():
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        dbname=os.getenv("WEALTH_DB_NAME", "scotland_wealth"),
        user=os.getenv("WEALTH_DB_USER", "wealth_user"),
        password=os.getenv("WEALTH_DB_PASSWORD", ""),
        host=os.getenv("WEALTH_DB_HOST", "localhost"),
        port=os.getenv("WEALTH_DB_PORT", "5432"),
    )


def ensure_table(conn) -> None:
    sql = (REPO_ROOT / "backend" / "db" / "schema" / "007_sepa_flood.sql").read_text(
        encoding="utf-8"
    )
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def _as_multipolygon(geom: BaseGeometry) -> dict[str, Any] | None:
    if geom.is_empty:
        return None
    if geom.geom_type == "Polygon":
        return mapping(MultiPolygon([geom]))
    if geom.geom_type == "MultiPolygon":
        return mapping(geom)
    if geom.geom_type == "GeometryCollection":
        parts = [
            g
            for g in geom.geoms
            if g.geom_type in ("Polygon", "MultiPolygon")
        ]
        if not parts:
            return None
        return _as_multipolygon(unary_union(parts))
    return None


def _layer_id(props: dict[str, Any]) -> int:
    raw = props.get("layer_id") or props.get("LAYER_ID")
    if raw is not None and str(raw).strip() != "":
        return int(raw)
    source = str(props.get("SOURCE") or props.get("source") or "").lower()
    if "coast" in source:
        return 7
    if "surface" in source:
        return 4
    return 1


def load_geojson(path: Path, conn, *, replace: bool) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features") or []
    if not isinstance(features, list):
        raise ValueError(f"{path} must be a FeatureCollection")

    with conn.cursor() as cur:
        if replace:
            cur.execute(f"TRUNCATE {TABLE}")
        inserted = 0
        for index, feature in enumerate(features):
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties") or {}
            geometry = feature.get("geometry")
            if not geometry:
                continue
            try:
                geom = shape(geometry)
            except Exception:
                logger.warning("Skip feature %s: bad geometry", index)
                continue
            multi = _as_multipolygon(geom)
            if multi is None:
                continue
            layer_id = _layer_id(props)
            object_id = int(props.get("OBJECTID") or props.get("object_id") or index + 1)
            source = (
                props.get("SOURCE")
                or props.get("source")
                or SOURCE_FROM_LAYER.get(layer_id)
                or "Unknown"
            )
            probability = props.get("PROB") or props.get("probability") or "M"
            cur.execute(
                f"""
                INSERT INTO {TABLE}
                    (object_id, layer_id, source, probability, scenario,
                     map_type, reference, version, geom)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s,
                     ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                ON CONFLICT (layer_id, object_id) DO UPDATE SET
                    source = EXCLUDED.source,
                    probability = EXCLUDED.probability,
                    scenario = EXCLUDED.scenario,
                    map_type = EXCLUDED.map_type,
                    reference = EXCLUDED.reference,
                    version = EXCLUDED.version,
                    geom = EXCLUDED.geom
                """,
                (
                    object_id,
                    layer_id,
                    str(source),
                    str(probability),
                    props.get("SCENARIO") or props.get("scenario") or "Present Day",
                    props.get("MAP_TYPE") or props.get("map_type"),
                    props.get("REFERENCE") or props.get("reference"),
                    props.get("VERSION") or props.get("version"),
                    json.dumps(multi),
                ),
            )
            inserted += 1
    conn.commit()
    return inserted


def write_local_stamp(input_path: Path, count: int, vintage: str) -> Path:
    stamp_path = input_path.with_suffix(input_path.suffix + ".ingest.json")
    stamp = {
        "layer": "sepa_flood",
        "product": "SEPA Flood Maps v3.0",
        "licence": "OGL-3.0",
        "source_url": "https://www2.sepa.org.uk/flooddata/",
        "mapserver_url": (
            "https://map.sepa.org.uk/server/rest/services/Open/Flood_Maps/MapServer"
        ),
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
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--vintage", default=date.today().isoformat())
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if not args.input.is_file():
        raise SystemExit(
            f"Input not found: {args.input}\n"
            "Download SEPA Flood Maps (OGL) from https://www2.sepa.org.uk/flooddata/ "
            "or export medium river+coastal GeoJSON from the MapServer into "
            "data/external/sepa/ (gitignored)."
        )
    resolved = args.input.resolve()
    if "data/processed" in str(resolved).replace("\\", "/"):
        raise SystemExit(
            "Refuse to read flood geometry from data/processed/. "
            "Keep raw extracts under data/external/ (gitignored)."
        )

    conn = connect()
    try:
        ensure_table(conn)
        count = load_geojson(args.input, conn, replace=args.replace)
    finally:
        conn.close()
    stamp = write_local_stamp(args.input, count, args.vintage)
    logger.info("Loaded %s flood polygons into %s. Stamp: %s", count, TABLE, stamp)


if __name__ == "__main__":
    main()
