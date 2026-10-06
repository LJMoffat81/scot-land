-- Scot-LAND Wealth Engine: core schema (DRAFT stub, lead SE, 2026-10-06).
-- Follows docs/surface_rent_spec.md section 8 and the draft economic rules
-- v0.4 (sections 2, 4.2, 4.3, 5, 6.3, 7, 8, 11, 13). Applied automatically by the
-- postgis container on first start (/docker-entrypoint-initdb.d) and by
-- `python -m etl.migrate_to_postgis --schema-only`. Idempotent.
--
-- Conventions
--   * Projected geometry is EPSG:27700 (British National Grid). Never 4326 in tables.
--   * Rent is GBP per year priced in `price_year` (the money year); `evidence_year` is the raw
--     sales/evidence year (rules 2). The only per-area column is rent_per_res_ha (rules v0.5).
--   * value_tier = valuation basis (market|proxy|shadow).
--     quality    = data state (live|derived|modelled|placeholder). Placeholders never enter totals.
--   * planning_uplift and infra_share are "of which" breakdowns. Never added to measured_rent.
--   * policy_rent is a policy/scenario column. Never folded into measured_rent.
--   * publish_level (licence level) is public_site|public_zone|internal. publication_status
--     (ok|blocked) is separate: a block withholds the figure publicly, the level is kept.
--   * Diagnostic columns (raw_residual, drc_*, typical_sale_gbp, price_skew_flag,
--     rebuild_mix_basis, ...) are internal only; the API serves an explicit allowlist.

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------- zone spine
-- OWNED BY Scot-LAND Data Zones: datazones.zone_spine (schema 004, vendored from
-- data/processed/datazones/schema.sql). The old dz_spine stub is gone.
-- Vintage standard: `vintage` is the INTEGER 2011 or 2022 everywhere.

