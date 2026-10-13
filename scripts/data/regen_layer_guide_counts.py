#!/usr/bin/env python3
"""Regenerate flood / woodland row counts in docs/mintlify/map-layer-guide.mdx.

Prefer live PostGIS counts (DATABASE_URL / WEALTH_DB_*). When a table is empty
or unreachable, fall back to NatureScot WFS numberMatched for woodland and to
the documented #57 baseline for SEPA flood (47,093 river + 16 coastal).

Usage (repo root or anywhere):

  python scripts/data/regen_layer_guide_counts.py
  python scripts/data/regen_layer_guide_counts.py --dry-run

No rent £ figures. Does not download SEPA FileGDBs.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE = REPO_ROOT / "docs" / "mintlify" / "map-layer-guide.mdx"

# #57 / release baseline (accept re-runs within ~0.1%)
FLOOD_BASELINE = {"river": 47_093, "coastal": 16}
NFI_BASELINE = 207_640
NWSS_BASELINE = 95_814

WFS_URL = "https://ogc.nature.scot/geoserver/scottishforestry/ows"
WFS_TYPES = {
    "nfi": "scottishforestry:National_Forest_Inventory_Woodland_Scotland",
    "native_woodland": "scottishforestry:Native_Woodland_Survey_of_Scotland",
}


def _connect():
    try:
        import psycopg2
    except ImportError:
        return None
    url = (os.getenv("DATABASE_URL") or "").strip()
    try:
        if url:
            return psycopg2.connect(url)
        return psycopg2.connect(
            dbname=os.getenv("WEALTH_DB_NAME", "scotland_wealth"),
            user=os.getenv("WEALTH_DB_USER", "wealth_user"),
            password=os.getenv("WEALTH_DB_PASSWORD", ""),
            host=os.getenv("WEALTH_DB_HOST", "localhost"),
            port=os.getenv("WEALTH_DB_PORT", "5432"),
        )
    except Exception as exc:
        print(f"PostGIS unavailable ({exc}); using fallbacks", file=sys.stderr)
        return None


def _table_count(conn, table: str, where: str | None = None) -> int | None:
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (f"public.{table}",),
            )
            if not cur.fetchone()[0]:
                return None
            cur.execute(sql)
            return int(cur.fetchone()[0])
    except Exception:
        conn.rollback()
        return None


def flood_counts(conn) -> tuple[int, int, str]:
    if conn is not None:
        river = _table_count(conn, "sepa_flood", "layer_id = 1")
        coastal = _table_count(conn, "sepa_flood", "layer_id = 7")
        if river is not None and coastal is not None and (river + coastal) > 0:
            return river, coastal, "postgis"
    return FLOOD_BASELINE["river"], FLOOD_BASELINE["coastal"], "baseline-#57"


def wfs_hits(type_name: str) -> int | None:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": type_name,
        "outputFormat": "application/json",
        "count": "1",
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(WFS_URL, params=params)
            response.raise_for_status()
            matched = response.json().get("numberMatched")
            if matched in (None, "unknown"):
                return None
            return int(matched)
    except Exception as exc:
        print(f"WFS hit failed for {type_name}: {exc}", file=sys.stderr)
        return None


def woodland_count(conn, table: str, layer: str, baseline: int) -> tuple[int, str]:
    if conn is not None:
        n = _table_count(conn, table)
        if n is not None and n > 0:
            return n, "postgis"
    hits = wfs_hits(WFS_TYPES[layer])
    if hits is not None:
        return hits, "wfs-numberMatched"
    return baseline, "baseline-#57"


def format_int(n: int) -> str:
    return f"{n:,}"


def patch_guide(text: str, *, river: int, coastal: int, nfi: int, nwss: int) -> str:
    flood_cell = f"{format_int(river)} river + {format_int(coastal)} coastal"
    text = re.sub(
        r"(\| SEPA flood extent \(medium likelihood\) \| `/layers/open/flood` \|[^|]+\|[^|]+\| )([^|]+)( \|)",
        rf"\g<1>{flood_cell}\g<3>",
        text,
        count=1,
    )
    text = re.sub(
        r"(\| National Forest Inventory \| `/layers/open/nfi` \|[^|]+\|[^|]+\| )([^|]+)( \|)",
        rf"\g<1>{format_int(nfi)}\g<3>",
        text,
        count=1,
    )
    text = re.sub(
        r"(\| Native Woodland Survey \| `/layers/open/native-woodland` \|[^|]+\|[^|]+\| )([^|]+)( \|)",
        rf"\g<1>{format_int(nwss)}\g<3>",
        text,
        count=1,
    )
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = _connect()
    try:
        river, coastal, flood_src = flood_counts(conn)
        nfi, nfi_src = woodland_count(conn, "nfi_woodland", "nfi", NFI_BASELINE)
        nwss, nwss_src = woodland_count(
            conn, "native_woodland", "native_woodland", NWSS_BASELINE
        )
    finally:
        if conn is not None:
            conn.close()

    print(
        f"flood: {river:,} river + {coastal:,} coastal ({flood_src})\n"
        f"nfi: {nfi:,} ({nfi_src})\n"
        f"native_woodland: {nwss:,} ({nwss_src})"
    )

    original = GUIDE.read_text(encoding="utf-8")
    updated = patch_guide(
        original, river=river, coastal=coastal, nfi=nfi, nwss=nwss
    )
    if updated == original:
        print(f"No change to {GUIDE.relative_to(REPO_ROOT)}")
        return
    if args.dry_run:
        print(f"Dry-run: would update {GUIDE.relative_to(REPO_ROOT)}")
        return
    GUIDE.write_text(updated, encoding="utf-8")
    print(f"Updated {GUIDE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
