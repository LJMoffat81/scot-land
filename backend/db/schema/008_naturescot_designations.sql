-- NatureScot protected-area designations (OGL-3.0).
-- Raw downloads stay under data/external/naturescot/ (gitignored).
-- Map bbox endpoints read these tables; 503 when unloaded.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS naturescot_sssi (
    pa_code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT,
    site_type TEXT,
    site_ha DOUBLE PRECISION,
    european_code TEXT,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_naturescot_sssi_geom
    ON naturescot_sssi USING GIST (geom);

CREATE TABLE IF NOT EXISTS naturescot_designations (
    site_key TEXT PRIMARY KEY,
    designation_type TEXT NOT NULL
        CHECK (designation_type IN ('spa', 'sac', 'nnr')),
    pa_code TEXT,
    name TEXT NOT NULL,
    status TEXT,
    site_type TEXT,
    site_ha DOUBLE PRECISION,
    european_code TEXT,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_naturescot_designations_geom
    ON naturescot_designations USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_naturescot_designations_type
    ON naturescot_designations (designation_type);
