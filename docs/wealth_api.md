# Wealth API (lead SE draft, branch `lead/wealth-api-boot`, 6 Oct 2026)

Experimental research estimates. Not official valuations or tax bills.

## Boot model

`backend/api/main.py` always mounts `api/wealth_routes.py`. The legacy AGR router
(`api/agr_routes.py`, moved verbatim from the old `main.py`) and
`api/platform_routes.py` are optional: if their imports fail they are skipped,
the reason is logged (operator `ROUTER_STATUS`; public `/health` is status + version only). Today both are skipped,
because modules deleted in `4aa9219` (`agr.valuation`, `agr.zone_prices`,
`agr.wide_range`, `agr.sales_comps`, `agr.seabed`, `agr.settlement`,
`validation.*`, `layers.open_stats|registers|public_land|vdl`) are missing.
The app refuses to start if any (method, path) is registered twice.

## Configuration (environment only)

| Variable | Use |
|---|---|
| `DATABASE_URL` or `PGHOST`+`PGDATABASE` (+`PGUSER`,`PGPASSWORD`,`PGPORT`) | PostGIS. No credential defaults. |
| `DB_CONNECT_TIMEOUT` | Seconds, default 3. |
| `ENABLE_INTERNAL_ENDPOINTS` | `1`/`true`/`yes`/`on` mounts the `/internal/...` developer routes (placeholders, mocks, diagnostics). **Default off.** |
| `INTERNAL_API_TOKEN` | Secret required whenever `/internal` is mounted. Send `Authorization: Bearer <token>` or `X-API-Key: <token>` (constant-time compare). **Missing secret → 403 `internal_locked` (never fall open). Missing/wrong token → 401.** |
| `DATA_DIR` | Data root (`config/`, `processed/`, `raw/`). Default: repo `data/`. Used by the API, resource/eco harvesters and `etl/`. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Compose only. `POSTGRES_PASSWORD` is required; compose refuses to start without it. |

## Endpoints

