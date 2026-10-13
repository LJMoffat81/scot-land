"""Ingest Crofting Commission Register of Crofts CSVs into PostGIS (OGL-3.0).

Sources (open licence, not Spatial Hub Restricted, not RoS map polygons):
  https://www.crofting.scotland.gov.uk/open-data/
  — List of Parishes, List of Holdings (Crofts), List of Grazings

Individuals CSV is intentionally NOT ingested (names / postal addresses).

Raw downloads default to data/external/crofting/ (gitignored). Never commit them.
Fixtures under data/fixtures/crofting/ are for tests only.

Usage:
  export DATABASE_URL=postgresql://...
  python -m etl.ingest_crofting --from-fixtures
  python -m etl.ingest_crofting --download
  python -m etl.ingest_crofting --input-dir ../data/external/crofting
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import psycopg2
from psycopg2 import extras

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("etl.ingest_crofting")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTERNAL = REPO_ROOT / "data" / "external" / "crofting"
DEFAULT_FIXTURES = REPO_ROOT / "data" / "fixtures" / "crofting"
OPEN_DATA_URL = "https://www.crofting.scotland.gov.uk/open-data/"
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
LICENCE = "OGL-3.0"

DATASETS = ("parishes", "holdings", "grazings")
# Never fetch or load Individuals — personal data out of scope for this portal.
FORBIDDEN = frozenset({"individuals"})


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
    sql_path = REPO_ROOT / "backend" / "db" / "schema" / "013_crofting.sql"
    with conn.cursor() as cur:
        cur.execute(sql_path.read_text(encoding="utf-8"))
    conn.commit()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "scot-land-etl/1.0"})
    with urlopen(req, timeout=120) as response:
        return response.read()


def download_open_data(dest: Path) -> dict[str, Path]:
    """Fetch Parishes / Holdings / Grazings CSVs via the open-data page nonce."""
    dest.mkdir(parents=True, exist_ok=True)
    html = _fetch(OPEN_DATA_URL).decode("utf-8", "replace")
    nonce_match = re.search(
        r"action=roc_generate_csv[^\"']*dataset=parishes[^\"']*nonce=([a-f0-9]+)",
        html,
        re.I,
    )
    if not nonce_match:
        # Fallback: any roc_generate_csv nonce on the page.
        nonce_match = re.search(r"roc_generate_csv[^\"']*nonce=([a-f0-9]+)", html, re.I)
    if not nonce_match:
        raise SystemExit(
            f"Could not find download nonce on {OPEN_DATA_URL}. "
            "Save CSVs manually under data/external/crofting/ and use --input-dir."
        )
    nonce = nonce_match.group(1)
    paths: dict[str, Path] = {}
    for dataset in DATASETS:
        url = (
            "https://www.crofting.scotland.gov.uk/wp-admin/admin-ajax.php"
            f"?action=roc_generate_csv&dataset={dataset}&nonce={nonce}"
        )
        raw = _fetch(url)
        if not raw.startswith(b"ParishID") and not raw.startswith(b"HoldingID") and not raw.startswith(
            b"GrazingID"
        ):
            raise SystemExit(f"Unexpected payload for {dataset}: {raw[:80]!r}")
        path = dest / f"{dataset}.csv"
        path.write_bytes(raw)
        logger.info("Downloaded %s (%s bytes) → %s", dataset, len(raw), path)
        paths[dataset] = path
    return paths


def _f_float(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _f_int(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_parishes(conn, path: Path) -> int:
    rows = _read_csv(path)
    payload = [
        (
            _f_int(r.get("ParishID")),
            (r.get("ParishCode") or "").strip() or None,
            (r.get("ParishName") or "").strip(),
        )
        for r in rows
        if _f_int(r.get("ParishID")) is not None and (r.get("ParishName") or "").strip()
    ]
    with conn.cursor() as cur:
        cur.execute("TRUNCATE croft_parishes CASCADE")
        extras.execute_values(
            cur,
            """
            INSERT INTO croft_parishes (parish_id, parish_code, parish_name)
            VALUES %s
            """,
            payload,
            page_size=500,
        )
    return len(payload)


def load_holdings(conn, path: Path) -> int:
    rows = _read_csv(path)
    payload = []
    for r in rows:
        hid = _f_int(r.get("HoldingID"))
        if hid is None:
            continue
        payload.append(
            (
                hid,
                (r.get("CroftName") or "").strip() or None,
                (r.get("StatusA") or "").strip() or None,
                (r.get("StatusB") or "").strip() or None,
                (r.get("StatusC") or "").strip() or None,
                _f_int(r.get("Croft_Let")),
                (r.get("MainLocationCode") or "").strip() or None,
                (r.get("CroftFileNumber") or "").strip() or None,
                (r.get("RegisterNumber") or "").strip() or None,
                _f_float(r.get("TotalArea")),
                _f_int(r.get("ParishID")),
                (r.get("Parish") or "").strip() or None,
                (r.get("Township") or "").strip() or None,
                (r.get("CroftingRegistrationNumber") or "").strip() or None,
                (r.get("Consent_to_Be_Absent_until") or "").strip() or None,
            )
        )
    with conn.cursor() as cur:
        cur.execute("TRUNCATE croft_holdings")
        extras.execute_values(
            cur,
            """
            INSERT INTO croft_holdings (
                holding_id, croft_name, status_a, status_b, status_c, croft_let,
                main_location_code, croft_file_number, register_number,
                total_area_ha, parish_id, parish_name, township,
                crofting_registration_number, consent_to_be_absent_until
            ) VALUES %s
            """,
            payload,
            page_size=500,
        )
    return len(payload)


def load_grazings(conn, path: Path) -> int:
    rows = _read_csv(path)
    payload = []
    for r in rows:
        gid = _f_int(r.get("GrazingID"))
        if gid is None:
            continue
        payload.append(
            (
                gid,
                (r.get("GrazingName") or "").strip() or None,
                (r.get("Code") or "").strip() or None,
                (r.get("CroftingRegistrationNumber") or "").strip() or None,
                (r.get("AreaName") or "").strip() or None,
                _f_int(r.get("ParishID")),
                (r.get("ParishName") or "").strip() or None,
                _f_float(r.get("CurrentExtent")),
                (r.get("CurrentExtentDate") or "").strip() or None,
                _f_float(r.get("OriginalExtent")),
                (r.get("OriginalExtentDate") or "").strip() or None,
                (r.get("AgriculturalCode") or "").strip() or None,
                (r.get("CommitteeEndDate") or "").strip() or None,
            )
        )
    with conn.cursor() as cur:
        cur.execute("TRUNCATE common_grazings")
        extras.execute_values(
            cur,
            """
            INSERT INTO common_grazings (
                grazing_id, grazing_name, code, crofting_registration_number,
                area_name, parish_id, parish_name, current_extent_ha,
                current_extent_date, original_extent_ha, original_extent_date,
                agricultural_code, committee_end_date
            ) VALUES %s
            """,
            payload,
            page_size=500,
        )
    return len(payload)


def record_meta(conn, dataset: str, path: Path, row_count: int) -> None:
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO crofting_ingest_meta
                (dataset, source_url, licence, retrieved_at, row_count, sha256)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (dataset) DO UPDATE SET
                source_url = EXCLUDED.source_url,
                licence = EXCLUDED.licence,
                retrieved_at = EXCLUDED.retrieved_at,
                row_count = EXCLUDED.row_count,
                sha256 = EXCLUDED.sha256
            """,
            (dataset, OPEN_DATA_URL, LICENCE, now, row_count, _sha256(path)),
        )


