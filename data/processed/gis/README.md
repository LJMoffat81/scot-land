# Scot-LAND GIS: open-data tables (updated 6 Oct 2026)
These files are on the box only. Nothing has been pushed to the repo. The publication copy is in `../data/processed/gis/` with `manifest.csv`.

| File | Rows | Notes |
|---|---|---|
| epc_dz_rollup.csv | 14,368 | 84 columns: the original 38, plus `recent10_*` (lodged 1 Jul 2016–30 Jun 2026), plus floor-area mean/sum and house/flat means for both sets, plus `dwellings_total_2025` (the coverage denominator, Data Zones count_year 2025) and `dwellings_flag` |
| dz_residential_land.csv | 14,368 | residential land ha per zone: settlement mask plus RoS INSPIRE residential-parcel union; official-dph `mask_too_big` QA flags |
| dz_detached_plot_bands.csv | 14,368 | **internal**: plot-size bands (<0.05 / 0.05–0.10 / >0.10 ha) and median parcel ha for detached houses, post-1980 and pre-1980, from the EPC UPRN ↔ RoS INSPIRE match; see README_dz_detached_plot_bands.md |
| dz_brma_share.csv | 14,593 | household-weighted (Census 2022 postcode points) |
| dz_park_overlay.csv | 157 | household-weighted |
| alt/dz_brma_share_oa2022.csv | 14,462 | OA2022-centroid variant |
| alt/dz_brma_share_dwelling_bounds.csv | 441 | dwelling sensitivity bounds for split zones |
| alt/dz_park_overlay_dwelling_bounds.csv | 157 | dwelling sensitivity bounds for the park overlay |
| README_dz_residential_land.md | – | method, QA and licence for dz_residential_land |
| NOTE_ros_house_sales.md, NOTE_census2022_dwellings.md | – | source findings |
| qa_*.json, alt/qa_*.json, SOURCES_SHA256.txt | – | QA output and raw-download checksums |

**Team rules (6 Oct 2026).** For the EPC, BRMA, park and alt files these are built into the generating scripts via `scripts/zone_rules.py`:
- `vintage` is the integer 2011 or 2022;
- codes are checked against the official ranges (2011: S01006506–S01013481; 2022: S01013482–S01020873);
- dwelling denominators come from Scot-LAND Data Zones' `dwellings_by_year.csv` (dwellings_total, count_year 2025). The alt dwelling-bounds files already used the same NRS household-estimate dwellings, which match dwellings_total in all 14,368 rows.

QA for the team-rule rebuild: `qa_team_rules_gis.json` (script `scripts/qa_team_rules_gis.py`).

## Vacant & derelict land and housing land supply (added 6 Oct 2026)
| File | Rows | Notes |
|---|---|---|
| dz_svdls_rollup.csv | 14,368 | SVDLS 2025 register sites by zone (footprint_area), OGL geometry only; see README_svdls_hls.md |
| dz_hls_rollup.csv | 14,368 | Spatial Hub housing land supply footprints by zone, with SVDLS overlap flags |
| svdls_sites.gpkg, hls_sites.gpkg, internal/dz_svdls_rollup_with_inspire.csv | – | internal only, kept in out/ and not staged |