| Route | No DB | Notes |
|---|---|---|
| `GET /health` | 200, `{status, version}` only | Liveness. Never 500s. DB/router detail is not public (HEALTH-TRIM / SW-037). |
| `GET /georgist/wealth?lat&lng&zone_id[&vintage]` | 503 `wealth_database_unavailable` | `zone_id` must match `^S01\d{6}$` and fall in the 2011 (S01006506–S01013481) or 2022 (S01013482–S01020873) range, else 422. `vintage` is the integer `2011` or `2022` (anything else, including `DZ2011`, is 422 `invalid_vintage`); it is inferred from the code when omitted, and a mismatch is 422 `vintage_mismatch`. Outside Scotland is 400. Validation runs before any DB access. |
| `GET /layers/context/data-zones/at?lat&lon` (`lng` alias) | 503 `dz_boundaries_unavailable` + `reasons` | Point → real `(code, vintage)` for every loaded vintage: `code`/`name`/`vintage` (integer; 2011 first), `zones[]`, `dz2011`, `dz2022` (`on_boundary`), `source`, `vintages_loaded`. PostGIS `dz_boundaries` first, then `DATA_DIR/processed/dz20xx_boundaries.geojson`. 404 `no_data_zone_at_point` on a miss; 400 outside Scotland. Never returns `unknown`. Load with `python -m etl.ingest_dz_boundaries --fetch` (or `--fixture` in CI); provenance in `dz_boundaries_meta`. |
| `GET /geocode/postcode?q=` | 503 `geocoder_unavailable` (4 s timeout) | Full UK postcode → its centroid `lat`/`lng` via postcodes.io (ONS Postcode Directory, OGL v3; OS and Royal Mail attributions). Point only: no value, rent or address. 422 not a postcode (free text is not geocoded) or outside Scotland; 404 unknown postcode or no location. The map then runs the data-zone lookup as for a click. Postcodes are not logged. |
| `GET /layers/georgist/surface-rent?vintage=2011` | 503 | Latest row per zone from `surface_rent_dz`, served only if `publish_level` is public_zone/public_site, `publication_status = ok` and not a placeholder; `withheld` / `withheld_by_reason` count the rest. **Allowlisted columns only** plus per-zone `status` (`ok` or `not_applicable`) and the three display views (`rent_per_residential_ha[_status]`, `rent_per_dwelling[_status]`, `rent_per_resident[_status]`, `second_home_share`). Also `zero_dwellings` (codes shown as not applicable), `method_settings` (depreciation settings read from `data/config/surface.yaml`) and `attributions`. `vintage` defaults to 2011; 422 `invalid_vintage` otherwise. 503 `surface_rent_not_built` if none; 503 `attribution_missing` if a dataset behind a shown view has no manifest attribution. |
| `GET /layers/georgist/resource-rent`, `/eco-rent` | 503 | Real, publishable (`public_site`, status ok, not placeholder) rows from `resource_wealth` / `eco_wealth` only, as GeoJSON. Site geometry, so every row must be a measured figure from a site-public source (publication geometry rule, below); otherwise 500 `publication_rule_violation`. Today there are none, so 503 `<layer>_layer_not_built`. **Mock features are never served here.** |
| `GET /internal/georgist/wealth`, `/internal/georgist/surface-rent/{zone}`, `/internal/georgist/surface-rent-rollup`, `/internal/layers/georgist/resource-rent`, `/internal/layers/georgist/eco-rent` | — | Only with `ENABLE_INTERNAL_ENDPOINTS` (otherwise 404). Always requires `INTERNAL_API_TOKEN` auth when mounted. Placeholders and withheld rows with numbers, Valuation diagnostics, mock harvests, and the **unpublished** DZ2022 → IZ → Council → Scotland surface-rent roll-up (`surface_rent_rollup`, `publish_level=internal` only). Header `X-Wealth-Internal: true`. Totals are computed by the same function as the public route. **No public route serves roll-up £ figures.** |
| `GET /internal/georgist/tax-scenario`, `/internal/georgist/tax-scenario/zone` | — | **HOLD — internal only / unpublished.** Approved defaults (v0.1, Oct 2026) scenarios **S1** (per-council revenue-swap vs that council’s CT+business rates; national single-rate off by default), **S2** (50%), **S3** (85%). Every payload `publication_status=blocked`. **No public £.** **TEMP while blocked:** £ at Data Zone grain only as `{low,central,high}` triples with `market`/`proxy`/`shadow` tags; council views are counts; council/Scotland £ roll-up built behind the setting for reconcile on **DZ2022** via `#71` `address_uprn` (spine `la_code` per zone; native DZ2011 with `vintage=2011`). S1 `s1_rate.low`/`high` keys follow the *rent* band (low rent → typically highest rate). Shadow never taxed. **`yield_placeholder`** reads shared `surface.yaml` `yield.central` (0.04499) + band 0.0398–0.0450 + v3 flags — no `land_yield: 0.05`. Same auth/flag rules as other `/internal` endpoints. |
| `GET /layers/parcels`, `/layers/parcels/at`, `/layers/parcels/tiles/...` | 503 / empty / PNG | RoS INSPIRE cadastral shapes (always mounted). BBox returns 503 when `inspire_parcels` is missing or empty — never placeholders. |
| `POST /sync/ros` | — | Removed from the API: the CKAN package id and columns were unverified and the target table is not in the schema. Superseded by `georgist/surface_harvester.py`. |

DB failure reasons: `not_configured`, `connection_failed` (password scrubbed), `schema_missing`, `query_failed`, `driver_missing`.

### `/georgist/wealth` response

Shape only; the values are placeholders, not results.

