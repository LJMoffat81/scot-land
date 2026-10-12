"""Ingest SEPA CAR licences from a public-register CSV export into PostGIS.

Download-only: operators export CSV from the SEPA public register
(https://search-the-register.sepa.org.uk/). This tool never scrapes MapServer
or viewer endpoints. Rows without a parseable NGR load with NULL geometry.

  python -m etl.ingest_sepa_car --csv /path/to/sepa_car_export.csv --replace
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import execute_batch
from pyproj import Transformer

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE = "sepa_car_licences"
SCHEMA_SQL = REPO_ROOT / "backend" / "db" / "schema" / "006_hydro_sepa_car.sql"

_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)

# OSGB 100km grid letters → SW corner metres (easting, northing of square).
_GRID_SQ = {
    "HL": (0, 1_200_000),
    "HM": (100_000, 1_200_000),
    "HN": (200_000, 1_200_000),
    "HO": (300_000, 1_200_000),
    "HP": (400_000, 1_200_000),
    "JL": (500_000, 1_200_000),
    "JM": (600_000, 1_200_000),
    "HQ": (0, 1_100_000),
    "HR": (100_000, 1_100_000),
    "HS": (200_000, 1_100_000),
    "HT": (300_000, 1_100_000),
    "HU": (400_000, 1_100_000),
    "JQ": (500_000, 1_100_000),
    "JR": (600_000, 1_100_000),
    "HV": (0, 1_000_000),
    "HW": (100_000, 1_000_000),
    "HX": (200_000, 1_000_000),
    "HY": (300_000, 1_000_000),
    "HZ": (400_000, 1_000_000),
    "JV": (500_000, 1_000_000),
    "JW": (600_000, 1_000_000),
    "NA": (0, 900_000),
    "NB": (100_000, 900_000),
    "NC": (200_000, 900_000),
    "ND": (300_000, 900_000),
    "NE": (400_000, 900_000),
    "OA": (500_000, 900_000),
    "OB": (600_000, 900_000),
    "NF": (0, 800_000),
    "NG": (100_000, 800_000),
    "NH": (200_000, 800_000),
    "NJ": (300_000, 800_000),
    "NK": (400_000, 800_000),
    "OF": (500_000, 800_000),
    "OG": (600_000, 800_000),
    "NL": (0, 700_000),
    "NM": (100_000, 700_000),
    "NN": (200_000, 700_000),
    "NO": (300_000, 700_000),
    "NP": (400_000, 700_000),
    "OL": (500_000, 700_000),
    "OM": (600_000, 700_000),
    "NQ": (0, 600_000),
    "NR": (100_000, 600_000),
    "NS": (200_000, 600_000),
    "NT": (300_000, 600_000),
    "NU": (400_000, 600_000),
    "OQ": (500_000, 600_000),
    "OR": (600_000, 600_000),
    "NV": (0, 500_000),
    "NW": (100_000, 500_000),
    "NX": (200_000, 500_000),
    "NY": (300_000, 500_000),
    "NZ": (400_000, 500_000),
    "OV": (500_000, 500_000),
    "OW": (600_000, 500_000),
    "SA": (0, 400_000),
    "SB": (100_000, 400_000),
    "SC": (200_000, 400_000),
    "SD": (300_000, 400_000),
    "SE": (400_000, 400_000),
    "TA": (500_000, 400_000),
    "TB": (600_000, 400_000),
    "SF": (0, 300_000),
    "SG": (100_000, 300_000),
    "SH": (200_000, 300_000),
    "SJ": (300_000, 300_000),
    "SK": (400_000, 300_000),
    "TF": (500_000, 300_000),
    "TG": (600_000, 300_000),
}

_NGR_RE = re.compile(
    r"^\s*([A-Z]{2})\s*(\d{2,5})\s+(\d{2,5})\s*$",
    re.IGNORECASE,
)


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


def _ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()


def ngr_to_wgs84(ngr: str | None) -> tuple[float, float] | None:
    """Parse a compact OSGB NGR (e.g. 'NS 95844 21321') to WGS84 lng/lat."""
    if not ngr:
        return None
    match = _NGR_RE.match(ngr.strip().upper().replace(",", " "))
    if not match:
        return None
    letters, east_s, north_s = match.group(1), match.group(2), match.group(3)
    if len(east_s) != len(north_s):
        return None
    origin = _GRID_SQ.get(letters)
    if origin is None:
        return None
    digits = len(east_s)
    scale = 10 ** (5 - digits)
    easting = origin[0] + int(east_s) * scale
    northing = origin[1] + int(north_s) * scale
    lng, lat = _TO_WGS84.transform(easting, northing)
    if not (54.4 <= lat <= 61.0 and -9.0 <= lng <= 0.2):
        return None
    return lng, lat


def _field(row: dict[str, str], *names: str) -> str:
    lower = {k.lower().strip(): v for k, v in row.items() if k}
    for name in names:
        value = lower.get(name.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _is_car_row(level: str, auth_no: str, regulatory_area: str) -> bool:
    blob = f"{level} {auth_no} {regulatory_area}".upper()
    return "CAR" in blob or regulatory_area.lower() == "water"


def parse_car_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            auth_no = _field(
                raw, "Authorisation number", "authorisation_no", "Authorisation Number"
            )
            if not auth_no:
                continue
            level = _field(
                raw, "Authorisation level", "authorisation_level", "Authorisation Level"
            )
            area = _field(raw, "Regulatory area", "regulatory_area", "Regulatory Area")
            if not _is_car_row(level, auth_no, area):
                continue
            ngr = _field(raw, "NGR", "representative_ngr", "Representative NGR")
            coords = ngr_to_wgs84(ngr)
            rows.append(
                {
                    "authorisation_no": auth_no,
                    "authorisation_holder": _field(
                        raw, "Authorisation holder", "authorisation_holder"
                    )
                    or None,
                    "authorisation_location": _field(
                        raw, "Authorisation location", "authorisation_location"
                    )
                    or None,
                    "authorisation_level": level or None,
                    "authorisation_status": _field(
                        raw, "Authorisation status", "authorisation_status"
                    )
                    or None,
                    "regulatory_area": area or None,
                    "authorisation_activity": _field(
                        raw, "Authorisation activity", "authorisation_activity"
                    )
                    or None,
                    "ngr": ngr or None,
                    "lng": coords[0] if coords else None,
                    "lat": coords[1] if coords else None,
                }
            )
    return rows


def ingest(csv_path: Path, *, replace: bool = True) -> dict[str, Any]:
    retrieved = date.today()
    rows = parse_car_csv(csv_path)
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
                  authorisation_no, authorisation_holder, authorisation_location,
                  authorisation_level, authorisation_status, regulatory_area,
                  authorisation_activity, ngr, geom, retrieved_at
                ) VALUES (
                  %(authorisation_no)s, %(authorisation_holder)s,
                  %(authorisation_location)s, %(authorisation_level)s,
                  %(authorisation_status)s, %(regulatory_area)s,
                  %(authorisation_activity)s, %(ngr)s,
                  CASE
                    WHEN %(lng)s IS NULL THEN NULL
                    ELSE ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)
                  END,
                  %(retrieved_at)s
                )
                ON CONFLICT (authorisation_no) DO UPDATE SET
                  authorisation_holder = EXCLUDED.authorisation_holder,
                  authorisation_location = EXCLUDED.authorisation_location,
                  authorisation_level = EXCLUDED.authorisation_level,
                  authorisation_status = EXCLUDED.authorisation_status,
                  regulatory_area = EXCLUDED.regulatory_area,
                  authorisation_activity = EXCLUDED.authorisation_activity,
                  ngr = EXCLUDED.ngr,
                  geom = EXCLUDED.geom,
                  retrieved_at = EXCLUDED.retrieved_at
                """,
                [{**row, "retrieved_at": retrieved} for row in rows],
                page_size=500,
            )
        conn.commit()
    finally:
        conn.close()

    with_geom = sum(1 for row in rows if row["lng"] is not None)
    return {
        "table": TABLE,
        "rows": len(rows),
        "rows_with_geometry": with_geom,
        "retrieved_at": retrieved.isoformat(),
        "licence": "OGL-3.0",
        "value_tier": "proxy",
        "commons_class": "extractive",
        "publication_status": "download_only",
        "note": "CSV export from SEPA public register only — no MapServer scrape",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Local CSV exported from the SEPA public register",
    )
    parser.add_argument(
        "--replace",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="TRUNCATE before load (default: true)",
    )
    args = parser.parse_args()
    if not args.csv.is_file():
        raise SystemExit(f"CSV not found: {args.csv}")
    print(ingest(args.csv, replace=args.replace))


if __name__ == "__main__":
    main()
