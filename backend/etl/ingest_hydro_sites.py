"""Ingest SEPA Hydropower Sites (OGL ATOM shapefile) into PostGIS `hydro_sites`.

Downloads the WGS84 shapefile zip from the SEPA ATOM feed (or reads a local
zip/dir). Does not write under data/external — uses a temp path unless --input
is given.

  python -m etl.ingest_hydro_sites
  python -m etl.ingest_hydro_sites --input /path/to/SEPA_Hydropower_SITES_WGS84_shp.zip
"""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import psycopg2
import shapefile
import yaml
from psycopg2.extras import execute_batch

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
TABLE = "hydro_sites"
DEFAULT_ZIP_URL = (
    "https://map.sepa.org.uk/atom/Data/SEPA_Hydropower_SITES_WGS84_shp.zip"
)
SCHEMA_SQL = REPO_ROOT / "backend" / "db" / "schema" / "006_hydro_sepa_car.sql"


def _db_connect():
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


def _zip_url() -> str:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    hydro = sources.get("hydro_sites") or {}
    return hydro.get("shapefile_wgs84_url") or DEFAULT_ZIP_URL


def _ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()


def _extract_shapefile(zip_or_dir: Path, work: Path) -> Path:
    if zip_or_dir.is_dir():
        matches = list(zip_or_dir.glob("*.shp"))
        if not matches:
            raise FileNotFoundError(f"No .shp under {zip_or_dir}")
        return matches[0]
    with zipfile.ZipFile(zip_or_dir) as zf:
        zf.extractall(work)
    matches = list(work.rglob("*.shp"))
    if not matches:
        raise FileNotFoundError(f"No .shp inside {zip_or_dir}")
    return matches[0]


def _parse_rows(shp_path: Path) -> list[dict[str, Any]]:
    reader = shapefile.Reader(str(shp_path))
    field_names = [field[0] for field in reader.fields[1:]]
    rows: list[dict[str, Any]] = []
    for record, shape in zip(reader.iterRecords(), reader.iterShapes()):
        props = dict(zip(field_names, record))
        lic = str(props.get("LIC_NO") or "").strip()
        points = shape.points or []
        if not lic or not points:
            continue
        lng, lat = float(points[0][0]), float(points[0][1])
        if not (54.4 <= lat <= 61.0 and -9.0 <= lng <= 0.2):
            continue
        start = props.get("LIC_STA_DA")
        rows.append(
            {
                "lic_no": lic,
                "auth_id": props.get("AUTH_ID"),
                "site_name": (str(props.get("SITE_NAME") or "").strip() or None),
                "licence_start_date": start.isoformat()
                if hasattr(start, "isoformat")
                else None,
                "lng": lng,
                "lat": lat,
            }
        )
    return rows


def ingest(input_path: Path | None = None, *, replace: bool = True) -> dict[str, Any]:
    retrieved = date.today()
    tmp_root = Path(tempfile.mkdtemp(prefix="hydro_sites_"))
    rows: list[dict[str, Any]] = []
    try:
        if input_path is None:
            zip_path = tmp_root / "hydro_wgs84.zip"
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                response = client.get(_zip_url())
                response.raise_for_status()
                zip_path.write_bytes(response.content)
            source = zip_path
        else:
            source = input_path

        work = tmp_root / "shp"
        work.mkdir()
        shp = _extract_shapefile(source, work)
        rows = _parse_rows(shp)

        conn = _db_connect()
        try:
            _ensure_table(conn)
            with conn.cursor() as cur:
                if replace:
                    cur.execute(f"TRUNCATE {TABLE}")
                execute_batch(
                    cur,
                    f"""
                    INSERT INTO {TABLE} (
                      lic_no, auth_id, site_name, licence_start_date,
                      geom, retrieved_at
                    ) VALUES (
                      %(lic_no)s, %(auth_id)s, %(site_name)s, %(licence_start_date)s,
                      ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326),
                      %(retrieved_at)s
                    )
                    ON CONFLICT (lic_no) DO UPDATE SET
                      auth_id = EXCLUDED.auth_id,
                      site_name = EXCLUDED.site_name,
                      licence_start_date = EXCLUDED.licence_start_date,
                      geom = EXCLUDED.geom,
                      retrieved_at = EXCLUDED.retrieved_at
                    """,
                    [{**row, "retrieved_at": retrieved} for row in rows],
                    page_size=200,
                )
            conn.commit()
        finally:
            conn.close()
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return {
        "table": TABLE,
        "rows": len(rows),
        "retrieved_at": retrieved.isoformat(),
        "licence": "OGL-3.0",
        "value_tier": "proxy",
        "commons_class": "extractive",
        "publication_status": "ok",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Local WGS84 shapefile zip or extracted directory",
    )
    parser.add_argument(
        "--replace",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="TRUNCATE before load (default: true)",
    )
    args = parser.parse_args()
    print(ingest(args.input, replace=args.replace))


if __name__ == "__main__":
    main()