```json
{"zone": {"code": "S01008677", "vintage": 2011, "vintage_source": "inferred_from_code"},
 "wealth": {
   "components": [{"layer": "surface", "measured_rent_gbp": "<GBP>", "value_tier": "proxy",
                   "quality": "derived", "price_year": 2025, "evidence_year": 2023, "publish_level": "public_zone",
                   "publication_status": "ok", "status": "ok", "in_totals": true, "withheld": false,
                   "excluded_reason": null, "model_filled": false, "...": "..."}],
   "totals_by_tier": {"proxy": {"total_gbp": "<GBP>", "low_gbp": ..., "high_gbp": ..., "price_year": 2025, "flags": []}},
   "attribution": {"planning_uplift": null, "infra_share": "<GBP>", "note": "of which; never added"},
   "policy": {"policy_rent": "<GBP>", "policy_despec_factor": "<from surface.yaml>"},
   "display": {"default": "per_residential_hectare", "flags": [],
               "order": ["per_residential_hectare", "per_dwelling", "per_resident"],
               "views": {"per_residential_hectare": {"status": "denominator_pending", "value": null, "...": "..."},
                         "per_dwelling": {"status": "ok", "value": "<GBP/dwelling>", "low": ..., "high": ..., "denominator": "dwellings (NRS total, incl. vacant and second homes)"},
                         "per_resident": {"status": "denominator_pending", "second_home_share": null, "...": "..."}}},
   "flags": [],
   "attributions": [{"dataset": "gis/epc_dz_rollup.csv", "licence": "...", "attribution": "...",
                     "publish_level": "public_zone", "use_restriction": "...", "source": "manifest"}]}}
```

No mixed headline total exists. Totals are per tier. If the components of one tier have
different (or missing) `price_year` values, summing them is refused outright. Both
`/georgist/wealth` and `/internal/georgist/wealth` answer **HTTP 500**
`{"error": "mixed_price_years", "tier", "price_years", "message"}`, with no partial total
and no flag-and-continue. Different tiers may carry different price years. A zone with no
surface row is flagged `surface_not_found`, not £0.

**Year names (rules section 2).** `price_year` is the year the money is priced in
(Valuation indexes RoS sales to it with the council UK HPI). `evidence_year` is the raw
sales/evidence year. `to_db_row` refuses rows that still carry the pre-rename names
(`zone_code`, `zone_vintage`, `price_base_year`, `price_years`, `dwelling_year`,
`dwelling_year_lag`).

