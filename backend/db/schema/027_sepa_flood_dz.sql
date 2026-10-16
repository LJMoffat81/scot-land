-- SEPA Flood Maps v3.0 medium-likelihood present-day extent, as Data Zone shares.
-- One row per 2022 Data Zone. No flood polygons. Nothing finer than a Data Zone.
-- Loader: python -m etl.ingest_sepa_frm_v3 --replace
CREATE TABLE IF NOT EXISTS sepa_flood_dz (
    data_zone         TEXT PRIMARY KEY CHECK (data_zone ~ '^S01[0-9]{6}$'),
    pct_area_river    SMALLINT NOT NULL CHECK (pct_area_river BETWEEN 0 AND 100),
    pct_area_coastal  SMALLINT NOT NULL CHECK (pct_area_coastal BETWEEN 0 AND 100),
    pct_area_surface  SMALLINT NOT NULL CHECK (pct_area_surface BETWEEN 0 AND 100),
    source_version    TEXT NOT NULL
);
