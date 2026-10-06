"""Write surface-rent output files with a manifest in the GIS format.

Manifest columns mirror scotland-gis data/processed/gis/manifest.csv:
file, owner, source, licence, publish_level, zone_vintage, key, rows, sha256,
plus a trailing `attribution` column (2026-10-06, lead's loader). The declared
key (code, vintage) must be real columns of every file. Files whose rows were
built from the GIS EPC rollup carry the rollup's licence text in `licence` and
the EPC attribution (OGL, NRS, Royal Mail PAF credit, OS) in `attribution`.

Two files per run:
- <stem>_internal.csv: every column including diagnostics (publish_level internal).
- <stem>_public.csv: `surface_rent.public_view` (no diagnostics, no blocked rows,
  no placeholders), at publish_level public_zone.
Nothing here uploads or publishes; it only writes local files.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from georgist import surface_rent as sr
from georgist.surface_zones import manifest_vintage_label

MANIFEST_COLUMNS = ("file", "owner", "source", "licence", "publish_level", "zone_vintage", "key", "rows", "sha256", "attribution")
OWNER = "valuation"
KEY = "(code, vintage)"
KEY_COLUMNS = ("code", "vintage")

# GIS epc_dz_rollup licence (manifest.csv) and attribution (README_epc_dz_rollup.md), verbatim.
EPC_ROLLUP_LICENCE = "OGL v3; EPC postcodes Royal Mail – non-commercial research use only, licence check before commercial use"
EPC_ROLLUP_ATTRIBUTION = (
    "Contains Scottish Government EPC data licensed under the Open Government Licence v3.0. "
    "Contains NRS data © Crown copyright and database right 2026. "
    "Incorporates data from PAF® the copyright in which is owned by Royal Mail Group Limited. "
    "Contains OS data © Crown copyright and database right 2026."
)
EPC_SOURCE_TAGS = ("epc_all_time", "epc_recent10")


def uses_epc_rollup(rows: Iterable[Mapping]) -> bool:
    """True if any row was built from the GIS EPC rollup (rebuild mix/area source tag)."""
    for r in rows:
        tags = r.get("proxy_tags") or ()
        if isinstance(tags, str):
            tags = tags.split(";")
        if any(t in EPC_SOURCE_TAGS for t in tags) or r.get("rebuild_source") in EPC_SOURCE_TAGS:
            return True
    return False


def epc_licence(base_licence: str, epc_licence_text: str = EPC_ROLLUP_LICENCE) -> str:
    """Row/manifest licence for figures built from the EPC rollup: base licence plus the rollup's licence text."""
    if epc_licence_text in base_licence:
        return base_licence
    return f"{base_licence}; EPC rollup: {epc_licence_text}"


def _licence_and_attribution(rows: Sequence[Mapping], licence: str, attribution: str) -> tuple[str, str]:
    if not uses_epc_rollup(rows):
        return licence, attribution
    att = attribution if EPC_ROLLUP_ATTRIBUTION in attribution else " ".join(x for x in (attribution, EPC_ROLLUP_ATTRIBUTION) if x)
    return epc_licence(licence), att


def _check_key(columns: Sequence[str]) -> None:
    missing = [c for c in KEY_COLUMNS if c not in columns]
    if missing:
        raise ValueError(f"declared key {KEY} but file lacks columns {missing}")


def _cell(v):
    if isinstance(v, (list, tuple, dict)):
        return json.dumps(v, sort_keys=True)
    return "" if v is None else v


def _write_csv(path: Path, rows: Sequence[Mapping], columns: Sequence[str]) -> str:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        for r in rows:
            w.writerow([_cell(r.get(c)) for c in columns])
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_outputs(
    rows: Iterable[Mapping], out_dir: Path | str, *, source: str, licence: str, stem: str = "surface_rent_dz",
    attribution: str = "",
) -> list[dict]:
    """Write internal and public CSVs plus manifest.csv (rows replaced by file name)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    for r in rows:
        sr.validate_required(r)
    licence, attribution = _licence_and_attribution(rows, licence, attribution)
    public = sr.public_view(rows)
    pub_cols = [c for c in sr.OUTPUT_COLUMNS if c not in sr.INTERNAL_ONLY_COLUMNS]
    entries = []
    for name, data, cols, level in (
        (f"{stem}_internal.csv", rows, list(sr.OUTPUT_COLUMNS), "internal"),
        (f"{stem}_public.csv", public, pub_cols, "public_zone"),
    ):
        _check_key(cols)
        sha = _write_csv(out / name, data, cols)
        vintages = manifest_vintage_label(r["vintage"] for r in data) or manifest_vintage_label(r["vintage"] for r in rows)
        entries.append({"file": name, "owner": OWNER, "source": source, "licence": licence, "publish_level": level,
                        "zone_vintage": vintages, "key": KEY, "rows": len(data), "sha256": sha, "attribution": attribution})
    manifest = out / "manifest.csv"
    existing = []
    if manifest.exists():
        with manifest.open(encoding="utf-8") as f:
            existing = [{**dict.fromkeys(MANIFEST_COLUMNS, ""), **r} for r in csv.DictReader(f) if r["file"] not in {e["file"] for e in entries}]
    with manifest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in existing + entries:
            w.writerow(r)
    return entries


def write_internal_table(
    rows: Sequence[Mapping], out_dir: Path | str, *, name: str, columns: Sequence[str], source: str, licence: str,
    attribution: str = "", key: Sequence[str] = KEY_COLUMNS,
) -> dict:
    """Write a diagnostic table at publish_level `internal` and record it in manifest.csv (GIS format).
    `key` starts (code, vintage), must be real columns and unique across rows."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _check_key(columns)
    key = tuple(key)
    if key[:2] != KEY_COLUMNS or not set(key) <= set(columns):
        raise ValueError(f"key {key} must start (code, vintage) and be real columns")
    seen = [tuple(r.get(k) for k in key) for r in rows]
    if len(set(seen)) != len(seen):
        raise ValueError(f"key {key} is not unique")
    licence, attribution = _licence_and_attribution(rows, licence, attribution)
    sha = _write_csv(out / name, rows, columns)
    entry = {"file": name, "owner": OWNER, "source": source, "licence": licence, "publish_level": "internal",
             "zone_vintage": manifest_vintage_label(r.get("vintage", 2011) for r in rows) or "DZ2011",
             "key": f"({', '.join(key)})", "rows": len(rows), "sha256": sha, "attribution": attribution}
    manifest = out / "manifest.csv"
    existing = []
    if manifest.exists():
        with manifest.open(encoding="utf-8") as f:
            existing = [{**dict.fromkeys(MANIFEST_COLUMNS, ""), **r} for r in csv.DictReader(f) if r["file"] != name]
    with manifest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in existing + [entry]:
            w.writerow(r)
    return entry
