"""Ingest NRS Census 2022 Settlements and Localities into PostGIS.

Open Government Licence. Preferred path: pull GeoJSON from the published
maps.gov.scot MapServer query (no raw commit). Optional local files under
data/external/nrs/ (gitignored) for offline reloads.

Usage:
  export DATABASE_URL=postgresql://...
  python -m etl.ingest_nrs_settlements --fetch
  # or
  python -m etl.ingest_nrs_settlements \\
    --settlements ../data/external/nrs/settlements_2022.geojson \\
    --localities ../data/external/nrs/localities_2022.geojson
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

from georgist.db import connect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / "data" / "external" / "nrs"

# Published NRS Census 2022 MapServer (OGL). Layer 8 = Settlements, 6 = Localities.
MAPSERVER = (
    "https://maps.gov.scot/server/rest/services/NRS/Census2022/MapServer"
)
LAYERS = {
    "settlements": {
        "table": "nrs_settlements",
        "layer_id": 8,
        "wfs_type": "CEN2022:Settlement2022",
    },
    "localities": {
        "table": "nrs_localities",
        "layer_id": 6,
        "wfs_type": "CEN2022:Locality2022",
    },
}


def ensure_tables(conn) -> None:
    sql_path = REPO_ROOT / "backend" / "db" / "schema" / "015_nrs_settlements_localities.sql"
    with conn.cursor() as cur:
        cur.execute(sql_path.read_text(encoding="utf-8"))
    conn.commit()


def fetch_layer_geojson(layer_id: int) -> dict[str, Any]:
    """Page through MapServer query → GeoJSON (WGS84)."""
    features: list[dict[str, Any]] = []
    offset = 0
    page = 500
    with httpx.Client(timeout=60.0) as client:
        while True:
            params = {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": str(offset),
                "resultRecordCount": str(page),
            }
            url = f"{MAPSERVER}/{layer_id}/query"
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("features") or []
            features.extend(batch)
            if len(batch) < page or payload.get("exceededTransferLimit") is not True:
                if len(batch) < page:
                    break
                # Some servers omit exceededTransferLimit; stop when a short page returns.
                if not batch:
                    break
            offset += len(batch)
            if offset > 50_000:
                raise RuntimeError(f"Unexpectedly large layer {layer_id}")
    return {"type": "FeatureCollection", "features": features}


def _props(feature: dict[str, Any]) -> dict[str, Any]:
    return dict(feature.get("properties") or {})


def load_collection(conn, table: str, payload: dict[str, Any], replace: bool) -> int:
    if payload.get("type") != "FeatureCollection":
        raise SystemExit(f"{table}: input must be a GeoJSON FeatureCollection")
    features = payload.get("features") or []
    with conn.cursor() as cur:
        if replace:
            cur.execute(f"TRUNCATE TABLE {table};")
        inserted = 0
        for feature in features:
            geometry = feature.get("geometry")
            if not geometry:
                continue
            props = _props(feature)
            code = str(props.get("code") or "").strip()
            name = str(props.get("name") or "").strip()
            if not code or not name:
                continue
            pop = props.get("Popcount")
            if pop is None:
                pop = props.get("popcount")
            area = props.get("st_area_shape_")
            if area is None:
                area = props.get("area_m2")
            cur.execute(
                f"""
                INSERT INTO {table} (code, name, popcount, area_m2, geom)
                VALUES (
                    %s, %s, %s, %s,
                    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                )
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    popcount = EXCLUDED.popcount,
                    area_m2 = EXCLUDED.area_m2,
                    geom = EXCLUDED.geom;
                """,
                (
                    code,
                    name,
                    int(pop) if pop is not None else None,
                    float(area) if area is not None else None,
                    json.dumps(geometry),
                ),
            )
            inserted += 1
    conn.commit()
    return inserted


def write_stamp(path: Path, kind: str, count: int) -> None:
    stamp = {
        "layer": kind,
        "product": LAYERS[kind]["wfs_type"],
        "licence": "OGL-3.0",
        "attribution": (
            "Contains National Records of Scotland data © Crown copyright "
            "and database right. Contains Ordnance Survey data © Crown "
            "copyright and database right."
        ),
        "source_url": MAPSERVER,
        "row_count": count,
        "vintage": "Census 2022",
        "ingested_on": date.today().isoformat(),
        "note": "Local stamp only — raw geometry stays out of git (data/external/).",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Download GeoJSON from the published NRS Census2022 MapServer",
    )
    parser.add_argument(
        "--settlements",
        type=Path,
        default=None,
        help="Local settlements GeoJSON under data/external/ (gitignored)",
    )
    parser.add_argument(
        "--localities",
        type=Path,
        default=None,
        help="Local localities GeoJSON under data/external/ (gitignored)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="TRUNCATE each table before load",
    )
    parser.add_argument(
        "--save-fetch",
        action="store_true",
        help="When --fetch, also write GeoJSON under data/external/nrs/ (gitignored)",
    )
    args = parser.parse_args()

    if not args.fetch and not args.settlements and not args.localities:
        raise SystemExit("Pass --fetch and/or --settlements / --localities paths.")

    for path in (args.settlements, args.localities):
        if path is None:
            continue
        resolved = path.resolve()
        if "data/processed" in str(resolved).replace("\\", "/"):
            raise SystemExit(
                "Refuse to read NRS geometry from data/processed/. "
                "Keep extracts under data/external/ (gitignored)."
            )

    if not (os.getenv("DATABASE_URL") or "").strip() and not (
        os.getenv("PGHOST", "").strip() and os.getenv("PGDATABASE", "").strip()
    ):
        raise SystemExit("Set DATABASE_URL or PGHOST+PGDATABASE before ingest.")

    conn = connect()
    try:
        ensure_tables(conn)
        counts: dict[str, int] = {}
        for kind, spec in LAYERS.items():
            local_path = args.settlements if kind == "settlements" else args.localities
            if args.fetch:
                logger.info("Fetching %s (layer %s)…", kind, spec["layer_id"])
                payload = fetch_layer_geojson(spec["layer_id"])
                if args.save_fetch:
                    out = DEFAULT_DIR / f"{kind}_2022.geojson"
                    DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
                    out.write_text(json.dumps(payload), encoding="utf-8")
                    logger.info("Wrote %s", out)
            elif local_path is not None:
                if not local_path.is_file():
                    raise SystemExit(f"Input not found: {local_path}")
                payload = json.loads(local_path.read_text(encoding="utf-8"))
            else:
                continue
            count = load_collection(conn, spec["table"], payload, replace=args.replace)
            counts[kind] = count
            write_stamp(DEFAULT_DIR / f"{kind}_2022.ingest.json", kind, count)
            logger.info("Loaded %s rows into %s", count, spec["table"])
    finally:
        conn.close()
    logger.info("Done: %s", counts)


if __name__ == "__main__":
    main()
