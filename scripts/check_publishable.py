#!/usr/bin/env python3
"""Publishability guard: this repository is PUBLIC.

Fails (exit 1) if anything tracked by git (the index, so staged files count) is:
  1. listed in a data/processed/*/manifest.csv with publish_level=internal;
  2. inside a raw/ or internal/ folder, a Spatial Hub download, a GeoPackage under data/
     (site layers such as svdls_sites.gpkg / hls_sites.gpkg are internal), an INSPIRE-derived
     file, or parcel geometry / a tile archive (size);
  3. a CSV/TSV whose header carries address, postcode, UPRN or similar columns,
     or a forbidden public AGR £ property name;
  4. a tracked .json / .geojson under data/processed or frontend/public whose object
     keys include a forbidden public AGR £ property name;
  5. under a discovered frontend preview app route (name ends in -panel / -card, a
     layout imports @/lib/internalUi, or a page imports an Internal* component)
     without a layout.tsx that actually gates via if (!internalUiEnabled()) notFound()
     (comments are stripped before the gate match).

Run from anywhere inside the repo:  python3 scripts/check_publishable.py
Used by scripts/hooks/pre-commit and CI. Standard library only.
"""

from __future__ import annotations

import csv
import json
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
# Modelled council/plot AGR £ columns — never in tracked public tabular data.
# Keep in sync with georgist.publication_rules.FORBIDDEN_PUBLIC_AGR_PROPERTIES.
FORBIDDEN_PUBLIC_AGR_PROPERTIES = frozenset({
    "annual_ground_rent_plot_gbp",
    "site_rental_per_sqm_gbp",
    "site_capital_per_sqm_gbp",
    "net_contribution_plot_gbp",
    "gross_plot_liability_gbp",
    "vacant_full_agr_gbp",
    "agr_as_pct_of_price",
    # camelCase aliases used by legacy roll / vdl-councils builders
    "siteRentalPerSqmGbp",
    "vacantFullAgrGbp",
    # Methods alignment £ totals — never in tracked public JSON (additive; local run output only)
    "scotland_total_central_gbp",
    "scotland_total_low_gbp",
    "scotland_total_high_gbp",
    "scotland_total_central_gbp_before",
    "scotland_total_low_gbp_before",
    "scotland_total_high_gbp_before",
    "scotland_total_central_gbp_after",
    "scotland_total_low_gbp_after",
    "scotland_total_high_gbp_after",
})
# DZ2022 empty-zone fill stays internal / blocked — never in public JSON/GeoJSON keys.
# Additive coverage only; does not weaken FORBIDDEN_PUBLIC_AGR_PROPERTIES.
FORBIDDEN_PUBLIC_FILL_TOKENS = frozenset({
    "model_fill_dz2022",
})
# Additive: banned visitor wording on public developers / catalog / ledger routes.
# Does not weaken FORBIDDEN_PUBLIC_AGR_PROPERTIES.
# "nested" is only flagged inside visitor prose (strings with whitespace), so the
# machine boolean key ``nested`` / ``nested_under`` is allowed.
FORBIDDEN_PUBLIC_ROUTE_PHRASES = frozenset({
    "£0",
    "market+proxy",
    ".env",
})
FORBIDDEN_PUBLIC_ROUTE_PROSE_WORDS = frozenset({
    "nested",
})
# Source modules / pages that feed /developers, /developers/checks, catalog.json, ledger.json.
PUBLIC_ROUTE_SCAN_PATHS = (
    "frontend/app/developers/page.tsx",
    "frontend/app/developers/checks/page.tsx",
    "backend/layers/ledger.py",
    "backend/georgist/ledger.py",
    "backend/georgist/place_stack.py",
)
NESTED_WORD = re.compile(r"(?i)\bnested\b")
# Prefer triple-quoted bodies, then single-line quotes (non-greedy).
QUOTED_STRING = re.compile(
    r'"""(?P<tbody>.*?)"""|'
    r"'''(?P<tbody2>.*?)'''|"
    r'"(?P<body>(?:\\.|[^"\\])*)"|'
    r"'(?P<body2>(?:\\.|[^'\\])*)'",
    re.DOTALL,
)
JSON_DATA_SUFFIXES = {".json", ".geojson"}
JSON_SCAN_PREFIXES = ("data/processed/", "frontend/public/")
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
# page.tsx importing an Internal* component marks the route as a preview.
INTERNAL_COMPONENT_IMPORT = re.compile(
    r"""(?:import\s+(?:type\s+)?(?:\{[^}]*\bInternal\w+\b[^}]*\}|Internal\w+)\s+from\s+["'][^"']+["']"""
    r"""|from\s+["']@/components/Internal\w+["'])""",
)
# Strip // and /* */ comments before matching the gate (commented-out gates fail).
LINE_COMMENT = re.compile(r"//[^\n]*")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def tracked() -> list[str]:
    return [p for p in git("ls-files", "-z").split("\0") if p]


