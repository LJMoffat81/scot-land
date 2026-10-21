#!/usr/bin/env python3
"""Fetch every raw input that build.py reads, from its official URL, into RAW, and verify SHA-256.

* Checksums come from SOURCES_SHA256.txt (default: next to this script). A mismatch is a hard failure:
  the publisher has changed or replaced the file, so outputs would no longer be reproducible.
* A file that is already present with the right checksum is not downloaded again.
* Zips are unpacked to the exact paths build.py expects; extracted members are checked against the zip's CRC-32.
* MANUAL INPUT: dz_park_overlay.csv is produced by Scot-LAND GIS (data/processed/gis/dz_park_overlay.csv) and has no
  publisher URL. Pass --park-overlay PATH (or env DZ_PARK_OVERLAY) to copy it into RAW and verify it, or set
  DZ_PARK_OVERLAY when running build.py.

Usage: python3 scripts/fetch.py [--raw DIR] [--sha-file FILE] [--park-overlay PATH] [--verify-only]
Licence of all downloads: Open Government Licence v3.0 (see sources.md).
"""
import argparse, hashlib, os, shutil, sys, time, urllib.error, urllib.request, zipfile, zlib
from pathlib import Path

NRS = "https://www.nrscotland.gov.uk/media"
GOV = "https://www.gov.scot/binaries/content/documents/govscot/publications/statistics/2020/01"
DGS = "https://data.gov.scot/dataset"
# raw-relative file, official URL, zip extraction (target dir, members or None = all)
SOURCES = [
    ("spd_postcodeindex_cut_26_2_csv.zip", f"{NRS}/hy3j3g1s/spd_postcodeindex_cut_26_2_csv.zip", ("spd_index", None)),
    ("spd_geographylookups_26_2_csv.zip", f"{NRS}/1a5hqdwr/spd_geographylookups_26_2_csv.zip", ("spd_lookups", None)),
    ("census_2022_index.zip", f"{NRS}/utrbt5ze/census_2022_index.zip", ("census_2022_index", None)),
    ("Census-2022-Output-Area-v1.zip",
     "https://www.scotlandscensus.gov.uk/media/zz85kfinmf97whklasd98gfkadft5hj4f_Topic2H_20241120_1747/Census-2022-Output-Area-v1.zip",
     ("census_oa", ["UV101b - Usual resident population by sex by age (6).csv"])),
    ("oa22_dz22_iz22.zip", f"{NRS}/iz3evrqt/oa22_dz22_iz22.zip", ("oa22_dz22_iz22", None)),
    ("sape22_11.xlsx", f"{NRS}/3qvj4ni4/sape-2022-11dz-corrected.xlsx", None),
    ("sape-2024-22dz-data.xlsx", f"{NRS}/efyoyacy/sape-2024-22dz-data.xlsx", None),
    ("household-estimates-by-2011-data-zones.xlsx", f"{NRS}/ramf3ik4/household-estimates-by-2011-data-zones.xlsx", None),
    ("household-estimates-by-2022-data-zones-24-25.xlsx", f"{NRS}/ynjma234/household-estimates-by-2022-data-zones-24-25.xlsx", None),
    ("dwellings-estimate-by-2011-data-zones.xlsx", f"{NRS}/fqword2k/dwellings-estimate-by-2011-data-zones.xlsx", None),
    ("dwelling-estimates-by-2022-data-zones-24-25.xlsx", f"{NRS}/43tfx3zo/dwelling-estimates-by-2022-data-zones-24-25.xlsx", None),
    ("SIMD_2020v2_datazone_lookup_updated_2025.xlsx",
     f"{GOV}/scottish-index-of-multiple-deprivation-2020-data-zone-look-up-file/documents/scottish-index-of-multiple-deprivation-data-zone-look-up/scottish-index-of-multiple-deprivation-data-zone-look-up/govscot%3Adocument/SIMD%2B2020v2%2B-%2Bdatazone%2Blookup%2B-%2Bupdated%2B2025.xlsx", None),
    ("SIMD_2020v2_ranks.xlsx",
     f"{GOV}/scottish-index-of-multiple-deprivation-2020-ranks-and-domain-ranks/documents/scottish-index-of-multiple-deprivation-2020-ranks-and-domain-ranks/scottish-index-of-multiple-deprivation-2020-ranks-and-domain-ranks/govscot%3Adocument/SIMD%2B2020v2%2B-%2Branks.xlsx", None),
    ("SIMD_2020v2_indicators.xlsx",
     f"{GOV}/scottish-index-of-multiple-deprivation-2020-indicator-data/documents/simd_2020_indicators/simd_2020_indicators/govscot%3Adocument/SIMD%2B2020v2%2B-%2Bindicators.xlsx", None),
    ("dgs_house_prices.csv", f"{DGS}/house_prices___residential_properties_sales_and_price/resource/3d9a31a5-4b62-436a-a537-7d9bbeba1723/download", None),
    ("dgs_ct_band_2022dz.csv", f"{DGS}/dwellings_by_council_tax_band_summary__2022_data_zones_/resource/e9d042a7-2244-498d-9ddf-da61ba9ccede/download", None),
    ("dgs_ct_band_cgb_2011dz.csv", f"{DGS}/dwellings_by_council_tax_band_summary__current_geographic_boundaries_/resource/aa8f7e2b-5507-4a2f-aaa2-14535d5b20b4/download", None),
    ("dgs_dwellings_by_type.csv", f"{DGS}/dwellings_by_type/resource/7ba9cb9b-2618-49ab-b26e-a43505781f8c/download", None),
    ("dgs_dwellings_by_rooms.csv", f"{DGS}/dwellings_by_number_of_rooms/resource/696d559f-19a1-42c7-9f82-7563607b68ff/download", None),
]
MANUAL = "dz_park_overlay.csv"   # Scot-LAND GIS product; no publisher URL


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def crc32(p):
    c = 0
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            c = zlib.crc32(b, c)
    return c & 0xFFFFFFFF


