# epc_dz_rollup.csv — domestic EPC rollup per data zone

Built 6 Oct 2026 (BST) by Scot-LAND GIS. Experimental input to the Wealth Engine, not an official statistic.
Script: `/workspace/scotland-gis/scripts/build_epc_rollup.py`.

## Rows
(Updated 6 Oct 2026 BST: `recent10_*` columns added; then floor-area mean/sum and house/flat means added. All earlier columns are unchanged, checked with pandas assert_frame_equal against both previous versions. 83 columns now.)

14,368 = 6,976 DZ2011 + 7,392 DZ2022. Key `(code, vintage)`, vintage is the integer 2011 or 2022 (team rule, 6 Oct 2026; codes asserted within the official range for their vintage). Every zone in the SG boundary files is present.

## Sources (all no-account downloads, checked 6 Oct 2026)
| Source | URL | Licence |
|---|---|---|
| Domestic EPCs, Extended Historic Dataset to Q2 2026 (Dec 2008–Jun 2026, extracted 1 Sep 2026) | https://data.gov.scot/dataset/domestic_energy_performance_certificates___extended_historic_dataset_to_q1_2026 | Non-address fields OGL v3. ADDRESS1/2, POST_TOWN and POSTCODE are Royal Mail address data (see note below) |
| Domestic EPCs, valid dataset to Q2 2026 (used for QA only) | https://data.gov.scot/dataset/domestic_energy_performance_certificates___dataset_to_q1_2026 | as above |
| NRS Scottish Postcode Directory 2026/2, Postcode Index (published 18 Aug 2026; July 2026 PAF) | https://www.nrscotland.gov.uk/publications/scottish-postcode-directory-20262/ | OGL v3 (NRS: "Indexes and Look-ups ... Open Government Licence") |
| Scot-LAND Data Zones `dwellings_by_year.csv` → `dwellings_total`, count_year 2025 (NRS household estimates by 2011/2022 Data Zone, council-tax dwellings, Sep 2025; published 30 Jul 2026) | https://www.nrscotland.gov.uk/publications/small-area-statistics-on-households-and-dwellings-2025/ | OGL v3 |
| SG Data Zone boundaries 2011 and 2022 (zone universe only) | https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip , ..._2022.zip | OGL v3 |

statistics.gov.scot (the URL in the brief) was down on 6 Oct 2026: HTTP 500/502 and TLS resets. The same files are linked from the Scottish EPC Register's Data Extracts page to data.gov.scot, which is where I downloaded them.

**Attribution:** Contains Scottish Government EPC data licensed under the Open Government Licence v3.0. Contains NRS data © Crown copyright and database right 2026. Incorporates data from PAF® the copyright in which is owned by Royal Mail Group Limited. Contains OS data © Crown copyright and database right 2026.

**Royal Mail address data:** postcodes were used only inside the box to place certificates in zones. No address or postcode leaves the box, and the output holds only zone aggregates. Royal Mail's notice on the EPC data permits energy-efficiency research and the statutory copyright exceptions, such as non-commercial research. A land-value use falls outside the listed energy-efficiency purposes, so it relies on the non-commercial research exception. **If Scot-LAND is ever used commercially, this needs a licence check.**

## Method
1. Loaded all 3,787,063 extended-historic EPC rows (the parser rejected 6 rows with unescaped quotes in the address field).
2. **Latest certificate per property:** partition by `BUILDING_REFERENCE_NUMBER` (the SEPCR property ID). Keep the row the register flags `HISTORIC=False`. Ties break on latest lodgement date, then inspection date. Result: 2,021,453 properties. No OSG UPRN maps to more than one register ID. QA: all 1,496,601 properties in the separate "valid EPC" file are in the set, and 95.8% carry the identical certificate (RRN).
3. **Postcode → zone** using NRS SPD 2026/2, live and deleted postcodes. Split postcodes (A/B parts) go to the part with the most 2022 Census households. For postcodes that were deleted and reintroduced, the live record is preferred. The SPD's own best-fit DZ2011 and DZ2022 codes are used.
4. Shares are taken over all latest certificates in the zone, including an `_unknown` category, so each family sums to 1:
   - property type: house, flat, bungalow, maisonette, park home
   - built form: 6 SAP classes
   - construction age band: 11 SAP bands
