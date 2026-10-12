# Vacant & derelict land (SVDLS) and housing land supply (HLS): site layers and Data Zone rollups

Built 6 Oct 2026 (BST) by Scot-LAND GIS. Script: `scripts/build_svdls_hls.py`. QA: `qa_svdls_hls.json`. Box only; nothing pushed.

| File | Level | Rows | Notes |
|---|---|---|---|
| `dz_svdls_rollup.csv` | public_zone | 14,368 (6,976 DZ2011 + 7,392 DZ2022) | every zone, zeros where no site; key `(code, vintage)` |
| `dz_hls_rollup.csv` | public_zone | 14,368 | same key |
| `internal/dz_svdls_rollup_with_inspire.csv` | **internal** | 14,368 | same as the public rollup, but the 27 INSPIRE-outline sites use their RoS outline and get their own `ha_register_ros_inspire_outline` column |
| `svdls_sites.gpkg` (layer `svdls_sites`) | **internal** | 3,091 | full site geometry, EPSG:27700; 27 outlines come from RoS INSPIRE (not cleared for publication) |
| `hls_sites.gpkg` (layer `hls_sites`) | **internal** | 6,166 | Spatial Hub HLS geometry (make_valid), EPSG:27700 |

`vintage` is the integer 2011 or 2022; codes are checked against the official ranges (`scripts/zone_rules.check_codes`). `crosswalk_method = footprint_area` on every row.

## Sources
| Source | URL | Licence / attribution |
|---|---|---|
| SVDLS Site Register 2025 (master list: 3,091 sites, points, hectares, DZ2011) | https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/ (`SVDLS_2025_Register.ods`, uploaded 10 Sep 2026) | OGL v3, © Scottish Government; data supplied by planning authorities |
| SVDLS 2025 publication + tables (national check figures) | https://www.gov.scot/publications/scottish-vacant-and-derelict-land-survey-2025/ | OGL v3, © Scottish Government |
| Spatial Hub *Vacant and Derelict Land – Scotland* (3,154 polygons, updated 18 Dec 2025) | https://data.spatialhub.scot/dataset/vacant_and_derelict_land-is | OGL v3. Contains data from Improvement Service under OGL; data from the Scottish local planning authorities and Loch Lomond & The Trossachs NPA |
| Spatial Hub *Housing Land Supply – Scotland* (open version: 6,166 polygons, hla_year 2020/21–2024/25, mostly 2024/25) | https://data.spatialhub.scot/ | OGL v3. Contains data from Improvement Service under OGL; data from the Scottish local planning authorities |
| RoS INSPIRE Index Polygons (Aug 2026), step b only | https://ros.locationcentre.co.uk/inspire/ | INSPIRE end-user licence, © Crown copyright and database right 2026, OS AC0000851063. **Internal only** until the end-user terms are cleared. The public CSV does not use it: see Method step 4 |
| SG Data Zone boundaries 2011 / 2022 | https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip , ..._2022.zip | OGL v3, © Scottish Government, contains OS data © Crown copyright and database right 2026 |

**Attribution line for any public view:** Contains data from Improvement Service under OGL, supplied by Scotland's local planning authorities and Loch Lomond & The Trossachs National Park Authority. Scottish Vacant and Derelict Land Survey 2025 © Scottish Government, OGL v3. Data Zone boundaries © Scottish Government, contains OS data © Crown copyright and database right 2026.

## Method
1. **Master list.** Every row of the 2025 register is one site. Key = planning authority + site code (authority names normalised: "Na h-Eileanan Siar"→"Na h-Eileanan an Iar", "Loch Lomond and the Trossachs…"→"Loch Lomond and Trossachs…"). Register hectares are the official size.
2. **Geometry, tagged `geom_provenance`:**
   - `spatialhub_polygon`: Spatial Hub VDL polygon with the same authority + site code.
   - `spatialhub_buffer`: same match, but the shape is an Improvement Service circle drawn round the grid reference (Polsby–Popper > 0.99 with ≥ 33 vertices; all 142 such shapes are 73-vertex circles). Kept under step a, as agreed.
   - `ros_inspire_outline`: unmatched sites only. RoS INSPIRE title polygon containing the register grid reference, accepted when its area is within ±30% of the register hectares (closest ratio wins). `ros_inspireid` is kept in the internal gpkg.
   - `point_sized`: a circle at the grid reference whose area equals the register hectares.
3. **Cross-list duplicates.** An HLS polygon and an SVDLS site are the same land when their overlap is ≥ 50% of the smaller shape. Both rows are kept: `dup_hls_site_refer` on the SVDLS site, `dup_svdls_site_code` on the HLS site (semicolon lists where there are several). The rollups give `*_dup_*` and `*_excl_*_dup` columns so a combined total can drop the overlap once.
4. **Zone assignment (`footprint_area`).** The public rollup uses OGL geometry only. The 27 sites with a RoS outline are placed using their `point_sized` circle and counted under `ha_register_point_sized` (28.0 ha in all), matching the team rule that INSPIRE-derived zone statistics stay internal until the OS end-user terms are cleared. The INSPIRE-based version is in `internal/`. Each site geometry is intersected with the zones; hectares are split in proportion to the overlap area (renormalised over land, so coastal sites keep their full register hectares). Counts go to the zone with the largest overlap. A site with no overlap would fall back to its point-on-surface and the nearest zone (none needed it).