def load_sums(path):
    sums = {}
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            h, name = line.split(None, 1)
            sums.setdefault(name.strip(), set()).add(h)   # several lines for one file = each accepted version
    return sums


def download(url, dest):
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "scot-land-datazones-fetch/1.0"})
    e = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            tmp.replace(dest)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            e = err  # network errors: retry, then fail loudly
            print(f"   download attempt {attempt + 1} failed: {e}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))
    tmp.unlink(missing_ok=True)
    raise SystemExit(f"FAIL: could not download {url}: {type(e).__name__}")


def extract(zpath, raw, target, members):
    tdir = raw / target
    with zipfile.ZipFile(zpath) as z:
        infos = [i for i in z.infolist() if not i.is_dir() and (members is None or i.filename in members or Path(i.filename).name in members)]
        if members and len(infos) != len(members):
            raise SystemExit(f"FAIL: {zpath.name} lacks expected member(s) {members}")
        n_ok = n_x = 0
        for i in infos:
            out = tdir / (Path(i.filename).name if members else i.filename)
            if out.is_file() and out.stat().st_size == i.file_size and crc32(out) == i.CRC:
                n_ok += 1
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            if crc32(out) != i.CRC:
                raise SystemExit(f"FAIL: CRC mismatch extracting {i.filename}")
            n_x += 1
    print(f"   unzip -> {target}/: {n_ok} already present (CRC ok), {n_x} extracted")


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.environ.get("DZ_ROOT"), help="project root (env DZ_ROOT; default: parent of this script's folder)")
    ap.add_argument("--raw", default=os.environ.get("DZ_RAW"), help="raw folder (env DZ_RAW; default ROOT/raw)")
    ap.add_argument("--sha-file", default=os.environ.get("DZ_SHA_FILE"), help="checksum file (default: SOURCES_SHA256.txt next to this script)")
    ap.add_argument("--park-overlay", default=os.environ.get("DZ_PARK_OVERLAY"), help="path to Scot-LAND GIS dz_park_overlay.csv to copy into RAW and verify")
    ap.add_argument("--verify-only", action="store_true", help="never download; fail if anything is missing or wrong")
    a = ap.parse_args()
    root = Path(a.root).resolve() if a.root else here.parent
    raw = Path(a.raw).resolve() if a.raw else root / "raw"
    sha_file = Path(a.sha_file) if a.sha_file else here / "SOURCES_SHA256.txt"
    if not sha_file.is_file():
        raise SystemExit(f"FAIL: checksum file not found: {sha_file}")
    sums = load_sums(sha_file)
    raw.mkdir(parents=True, exist_ok=True)
    print(f"RAW={raw}\nSHA file={sha_file}")
    bad = []
    for name, url, unzip in SOURCES:
        dest = raw / name
        want = sums.get(name)
        if not want:
            raise SystemExit(f"FAIL: no checksum for {name} in {sha_file}")
        if dest.is_file() and sha256(dest) in want:
            print(f"OK (present)    {name}")
        elif a.verify_only:
            print(f"MISSING/BAD     {name}"); bad.append(name); continue
        else:
            print(f"downloading     {name}\n   <- {url}")
            download(url, dest)
            got = sha256(dest)
            if got not in want:
                bad.append(name)
                print(f"FAIL checksum   {name}: expected {' or '.join(sorted(want))}, got {got}\n"
                      f"   The publisher has changed this file. Outputs will differ; review sources.md and update the checksum deliberately.",
                      file=sys.stderr)
                continue
            print(f"OK (downloaded) {name}")
        if unzip:
            extract(dest, raw, *unzip)
    # manual input: GIS park overlay
    ov = raw / MANUAL
    if a.park_overlay:
        src = Path(a.park_overlay).resolve()
        if not src.is_file():
            raise SystemExit(f"FAIL: --park-overlay {src} not found")
        if src != ov:
            shutil.copy2(src, ov)
    if ov.is_file():
        if sums.get(MANUAL) and sha256(ov) not in sums[MANUAL]:
            bad.append(MANUAL)
            print(f"FAIL checksum   {MANUAL}: differs from the version these outputs were built with "
                  f"(GIS may have rebuilt it). Update the checksum deliberately if intended.", file=sys.stderr)
        else:
            print(f"OK (present)    {MANUAL}  [manual input from Scot-LAND GIS]")
    else:
        print(f"MANUAL STEP     {MANUAL} not in RAW. Copy it from Scot-LAND GIS (data/processed/gis/dz_park_overlay.csv): "
              f"re-run with --park-overlay PATH, or set DZ_PARK_OVERLAY when running build.py.")
    if bad:
        raise SystemExit(f"FAIL: {len(bad)} file(s) failed verification: {', '.join(bad)}")
    print("All downloadable inputs verified.")


if __name__ == "__main__":
    main()