5. Floor area uses `TOTAL_FLOOR_AREA` only where it is between 10 and 1,500 m². 212,886 raw rows have 0, which is treated as missing. 97.7% of latest certificates are valid. Columns: `tfa_median_m2`, `tfa_q1_m2`, `tfa_q3_m2`, `tfa_iqr_m2`, and `tfa_n` (the certificates used).
6. `share_lodged_last_10y` is the share of certificates lodged on or after 1 Jul 2016 (staleness indicator).
7. **Denominator (team rule, 6 Oct 2026):** `dwellings_total_2025` is Scot-LAND Data Zones' `dwellings_total` (`/workspace/scotland-datazones/data/processed/datazones/dwellings_by_year.csv`, count_year 2025, same vintage; NRS household estimates, council-tax based, Sep 2025). `coverage_share` = cert_count / dwellings_total_2025. The previous provisional column `dwellings_nrs_2025` (NRS assessor count, Dec 2025, total 2,763,896) has been **removed** and the script (`build_epc_rollup.py`) now reads Data Zones' file directly. `dwellings_flag` is blank, `zero_dwellings_2025` (coverage left blank) or `missing_count_2025` (never filled from another year; no zone has this). The assessor count differed from dwellings_total in 7,072 of 14,368 rows (median difference 0, max 550, e.g. new-build/student blocks in Glasgow city centre and Laurieston), so zone-level coverage moved by up to 1.19 even though the national figure moved only 0.731 → 0.733.
8. **Suppression:** any zone with fewer than 5 certificates gets cert_count, coverage and all statistics blanked, and `suppressed=True`. Floor-area statistics are also blanked where `tfa_n` < 5. In this build no zone fell below 5, so nothing was suppressed.

## QA results
- Unmatched postcodes: 936 of 2,021,453 latest certificates (**0.046%**) had no SPD match and were excluded. 7,212 matched only a deleted postcode, which was kept. 0 had malformed postcodes.
- Postcode-derived DZ2011 agrees with the EPC's own `DATA_ZONE_2011` field for **99.73%** of 1,941,989 certificates.
- Certificates in split or straddling postcodes, where different SPD records give different zones: 39,658 for DZ2011 and 41,192 for DZ2022 (about 2%). These were assigned to the most-populated part, as above.
- All 6,976 / 7,392 zones have at least 5 certificates. Share families sum to 1 within 5e-16.
- National coverage: 2,020,517 certificates / 2,757,376 dwellings_total (DZ2011; 2,757,323 for DZ2022) = **0.733**. With the old assessor denominator (2,763,896) it was 0.731.
- Coverage-share quantiles on dwellings_total (min / p5 / p25 / median / p75 / p95 / max):
  - DZ2011: 0.24 / 0.51 / 0.62 / 0.71 / 0.80 / 0.93 / 2.33
  - DZ2022: 0.18 / 0.51 / 0.62 / 0.71 / 0.81 / 0.95 / 2.18
- Coverage above 1 (dwellings_total denominator): 137 DZ2011 zones and 222 DZ2022 zones. Above 1.2: 23 and 40. (On the old assessor denominator: 110/193 and 19/31.) These are mostly regeneration areas in Glasgow and elsewhere. The latest-ever certificate survives for demolished stock, and new-build replacement adds more. Treat coverage above 1 as a flag, not an error.
- 3 DZ2011 zones have 0 dwellings in 2025, so their coverage_share is blank: S01010206 Petershill-04, S01010226 Sighthill-02, S01010227 Sighthill-03.

## Caveats
- EPCs are lodged on sale, let or construction, so the stock is biased towards transacted and rented homes. Owner-occupied homes that haven't sold since 2008 are under-represented.
- The historic dataset includes certificates for buildings since demolished or merged.
- Age band and built form are assessor-recorded RdSAP fields and are often defaulted.

## recent10_* columns (added 6 Oct 2026)
Script: `scripts/build_epc_recent10.py` (step 2, run after `build_epc_rollup.py`). QA: `qa_epc_recent10.json`.
- **Universe:** certificates with `LODGEMENT_DATE` from 1 Jul 2016 to 30 Jun 2026 inclusive. Within that window, the latest certificate per `BUILDING_REFERENCE_NUMBER` (ties: register `HISTORIC=False` first). 1,497,380 properties; one row is dated after 30 Jun 2026 and is excluded. This effectively reproduces the published "valid EPC" file: 1,496,573 of its 1,496,601 properties (99.998%) are in the recent10 set.
- **Same lookup and rules as the main columns:** same SPD postcode lookup, category maps, floor-area range (10–1,500 m²) and <5 suppression.
- **Columns:**
  - `recent10_cert_count`
  - `recent10_pt_*_share`, `recent10_bf_*_share`, `recent10_age_*_share` (each family sums to 1, including `_unknown`)
  - `recent10_tfa_n`, `recent10_tfa_median_m2`, `recent10_tfa_q1_m2`, `recent10_tfa_q3_m2`, `recent10_tfa_iqr_m2`
  - `recent10_coverage_share` = recent10_cert_count / dwellings_total_2025
  - `recent10_suppressed`