-- ---------------------------------------------------------------- surface rent
-- Column names and order = georgist.surface_rent.OUTPUT_COLUMNS (Valuation),
-- then DB-only columns (georgist.wealth_schema.DB_EXTRA_COLUMNS).
CREATE TABLE IF NOT EXISTS surface_rent_dz (
  -- Column names and order = georgist.surface_rent.OUTPUT_COLUMNS (Valuation fd03c4b)
  code                        TEXT NOT NULL CHECK (code ~ '^S01[0-9]{6}$'),
  vintage                     SMALLINT NOT NULL CHECK (vintage IN (2011, 2022)),  -- integer vintage standard
  valuation_date              DATE NOT NULL,
  price_year                  SMALLINT NOT NULL, -- year the money is priced in (rules 2), e.g. 2025
  ur6_class                   SMALLINT CHECK (ur6_class BETWEEN 1 AND 6),
  ur8_class                   SMALLINT CHECK (ur8_class BETWEEN 1 AND 8),
  dwellings                   INTEGER,           -- NRS council-tax dwellings, TOTAL incl. vacant + second homes (rules v0.5)
  sales_n_pooled              INTEGER,
  evidence_year               SMALLINT,          -- raw sales/evidence year (e.g. RoS 2023); rules 2
  evidence_years              TEXT,              -- pooled sales years, e.g. 2021-2023
  price_measure               TEXT,
  price_gbp                   NUMERIC,           -- MEAN price (rules 6.1)
  price_indexed_gbp           NUMERIC,           -- mean price indexed to price_year (council UK HPI)
  price_index_series          TEXT,
  price_index_factor          NUMERIC,
  typical_sale_gbp            NUMERIC,           -- median, display/diagnostic only (internal)
  mean_median_ratio           NUMERIC,           -- internal diagnostic
  price_skew_flag             BOOLEAN,           -- internal diagnostic
  count_year                  SMALLINT,          -- year of the dwelling count; = price_year by default (rules 4.2)
  count_year_lag              SMALLINT,
  dwellings_source            TEXT,
  vacant_share                NUMERIC CHECK (vacant_share BETWEEN 0 AND 1),       -- reported alongside; never changes rent (rules v0.5)
  second_home_share           NUMERIC CHECK (second_home_share BETWEEN 0 AND 1),
  rebuild_status              TEXT CHECK (rebuild_status IN ('OPEN_ESTIMATE', 'LICENSED')),
  rebuild_mix_basis           TEXT CHECK (rebuild_mix_basis IN ('sold', 'all_stock')),  -- internal
  floor_area_basis            TEXT CHECK (floor_area_basis IN ('mean', 'median', 'default')),  -- internal
  rebuild_new_gbp             NUMERIC,
  remaining_factor            NUMERIC,
  drc_gbp                     NUMERIC,
  drc_low_gbp                 NUMERIC,
  drc_high_gbp                NUMERIC,
  drc_swing_gbp               JSONB,             -- one-at-a-time DRC swing (rules 6.2 v0.7), internal
  raw_residual                NUMERIC,           -- per dwelling, GBP; MAY BE NEGATIVE (rules 6.3)
  negative_residual           BOOLEAN NOT NULL DEFAULT false,
  land_value                  NUMERIC CHECK (land_value >= 0),  -- published, floored
  land_value_low              NUMERIC,
  land_value_high             NUMERIC,
  land_value_zone_total       NUMERIC,           -- mean land value x dwellings
  yield_gross                 NUMERIC,
  yield_land                  NUMERIC,           -- the observed r - g (rules 1); one config/evidence value
  yield_source                TEXT,
  brma_mix                    JSONB,
  measured_rent_per_dwelling  NUMERIC,           -- = measured_rent / dwellings (same vintage)
  measured_rent_per_resident  NUMERIC,           -- Valuation's; NULL on pop_dwellings_mismatch; internal (API derives its own view)
  measured_rent               NUMERIC,           -- GBP/yr, zone total, in price_year GBP. The only summable column.
  residential_land_ha         NUMERIC CHECK (residential_land_ha > 0),       -- never whole-zone area (rules v0.5)
  rent_per_res_ha             NUMERIC,           -- default map view (rules v0.5)
  uncertainty_low             NUMERIC,
  uncertainty_high            NUMERIC,
  uncertainty                 TEXT CHECK (uncertainty IN ('low', 'medium', 'high')),
  infra_share                 NUMERIC,           -- GBP/yr of measured_rent explained by infrastructure
  planning_uplift             NUMERIC,           -- NULL until the existing-use (farm) proxy exists (rules 8)
  policy_despec_factor        NUMERIC,
  policy_rent                 NUMERIC,
  value_tier                  TEXT NOT NULL CHECK (value_tier IN ('market', 'proxy', 'shadow')),
  quality                     TEXT NOT NULL CHECK (quality IN ('live', 'derived', 'modelled', 'placeholder')),
  fill_method                 TEXT CHECK (fill_method IN ('observed_pooled', 'shrunk_to_model', 'model_filled', 'no_residential', 'not_applicable')),
  publish_level               TEXT NOT NULL CHECK (publish_level IN ('public_site', 'public_zone', 'internal')),
  publication_status          TEXT NOT NULL DEFAULT 'ok' CHECK (publication_status IN ('ok', 'blocked')),
  commons_class               TEXT NOT NULL,
  net_of                      TEXT[] NOT NULL DEFAULT '{}' CHECK (net_of <@ ARRAY['extractive', 'eco_externality']::TEXT[]),
  use_basis                   TEXT NOT NULL CHECK (use_basis IN ('existing_authorised_use', 'existing_use', 'best_permitted_use', 'permitted_use')),
  crosswalk_method            TEXT NOT NULL CHECK (crosswalk_method IN ('none', 'address_uprn', 'value_weighted')),
                              -- surface subset of the team enum: never population or area weights (rules 11)
  source_id                   TEXT NOT NULL,
  licence                     TEXT NOT NULL,
  proxy_tags                  TEXT[] NOT NULL DEFAULT '{}',
  method                      TEXT NOT NULL,
  -- DB-only
  absent_from_ros_price_file  BOOLEAN NOT NULL DEFAULT false,
  planning_uplift_flag        TEXT,
  model_version               TEXT,
  config_sha256               TEXT,
  source_sha256               JSONB,
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (code, vintage, valuation_date),
  CHECK (
    (vintage = 2011 AND substr(code, 4)::int BETWEEN 6506 AND 13481)
    OR (vintage = 2022 AND substr(code, 4)::int BETWEEN 13482 AND 20873)
  ),
  CHECK (uncertainty_low IS NULL OR uncertainty_high IS NULL OR uncertainty_low <= uncertainty_high)
);
CREATE INDEX IF NOT EXISTS surface_rent_dz_zone_idx ON surface_rent_dz (code, vintage);