**Attribution.** Every public view carries `attributions` for the datasets it is built
from: `gis/epc_dz_rollup.csv` for surface rent, and Data Zones' `dwellings_by_year` /
`zone_spine` only when the per-dwelling or per-resident view is actually shown. Licence and
text come **only** from the manifest's `attribution` column (`georgist/attribution.py`,
`source: "manifest"`); READMEs are not scraped and there is no pinned copy. A missing
attribution is a 503 `attribution_missing`, never a silent omission. The frontend inspector
shows credits under "Data credits"; a future surface-rent map layer must put
`layer.attributions` into the map attribution control. The per-residential-hectare view
credits `gis/dz_residential_land.csv` (RoS / OS wording from GIS's manifest) whenever it shows
a figure.

**Zero-dwelling zones (rules v0.7).** Data Zones' `zone_spine.flags` is the single source.
It is ONE text column, `;`-separated, `''` when there are no flags; the engine splits it
(`display_views.parse_zone_flags`) and tests token membership, never an exact match (e.g.
S01010227 is `no_census2022_household_residents;zero_dwellings;pop_dwellings_mismatch`). The
join is on `(code, vintage)`. `zero_dwellings` overrides any surface row or RoS price: the
component has `status: "not_applicable"`, `excluded_reason: "zero_dwellings"`, null rent and
band, is never summed, and every display view is `not_applicable` with a null value (never
£0). The layer nulls `display_views.ZERO_DWELLING_NULL_COLUMNS` for such zones and lists
them in `zero_dwellings`. `pop_dwellings_mismatch` withholds the per-resident view with that
reason, even when the years align.

Publication (economic rules v0.4 section 2):

* **Placeholders are absent**, not flagged. The public SQL filters
  `quality = 'placeholder'` rows out of extractive/eco, and a placeholder surface row
  gives only the flag `surface_not_measured` with no figure.
* **Withheld**: a component with `publish_level = internal` (`not_publishable`) or
  `publication_status = blocked` (`blocked`) is listed with `withheld: true`, its
  reason and its level, but no rent, band, attribution or policy figure.
* **Diagnostics are internal only.** Public queries select the explicit allowlist
  `wealth_schema.PUBLIC_SURFACE_COLUMNS`. `raw_residual`, `drc_*`, `rebuild_new_gbp`,
  `remaining_factor`, `land_value_low/high`, `typical_sale_gbp`, `mean_median_ratio`,
  `price_skew_flag`, `rebuild_mix_basis`, `brma_mix`, `yield_source`, `fill_method`,
  `proxy_tags` and provenance hashes stay on the row and appear only on `/internal/...`.
  New Valuation columns stay internal until someone adds them to the allowlist.
  `model_filled` (boolean) is published in place of `fill_method`.

### Display denominators (rules v0.5)

`georgist/display_views.py`. Areas come from `dz_denominators` (schema `003`, keyed
`(code, vintage)`). Counts come from Data Zones' own tables (schema `004`): dwellings from
`datazones.dwellings_by_year.dwellings_total` (`(code, vintage, count_year)`), population
from `datazones.zone_spine.population` at `pop_year`. 2022 zones have dwellings for
2024–2025 only; population is 2022-based, so a 2025-priced row shows per-resident as
`denominator_pending`.

**Count join rule.** A dwelling or population count is used only when
`count_year = price_year` of the surface row **and** its vintage is the row's vintage
(2011 counts only with 2011 rows, 2022 only with 2022). Valuation's own `dwellings` are
never used as the denominator; if they differ from Data Zones' same-year count the zone is
flagged `dwellings_differ_from_valuation_row`. Otherwise (no matching count) the view is
`denominator_pending` and the zone is flagged `dwellings_count_missing_for_price_year` /
`population_count_missing_for_price_year` (in `display.flags`, the payload `flags`, and
the layer's `denominator_flags`). A count is **never** taken from another year or vintage.

Valuation's area values (`residential_land_ha`, `rent_per_res_ha`, `second_home_share`,
`vacant_share`; the tag `res_land_settlement_area_rough` marks the interim settlement-area
denominator) take precedence; `dz_denominators` fills gaps.

1. **Default: per hectare of residential land** (`residential_land_ha`, from GIS; not built yet).
   Interim: zone area inside the NRS settlement (`settlement_area_ha`), status `interim_rough`.
2. **Per dwelling**: `measured_rent / dwellings` (NRS total dwellings, including vacant and
   second homes; same-year count only, see above).
3. **Per resident** (optional): same-year `population`, always returned with `second_home_share`
   (flagged when the share is ≥ 10%).

A missing denominator gives `status: "denominator_pending"` and `value: null`. Nothing is
computed in its place.

**Residential area and confidence.** `etl.load_processed` derives `dz_denominators` from GIS's
`dz_residential_land.csv` (`residential_parcel_ha`, `settlement_ha`, plus
`share_res_uprn_in_parcels`, `mask_too_big_parcel`, `res_uprn_exceeds_dwellings` and the
method flags); a 0 or blank area becomes NULL (pending), never 0. The per-residential-hectare
view carries `confidence`: `low` where `share_res_uprn_in_parcels < 0.5`, `mask_too_big_parcel`
is set, or only the settlement mask is available, with `confidence_reasons`. Where it is low
and a per-dwelling figure exists, `display.default` (and the layer's `preferred_view`) becomes
`per_dwelling` and the zone is flagged `residential_area_low_confidence`. The layer adds
`rent_per_residential_ha_confidence` per zone. Residential area is display only: it never
changes `measured_rent` or any tier total (tested).

**Quality flags from Valuation.** Tags listed in `wealth_schema.QUALITY_FLAG_TAGS` (today
`plot_bands_borrowed`: the zone had no plot-band shares and borrowed its council × urban-rural
class shares) are read from Valuation's internal `proxy_tags` and served as `quality_flags`
on the surface component and in the layer, and added to the payload `flags`. No other tag is
served, and the API never re-values such zones (no all-estate or all-one-off default). There is no whole-zone area column, and rent per hectare of
whole-zone area is never served for surface rent.

## Schema (`backend/db/schema/*.sql` + Alembic)

Schema is applied with **Alembic** (`alembic upgrade head`). See
[`docs/DB_MIGRATIONS.md`](DB_MIGRATIONS.md). The baseline revision executes the
SQL files under `backend/db/schema/`. CI upgrades a fresh PostGIS and runs
`python -m db.check_drift`.

## Schema files (`backend/db/schema/*.sql`)

Applied by the postgis container on first start and by
`python -m etl.migrate_to_postgis --schema-only`. Idempotent. Geometry is EPSG:27700.

- `surface_rent_dz` — PK `(code, vintage, valuation_date)`; `vintage` SMALLINT 2011|2022 with
  a code-range CHECK per vintage; valuation date keeps history. **Column names and order are
  Valuation's `surface_rent.OUTPUT_COLUMNS`** (e.g. `raw_residual`,
  `negative_residual`, `land_value[_low|_high]`, `measured_rent`,
  `measured_rent_per_dwelling`, `uncertainty_low/high`, `uncertainty`,
  `infra_share`, `planning_uplift`, `policy_despec_factor`, `policy_rent`,
  `value_tier`, `quality`, `fill_method`, `publish_level`, `use_basis`,
  `crosswalk_method`, `source_id`, `licence`, `evidence_year`, `rebuild_status`,
  `typical_sale_gbp`, `mean_median_ratio`, `price_skew_flag`, `count_year`,
  `rebuild_mix_basis`, `land_value_zone_total`, `price_indexed_gbp`,
  `price_index_series`, `price_index_factor`, `price_year` (NOT NULL),
  `dwellings_source`, `vacant_share`, `second_home_share`, `floor_area_basis`,
  `residential_land_ha`, `rent_per_res_ha`, `publication_status`), then DB-only `absent_from_ros_price_file`, `planning_uplift_flag`,
  `model_version`, `config_sha256`, `source_sha256`. CHECKs: value_tier
  market|proxy|shadow; quality live|derived|modelled|placeholder; crosswalk
  none|address_uprn|value_weighted (surface subset of the team enum);
  publish_level public_site|public_zone|internal; publication_status ok|blocked; net_of ⊆
  {extractive, eco_externality}. No per-area rent or SIMD columns.
- `surface_rent_rollup` (`023`) — **internal only** SG hierarchy aggregates for DZ2022
  surface rent: Intermediate Zone (S02) → Council (S12) → Scotland (`S92000003`).
  Hierarchy parents come from `datazones.zone_spine` (official SG 2022 Data Zone
  lookup, OGL v3.0). Built by `georgist.surface_dz2022` (address-UPRN 2011→2022
  crosswalk from a configured local GIS handoff —
  `SCOT_LAND_DZ_UPRN_CROSSWALK_DIR` / `paths.dz_uprn_crosswalk`; min-share filter
  default ON; population/area weights refused; `crosswalk_method=address_uprn`)
  then `georgist.surface_rollup` (sums `measured_rent` once per DZ; carries
  `estimate_label` to council and Scotland; refuses mixed `price_year`).
  `publication_status` stays `blocked`. `publish_level` is constrained to
  `internal` in SQL. Served only on `/internal/georgist/surface-rent-rollup`.
  Leaves stay on `surface_rent_dz`. **Roll-up £ figures stay unpublished**
  (designer brief v3.1). Tax-scenario council/Scotland reconcile pin is DZ2022
  (same UPRN crosswalk + spine council).
- `planning_sites` — PK `(source, site_id)`; source hla|svdls|planning_app,
  geom_source surveyed|ros_title|point (a point must be a POINT), MultiPolygon or
  Point 27700, both DZ codes, plan-making vs deciding authority, publish_level
  public_site|public_zone|internal,
  `dedup_group` for HLA/SVDLS overlap.
- `resource_wealth`, `eco_wealth` — MultiPolygon 27700 with tier/quality tags and
  publish_level + publication_status; today's rows are placeholders (internal only).
- `dz_boundaries` (`002`) — `(code, vintage)` MultiPolygon 27700 with NRS range CHECKs; feeds the zone lookup.
- `dz_denominators` (`003`) holds the display area denominators (see above).
- `datazones.*` (`004`) — Data Zones' own typed tables (`zone_spine`, `dwellings_by_year`,
  `dz_crosswalk_people`, SIMD, council-tax bands, planning authority, ...), vendored from
  their `schema.sql` and loaded by `etl.load_processed`. They replace the earlier `dz_spine`
  stub and the `dz_dwelling_counts` / `dz_population_counts` contract, which are gone.
