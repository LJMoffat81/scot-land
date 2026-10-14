#!/usr/bin/env python3
"""Publishability guard: this repository is PUBLIC.

Fails (exit 1) if anything tracked by git (the index, so staged files count) is:
  1. listed in a data/processed/*/manifest.csv with publish_level=internal;
  2. inside a raw/ or internal/ folder, a Spatial Hub download, a GeoPackage under data/
     (site layers such as svdls_sites.gpkg / hls_sites.gpkg are internal), an INSPIRE-derived
     file, or parcel geometry / a tile archive (size);
  3. a CSV/TSV whose header carries address, postcode, UPRN or similar columns;
  4. under a discovered frontend preview app route (name ends in -panel / -card, or a
     layout imports @/lib/internalUi) without a layout.tsx that actually gates via
     if (!internalUiEnabled()) notFound().

Run from anywhere inside the repo:  python3 scripts/check_publishable.py
Used by scripts/hooks/pre-commit and CI. Standard library only.
"""

from __future__ import annotations

import csv
import os
import io
import re
import subprocess
import sys
from pathlib import PurePosixPath

# Aggregate columns that merely count or share such things (e.g. GIS's n_res_uprn,
# share_res_uprn_in_parcels, res_uprn_exceeds_dwellings) are not identifiers.
AGGREGATE_TOKENS = {"n", "num", "count", "counts", "share", "pct", "exceeds", "in", "per", "median", "mean",
                    "total", "ha", "has", "coverage"}
PERSONAL_COLUMN = re.compile(
    r"(^|[_\s])(address(es)?|addr|address_line\d*|postcode|post_code|postcodes|pcode|pc_sector"
    r"|uprn|udprn|usrn|street|street_name|thoroughfare|house_number|house_no|building_name"
    r"|building_number|paon|saon|flat_number|full_address)($|[_\s])",
    re.IGNORECASE,
)
SPATIAL_HUB = re.compile(r"spatial[_-]?hub", re.IGNORECASE)
# Parcel-level geometry and tile archives stay out of the repo (size; RoS INSPIRE is OGL v3).
# This is a geometry rule, not a licence list: whether a DATA TABLE may be published is decided
# only by its manifest publish_level (check 1), never by hard-coded file names.
GEOMETRY_PRODUCT = re.compile(r"parcel[^/]*\.(geojson|gpkg|fgb|shp|pmtiles|mbtiles|parquet)$"
                              r"|\.(pmtiles|mbtiles)$|site[_-]?outline", re.IGNORECASE)
# Code that may name these things (scripts, routes) is not data.
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".md", ".sql", ".yml", ".yaml", ".json", ".txt", ".sh"}
TABULAR = {".csv": ",", ".tsv": "\t"}
# Top-level app segments that look like Dev/QA previews (no hard-coded route list).
PREVIEW_ROUTE_NAME = re.compile(r".+-(panel|card)$")
# Layout must call the gate — mentioning the two identifiers is not enough.
PREVIEW_GATE_CALL = re.compile(
    r"if\s*\(\s*!\s*internalUiEnabled\s*\(\s*\)\s*\)\s*(?:\{\s*)?notFound\s*\(\s*\)",
)
INTERNAL_UI_IMPORT = re.compile(
    r"""from\s+["']@/lib/internalUi["']""",
)
NOTFOUND_IMPORT = re.compile(
    r"""from\s+["']next/navigation["']""",
)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def tracked() -> list[str]:
    return [p for p in git("ls-files", "-z").split("\0") if p]


def index_head(path: str, nbytes: int = 65536) -> str:
    """First bytes of the staged (index) version, so the hook checks what will be committed."""
    out = subprocess.run(["git", "cat-file", "blob", f":{path}"], check=True, capture_output=True).stdout
    return out[:nbytes].decode("utf-8-sig", errors="replace")


