-- Display denominators per data zone (DRAFT stub, lead SE, 2026-10-06). Economic rules v0.5.
-- Map views for surface rent:
--   1. default: rent per hectare of RESIDENTIAL land (settlement + residential parcels; GIS, not built yet).
--      Interim fallback: zone area inside the NRS settlement boundary, flagged as rough.
--   2. rent per dwelling: NRS council-tax dwellings, TOTAL (incl. vacant and second homes).
--   3. optional: rent per resident, always shown with the second-home share.
-- There is deliberately NO whole-zone area column: rent per hectare of whole-zone
-- area is never shown for surface rent (farmland and moor dilute it).
-- Missing value => the API reports 'denominator_pending' and computes nothing.

-- Areas (GIS). Keyed (code, vintage): areas do not change with the money year.
CREATE TABLE IF NOT EXISTS dz_denominators (
  code                     TEXT NOT NULL CHECK (code ~ '^S01[0-9]{6}$'),
  vintage                  SMALLINT NOT NULL CHECK (vintage IN (2011, 2022)),
  residential_land_ha      NUMERIC CHECK (residential_land_ha > 0),
  residential_land_source  TEXT,
  settlement_area_ha       NUMERIC CHECK (settlement_area_ha > 0),   -- interim, rough
  settlement_source        TEXT,
  source_id                TEXT,
  licence                  TEXT,
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (code, vintage),
  CHECK (
    (vintage = 2011 AND substr(code, 4)::int BETWEEN 6506 AND 13481)
    OR (vintage = 2022 AND substr(code, 4)::int BETWEEN 13482 AND 20873)
  )
);

-- Confidence inputs for the per-residential-hectare view (GIS dz_residential_land.csv; filled by
-- etl.load_processed). Display only: residential area never touches surface money totals.
ALTER TABLE dz_denominators ADD COLUMN IF NOT EXISTS share_res_uprn_in_parcels NUMERIC
  CHECK (share_res_uprn_in_parcels BETWEEN 0 AND 1);
ALTER TABLE dz_denominators ADD COLUMN IF NOT EXISTS mask_too_big_parcel BOOLEAN;
ALTER TABLE dz_denominators ADD COLUMN IF NOT EXISTS res_uprn_exceeds_dwellings BOOLEAN;
ALTER TABLE dz_denominators ADD COLUMN IF NOT EXISTS residential_flags TEXT;

-- Counts are Scot-LAND Data Zones' tables (schema 004), never copies:
--   dwellings  datazones.dwellings_by_year.dwellings_total  (NRS council tax, Sept; NOT assessor_dwellings_dec)
--   population datazones.zone_spine.population at pop_year  (mid-2022 on 2011 zones, mid-2024 on 2022 zones)
-- The engine joins on surface_rent_dz (code, vintage) AND count_year (pop_year) = price_year.
-- A missing count is flagged on the row; it is NEVER filled from another year or vintage.
