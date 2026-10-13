-- NFI Woodland (Scotland) and Native Woodland Survey of Scotland.
-- Local PostGIS ingest from NatureScot / Scottish Forestry open WFS (OGL).
-- Raw national extracts stay under data/external/ (gitignored).

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS nfi_woodland (
    feature_id TEXT PRIMARY KEY,
    category TEXT,
    ift_ioa TEXT,
    country TEXT,
    area_ha DOUBLE PRECISION,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nfi_woodland_geom
    ON nfi_woodland USING GIST (geom);

CREATE TABLE IF NOT EXISTS native_woodland (
    feature_id TEXT PRIMARY KEY,
    object_id INTEGER,
    scptdata_i INTEGER,
    woodland_type TEXT,
    canopy_pct INTEGER,
    native_pct INTEGER,
    dom_habitat TEXT,
    hectares DOUBLE PRECISION,
    maturity TEXT,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_native_woodland_geom
    ON native_woodland USING GIST (geom);