- `processed.*` — manifest-loaded datasets, see `docs/processed_data_manifest.md`.

Schema files use `CREATE TABLE IF NOT EXISTS`: an existing database does not pick up new
columns (e.g. `publication_status`). Recreate it, or add an explicit migration, before
deploying over old data.

`georgist/wealth_schema.py` holds the matching Python Literals and `to_db_row`,
which takes a Valuation `build_output_row` row unchanged, validates it against
the enums, maps older publish vocabulary to the rules v0.4 levels
(`public`→`public_zone`, `zone_total_only`→`public_zone`; anything else refused),
derives `publication_status` (Valuation's own value, which `687cf43` always emits, else `blocked` when the row is tagged
`reconciliation_breach` or carries the pre-v0.4 level `blocked`, which becomes `internal`), and
adds the DB-only columns.

Reconciliation (rules 4.2, v0.3) is Valuation's: `surface_rent.observed_total_value`
(MEAN price × dwellings, same vintage, DZ2011 until the spine is crosswalked) and
`surface_rent.reconciliation_check` (× **gross** yield). A breach means
`publication_status = blocked`: withheld publicly, licence level kept (Valuation `687cf43`).

**Years.** Land value and rent are in `price_year` GBP; `evidence_year` is the raw RoS
sales year; `count_year` is the year of a dwelling or population count (see Year names
above). Valuation's rows use these names directly. Land yield is one stored
`r − g` value (rules 1). Per-person figures divide by same-vintage population only
(`wealth_schema.per_person`).

