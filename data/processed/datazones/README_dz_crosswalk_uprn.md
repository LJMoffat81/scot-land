# DZ2011 → DZ2022 address-point (UPRN) crosswalk

Built 2026-10-13 by Scot-LAND GIS (`scripts/build_dz_crosswalk_uprn.py`). Staged into the repo for surface-rent vintage conversion (PR B). Column names use the datazones crosswalk key `(dz2011, dz2022)`; `weight` is the UPRN share of the 2011 zone (`share_of_dz2011` in the GIS build).

## Files
- `dz2011_dz2022_uprn_weights.csv` — 14,458 pairs; all 6,976 DZ2011 and 7,392 DZ2022 zones; weights sum to 1 per DZ2011
- `dz_crosswalk_zero_uprn.csv` — 1,069 area-overlap pairs with zero UPRNs (`kind=overlap_pair`); not in the weight file; receive no rent
- `qa_dz_crosswalk_uprn.json` — build QA counts

## Sources
- OS Open UPRN, release 202609 (EPSG:27700). OGL v3.
- Data Zone 2011 and 2022 boundaries, Scottish Government (spatialdata.gov.scot), EPSG:27700. OGL.
- Census 2022 Output Area population-weighted centroids with household counts (HHcount), NRS. OGL.

**Attribution:** Contains OS data © Crown copyright and database right 2026. Contains NRS data © Crown copyright 2026, licensed under the Open Government Licence v3.0. Contains Scottish Government data © Crown copyright 2026 (OGL).

## Method
Each UPRN inside the Scotland DZ2011 extent is placed in a DZ2011 and a DZ2022 polygon (point-in-polygon, intersects). `weight` = uprn_count / DZ2011 total. `hh2022_share` is the Census 2022 household check share (blank for five DZ2011 zones with no OA centroid). `share_diff_flag` = |weight − hh2022_share| > 0.2. GIS `method` = `uprn_point_in_polygon`. Surface rent stamps `crosswalk_method=address_uprn` (never population or area; never `value_weighted` for this path).

## Runtime minimum-share filter (default ON)
Drop a pair only when weight < 1% of its 2011 zone **and** uprn_count < 5; redistribute the dropped share within the same 2011 zone. Expected: 2,848 of 14,458 pairs dropped (5,197 UPRNs); every 2011 and 2022 zone still covered; weights still sum to 1.

## Caveats
Open UPRN covers every addressable object (not class-filtered). Many sub-1% pairs are boundary slivers. Zero-UPRN DZ2011/DZ2022 zones: none in this build.
