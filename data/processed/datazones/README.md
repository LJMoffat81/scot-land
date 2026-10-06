# Scot-LAND Data Zones: zone spine, crosswalk, SIMD, dwellings, planning authority

Built on the box on 6 Oct 2026 (BST) by Scot-LAND Data Zones. Nothing here has been pushed or added to the repo. Scot-LAND (lead SE) will wire the tables in.
* Staged outputs: `data/processed/datazones/`, which mirrors the repo layout. It holds the CSVs, `manifest.csv`, `schema.sql`, `README.md`, `sources.md` and `qa_results.json`.
* Rebuild from scratch: see **Rebuild** below. `scripts/` is self-contained (fetch, build, stage, `SOURCES_SHA256.txt`, `requirements.txt`). `raw/` is not committed. Provenance is in `sources.md`.
* `schema.sql` has Postgres DDL in schema `datazones`. Every CSV was loaded into a throwaway Postgres 17 instance with all PK, FK and CHECK constraints, with 0 errors.

**Keys.** Every zone table is keyed `(code, vintage)` with `vintage ∈ {2011, 2022}`. Multi-row tables add one extra key column (`count_year`, or `plan_making_authority` for the planning lookup). The crosswalk is keyed `(dz2011, dz2022)`. Codes: DZ2011 runs S01006506–S01013481 (6,976 zones) and DZ2022 runs S01013482–S01020873 (7,392). Council areas use 2019 S12 codes. Every number is read from an official file or derived by the arithmetic documented here. Nothing is imputed, carried forward or crosswalked silently.

## Rebuild (3 steps)
Python 3.13 (built with 3.13.5): `pip install -r scripts/requirements.txt`. The commands below assume the folder layout here; in the repo, run them with `scripts/` replaced by `etl/`.
```
python3 scripts/fetch.py --park-overlay /path/to/scotland-gis/data/processed/gis/dz_park_overlay.csv   # 1. fetch + verify raw/
python3 scripts/build.py                                                                              # 2. build out/ (~75 s)
python3 scripts/stage.py                                                                              # 3. stage CSVs + manifest.csv
```
* **fetch.py** downloads all 19 publisher files that build.py reads (NRS, SG, data.gov.scot; about 400 MB, mostly the two data.gov.scot dwellings CSVs) into `raw/`. It unzips the 5 zips to the exact paths build.py expects and checks each file's SHA-256 against `scripts/SOURCES_SHA256.txt`. A file already present with a matching checksum is not downloaded again. `--verify-only` never downloads. **A checksum mismatch is a hard failure.** It means the publisher has replaced the file (for example SPD 2026/2 superseded by the next release, or a data.gov.scot resource updated in place), so outputs would differ. In that case review `sources.md` and update the checksum deliberately; never update it just to make the check pass.
* **Manual input: national park overlay.** `dz_park_overlay.csv` is a Scot-LAND GIS product (SG national park boundaries plus SPD 2026/2 Census 2022 households). It has no publisher URL, so fetch.py cannot download it. Get it from Scot-LAND GIS (`data/processed/gis/dz_park_overlay.csv`) and do one of the following:
  * pass `--park-overlay PATH` to fetch.py, which copies it to `raw/dz_park_overlay.csv` and verifies it;
  * or set `DZ_PARK_OVERLAY=PATH` (or pass `--park-overlay PATH`) when running build.py.

  build.py stops with a clear error if the overlay is missing. Both accepted overlay versions are listed in `SOURCES_SHA256.txt`: the current one, with integer `vintage`, and the earlier one, with `DZ2011`/`DZ2022`. Both give identical outputs.
