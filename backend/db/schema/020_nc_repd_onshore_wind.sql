-- Natural capital P1: DESNZ REPD onshore wind (Scotland).
-- Data/layer only — MW and development status. No £ rent figures.
-- Overlays never add to Surface Rent / AGR totals.
-- Raw CSV stays out of git; load via: python -m etl.ingest_repd_onshore_wind

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS repd_onshore_wind (
    ref_id TEXT PRIMARY KEY,
    site_name TEXT,
    operator_name TEXT,
    technology_type TEXT NOT NULL,
    development_status TEXT,
    development_status_short TEXT,
    installed_capacity_mw DOUBLE PRECISION,
    country TEXT,
    region TEXT,
    postcode TEXT,
    planning_authority TEXT,
    -- Evidence class for natural-capital work (not a rent tier on this layer).
    value_tier TEXT NOT NULL DEFAULT 'market'
        CHECK (value_tier IN ('market', 'proxy', 'shadow')),
    -- Honest gate when a row is too thin to publish as site evidence.
    publication_status TEXT NOT NULL DEFAULT 'ok'
        CHECK (publication_status IN ('ok', 'blocked')),
    publish_level TEXT NOT NULL DEFAULT 'public_site'
        CHECK (publish_level IN ('public_site', 'public_zone', 'internal')),
    geom GEOMETRY(Point, 4326) NOT NULL,
    source TEXT NOT NULL DEFAULT 'DESNZ REPD',
    licence TEXT NOT NULL DEFAULT 'OGL-3.0',
    retrieved_at DATE
);

CREATE INDEX IF NOT EXISTS idx_repd_onshore_wind_geom
    ON repd_onshore_wind USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_repd_onshore_wind_status
    ON repd_onshore_wind (development_status_short);
CREATE INDEX IF NOT EXISTS idx_repd_onshore_wind_pub
    ON repd_onshore_wind (publication_status, publish_level);