def index_head(path: str, nbytes: int = 65536) -> str:
    """First bytes of the staged (index) version, so the hook checks what will be committed."""
    out = subprocess.run(["git", "cat-file", "blob", f":{path}"], check=True, capture_output=True).stdout
    return out[:nbytes].decode("utf-8-sig", errors="replace")


def index_text(path: str) -> str:
    """Full staged (index) text for a path."""
    out = subprocess.run(["git", "cat-file", "blob", f":{path}"], check=True, capture_output=True).stdout
    return out.decode("utf-8-sig", errors="replace")


def forbidden_json_keys(obj: object) -> list[str]:
    """Return forbidden AGR £ / fill-token property names found as object keys (any depth)."""
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str) and (
                key in FORBIDDEN_PUBLIC_AGR_PROPERTIES or key in FORBIDDEN_PUBLIC_FILL_TOKENS
            ):
                found.append(key)
            found.extend(forbidden_json_keys(value))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(forbidden_json_keys(item))
    return found


def forbidden_json_fill_values(obj: object) -> list[str]:
    """Return forbidden fill tokens found as string *values* (any depth).

    Additive coverage for model_fill_dz2022 leaking via tag arrays / string fields
    in public JSON/GeoJSON — does not weaken existing AGR key rules.
    """
    found: list[str] = []
    if isinstance(obj, dict):
        for value in obj.values():
            found.extend(forbidden_json_fill_values(value))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(forbidden_json_fill_values(item))
    elif isinstance(obj, str):
        for token in FORBIDDEN_PUBLIC_FILL_TOKENS:
            if token in obj:
                found.append(token)
    return found


def _phrase_hits_in_sample(sample: str) -> list[str]:
    """Flag forbidden phrases in one visitor-facing text sample."""
    hits: list[str] = []
    if sample in FORBIDDEN_PUBLIC_ROUTE_PHRASES:
        hits.append(sample)
        return hits
    if not re.search(r"\s", sample):
        return hits
    if "£0" in sample:
        hits.append("£0")
    if "market+proxy" in sample:
        hits.append("market+proxy")
    if ".env" in sample:
        hits.append(".env")
    if NESTED_WORD.search(sample) and "nested" in FORBIDDEN_PUBLIC_ROUTE_PROSE_WORDS:
        hits.append("nested")
    return hits