- **QA:**
  - Unmatched postcodes: 735 (0.049%).
  - Suppressed (<5 certificates): 3 DZ2011 zones (S01010206, S01010226, S01010227 — Petershill/Sighthill, cleared) and 0 DZ2022 zones.
  - Share families sum to 1 within 5e-16. Floor area is valid on 100% of recent certificates.
  - National recent10 coverage is 0.543, against 0.733 all-time (dwellings_total denominator). Zone quantiles (DZ2022):
    - p5: 0.33
    - median: 0.51
    - p95: 0.81
    - max: 1.59
  - Median absolute difference from the all-time columns: flat share 0.013; floor-area median 1 m².
- **Interpretation:** recent10 is fresher, and closer to the stock that has sold or let since 2016. All-time has wider coverage, but includes demolished stock and pre-2016 assessments. Valuation can test both.

## Floor-area means and sums (added 6 Oct 2026)
Script: `scripts/build_epc_tfa_means.py` (step 3; reads the step-1 and step-2 joins). QA: `qa_epc_tfa_means.json`. The same floor-area filter applies (10–1,500 m²; 0 or missing excluded). Each column comes in two versions: plain (all-time latest certificate per property) and `recent10_` (latest certificate lodged 1 Jul 2016–30 Jun 2026).

| column | meaning |
|---|---|
| `tfa_n` / `recent10_tfa_n` | (already present) count of certificates with valid floor area = the divisor for the mean |
| `tfa_mean_m2` / `recent10_tfa_mean_m2` | mean floor area |
| `tfa_sum_m2` / `recent10_tfa_sum_m2` | sum of valid floor area, written to 2 decimals so that sum / tfa_n reproduces the mean exactly; use these for totals |
| `tfa_n_house`, `tfa_mean_house_m2` (+ `recent10_`) | houses = EPC property type **House + Bungalow** |
| `tfa_n_flat`, `tfa_mean_flat_m2` (+ `recent10_`) | flats = EPC property type **Flat + Maisonette** (park homes are in neither group) |

**Suppression:**
- Mean and sum are blank when the zone is suppressed (<5 certificates) or `tfa_n` < 5.
- House and flat means are blank when that cell has fewer than 5 certificates with valid floor area. The cell counts stay visible, except in suppressed zones.

**QA:**
- `tfa_n` equals the count behind the new columns in every zone. Sum = mean × n within float error, with relative error under 5e-6 after CSV rounding of the mean.
- National mean is 90.7 m² (all-time) and 89.6 m² (recent10).
- The zone mean exceeds the zone median by a median 5.6 m², which is why totals must use means.
- House mean present for 7,070 DZ2022 / 6,680 DZ2011 zones; flat mean for 6,180 / 5,950. Recent10: house 7,025 / 6,646; flat 6,058 / 5,824.
- Only the 3 suppressed DZ2011 zones in recent10 have a blank overall mean.

## Team rules applied (6 Oct 2026)
Built into the three generating scripts via `scripts/zone_rules.py` (no post-processing step):
- `vintage` is written as the integer 2011 or 2022 (it was 'DZ2011'/'DZ2022');
- codes are asserted to fall in the official ranges (2011: S01006506–S01013481; 2022: S01013482–S01020873);
- `dwellings_nrs_2025` → `dwellings_total_2025` (Data Zones `dwellings_by_year`, count_year 2025, joined on (code, vintage)); `dwellings_flag` added; `coverage_share` and `recent10_coverage_share` recomputed; `dwellings_source` = "Scot-LAND Data Zones dwellings_by_year (NRS council-tax dwellings, Sept 2025), count_year 2025".
- The latest-certificate ordering now has a deterministic final tie-break (postcode, property type, built form, age band, floor area). The report reference number is blank on tied rows, and a rerun had flipped one tied certificate (BRN 1000022660, Mid- vs End-Terrace). With the tie-break every non-denominator cell is identical to the previous build.

The table has 84 columns: code, vintage, cert_count, dwellings_total_2025, dwellings_flag, coverage_share, suppressed, … , dwellings_source.