* **Configuration** (CLI arg, then env var, then default):

  | Setting | CLI arg | Env var | Default | Used by |
  |---|---|---|---|---|
  | Project root | `--root` | `DZ_ROOT` | parent of the script's folder | all three scripts |
  | Raw inputs | `--raw` | `DZ_RAW` | `ROOT/raw` | fetch.py, build.py |
  | Build output | `--out` | `DZ_OUT` | `ROOT/out` | build.py, stage.py |
  | Park overlay | `--park-overlay` | `DZ_PARK_OVERLAY` | `RAW/dz_park_overlay.csv` | build.py; fetch.py copies it in |
  | Staging folder | `--dest` | `DZ_STAGE` | `ROOT/data/processed/datazones` | stage.py |
  | Checksum file | `--sha-file` | `DZ_SHA_FILE` | `SOURCES_SHA256.txt` next to fetch.py | fetch.py |
* **Notes.**
  * statistics.gov.scot was unreachable from the build box, so the data.gov.scot resource URLs are used.
  * `DZ22_Lookup.csv` is cp1252-encoded, and build.py reads it as such.
  * `manifest.csv` has an `attribution` column with the OGL attribution line for each file. stage.py refuses to stage a public file without one.
* **Reproducibility check (6 Oct 2026):**
  * fetch.py run against the existing `raw/` verified all 19 files plus the overlay without downloading anything.
  * A spot check downloaded 4 sources live from their URLs; all checksums matched.
  * build.py followed by stage.py, before the v0.7 flags, reproduced all 10 staged CSVs byte-identically: the sha256 in manifest.csv was unchanged.
  * After the v0.7 flags, 9 CSVs are still byte-identical. `zone_spine.csv` differs only in the `flags` cell of the 4 newly flagged zones (S01010206, S01010226, S01010227, S01011598).

## Tables

### 1. `zone_spine` (14,368 rows = 6,976 + 7,392)
`code, vintage, name, iz_code, la_code, la_name, population, pop_year, households, hh_year, dwellings, dw_year, vacant_share, second_home_share, share_year, in_ros_price_file, flags`
* **Hierarchy.** DZ2011→IZ2011→LA comes from the SG SIMD 2020v2 DZ look-up (S11). DZ2022→IZ2022 comes from the NRS OA22_DZ22_IZ22 lookup (S4), and DZ2022→LA from the NRS SAPE file (S6). Both were cross-checked against the SPD 2026/2 postcode index, with 0 mismatches for IZ and LA in both vintages. There are 1,279 IZ2011 and 1,334 IZ2022 zones and 32 LAs. No IZ spans two LAs.
* **population.** NRS small area population estimates, each on its own vintage. **DZ2011 is mid-2022** (the latest on 2011 zones, corrected Feb 2026; Scotland total 5,447,000). **DZ2022 is mid-2024** (published 1 Sep 2026; total 5,543,300). The years differ, so `pop_year` says which.
* **households** = NRS *occupied dwellings*, the official household proxy, for Sept 2025. **dwellings** = NRS council-tax `dwellings_total`, Sept 2025 (rules v0.5 surface denominator). `vacant_share` and `second_home_share` are vacant ÷ total and second homes ÷ total for 2025. All of these come from the NRS household-estimate files on each vintage, so there are no nulls and nothing is crosswalked.
* **in_ros_price_file.** Whether the code appears in the data.gov.scot RoS house price file, which is DZ2011-only: 6,970 of 6,976 do. It is NULL on DZ2022, because the file isn't published on 2022 zones.
* **flags** (`;`-separated):
  * `absent_from_ros_price_file` (6 zones): S01007788 Whitfield-07, S01010206 Petershill-04, S01010226 Sighthill-02, S01010462 Knightswood Park East-03, S01010493 Drumchapel North-03, S01011598 Cliftonville-01. The codes are missing from the file entirely. That is not the same as zero sales.
  * `population_zero` (S01010206, S01010226: demolished, 0 population and 0 dwellings).
  * `no_census2022_household_residents` (S01010206, S01010226, S01010227).
  * `zero_dwellings` (team rule v0.7): 2025 `dwellings_total` = 0. Exactly S01010206, S01010226 and S01010227 on DZ2011; none on DZ2022.
  * `pop_dwellings_mismatch` (team rule v0.7): `pop_year` ≠ `dw_year` **and** (population < 0.5 × households, or households = 0 with population > 0). Exactly 2 zones, both DZ2011:
    * S01011598 Cliftonville-01: population 8 (SAPE mid-2022) against 163 occupied dwellings (2025);
    * S01010227 Sighthill-03 (demolished): population 1 (mid-2022) against 0 households (2025), caught by the households = 0 clause.

    Values are left as published.
  * build.py asserts both lists, so any change in the source data stops the build.
  * `flags` is always a string, and an empty value means no flags; it is never NULL in build.py. A CSV can't tell an empty string from a missing value, so read it as text: in pandas use `pd.read_csv(path, converters={"flags": str})`, which gives "" rather than NaN (avoid `keep_default_na=False`, which turns empty numeric cells into strings); in Postgres use `\copy ... CSV HEADER FORCE_NOT_NULL (flags)`. This also removes the pandas DtypeWarning on `dwellings_by_year.csv`, whose `flags` column is mostly empty.

