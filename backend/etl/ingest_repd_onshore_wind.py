"""Ingest DESNZ REPD onshore wind (Scotland) into PostGIS ``repd_onshore_wind``.

Natural capital P1 — MW and development status only. No £ rent figures.
Downloads the OGL quarterly CSV (or reads ``--csv``). Does not write under
``data/external`` in the repo.

  python -m etl.ingest_repd_onshore_wind
  python -m etl.ingest_repd_onshore_wind --csv /path/to/REPD.csv --replace
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
TABLE = "repd_onshore_wind"
DEFAULT_CSV_URL = (
    "https://assets.publishing.service.gov.uk/media/"
    "6a6cbdc00c36759b5ccaa305/REPD_Publication_Q2_2026.csv"
)

# REPD technology labels for onshore wind (case-insensitive exact match after strip).
ONSHORE_WIND_TECHNOLOGIES = frozenset({"wind onshore", "onshore wind"})

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
    return (sources.get("repd_onshore_wind") or {}).get("csv_url") or DEFAULT_CSV_URL


def _ensure_table(conn) -> None:
    sql_path = (
        REPO_ROOT / "backend" / "db" / "schema" / "020_nc_repd_onshore_wind.sql"
    )
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


def _is_onshore_wind(technology: str) -> bool:
    return technology.strip().lower() in ONSHORE_WIND_TECHNOLOGIES


def classify_row(
    *,
    technology: str,
    capacity_mw: float | None,
    status: str | None,
    status_short: str | None,
) -> tuple[str, str]:
    """Return (value_tier, publication_status) for natural-capital evidence.

    Official DESNZ register facts are ``market``. Rows with neither capacity
    nor any status text are ``blocked`` (too thin to publish as site evidence).
    Unclear technology is refused before this helper is called.
    """
    has_status = bool((status_short or "").strip() or (status or "").strip())
    if capacity_mw is None and not has_status:
        return "market", "blocked"
    if not _is_onshore_wind(technology):
        return "market", "blocked"
    return "market", "ok"


def scotland_onshore_wind_rows(path: Path) -> list[dict[str, Any]]:
    """Parse REPD CSV → Scotland onshore-wind rows (synthetic-safe, no network)."""
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="cp1252") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            country = (raw.get("Country") or "").strip().lower()
            if country != "scotland":
                continue
            technology = (raw.get("Technology Type") or "").strip()
            if not _is_onshore_wind(technology):
                continue
            ref = (raw.get("Ref ID") or "").strip()
            x = _parse_float(raw.get("X-coordinate"))
            y = _parse_float(raw.get("Y-coordinate"))
            if not ref or x is None or y is None:
                continue
            lng, lat = _TO_WGS84.transform(x, y)
            if not (54.4 <= lat <= 61.0 and -9.0 <= lng <= 0.2):
                continue
            capacity = _parse_float(raw.get("Installed Capacity (MWelec)"))
            status = (raw.get("Development Status") or "").strip() or None
            status_short = (
                raw.get("Development Status (short)") or ""
            ).strip() or None
            value_tier, publication_status = classify_row(
                technology=technology,
                capacity_mw=capacity,
                status=status,
                status_short=status_short,
            )
            rows.append(
                {
                    "ref_id": ref,
                    "site_name": (raw.get("Site Name") or "").strip() or None,
                    "operator_name": (
                        raw.get("Operator (or Applicant)") or ""
                    ).strip()
                    or None,
                    "technology_type": technology,
                    "development_status": status,
                    "development_status_short": status_short,
                    "installed_capacity_mw": capacity,
                    "country": "Scotland",
                    "region": (raw.get("Region") or "").strip() or None,
                    "postcode": (raw.get("Post Code") or "").strip() or None,
                    "planning_authority": (
                        raw.get("Planning Authority") or ""
                    ).strip()
                    or None,
                    "value_tier": value_tier,
                    "publication_status": publication_status,
                    "publish_level": "public_site",
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
        fd, name = tempfile.mkstemp(prefix="repd_ow_", suffix=".csv")
        os.close(fd)
        tmp = Path(name)
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            tmp.write_bytes(response.content)
        csv_path = tmp

    rows = scotland_onshore_wind_rows(csv_path)
    publishable = [r for r in rows if r["publication_status"] == "ok"]
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
                  planning_authority, value_tier, publication_status,
                  publish_level, geom, retrieved_at
                ) VALUES (
                  %(ref_id)s, %(site_name)s, %(operator_name)s, %(technology_type)s,
                  %(development_status)s, %(development_status_short)s,
                  %(installed_capacity_mw)s, %(country)s, %(region)s, %(postcode)s,
                  %(planning_authority)s, %(value_tier)s, %(publication_status)s,
                  %(publish_level)s,
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
                  value_tier = EXCLUDED.value_tier,
                  publication_status = EXCLUDED.publication_status,
                  publish_level = EXCLUDED.publish_level,
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
        "publishable_ok": len(publishable),
        "blocked": len(rows) - len(publishable),
        "technology": "Wind Onshore",
        "country": "Scotland",
        "value_tier": "market",
        "adds_to_surface_rent": False,
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