**Method settings.** `georgist/surface_settings.py` reads the depreciation life and floor
(low/central/high) and the band-combination rule from `data/config/surface.yaml`; the layer
serves them as `method_settings`. Nothing is hard-coded in the API.

### Access context (`wealth.context.access`)

GIS's `dz_access.csv` (job accessibility from BRES employment, road km to the nearest large
urban centre) is a context layer for Valuation's gradient check. `/georgist/wealth` passes the
zone's row through as `context.access`: `job_access`, `log_job_access`, `road_km_nearest_luc`,
`nearest_luc`, `distance_method`, `job_access_method`, `network_component`, the GIS `flags`
verbatim as a list (e.g. `luc_distance_euclid_x1.3`, `job_access_partly_euclid_x1.3`,
`off_mainland_network`, `nearest_emp_point_gt_5km`), `source_year` and the file's manifest
`attributions`. `status` is `ok`, `not_loaded` (table absent), `zone_missing` or
`attribution_missing` (context withheld, logged). It never enters rents, views or totals, and its
credit sits inside the block, not in the top-level `attributions`.

## Publication geometry rule

**Modelled or proxy home land values and rents are zone-level only.** No public endpoint, tile
or layer attaches a modelled or proxy value or rent to sub-zone geometry (site, parcel, plot,
UPRN, building). Plain parcel shapes with no value attached are fine. A site-level figure is
public only where its source is itself public at site level: SVDLS derelict sites, HLS housing
land sites, published business rateable values; and it must be that source's measured figure
(value tier `market`, quality not `modelled`). Spreading zone values down to plots is internal:
`/internal` only, behind `ENABLE_INTERNAL_ENDPOINTS` (no such route exists yet).