-- ---------------------------------------------------------------- planning sites
CREATE TABLE IF NOT EXISTS planning_sites (
  site_id              TEXT NOT NULL,
  source               TEXT NOT NULL CHECK (source IN ('hla', 'svdls', 'planning_app')),
  permitted_use        TEXT,
  planning_status      TEXT,
  status_date          DATE,
  dz2011_code          TEXT CHECK (dz2011_code ~ '^S01[0-9]{6}$'),
  dz2022_code          TEXT CHECK (dz2022_code ~ '^S01[0-9]{6}$'),
  plan_authority       TEXT,             -- plan-making authority (incl. national parks)
  deciding_authority   TEXT,             -- authority that decides applications
  geom_source          TEXT NOT NULL CHECK (geom_source IN ('surveyed', 'ros_title', 'point')),
  geom                 geometry(Geometry, 27700) NOT NULL
                       CHECK (GeometryType(geom) IN ('MULTIPOLYGON', 'POINT')),
  hectares             NUMERIC CHECK (hectares >= 0),
  capacity_homes       INTEGER CHECK (capacity_homes >= 0),
  publish_level        TEXT NOT NULL CHECK (publish_level IN ('public_site', 'public_zone', 'internal')),
  licence              TEXT,
  source_vintage       TEXT,
  dedup_group          TEXT,             -- HLA/SVDLS outline-overlap group; one valuation per group
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (source, site_id),
  CHECK ((geom_source = 'point') = (GeometryType(geom) = 'POINT'))
);
CREATE INDEX IF NOT EXISTS planning_sites_geom_idx ON planning_sites USING GIST (geom);
CREATE INDEX IF NOT EXISTS planning_sites_dz2011_idx ON planning_sites (dz2011_code);
CREATE INDEX IF NOT EXISTS planning_sites_dz2022_idx ON planning_sites (dz2022_code);

-- ---------------------------------------------------------------- extractive / eco (placeholders today)
-- The current harvesters emit MOCK features. They load with quality='placeholder'
-- and are never served publicly (rules v0.4 section 2); only /internal/... shows them.
CREATE TABLE IF NOT EXISTS resource_wealth (
  id                 BIGSERIAL PRIMARY KEY,
  resource_type      TEXT,
  name               TEXT,
  annual_rent_gbp    NUMERIC,
  price_year         SMALLINT,          -- money year (rules 2)
  evidence_year      SMALLINT,          -- raw evidence year
  commons_class      TEXT NOT NULL DEFAULT 'extractive',
  value_tier         TEXT NOT NULL CHECK (value_tier IN ('market', 'proxy', 'shadow')),
  quality            TEXT NOT NULL CHECK (quality IN ('live', 'derived', 'modelled', 'placeholder')),
  crosswalk_method   TEXT NOT NULL DEFAULT 'footprint_area'
                     CHECK (crosswalk_method IN ('none', 'pop_hhres_2022', 'address_uprn', 'value_weighted', 'footprint_area')),
  source_id          TEXT,
  licence            TEXT,
  publish_level      TEXT NOT NULL DEFAULT 'internal' CHECK (publish_level IN ('public_site', 'public_zone', 'internal')),
  publication_status TEXT NOT NULL DEFAULT 'ok' CHECK (publication_status IN ('ok', 'blocked')),
  geom               geometry(MultiPolygon, 27700)
);
CREATE INDEX IF NOT EXISTS resource_wealth_geom_idx ON resource_wealth USING GIST (geom);

CREATE TABLE IF NOT EXISTS eco_wealth (
  id                 BIGSERIAL PRIMARY KEY,
  resource_type      TEXT,
  name               TEXT,
  annual_rent_gbp    NUMERIC,
  price_year         SMALLINT,          -- money year (rules 2)
  evidence_year      SMALLINT,          -- raw evidence year
  commons_class      TEXT NOT NULL DEFAULT 'eco',
  value_tier         TEXT NOT NULL CHECK (value_tier IN ('market', 'proxy', 'shadow')),
  quality            TEXT NOT NULL CHECK (quality IN ('live', 'derived', 'modelled', 'placeholder')),
  crosswalk_method   TEXT NOT NULL DEFAULT 'footprint_area'
                     CHECK (crosswalk_method IN ('none', 'pop_hhres_2022', 'address_uprn', 'value_weighted', 'footprint_area')),
  source_id          TEXT,
  licence            TEXT,
  publish_level      TEXT NOT NULL DEFAULT 'internal' CHECK (publish_level IN ('public_site', 'public_zone', 'internal')),
  publication_status TEXT NOT NULL DEFAULT 'ok' CHECK (publication_status IN ('ok', 'blocked')),
  geom               geometry(MultiPolygon, 27700)
);
CREATE INDEX IF NOT EXISTS eco_wealth_geom_idx ON eco_wealth USING GIST (geom);
