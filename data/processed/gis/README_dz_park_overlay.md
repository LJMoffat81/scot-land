# dz_park_overlay.csv — data zones intersecting Scotland's two national parks

Built 6 Oct 2026 (BST) by Scot-LAND GIS. Script: `/workspace/scotland-gis/scripts/build_brma_park.py`.

## Columns
`code, vintage, park_code, park_name, area_share, hh_in_park, hh_total, hh_share, method, intersect_area_m2`
- `park_code` is the GSS code from the NRS SPD National Park 2010 lookup:
  - S21000002 Loch Lomond and The Trossachs National Park
  - S21000003 Cairngorms National Park
- `area_share`: share of the zone's polygon area inside the park.
- `hh_in_park` / `hh_total`: Census 2022 households at postcode points inside the park, and in the whole zone.
- `hh_share`: hh_in_park / hh_total. Where a zone has no household points, it falls back to area_share and `method` is flagged accordingly; no zone needed this fallback.
- `intersect_area_m2` is kept so users can filter boundary slivers.

## Rows
157 in total: 81 DZ2011 (LLTNP 41, CNP 40) and 76 DZ2022 (38 each). The table covers every zone with any positive-area overlap, including zones wholly inside a park (area_share ≥ 0.9999): 24 DZ2011 (LLTNP 8, CNP 16) and 29 DZ2022 (LLTNP 10, CNP 19).

## Sources
| Source | URL | Licence |
|---|---|---|
| Cairngorms National Park 2010 (designated boundary including the 2010 Perthshire extension; 4,528.1 km²) | https://maps.gov.scot/ATOM/shapefiles/SG_CairngormsNationalPark_2010.zip | OGL v3 |
| Loch Lomond & The Trossachs National Park 2002 (1,863.4 km²) | https://maps.gov.scot/ATOM/shapefiles/SG_LochLomondTrossachsNationalPark_2002.zip | OGL v3 |
| SG Data Zone boundaries 2011 / 2022 | https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip , ..._2022.zip | OGL v3 |
| NRS SPD 2026/2 Postcode Index (Census 2022 households, grid ref, zone codes, NationalPark2010Code) | https://www.nrscotland.gov.uk/publications/scottish-postcode-directory-20262/ | OGL v3 |

**Attribution:** Copyright Scottish Government, contains OS data © Crown copyright and database right 2026. Contains NRS data © Crown copyright and database right 2026.

## Method
1. Each zone polygon was intersected with each park polygon in EPSG:27700, after `make_valid`. Any positive area kept the zone.
2. Households: the same 141,760 Census 2022 postcode points as in dz_brma_share, placed in park polygons.
3. Zone totals come from the SPD's zone code for each postcode.

## QA
- Households in park by point-in-polygon equal the NRS SPD `NationalPark2010Code` flag exactly: LLTNP 6,835, CNP 8,518 (2022 Census households). 0 postcodes disagree.
- These totals are identical whether summed over DZ2011 or DZ2022 rows.
- No zone has park households without polygon overlap.
- Slivers: 8 DZ2011 and 12 DZ2022 rows have area_share < 0.1% and no park households. These are edge-digitising artefacts or real thin overlaps. They are kept as the brief asked, but `intersect_area_m2` lets users drop them (smallest is 0.2 m²).

## Caveat for the planning-authority lookup
LLTNP is the planning authority for all applications. In the Cairngorms, councils decide most applications and the park calls in larger ones, but the park writes the development plan for the whole area. Record the plan-making authority and the deciding authority separately.

## Dwelling weighting (checked 6 Oct 2026)
No open 2022 sub-zone dwelling counts exist (see `NOTE_census2022_dwellings.md`). `alt/dz_park_overlay_dwelling_bounds.csv` adds `dw_share_lower` and `dw_share_upper`, with 2025 total, unoccupied and second-home dwellings per zone (`dwellings_total_2025`, `dw_unoccupied_2025`, `second_homes_2025`, from Scot-LAND Data Zones `dwellings_by_year`, count_year 2025 = NRS council-tax dwellings, Sep 2025).

| Park | Households in park (Census 2022) | Dwellings in park, 2022-zone bounds (Data Zones dwellings_total, count_year 2025) |
|---|---|---|
| Loch Lomond & The Trossachs | 6,835 | 7,340–8,640 |
| Cairngorms | 8,518 | 10,653–11,799 |

Cairngorms edge zones are the most sensitive (median max shift 0.13). The `hh_*` columns in this table remain household-based.

Midpoint rule (Georgist v0.5): `alt/dz_park_overlay_dwelling_bounds.csv` now has `share_mid` (not renormalised) and `share_halfwidth`. In-park dwellings at the midpoint (DZ2022): LLTNP 7,990 ± 650, Cairngorms 11,226 ± 573.


**Team rules (6 Oct 2026), built into the generating scripts (`scripts/zone_rules.py`):** `vintage` is the integer 2011 or 2022 (was 'DZ2011'/'DZ2022') and every code is asserted to lie in the official range for its vintage (2011: S01006506–S01013481; 2022: S01013482–S01020873). Every other cell is byte-identical to the previous build. The alt dwelling-bounds files now read their dwelling counts directly from Scot-LAND Data Zones' `dwellings_by_year.csv` (count_year 2025, joined on (code, vintage)); these equal the NRS Sep 2025 household-estimate counts used before in all rows, so no bound moved. Bounds columns are renamed `dwellings_total_2025`, `dw_unoccupied_2025`, `second_homes_2025`, and `dwellings_flag` / `dwellings_source` are added (a zone with no 2025 count would be flagged `missing_count_2025` and left blank, never filled from another year; none is).
