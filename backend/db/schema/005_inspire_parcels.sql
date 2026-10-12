-- RoS INSPIRE Index Polygons (local ingest). Raw GML stays out of git (data/external).
-- EPSG:4326 here matches the PR #4 ingest and layers.cadastral bbox query.
-- Map tiles still proxy the live ROS WMS (spatial.parcels).

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS inspire_parcels (
    inspire_id TEXT PRIMARY KEY,
    national_reference TEXT,
    label TEXT,
    area_sqm DOUBLE PRECISION,
    county TEXT,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_inspire_parcels_geom
    ON inspire_parcels USING GIST (geom);