## `dz_svdls_rollup.csv` columns
`code, vintage, n_sites, ha_register, ha_geometry, n_derelict, n_vacant, ha_derelict, ha_vacant, ha_published_scope, ha_unused_15plus, ha_period_unknown, n_dup_hls, ha_dup_hls, n_owner_local_authority, n_owner_housing_association, n_owner_private, n_owner_other_public, n_owner_unknown, ha_register_spatialhub_polygon, ha_register_spatialhub_buffer, ha_register_point_sized, ha_register_excl_hls_dup, crosswalk_method`
- The cross-list duplicate flags (`n_dup_hls`, `ha_dup_hls`) were computed on the best geometry, which for 10 of the 812 flagged sites is a RoS outline. That is a yes/no attribute, not published geometry.
- `ha_register`: register hectares allocated by footprint share; `ha_geometry`: the geometry's own area in the zone.
- `ha_vacant` = "Vacant Land" + "Vacant Land and Buildings" anywhere. `ha_published_scope` = derelict + vacant in settlements of 2,000+ (the SG headline definition); the difference is 89 vacant sites (269.8 ha) in settlements under 2,000, which the register carries but the headline excludes.
- `ha_unused_15plus`: period vacant/derelict ends in 2010 or earlier (2025 − 15), using the upper year of banded periods ("1980 or earlier", "2001-2004" etc.). "Unknown" periods go to `ha_period_unknown`, not to 15+.
- Owner groups from `owner_1` (28 categories): local_authority; housing_association; private (Other/Unknown Private, private utilities and companies, Network Rail, Scottish Power); unknown ("Ownership unknown"); other_public (everything else: Scottish Enterprise, URCs, health boards, Defence, Coal Authority, SG, HIE, port and harbour bodies, etc.).

## `dz_hls_rollup.csv` columns
`code, vintage, n_sites, ha_geometry, n_buffered, ha_buffered, n_dup_svdls, ha_dup_svdls, ha_excl_svdls_dup, crosswalk_method`
- The open HLS has no capacity or status (those are in the restricted PREMIUM version), so these are footprint hectares only.
- HLS polygons overlap each other (phases, re-drawn sites): the sum is 26,505.6 ha but the union is 24,969.2 ha. Totals here are sums; don't read them as unique land area. 341 rows share authority + site_refer + year, so the gpkg uses a row id `hls_uid`.

## QA (full detail in `qa_svdls_hls.json`)
- **National check:** register 3,091 sites, 8,860.7 ha. Derelict plus urban vacant in settlements of 2,000+ comes to 3,002 sites and 8,591.0 ha, which matches the published 2025 headline exactly (Table 2: 3,002 sites, 8,591 ha; derelict 6,958 ha, urban vacant 1,633 ha). Both vintages' `ha_register` and `ha_published_scope` sum back to these totals. The register's cover text says "3,099" sites, but the sheet holds 3,091 rows; the published tables agree with the rows.
- **Spatial Hub match** on authority + site code: 2,968 of 3,091 (96.0%). The 123 unmatched are Glasgow 38, Renfrewshire 23, Angus 16, Aberdeen City 12, Aberdeenshire 5, Scottish Borders 5, Fife 4, East Ayrshire 4, North Lanarkshire 4, Stirling 3, East Renfrewshire 3, East Dunbartonshire 2, and one each in Dumfries & Galloway, Argyll & Bute, North Ayrshire and South Ayrshire. Of those, 27 took a RoS outline and 96 are `point_sized`. In the other direction, 186 Spatial Hub shapes are not on the 2025 register: they're sites removed since 2024, or re-coded. Only 4 unmatched register points fall inside an unclaimed Spatial Hub shape in the same authority, so re-coding explains very few. They were left unmatched, per the agreed code-match rule.
- **Area agreement** (geometry ha ÷ register ha): true polygons median 1.000, with 3.4% outside ±30% (0.8% below, 2.6% above). All matched shapes, buffers included: median 1.000, 7.1% outside. All sites: median 1.000, 6.8% outside.
- **Buffered circles:** 132 sites, 4.3% of register sites (4.5% of matched), 208.2 ha. 23 of them have an INSPIRE title within ±30%; that's for information only, and they stay `spatialhub_buffer`. HLS: 148 buffered shapes (2.4%), 115.5 ha.
- **Cross-list overlap (≥ 50% of the smaller shape):** 874 pairs. 812 SVDLS sites (2,029.2 ha register) are flagged with an HLS site, and 726 HLS sites (3,827.0 ha) with an SVDLS site. Flagged SVDLS sites by provenance: 757 polygon, 34 buffer, 11 point_sized, 10 RoS outline. Flagged HLS by year: 611 from 2024/25, 86 from 2023/24, 28 from 2022/23, 1 from 2020/21. SVDLS hectares excluding the overlap: 6,831.6.
- **Zone assignment:** no site needed the point-on-surface fallback. Sites split across zones: SVDLS 863 (2011) and 773 (2022); HLS 2,052 and 2,132. The register's own DZ2011 code equals our largest-overlap zone for 99.1% of sites.