def public_route_phrase_hits(text: str) -> list[str]:
    """Return forbidden visitor phrases found in quoted / JSX text values.

    Exact ``£0`` / ``market+proxy`` / ``.env`` values are flagged. Prose
    strings (with whitespace) are also scanned for those tokens and the word
    ``nested``. Machine keys such as ``nested`` / ``nested_under`` stay allowed.
    Additive coverage only — does not weaken AGR property rules.
    """
    cleaned = LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", text))
    # Also drop Python # comments so doc/comment asides are not scanned.
    cleaned = re.sub(r"(?m)^\s*#.*?$", "", cleaned)
    hits: list[str] = []
    for match in QUOTED_STRING.finditer(cleaned):
        body = (
            match.group("tbody")
            or match.group("tbody2")
            or match.group("body")
            or match.group("body2")
        )
        if body is None:
            continue
        sample = body.replace("\\n", " ").replace("\\t", " ").replace('\\"', '"')
        hits.extend(_phrase_hits_in_sample(sample))
    # JSX / HTML text nodes: >visitor copy<
    for match in re.finditer(r">([^<>{]+)<", cleaned):
        sample = re.sub(r"\s+", " ", match.group(1)).strip()
        if sample:
            hits.extend(_phrase_hits_in_sample(sample))
    return hits


def strip_ts_comments(text: str) -> str:
    """Remove // and /* */ comments so a commented-out gate does not count."""
    return LINE_COMMENT.sub("", BLOCK_COMMENT.sub("", text))


def discover_preview_routes(files: list[str]) -> set[str]:
    """Find top-level frontend/app preview segments without a fixed allow-list.

    A route is a preview if its segment name ends in -panel / -card, its
    layout.tsx imports @/lib/internalUi (claiming the internal-UI gate), or
    its page.tsx imports an Internal* component.
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
                continue
        if len(parts) == 4 and parts[3] == "page.tsx":
            text = strip_ts_comments(index_head(f))
            if INTERNAL_COMPONENT_IMPORT.search(text):
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
    # Comments stripped: a commented-out fake gate must not pass.
    return PREVIEW_GATE_CALL.search(strip_ts_comments(text)) is not None


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
        # 3. address / postcode / UPRN-like columns, or forbidden public AGR £ properties
        sep = TABULAR.get(PurePosixPath(f).suffix.lower())
        if sep:
            first = index_head(f).splitlines()[:1]
            header = next(csv.reader(first, delimiter=sep), []) if first else []
            bad = [c for c in header if PERSONAL_COLUMN.search(c.strip())
                   and not AGGREGATE_TOKENS & set(c.strip().lower().split("_"))]
            if bad:
                problems.append(f"{f}: address/postcode/UPRN-like column(s) {bad}")
            agr_bad = [c for c in header if c.strip() in FORBIDDEN_PUBLIC_AGR_PROPERTIES]
            if agr_bad:
                problems.append(f"{f}: forbidden public AGR £ property column(s) {agr_bad}")
            fill_bad = [c for c in header if c.strip() in FORBIDDEN_PUBLIC_FILL_TOKENS]
            if fill_bad:
                problems.append(f"{f}: forbidden public DZ2022 fill token column(s) {fill_bad}")
        # 4. tracked JSON / GeoJSON under data/processed or frontend/public
        if (
            PurePosixPath(f).suffix.lower() in JSON_DATA_SUFFIXES
            and f.startswith(JSON_SCAN_PREFIXES)
        ):
            try:
                payload = json.loads(index_text(f))
            except json.JSONDecodeError as exc:
                problems.append(f"{f}: invalid JSON ({exc.msg})")
                continue
            agr_keys = sorted(set(forbidden_json_keys(payload)))
            if agr_keys:
                problems.append(f"{f}: forbidden public AGR £ / fill property key(s) {agr_keys}")
            fill_vals = sorted(set(forbidden_json_fill_values(payload)))
            if fill_vals:
                problems.append(f"{f}: forbidden public DZ2022 fill token value(s) {fill_vals}")

    # 4b. banned visitor wording on public developers / ledger / catalog sources
    for f in PUBLIC_ROUTE_SCAN_PATHS:
        if f not in fileset:
            continue
        phrase_hits = sorted(set(public_route_phrase_hits(index_text(f))))
        if phrase_hits:
            problems.append(
                f"{f}: forbidden public-route wording {phrase_hits} "
                "(use Limits use (not a money value); separate market/proxy totals; "
                "already included in <parent>)"
            )

    # 5. discovered preview app routes must actually gate via layout.tsx
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
