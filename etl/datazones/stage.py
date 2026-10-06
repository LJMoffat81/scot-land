#!/usr/bin/env python3
"""Stage outputs into data/processed/datazones/ with manifest.csv in the Scot-LAND GIS manifest format."""
import csv, hashlib, shutil, os, sys, argparse
from pathlib import Path
import pandas as pd
_ap = argparse.ArgumentParser(description="Stage build outputs with manifest.csv")
_ap.add_argument("--root", default=os.environ.get("DZ_ROOT"), help="project root (env DZ_ROOT; default: parent of this script's folder)")
_ap.add_argument("--out", default=os.environ.get("DZ_OUT"), help="build output folder (env DZ_OUT; default ROOT/out)")
_ap.add_argument("--dest", default=os.environ.get("DZ_STAGE"), help="staging folder (env DZ_STAGE; default ROOT/data/processed/datazones)")
_a = _ap.parse_args()
HERE = Path(__file__).resolve().parent
ROOT = Path(_a.root).resolve() if _a.root else HERE.parent
OUT = Path(_a.out).resolve() if _a.out else ROOT / "out"
DST = Path(_a.dest).resolve() if _a.dest else ROOT / "data/processed/datazones"
DST.mkdir(parents=True, exist_ok=True)
OGL = "OGL v3"
_L = ", licensed under the Open Government Licence v3.0"
NRS = "Contains National Records of Scotland data ({}) \u00a9 Crown copyright and database right 2026"
A = {  # OGL attribution line per file; every contributing source listed
 "zone_spine.csv": NRS.format("small area population estimates mid-2022 and mid-2024; small area household estimates 2025; 2022 output area to data zone lookup") + "; contains Scottish Government data (SIMD 2020v2 data zone look-up, updated 2025) \u00a9 Crown copyright 2025; contains Registers of Scotland data (residential sales and price, via data.gov.scot) \u00a9 Crown copyright 2026" + _L,
 "dz_crosswalk_people.csv": NRS.format("Census 2022 postcode index; Scottish Postcode Directory 2026/2; 2022 output area to data zone lookup") + _L,
 "simd2020v2_dz2011.csv": "Contains Scottish Government data (SIMD 2020v2 data zone look-up, updated 2025) \u00a9 Crown copyright 2025" + _L,
 "simd2020v2_access_indicators_dz2011.csv": "Contains Scottish Government data (SIMD 2020v2 indicator data) \u00a9 Crown copyright 2020" + _L,
 "simd2020v2_on_dz2022.csv": "Contains Scottish Government data (SIMD 2020v2 data zone look-up, updated 2025) \u00a9 Crown copyright 2025; " + NRS.format("Census 2022 postcode index; Scottish Postcode Directory 2026/2; 2022 output area to data zone lookup").replace("Contains", "contains") + _L,
 "dwellings_ct_band.csv": NRS.format("small area dwelling estimates 2005-2025; dwellings by council tax band summaries via data.gov.scot") + _L,
 "dwellings_by_year.csv": NRS.format("small area household and dwelling estimates 2005-2025") + _L,
 "dwellings_by_year_coverage.csv": NRS.format("small area household and dwelling estimates 2005-2025") + _L,
 "nrs_dwelling_mix_2011_fallback.csv": NRS.format("dwellings by type; dwellings by number of rooms, via data.gov.scot") + _L,
 "dz_planning_authority.csv": NRS.format("Scottish Postcode Directory 2026/2 with Census 2022 households; small area population estimates") + "; contains Scottish Government data (national park boundaries, via Scot-LAND GIS dz_park_overlay) \u00a9 Crown copyright 2026; contains OS data \u00a9 Crown copyright and database right 2026" + _L,
}
M = [  # file, source, licence, publish_level, zone_vintage, key
 ("zone_spine.csv", "NRS SAPE mid-2022 (DZ2011, corrected Feb 2026) & mid-2024 (DZ2022); NRS household estimates Sept 2025 (both vintages); SG SIMD 2020v2 DZ look-up + NRS OA22_DZ22_IZ22 (hierarchy); RoS house price file via data.gov.scot (DZ2011 presence)", OGL, "public_zone", "DZ2011;DZ2022", ["code", "vintage"]),
 ("dz_crosswalk_people.csv", "NRS Census 2022 index Postcode_To_OA (postcode household population) + NRS SPD 2026/2 (postcode DZ2011) + NRS OA22_DZ22_IZ22; method pop_hhres_2022", OGL, "public_zone", "DZ2011;DZ2022", ["dz2011", "dz2022"]),
 ("simd2020v2_dz2011.csv", "SG SIMD 2020v2 data zone look-up (updated 2025), gov.scot", OGL, "public_zone", "DZ2011", ["code", "vintage"]),
 ("simd2020v2_access_indicators_dz2011.csv", "SG SIMD 2020v2 indicator data (SIMD 2020v2 - indicators.xlsx, sheet Data), gov.scot; access minutes + broadband proportion; DZ2011 only, not crosswalked", OGL, "public_zone", "DZ2011", ["code", "vintage"]),
 ("simd2020v2_on_dz2022.csv", "Derived: SG SIMD 2020v2 deciles/quintiles x dz_crosswalk_people reverse_weight (Census 2022 household population); ranks never averaged", OGL, "public_zone", "DZ2022", ["code", "vintage"]),
 ("dwellings_ct_band.csv", "NRS dwelling estimates (Assessors portal, Dec): DZ2011 2005-2025, DZ2022 2024-2025; reconciled to data.gov.scot CT band summary datasets", OGL, "public_zone", "DZ2011;DZ2022", ["code", "vintage", "count_year"]),
 ("dwellings_by_year.csv", "NRS small-area household & dwelling estimates (council tax, Sept): DZ2011 2014-2025, DZ2022 2024-2025; + NRS Assessors Dec totals", OGL, "public_zone", "DZ2011;DZ2022", ["code", "vintage", "count_year"]),
 ("dwellings_by_year_coverage.csv", "Metadata: which NRS dwelling series/sheets exist per vintage and year 2005-2025", OGL, "public_zone", "DZ2011;DZ2022", ["vintage", "count_year"]),
 ("nrs_dwelling_mix_2011_fallback.csv", "data.gov.scot Dwellings by Type / Dwellings by Number of Rooms (NRS), DZ2011 2014-2017; HISTORIC FALLBACK ONLY", OGL, "public_zone", "DZ2011", ["code", "vintage", "count_year"]),
 ("dz_planning_authority.csv", "Scot-LAND GIS dz_park_overlay (SG national park boundaries + SPD 2026/2 Census 2022 households) + zone_spine council codes", "OGL v3; Copyright Scottish Government, contains OS data (c) Crown copyright and database right 2026", "public_zone", "DZ2011;DZ2022", ["code", "vintage", "plan_making_authority"]),
]
rows = []
for f, src, lic, pub, zv, key in M:
    shutil.copy2(OUT / f, DST / f)
    d = pd.read_csv(DST / f, dtype=str, keep_default_na=False)
    missing = [k for k in key if k not in d.columns]
    assert not missing, (f, missing)
    assert not d.duplicated(key).any(), (f, "duplicate keys")
    assert all((d[k] != "").all() for k in key), (f, "empty key")
    sha = hashlib.sha256((DST / f).read_bytes()).hexdigest()
    if pub.startswith("public") and not A.get(f, "").strip():
        sys.exit(f"ERROR: {f} is {pub} but has no attribution line")
    rows.append({"file": f, "owner": "datazones", "source": src, "licence": lic, "publish_level": pub, "zone_vintage": zv,
                 "key": "(" + ", ".join(key) + ")", "rows": len(d), "sha256": sha, "attribution": A.get(f, "")})
with open(DST / "manifest.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["file", "owner", "source", "licence", "publish_level", "zone_vintage", "key", "rows", "sha256", "attribution"])
    w.writeheader(); w.writerows(rows)
for f in ["README.md", "sources.md", "schema.sql", "SOURCES_SHA256.txt"]:  # docs: ROOT first, then scripts/ (repo etl/ layout)
    src = next((p for p in (ROOT / f, HERE / f) if p.is_file()), None)
    if src: shutil.copy2(src, DST / f)
    else: print(f"warning: {f} not found in {ROOT} or {HERE}; not staged", file=sys.stderr)
shutil.copy2(OUT / "qa_results.json", DST / "qa_results.json")
for r in rows: print(r["file"], r["rows"], r["key"], r["sha256"][:12])
