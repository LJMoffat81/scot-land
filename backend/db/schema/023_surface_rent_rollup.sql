-- SG surface-rent roll-up (DZ2022 → IZ → Council → Scotland). INTERNAL ONLY.
-- Measured £ figures here are unpublished until ECONOMIC_RULES approval.
-- Leaves stay on surface_rent_dz; this table holds parent aggregates only.
-- Hierarchy codes: S02 Intermediate Zone, S12 Council Area, S92 Scotland.

CREATE TABLE IF NOT EXISTS surface_rent_rollup (
  geo_level            TEXT NOT NULL CHECK (geo_level IN ('intermediate_zone', 'council', 'scotland')),
  code                 TEXT NOT NULL,
  vintage              SMALLINT NOT NULL CHECK (vintage = 2022),
  valuation_date       DATE NOT NULL,
  price_year           SMALLINT NOT NULL,
  measured_rent        NUMERIC,  -- GBP/yr sum of child DZ measured_rent (same price_year)
  zone_count           INTEGER NOT NULL CHECK (zone_count > 0),
  withheld_zone_count  INTEGER NOT NULL DEFAULT 0 CHECK (withheld_zone_count >= 0),
  value_tier           TEXT NOT NULL CHECK (value_tier IN ('market', 'proxy', 'shadow')),
  quality              TEXT NOT NULL CHECK (quality IN ('live', 'derived', 'modelled', 'placeholder')),
  publish_level        TEXT NOT NULL CHECK (publish_level = 'internal'),  -- never public
  publication_status   TEXT NOT NULL DEFAULT 'ok' CHECK (publication_status IN ('ok', 'blocked')),
  commons_class        TEXT NOT NULL DEFAULT 'surface',
  crosswalk_method     TEXT NOT NULL CHECK (crosswalk_method IN ('none', 'address_uprn', 'value_weighted')),
  source_id            TEXT NOT NULL,
  licence              TEXT NOT NULL,
  method               TEXT NOT NULL,
  parent_code          TEXT,  -- IZ→LA, LA→Scotland; NULL for Scotland
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (geo_level, code, vintage, valuation_date),
  CHECK (
    (geo_level = 'intermediate_zone' AND code ~ '^S02[0-9]{6}$')
    OR (geo_level = 'council' AND code ~ '^S12[0-9]{6}$')
    OR (geo_level = 'scotland' AND code = 'S92000003')
  )
);
CREATE INDEX IF NOT EXISTS surface_rent_rollup_parent_idx
  ON surface_rent_rollup (parent_code, geo_level);
CREATE INDEX IF NOT EXISTS surface_rent_rollup_level_idx
  ON surface_rent_rollup (geo_level, vintage, valuation_date);