### 2. `dz_crosswalk_people` (10,473 rows)
`dz2011, dz2022, weight, reverse_weight, method, basis_count`. Many-to-many, built from codes only (no geometry).
* **Basis.** Census 2022 **household population** at postcode level, from the NRS Census 2022 index `Postcode_To_OA.csv` (`PopulationCount` = "2022 Census household population count at postcode level"; 153,192 frozen census postcodes; total 5,330,984). Each postcode gets its **DZ2022** through its frozen OA2022 and the NRS OA22→DZ22 lookup (OAs nest in DZ2022). It gets its **DZ2011** from the SPD 2026/2 record that carries the Census 2022 counts (one record per postcode). `basis_count` is the household population in each (dz2011, dz2022) intersection.
* **weight** = the share of the dz2011 zone's 2022 household population that sits in dz2022. Weights sum to 1 for each dz2011.
* **reverse_weight** = the share of the dz2022 zone's household population that came from dz2011. Reverse weights sum to 1 for each dz2022. Use `weight` to push DZ2011 counts onto DZ2022, and `reverse_weight` for DZ2022 composition (for example SIMD shares).
* **method.** `pop_hhres_2022` covers 10,470 rows. The other 3 rows are `fallback_census2011_pop_terminated_postcodes`, for the three DZ2011 zones that had **no household residents at Census 2022** (S01010206, S01010226 and S01010227, demolished Glasgow estates). Each is mapped to the DZ2022 holding its terminated postcodes, weighted on 2011 Census postcode population. These rows have reverse_weight 0, so they add nobody to any DZ2022.
* **QA.**
  * All 6,976 DZ2011 and all 7,392 DZ2022 codes are covered.
  * The largest deviation of a weight sum from 1 is 2e-16 in memory and 1.3e-15 after CSV round-trip, against a tolerance of 1e-6.
  * The postcode household population summed to OA matches UV101b OA household residents (5,332,173) exactly in 26,980 of 46,363 OAs; the difference is at most 14 people per OA, mean 1.2, from cell-key perturbation.
  * **One-to-one:** 3,145 pairs, where the dz2011 sits wholly in one dz2022 and that dz2022 draws only from it.
  * **Split:** 2,369 DZ2011 zones map to more than one DZ2022 (2,117 once intersections under 2% on both sides are ignored). 4,607 DZ2011 zones sit wholly in one DZ2022, and 4,874 have at least 98% in one.
  * **Merged:** 2,498 DZ2022 zones draw from more than one DZ2011 (2,106 material at 2%). 4,894 DZ2022 zones draw from a single DZ2011, and 5,277 draw at least 98% from one.
  * **Caveat:** SPD best-fits each postcode to one DZ2011, so postcodes split across DZ2011 boundaries create slivers. 100 census postcodes (1,417 people) have a *current* SPD DZ2022 that differs from their frozen census OA's DZ2022; the frozen census assignment is used.

