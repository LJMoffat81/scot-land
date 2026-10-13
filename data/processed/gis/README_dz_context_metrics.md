# dz_context_metrics.csv — Data Zone HPI, SIMD, population density

Built by `python etl/gis/build_dz_context_metrics.py` (14,368 rows, both vintages).

| Column | Source |
|--------|--------|
| population, pop_year | NRS SAPE via `datazones/zone_spine.csv` |
| zone_ha | GIS `dz_residential_land.csv` (SG DZ boundaries area) |
| population_density_per_km2 | population ÷ (zone_ha / 100) |
| simd_* | SG SIMD 2020v2 (DZ2011 ranks/deciles; DZ2022 modal decile via people crosswalk) |
| house_price_median_gbp | RoS residential sales medians (`dz2011_prices.csv`, DZ2011 only) |
| council_hpi_average_price_gbp | UK HPI council average attributed via `la_code` |

Licence: **OGL v3.0**. Catalogued in `data/config/sources.yaml` → `dz_context_metrics`.

Loads to PostGIS as `processed.gis_dz_context_metrics`. Public endpoint: `GET /layers/open/dz-context`. Zone polygons come from `dz_boundaries` (separate GIS boundaries work) — never invented here. **No modelled AGR £.**
