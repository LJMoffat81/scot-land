"""Ingest James Hutton Land Capability for Agriculture (1:250k) into PostGIS.

Raw downloads stay under data/external/lca/ (gitignored). This script never
commits geometry — it only loads a local extract into ``lca_agriculture``.

Licence is the James Hutton Institute Open Data Licence (not pure OGL).
Public-sector information in the product is licensed under OGL v2.0 per the
Hutton attribution clause. See data/config/sources.yaml → lca.

Usage:
  export DATABASE_URL=postgresql://...
  python -m etl.ingest_lca \\
    --input ../data/external/lca/LCA_250K.shp \\
    --replace
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
import shapefile
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform as shp_transform

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE = "lca_agriculture"
DEFAULT_INPUT = REPO_ROOT / "data" / "external" / "lca" / "LCA_250K.shp"
SOURCE_EPSG = 27700
TARGET_EPSG = 4326

# Standard LCA classes + Hutton non-agricultural codes used in the 250k product.
CLASS_LABELS: dict[float, str] = {
    1.0: "Class 1 — very wide range of crops",
    2.0: "Class 2 — wide range of crops",
    3.1: "Class 3.1 — moderate range of crops",
    3.2: "Class 3.2 — moderate range of crops",
    4.1: "Class 4.1 — narrow range of crops",
    4.2: "Class 4.2 — narrow range of crops",
    5.1: "Class 5.1 — improved grassland",
    5.2: "Class 5.2 — improved grassland",
    5.3: "Class 5.3 — improved grassland",
    6.1: "Class 6.1 — rough grazing",
    6.2: "Class 6.2 — rough grazing",
    6.3: "Class 6.3 — rough grazing",
    7.0: "Class 7 — very limited agricultural value",
    888.0: "Built-up area",
    999.0: "Inland water",
    9500.0: "Sea / non-agricultural other",
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


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                id SERIAL PRIMARY KEY,
                lccode DOUBLE PRECISION NOT NULL,
                class_label TEXT NOT NULL,
                prime TEXT,
                scale TEXT,
                hectares DOUBLE PRECISION,
                sqmid TEXT,
                geom GEOMETRY(MultiPolygon, 4326) NOT NULL
            );
            """
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_geom "
            f"ON {TABLE} USING GIST (geom);"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_lccode "
            f"ON {TABLE} (lccode);"
        )
    conn.commit()


def class_label(lccode: float) -> str:
    if lccode in CLASS_LABELS:
        return CLASS_LABELS[lccode]
    return f"LCA code {lccode:g}"


def _as_multipolygon(geom) -> MultiPolygon | None:
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    # Dissolve geometry collections / unexpected types into polygons only.
    polys = [g for g in getattr(geom, "geoms", []) if isinstance(g, (Polygon, MultiPolygon))]
    parts: list[Polygon] = []
    for poly in polys:
        if isinstance(poly, MultiPolygon):
            parts.extend(list(poly.geoms))
        else:
            parts.append(poly)
    if not parts:
        return None
    return MultiPolygon(parts)


def load_shapefile(path: Path, conn, replace: bool) -> int:
    """Read BNG shapefile, reproject to WGS84, upsert into PostGIS."""
    reader = shapefile.Reader(str(path))
    field_names = [f[0] for f in reader.fields[1:]]
    transformer = Transformer.from_crs(SOURCE_EPSG, TARGET_EPSG, always_xy=True)

    def _reproject(x, y, z=None):
        lng, lat = transformer.transform(x, y)
        return (lng, lat) if z is None else (lng, lat, z)

    with conn.cursor() as cur:
        if replace:
            cur.execute(f"TRUNCATE TABLE {TABLE} RESTART IDENTITY;")
        inserted = 0
        for shape_rec in reader.iterShapeRecords():
            props = dict(zip(field_names, shape_rec.record))
            try:
                lccode = float(props.get("LCCODE"))
            except (TypeError, ValueError):
                continue
            geom_bng = shape(shape_rec.shape.__geo_interface__)
            geom_wgs = _as_multipolygon(shp_transform(_reproject, geom_bng))
            if geom_wgs is None or not geom_wgs.is_valid:
                if geom_wgs is not None:
                    geom_wgs = _as_multipolygon(geom_wgs.buffer(0))
                if geom_wgs is None:
                    continue
            hectares = props.get("Hectares")
            try:
                hectares_f = float(hectares) if hectares is not None else None
            except (TypeError, ValueError):
                hectares_f = None
            cur.execute(
                f"""
                INSERT INTO {TABLE}
                    (lccode, class_label, prime, scale, hectares, sqmid, geom)
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                );
                """,
                (
                    lccode,
                    class_label(lccode),
                    str(props.get("Prime") or "") or None,
                    str(props.get("Scale") or "") or None,
                    hectares_f,
                    str(props.get("SqMid") or "") or None,
                    json.dumps(mapping(geom_wgs)),
                ),
            )
            inserted += 1
            if inserted % 2000 == 0:
                conn.commit()
                logger.info("… loaded %s features", inserted)
    conn.commit()
    return inserted


def write_local_stamp(input_path: Path, count: int, vintage: str) -> Path:
    stamp_path = input_path.with_suffix(input_path.suffix + ".ingest.json")
    stamp = {
        "layer": TABLE,
        "product": "Land Capability for Agriculture 1:250,000",
        "licence": (
            "James Hutton Institute Open Data Licence "
            "(public-sector information under OGL v2.0)"
        ),
        "source_url": (
            "https://www.hutton.ac.uk/sites/default/files/files/soils/downloads/"
            "Hutton_LCA250K_OpenData.zip"
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
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to LCA_250K.shp under data/external/lca/ (gitignored)",
    )
    parser.add_argument(
        "--vintage",
        default="1:250k national open release",
        help="Dataset vintage recorded in the local stamp",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=f"TRUNCATE {TABLE} before load",
    )
    args = parser.parse_args()
    if not args.input.is_file():
        raise SystemExit(
            f"Input not found: {args.input}\n"
            "Download Hutton_LCA250K_OpenData.zip to data/external/lca/ "
            "(gitignored), unzip, and pass --input. See scripts/data/README-lca.md."
        )
    resolved = args.input.resolve()
    if "data/processed" in str(resolved).replace("\\", "/"):
        raise SystemExit(
            "Refuse to read LCA geometry from data/processed/. "
            "Keep raw extracts under data/external/ (gitignored)."
        )

    conn = connect()
    try:
        ensure_table(conn)
        count = load_shapefile(args.input, conn, replace=args.replace)
    finally:
        conn.close()
    stamp = write_local_stamp(args.input, count, args.vintage)
    logger.info("Loaded %s LCA polygons into %s. Stamp: %s", count, TABLE, stamp)


if __name__ == "__main__":
    main()
