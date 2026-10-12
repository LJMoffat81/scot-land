# Census 2022 dwelling counts (including unoccupied / second homes): what is and isn't open

Checked 6 Oct 2026.

## Finding: Scotland's Census 2022 publishes NO open dwelling or occupancy-status counts at OA2022 or data zone level
- **OA tables:** the 2022 output-area bulk files on https://www.scotlandscensus.gov.uk/documents/2022-output-area-data/ (OGL v3) are:
  - topic tables `Census-2022-Output-Area-v1.zip`: UV101b–UV902, 71 tables
  - multivariate tables `OutputArea.zip`: MV101–MV901, 47 tables

  All housing tables (UV401–UV408, UV415, MV401–MV415) have populations of "All occupied households", "All people in households" or "All occupied household spaces". None counts dwellings or unoccupied household spaces. A text search of every file for unoccupied / second residence / holiday / vacant / dwelling found nothing.
- **NRS says so itself:** the Census 2022 Housing report (last updated 22 Aug 2024) states: *"The census figures in this section are counts of households (groups of people). They are not counts of the accommodation (actual houses, flats, etc.). And they do not include empty properties. The Scottish Government publishes data on housing stocks which provides a better indication of housing supply by tenure."*
- **The metadata variable exists but no table uses it:** the census metadata page for the variable "Occupancy status" (occupied / second residence or holiday home / vacant) exists. Its text is carried over from 2011, and I found no 2022 table using it.
- **Not a 2022 figure:** the "101,000 unoccupied household spaces, 36% second or holiday homes" figure on scotlandscensus.gov.uk is from the **2011** "at a glance" page.

So `dz_brma_share_dwellings.csv` and a dwelling-weighted park overlay were **not built**, as instructed.

## What does exist openly
1. **NRS Household estimates by 2022 Data Zone and by 2011 Data Zone, 2014–2025** (council-tax based, Sep 2025; published 30 Jul 2026; OGL)
   - Source: https://www.nrscotland.gov.uk/publications/small-area-statistics-on-households-and-dwellings-2025/
   - Contents: total dwellings, occupied, vacant, unoccupied-exempt, long-term empty, second homes, single-adult discount.
   - Scotland 2025 totals: 2,757,323 dwellings, 2,647,296 occupied, 89,497 vacant, 20,876 second homes.
   - **Data zone level only, so no sub-zone placement is possible.**
   - Holiday lets available for 140+ days a year pay non-domestic rates and are **not** counted as second homes.