def discover_preview_routes(files: list[str]) -> set[str]:
    """Find top-level frontend/app preview segments without a fixed allow-list.

    A route is a preview if its segment name ends in -panel / -card, or its
    layout.tsx imports @/lib/internalUi (claiming the internal-UI gate).
    """
    routes: set[str] = set()
    for f in files:
        parts = PurePosixPath(f).parts
        if len(parts) < 3 or parts[0] != "frontend" or parts[1] != "app":
            continue
        route = parts[2]
        if not route or route.startswith(("(", "_")) or route == "api":
            continue
        if PREVIEW_ROUTE_NAME.fullmatch(route):
            routes.add(route)
            continue
        if len(parts) == 4 and parts[3] == "layout.tsx":
            text = index_head(f)
            if INTERNAL_UI_IMPORT.search(text) or "internalUiEnabled" in text:
                routes.add(route)
    return routes


def _preview_route_gated(fileset: set[str], route: str) -> bool:
    """True only when layout imports and calls if (!internalUiEnabled()) notFound()."""
    layout = f"frontend/app/{route}/layout.tsx"
    if layout not in fileset:
        return False
    text = index_head(layout)
    if not INTERNAL_UI_IMPORT.search(text):
        return False
    if not NOTFOUND_IMPORT.search(text):
        return False
    if "internalUiEnabled" not in text or "notFound" not in text:
        return False
    return PREVIEW_GATE_CALL.search(text) is not None


def check(files: list[str]) -> list[str]:
    problems: list[str] = []
    fileset = set(files)

    # 1. internal files listed in manifests must not be tracked
    for manifest in sorted(f for f in files if re.fullmatch(r"data/processed/[^/]+/manifest\.csv", f)):
        folder = PurePosixPath(manifest).parent
        rows = list(csv.DictReader(io.StringIO(index_head(manifest, 10**7))))
        for row in rows:
            level = (row.get("publish_level") or "").strip().lower()
            name = (row.get("file") or "").strip()
            if not name:
                problems.append(f"{manifest}: row without a file name")
                continue
            target = str(folder / name)
            if level == "internal" and target in fileset:
                problems.append(f"{target}: publish_level=internal in {manifest} but tracked by git")

    for f in files:
        parts = PurePosixPath(f).parts
        # 2. raw/ folders and Spatial Hub downloads
        if "raw" in (p.lower() for p in parts[:-1]):
            problems.append(f"{f}: tracked file inside a raw/ folder")
        if "internal" in (p.lower() for p in parts[:-1]):
            problems.append(f"{f}: tracked file inside an internal/ folder")
        if f.startswith("data/") and PurePosixPath(f).suffix.lower() == ".gpkg":
            problems.append(f"{f}: GeoPackage under data/ (site layers are internal)")
        if f.startswith("data/") and "inspire" in f.lower():
            problems.append(f"{f}: INSPIRE-derived file (internal until the RoS terms are cleared)")
        if GEOMETRY_PRODUCT.search(f) and PurePosixPath(f).suffix.lower() not in CODE_SUFFIXES:
            problems.append(f"{f}: parcel geometry / tile archive (kept out of the repo for size)")
        if SPATIAL_HUB.search(f):
            problems.append(f"{f}: looks like a Spatial Hub download")
        # 3. address / postcode / UPRN-like columns
        sep = TABULAR.get(PurePosixPath(f).suffix.lower())
        if sep:
            first = index_head(f).splitlines()[:1]
            header = next(csv.reader(first, delimiter=sep), []) if first else []
            bad = [c for c in header if PERSONAL_COLUMN.search(c.strip())
                   and not AGGREGATE_TOKENS & set(c.strip().lower().split("_"))]
            if bad:
                problems.append(f"{f}: address/postcode/UPRN-like column(s) {bad}")

    # 4. discovered preview app routes must actually gate via layout.tsx
    for route in sorted(discover_preview_routes(files)):
        if not _preview_route_gated(fileset, route):
            problems.append(
                f"frontend/app/{route}/: preview route must be gated via layout.tsx "
                "(if (!internalUiEnabled()) notFound())"
            )
    return problems


def main() -> int:
    try:
        top = git("rev-parse", "--show-toplevel").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("check_publishable: not inside a git repository", file=sys.stderr)
        return 2

    os.chdir(top)
    files = tracked()
    problems = check(files)
    if problems:
        print(f"check_publishable: FAIL ({len(problems)} problem(s)). This repository is PUBLIC.")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"check_publishable: OK ({len(files)} tracked files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