Implementation, `backend/georgist/publication_rules.py`:

* Every public route declares a `LayerRule`: `geometry_level` (zone|site|parcel|plot|uprn|building),
  `source_granularity` (zone|site), `value_basis` (none|measured|modelled) and, for site layers
  with values, the site-public sources allowed. Declarations are validated on import.

  | route | geometry_level | source_granularity | values |
  |---|---|---|---|
  | `/georgist/wealth` | zone | zone | modelled (zone); site rows from `resource_wealth`/`eco_wealth` checked per row |
  | `/layers/georgist/surface-rent` | zone | zone | modelled |
  | `/layers/georgist/resource-rent`, `/eco-rent` | site | site | measured, SVDLS/HLS/business rates only |
  | `/layers/context/data-zones/at` | zone | zone | none |
  | `/geocode/postcode` | site | site | none |
  | `/layers/parcels/tiles/...` (legacy AGR, not mounted) | parcel | zone | none (plain shapes) |

* **App build.** `create_app` refuses an undeclared public route: the core Wealth router raises
  `PublicationRuleError`; an optional router (AGR, platform) with one is not mounted and
  the skip is logged on `ROUTER_STATUS`. `/internal/...` routes are exempt and mounted only with
  `ENABLE_INTERNAL_ENDPOINTS`, and always require `INTERNAL_API_TOKEN` when mounted.
* **Load time.** Optional manifest columns `geometry_level`, `source_granularity`, `site_source`
  (see `processed_data_manifest.md`); public sub-zone files with value columns are rejected.
* **Public serializers.** The site layers and the wealth payload check every row whose figure would
  be shown (`check_site_rows`); the surface layer checks each row is keyed by a Data Zone code
  (`check_zone_row`). A violation is a loud 500 `publication_rule_violation`, never a silently
  thinned layer. Internal payloads are not checked.
* Tests: `backend/tests/api/test_publication_rules.py`, the load-time cases in
  `tests/etl/test_load_processed.py`, and PostGIS cases in `tests/api/test_postgis_integration.py`.

## Economic rules

The Georgist economic rules this engine follows are in [`ECONOMIC_RULES.md`](ECONOMIC_RULES.md)
(copied verbatim from the Georgist owner; an unapproved draft until its status line says
otherwise).

## Tests and CI

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest -q
# throwaway PostGIS (the PostGIS suites skip without it):
WEALTH_TEST_DATABASE_URL=postgresql://user@127.0.0.1:54329/wealth_it python -m pytest -q
python3 ../scripts/check_publishable.py   # public-repo guard
```

Processed data: `python -m etl.load_processed --check` (no DB) / `python -m etl.load_processed`.

`.github/workflows/ci.yml` runs on every push and pull request: a `postgis/postgis:17-3.5`
service with throwaway credentials (no secrets), the full backend suite with
`WEALTH_REQUIRE_POSTGIS=1` (the run fails rather than skipping the PostGIS tests), Valuation's
`tests/surface`, `etl.load_processed --check`, the publishability guard, and the frontend
`npm ci`, `tsc --noEmit` and `next build`.