### 3a. `simd2020v2_dz2011` (6,976 rows)
SIMD 2020v2 rank, vigintile, decile and quintile, plus the 7 domain ranks and the 2017 population and working-age population as published, from the SG look-up (S11). Ranks match the SG ranks workbook (S12) exactly, with 0 mismatches across all 8 rank columns, and the overall rank is a permutation of 1–6,976. Deciles hold 697 or 698 zones each. Domain ranks keep the official **half-ranks for ties** (for example 5955.5): income 700, employment 568, crime 156, housing 472. That is why they are `numeric(6,1)`.

### 3b. `simd2020v2_access_indicators_dz2011` (6,976 rows, DZ2011 only, not crosswalked)
Raw access-domain indicators in **minutes**, as published in the SG indicators workbook (S13, sheet "Data"): `drive_petrol, drive_GP, drive_post, drive_primary, drive_retail, drive_secondary, PT_GP, PT_post, PT_retail`. The table also carries `broadband`, which is a **0–1 proportion** of premises without superfast broadband (≥30 Mb/s), not minutes. No ranks or scores are included. All 6,976 codes are in zone_spine. Nulls: 0 in every minutes column; broadband has 2 nulls (S01010206 and S01010226, shown as `*` in the source and flagged `broadband_suppressed_in_source`). Every row carries the flag `dz2011_only_not_crosswalked`.

### 3c. `simd2020v2_on_dz2022` (7,392 rows)
For each DZ2022, the share of its 2022 household population in each SIMD 2020v2 decile and quintile (`decile_1_share … decile_10_share`, `quintile_1_share … quintile_5_share`). These are computed as the sum of `reverse_weight` over source DZ2011 zones in each band. The table also gives `modal_decile`, `modal_decile_share` and `n_dz2011_sources`. **Ranks are never averaged.** Shares sum to 1 (largest deviation 2e-16). 5,362 zones take ≥99.9% of their people from one decile. SIMD 2020v2 is DZ2011-based, and the next SIMD is expected on DZ2022.

### 4. `dwellings_ct_band` (161,277 rows)
`code, vintage, count_year, band_a … band_h, total_dwellings`, from the NRS dwelling estimate files: Assessors' portal, December of each year.
* **Coverage:** DZ2011 for 2005–2025, from `dwellings-estimate-by-2011-data-zones.xlsx`, where 2005–2013 are NRS rebased from 2001 zones. DZ2022 for 2024–2025.
* 3 rows are absent rather than filled: S01010206, S01010226 and S01010227 have no row in the 2022 sheet.
* Bands A–H sum to `total_dwellings` in every row.
* The data.gov.scot "Dwellings by Council Tax Band **Summary**" datasets (2022 Data Zones; Current Geographic Boundaries) only publish **grouped bands A–C / D–E / F–H** plus the total. So A–H come from the NRS source files, and the grouped sums were reconciled against both summaries: 7,392 rows (DZ2022 2024) and 132,541 rows (DZ2011 2005–2023), **0 mismatches**.

### 5. `dwellings_by_year` (98,496 rows): canonical dwellings table, long format
`code, vintage, count_year, dwellings_total, occupied, vacant, second_homes, long_term_empty, unoccupied_exempt, occupied_exempt, single_adult_discount, vacant_share, second_home_share, assessor_dwellings_dec, source_file, source_sheet, flags`
* Source: the NRS council-tax small-area **household & dwelling estimates** (September of `count_year`). Per rules v0.5, surface totals use `dwellings_total`. `assessor_dwellings_dec` is the December Assessors' count from table 4, kept for reference.
* **Published coverage:**
  * **DZ2011, 2014–2025**: total, occupied, vacant and second homes in every year, from `household-estimates-by-2011-data-zones.xlsx`, sheets "2014"–"2025".
  * **DZ2022, 2024 and 2025 only**, from `household-estimates-by-2022-data-zones-24-25.xlsx`, sheets "2024" and "2025".
  * NRS has **not** published DZ2022 estimates before 2024, so those years are absent rather than filled. `dwellings_by_year_coverage.csv` lists, for every vintage and year from 2005 to 2025, whether each series exists and which file and sheet it comes from.
