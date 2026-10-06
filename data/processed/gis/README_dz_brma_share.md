# dz_brma_share.csv — share of each data zone's households in each Broad Rental Market Area

Built 6 Oct 2026 (BST) by Scot-LAND GIS. Script: `/workspace/scotland-gis/scripts/build_brma_park.py`.

## Columns
`code, vintage, brma_id, brma_name, household_share, hh2022_weight, method`
- `household_share`: share of the zone's 2022 Census households that fall in the BRMA. Renamed from `dwelling_share` on 6 Oct 2026 because **the weight is households, not dwellings**. For dwelling-based shares use `share_mid` in `alt/dz_brma_share_dwelling_bounds.csv`.
- `hh2022_weight`: the Census 2022 households behind that share.
- `method` is either `postcode_hh2022_points` or `area_share_fallback_no_hh_points`.

## Rows
14,593. DZ2011: 6,976 zones, 107 split across 2 or more BRMAs. DZ2022: 7,392 zones, 109 split.

## Sources
| Source | URL | Licence |
|---|---|---|
| SG Broad Rental Market Areas 2009 (18 BRMAs, EPSG:27700) | https://maps.gov.scot/ATOM/shapefiles/SG_BroadRentalMarketAreas_2009.zip | OGL v3 |
| NRS SPD 2026/2 Postcode Index: `CensusHouseholdCount2022`, grid reference, DZ2011/DZ2022 codes | https://www.nrscotland.gov.uk/media/hy3j3g1s/spd_postcodeindex_cut_26_2_csv.zip | OGL v3 |
| SG Data Zone boundaries 2011 / 2022 | https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip , ..._2022.zip | OGL v3 |

**Attribution:** Copyright Scottish Government, contains Ordnance Survey data © Crown copyright and database right 2026. Contains NRS data © Crown copyright and database right 2026.

## Method
1. Took the 141,760 postcodes with `CensusHouseholdCount2022` > 0, both live and since-deleted, totalling 2,508,715 households. Each was placed as a point at its SPD grid reference (EPSG:27700).
2. Each point was placed in a BRMA polygon. 27 points (583 households) fell just outside every BRMA polygon, on reclaimed waterfront at Granton (EH5) and Ardrossan and on island coasts. They were snapped to the nearest BRMA: median about 40 m, maximum 2.3 km (Uist), all in the obviously correct BRMA.
3. Zone membership uses the SPD's own DZ2011/DZ2022 code for each postcode. Share = households in BRMA / zone households.
4. Three DZ2011 zones have no household postcodes: S01010206, S01010226 and S01010227 (Petershill and Sighthill, Glasgow, cleared for regeneration). They use the zone-polygon area share instead, flagged in `method`. No DZ2022 zone needed the fallback.

## QA
- Shares sum to 1 per zone: max |sum − 1| = **0.0** for both vintages (tolerance 1e-9).
- Zone counts: 6,976 DZ2011 and 7,392 DZ2022, matching the boundary files.
- Postcode centroids falling outside their assigned zone polygon: 0.001% of households (DZ2011) and 0.000% (DZ2022).
- Postcode-level Census counts sum per DZ2022 to within ±72 of the boundary-file `hhcnt2022` (mean −0.07). This is NRS disclosure perturbation at postcode level.
- **Robustness check:** `alt/dz_brma_share_oa2022.csv` uses Census 2022 OA household counts placed at the NRS OA2022 population-weighted centroids (NRS Census 2022 WFS `CEN2022:OutputAreaCent2022`, a census geography under OGL). It also sums to 1 exactly. It finds fewer split zones (45 against 109 for DZ2022) because OA points are coarser. 24 zones per vintage differ by more than 0.05, max 0.21 (DZ2022) and 0.40 (DZ2011).

## Licence note (please read)
NRS's licensing page says "Scottish Postcode Directory – postcode boundaries and grid references" are restricted to PSGA members, while the "Indexes and Look-ups" are OGL. I used only the Postcode Index CSV, the OGL product, whose `GridReferenceEasting/Northing` columns gave the points. I did not use the separate restricted `Postcode_GridRef` shapefile: it was downloaded by mistake, never used, and deleted. The outputs contain no coordinates, only zone-level shares. If the team wants zero ambiguity, the OA2022-centroid version in `alt/` uses only census geography.

## Caveats
- BRMA boundaries are the 2009 SG version. Check they are still current for Local Housing Allowance before relying on them for rents.
- Household weights are from Census 2022 (March 2022). New-build postcodes after 2022 carry no weight.

## Dwelling weighting (checked 6 Oct 2026)
Census 2022 publishes no open dwelling or unoccupied counts below council level (see `NOTE_census2022_dwellings.md`), so no dwelling-weighted version was built. `alt/dz_brma_share_dwelling_bounds.csv` gives lower and upper bounds for the 216 split zones, putting each zone's 2025 unoccupied dwellings (Data Zones `dwellings_by_year`, count_year 2025) all outside or all inside each BRMA. Median max shift is 0.027; 57 zones could move by more than 0.05. Island zones are never split across BRMAs.

Midpoint rule (Georgist v0.5): `alt/dz_brma_share_dwelling_bounds.csv` now has `share_mid` (renormalised to sum to 1 per zone), `share_mid_raw` and `share_halfwidth`. The largest renormalisation adjustment is 0.035, in 9 zones split across three or more BRMAs. See `NOTE_census2022_dwellings.md`.


**Team rules (6 Oct 2026), built into the generating scripts (`scripts/zone_rules.py`):** `vintage` is the integer 2011 or 2022 (was 'DZ2011'/'DZ2022') and every code is asserted to lie in the official range for its vintage (2011: S01006506–S01013481; 2022: S01013482–S01020873). Every other cell is byte-identical to the previous build. The alt dwelling-bounds files now read their dwelling counts directly from Scot-LAND Data Zones' `dwellings_by_year.csv` (count_year 2025, joined on (code, vintage)); these equal the NRS Sep 2025 household-estimate counts used before in all rows, so no bound moved. Bounds columns are renamed `dwellings_total_2025`, `dw_unoccupied_2025`, `second_homes_2025`, and `dwellings_flag` / `dwellings_source` are added (a zone with no 2025 count would be flagged `missing_count_2025` and left blank, never filled from another year; none is).