def resolve_paths(args: argparse.Namespace) -> dict[str, Path]:
    if args.from_fixtures:
        root = Path(args.input_dir) if args.input_dir else DEFAULT_FIXTURES
    elif args.download:
        root = Path(args.input_dir) if args.input_dir else DEFAULT_EXTERNAL
        return download_open_data(root)
    else:
        root = Path(args.input_dir) if args.input_dir else DEFAULT_EXTERNAL
    paths = {}
    for dataset in DATASETS:
        path = root / f"{dataset}.csv"
        if not path.is_file():
            raise SystemExit(
                f"Missing {path}. Use --download, --from-fixtures, or place CSVs "
                "under data/external/crofting/ (gitignored)."
            )
        paths[dataset] = path
    return paths


def run(args: argparse.Namespace) -> int:
    for name in FORBIDDEN:
        if name in (args.datasets or []):
            raise SystemExit(f"Refusing to ingest {name} (personal data).")
    paths = resolve_paths(args)
    datasets = args.datasets or list(DATASETS)
    conn = connect()
    try:
        ensure_tables(conn)
        # Parishes first (FK parents).
        order = [d for d in ("parishes", "holdings", "grazings") if d in datasets]
        counts: dict[str, int] = {}
        for dataset in order:
            path = paths[dataset]
            if dataset == "parishes":
                n = load_parishes(conn, path)
            elif dataset == "holdings":
                n = load_holdings(conn, path)
            else:
                n = load_grazings(conn, path)
            record_meta(conn, dataset, path, n)
            counts[dataset] = n
            logger.info("Loaded %s: %s rows", dataset, n)
        conn.commit()
    finally:
        conn.close()
    print(
        "OK crofting ingest:",
        ", ".join(f"{k}={v}" for k, v in counts.items()),
        f"licence={LICENCE}",
        f"ogl={OGL_URL}",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--download",
        action="store_true",
        help="Fetch OGL CSVs from Crofting Commission open-data into input dir",
    )
    parser.add_argument(
        "--from-fixtures",
        action="store_true",
        help="Load data/fixtures/crofting/*.csv (tests / CI smoke)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Directory containing parishes.csv, holdings.csv, grazings.csv",
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=list(DATASETS),
        default=None,
        help="Subset to load (default: all three)",
    )
    args = parser.parse_args(argv)
    if args.download and args.from_fixtures:
        parser.error("Use only one of --download or --from-fixtures")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