* **2025 totals:**
  * DZ2011: dwellings_total 2,757,376, occupied 2,647,347, vacant 89,516, second homes 20,876 (Assessors' Dec count 2,763,896).
  * DZ2022: dwellings_total 2,757,323, occupied 2,647,296, vacant 89,497, second homes 20,876.
* **flags:**
  * `zero_dwellings` (27 rows): the demolished zones S01010206 (2016+), S01010226 (2017+) and S01010227 (2018+).
  * `assessor_dwellings_missing_for_zone_year` (3 rows): 2022 for those same three zones.
* occupied + vacant + second_homes ≠ dwellings_total in 7,191 rows, by at most ±3. This comes from NRS rounding and council-tax-base constraining, as stated on the NRS cover sheet. Values are left exactly as published.

### 6. `nrs_dwelling_mix_2011_fallback` (27,904 rows): HISTORIC FALLBACK, DZ2011 ONLY
Dwelling type (detached, semi-detached, terraced, flat, unknown, all) and rooms (1–9, 10+, unknown) for **2014–2017**, from data.gov.scot "Dwellings by Type" / "Dwellings by Number of Rooms" on 2011 zones. NRS stopped publishing type and rooms after 2017, and there are none on DZ2022. Every row has `status = historic_fallback_dz2011_only`. Do not present it as current; current mix comes from GIS's EPC rollup. The 2017 figures match the NRS xlsx 2017 sheet exactly (0 mismatches, with rooms 7+ aggregated). In 2015, type parts ≠ all in 278 zones (by 1–28), because NRS *estimated* 2015 type from other years (NRS note 6); the data is left as published.

### 7. `dz_planning_authority` (14,455 rows)
`code, vintage, plan_making_authority, plan_making_authority_name, deciding_authority, deciding_authority_name, share, area_share, hh_2022, hh_2022_zone_total, method, note`, keyed `(code, vintage, plan_making_authority)`.
* Built from GIS's `dz_park_overlay.csv` (S19). There are 34 plan-making authorities: 32 councils, **Loch Lomond & The Trossachs NP (S21000002)** and **Cairngorms NP (S21000003)**.
* **Zones outside parks:** the council is both plan-making and deciding authority, with share 1 (`council_outside_park`).
* **Zones touching a park:** split by Census 2022 postcode households (`hh_share` from GIS). There is one park row, plus a council row for the remainder if any.
  * **LL&T:** plan-making = deciding = LLTNP.
  * **Cairngorms:** plan-making = CNPA, deciding = the host council (note: CNPA calls in larger applications).
* Methods: `wholly_in_park` (24 DZ2011 / 29 DZ2022 zones), `park_split_census2022_postcode_households` (104 / 87 rows) and `council_outside_park` (6,895 / 7,316).
* Zones that overlap a park by area but have no park households get a park row with share 0. `area_share` keeps the polygon share, so Valuation can use area if needed.
* **QA:** shares sum to 1 for every zone. Park household totals are **LL&T 6,835 and Cairngorms 8,518** on both vintages, as required. No zone touches both parks.

## Not built / limits
* Planning authority deciding rules are structural only. Cairngorms call-ins aren't zone-attributable, so they appear as a note.
* Population years differ by vintage (mid-2022 on DZ2011, mid-2024 on DZ2022), because NRS has published nothing later on 2011 zones.
* statistics.gov.scot was unreachable from the box, so its datasets came from their data.gov.scot resources or the NRS/SG originals.