2. **NRS Dwelling estimates by DZ** (assessor total dwellings Dec 2025, council tax band, density). Formerly the provisional EPC denominator; replaced on 6 Oct 2026 by Data Zones' `dwellings_total` (item 1, council-tax Sep 2025).
3. **Census 2011 KS401SC "Dwellings, household spaces and accommodation type" at OA2011** (OGL; 2011 OA bulk download https://www.scotlandscensus.gov.uk/documents/2011-census-table-data-output-area-2011/)
   - Includes "household spaces with no usual residents", split into second residence/holiday accommodation and vacant.
   - It's the only open sub-zone dwelling count, but it is 15 years old. Not built; can be if wanted.
4. **Postcode-level Royal Mail delivery-point and household counts in the SPD:** PSGA members only, or charged. **Not open.**

## What I built instead: sensitivity bounds
These are in `alt/`, made by `scripts/build_alt_dwelling_bounds.py`, with QA in `alt/qa_alt_dwelling_bounds.json` and `alt/qa_islands.json`.

**Method:** for every zone that is split (across BRMAs, or partly in a park), occupied dwellings are spread like the published Census 2022 household share. The zone's unoccupied dwellings (Scot-LAND Data Zones `dwellings_by_year`, count_year 2025: dwellings_total − occupied) then go either all outside (lower bound) or all inside (upper bound). `max_shift` is the largest possible change in the share. Zones wholly inside a park are fixed at 1.

| Table | Results |
|---|---|
| `alt/dz_brma_share_dwelling_bounds.csv` | 441 rows covering the 216 split zones (107 DZ2011 + 109 DZ2022). Median max_shift 0.027, p90 0.095, max 0.30. 57 zones could move by more than 0.05; these are mostly Highland Perthshire (Rannoch & Aberfeldy), Speyside, Loch Awe/Cowal and the Stirling Highland edge. |
| `alt/dz_park_overlay_dwelling_bounds.csv` | 157 rows. 49 rows are partly inhabited in a park. **LLTNP:** median max_shift 0.04 (max 0.24). **Cairngorms:** median 0.13–0.14 (max 0.21). |

**Dwellings in each park:**

| Park | Households in park (Census 2022) | Dwellings in park, 2022-zone bounds (Data Zones dwellings_total, count_year 2025) |
|---|---|---|
| Loch Lomond & The Trossachs | 6,835 | 7,340–8,640 |
| Cairngorms | 8,518 | 10,653–11,799 |

Partly-in-park Cairngorms zones have a median 16% unoccupied dwellings (2.6% nationally). So weighting by households understates in-park housing stock there, and the size of the error depends on which side of the park line the second homes sit, which no open data reveals.

**Islands:** 139 DZ2011 / 145 DZ2022 zones have more than half their households on islands. **None is split across BRMAs**, so their BRMA shares are 1.0 whatever the weighting. Their median unoccupied share is about 10% (against 2.5% on the mainland), which matters for denominators, not for the BRMA split.

**Coastal zones:** not separately classified. Only split zones can change, and the largest possible shifts are inland, in rural Highland Perthshire, Speyside and Argyll.

## Midpoint rule (Georgist v0.5), added 6 Oct 2026
Built by `scripts/build_alt_dwelling_bounds.py`; QA in `alt/qa_alt_dwelling_bounds.json`. Split zones use the midpoint of the dwelling bounds, and half the gap goes into the uncertainty band.

**`alt/dz_brma_share_dwelling_bounds.csv`** gains three columns:
- `share_mid_raw` = (lower + upper) / 2
- `share_halfwidth` = (upper − lower) / 2
- `share_mid` = share_mid_raw renormalised within each (code, vintage) so the shares sum to 1

QA:
- Raw midpoints already sum to exactly 1 in zones split across two BRMAs.
- They exceed 1 only in the 9 zones (27 rows) split across three or more BRMAs, where the raw sum ranges up to 1.039.
- Largest renormalisation adjustment: 0.0350 (S01013002, DZ2011, BRMA S33000008: 0.929 → 0.894).
- After renormalisation, max |Σ share_mid − 1| = 2.2e-16.
- Half-widths: median 0.015, p90 0.054, max 0.156.
- `share_halfwidth` is reported on the raw (un-renormalised) scale.

**`alt/dz_park_overlay_dwelling_bounds.csv`** gains `share_mid` and `share_halfwidth`. These are **not** renormalised, because the share is in-park versus out. Zones wholly inside a park have mid = 1 and half-width = 0.

Implied in-park dwellings (2025 stock, Data Zones dwellings_total) at the midpoint, ± half-width:

| Park | DZ2022 | DZ2011 |
|---|---|---|
| Loch Lomond & The Trossachs | 7,990 ± 650 | 7,938 ± 694 |
| Cairngorms | 11,226 ± 573 | 11,161 ± 764 |


**Team rules (6 Oct 2026), built into the generating scripts (`scripts/zone_rules.py`):** `vintage` is the integer 2011 or 2022 (was 'DZ2011'/'DZ2022') and every code is asserted to lie in the official range for its vintage (2011: S01006506–S01013481; 2022: S01013482–S01020873). Every other cell is byte-identical to the previous build. The alt dwelling-bounds files now read their dwelling counts directly from Scot-LAND Data Zones' `dwellings_by_year.csv` (count_year 2025, joined on (code, vintage)); these equal the NRS Sep 2025 household-estimate counts used before in all rows, so no bound moved. Bounds columns are renamed `dwellings_total_2025`, `dw_unoccupied_2025`, `second_homes_2025`, and `dwellings_flag` / `dwellings_source` are added (a zone with no 2025 count would be flagged `missing_count_2025` and left blank, never filled from another year; none is).
