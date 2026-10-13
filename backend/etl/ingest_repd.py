"""Ingest DESNZ REPD (Scotland) into PostGIS `repd_sites`.

Downloads the OGL quarterly CSV (or reads a local path). Does not write under
data/external in the repo — pass --csv for a local file or let the tool fetch
to a temp path.

  python -m etl.ingest_repd
  python -m etl.ingest_repd --csv /path/to/REPD.csv --replace
"""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import psycopg2
import yaml
from psycopg2.extras import execute_batch
from pyproj import Transformer

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
TABLE = "repd_sites"
DEFAULT_CSV_URL = (
    "https://assets.publishing.service.gov.uk/media/"
    "6a6cbdc00c36759b5ccaa305/REPD_Publication_Q2_2026.csv"
)

_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


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


def _csv_url() -> str:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    return (sources.get("repd") or {}).get("csv_url") or DEFAULT_CSV_URL


def _ensure_table(conn) -> None:
    sql_path = REPO_ROOT / "backend" / "db" / "schema" / "017_open_energy_leases.sql"
    with conn.cursor() as cur:
        cur.execute(sql_path.read_text(encoding="utf-8"))
    conn.commit()


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _scotland_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="cp1252") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            country = (raw.get("Country") or "").strip().lower()
            if country != "scotland":
                continue
            ref = (raw.get("Ref ID") or "").strip()
            x = _parse_float(raw.get("X-coordinate"))
            y = _parse_float(raw.get("Y-coordinate"))
            if not ref or x is None or y is None:
                continue
            lng, lat = _TO_WGS84.transform(x, y)
            if not (54.4 <= lat <= 61.0 and -9.0 <= lng <= 0.2):
                continue
            rows.append(
                {
                    "ref_id": ref,
                    "site_name": (raw.get("Site Name") or "").strip() or None,
                    "operator_name": (raw.get("Operator (or Applicant)") or "").strip()
                    or None,
                    "technology_type": (raw.get("Technology Type") or "").strip() or None,
                    "development_status": (raw.get("Development Status") or "").strip()
                    or None,
                    "development_status_short": (
                        raw.get("Development Status (short)") or ""
                    ).strip()
                    or None,
                    "installed_capacity_mw": _parse_float(
                        raw.get("Installed Capacity (MWelec)")
                    ),
                    "country": "Scotland",
                    "region": (raw.get("Region") or "").strip() or None,
                    "postcode": (raw.get("Post Code") or "").strip() or None,
                    "planning_authority": (raw.get("Planning Authority") or "").strip()
                    or None,
                    "lng": lng,
                    "lat": lat,
                }
            )
    return rows


def ingest(csv_path: Path | None = None, *, replace: bool = True) -> dict[str, Any]:
    retrieved = date.today()
    tmp: Path | None = None
    if csv_path is None:
        url = _csv_url()
        fd, name = tempfile.mkstemp(prefix="repd_", suffix=".csv")
        os.close(fd)
        tmp = Path(name)
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            tmp.write_bytes(response.content)
        csv_path = tmp

    rows = _scotland_rows(csv_path)
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
                  ref_id, site_name, operator_name, technology_type,
                  development_status, development_status_short,
                  installed_capacity_mw, country, region, postcode,
                  planning_authority, geom, retrieved_at
                ) VALUES (
                  %(ref_id)s, %(site_name)s, %(operator_name)s, %(technology_type)s,
                  %(development_status)s, %(development_status_short)s,
                  %(installed_capacity_mw)s, %(country)s, %(region)s, %(postcode)s,
                  %(planning_authority)s,
                  ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326),
                  %(retrieved_at)s
                )
                ON CONFLICT (ref_id) DO UPDATE SET
                  site_name = EXCLUDED.site_name,
                  operator_name = EXCLUDED.operator_name,
                  technology_type = EXCLUDED.technology_type,
                  development_status = EXCLUDED.development_status,
                  development_status_short = EXCLUDED.development_status_short,
                  installed_capacity_mw = EXCLUDED.installed_capacity_mw,
                  region = EXCLUDED.region,
                  postcode = EXCLUDED.postcode,
                  planning_authority = EXCLUDED.planning_authority,
                  geom = EXCLUDED.geom,
                  retrieved_at = EXCLUDED.retrieved_at
                """,
                [{**row, "retrieved_at": retrieved} for row in rows],
                page_size=500,
            )
        conn.commit()
    finally:
        conn.close()
        if tmp is not None:
            tmp.unlink(missing_ok=True)

    return {
        "table": TABLE,
        "rows": len(rows),
        "country": "Scotland",
        "retrieved_at": retrieved.isoformat(),
        "licence": "OGL-3.0",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=None, help="Local REPD CSV path")
    parser.add_argument(
        "--replace",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="TRUNCATE before load (default: true)",
    )
    args = parser.parse_args()
    result = ingest(args.csv, replace=args.replace)
    print(result)


if __name__ == "__main__":
    main()
