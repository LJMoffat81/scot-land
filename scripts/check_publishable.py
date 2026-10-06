#!/usr/bin/env python3
"""Publishability guard: this repository is PUBLIC.

Fails (exit 1) if anything tracked by git (the index, so staged files count) is:
  1. listed in a data/processed/*/manifest.csv with publish_level=internal;
  2. inside a raw/ or internal/ folder, a Spatial Hub download, a GeoPackage under data/
     (site layers such as svdls_sites.gpkg / hls_sites.gpkg are internal) or an INSPIRE-derived file;
  3. a CSV/TSV whose header carries address, postcode, UPRN or similar columns.

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

PERSONAL_COLUMN = re.compile(
    r"(^|[_\s])(address(es)?|addr|address_line\d*|postcode|post_code|postcodes|pcode|pc_sector"
    r"|uprn|udprn|usrn|street|street_name|thoroughfare|house_number|house_no|building_name"
    r"|building_number|paon|saon|flat_number|full_address)($|[_\s])",
    re.IGNORECASE,
)
SPATIAL_HUB = re.compile(r"spatial[_-]?hub", re.IGNORECASE)
TABULAR = {".csv": ",", ".tsv": "\t"}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def tracked() -> list[str]:
    return [p for p in git("ls-files", "-z").split("\0") if p]


def index_head(path: str, nbytes: int = 65536) -> str:
    """First bytes of the staged (index) version, so the hook checks what will be committed."""
    out = subprocess.run(["git", "cat-file", "blob", f":{path}"], check=True, capture_output=True).stdout
    return out[:nbytes].decode("utf-8-sig", errors="replace")


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
        if SPATIAL_HUB.search(f):
            problems.append(f"{f}: looks like a Spatial Hub download")
        # 3. address / postcode / UPRN-like columns
        sep = TABULAR.get(PurePosixPath(f).suffix.lower())
        if sep:
            first = index_head(f).splitlines()[:1]
            header = next(csv.reader(first, delimiter=sep), []) if first else []
            bad = [c for c in header if PERSONAL_COLUMN.search(c.strip())]
            if bad:
                problems.append(f"{f}: address/postcode/UPRN-like column(s) {bad}")
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
