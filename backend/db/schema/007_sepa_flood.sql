-- SEPA Flood Maps v3.0 (OGL-3.0). Raw geodatabase stays out of git (data/external).
-- Live map prefers context raster tiles; bbox GeoJSON comes from this table when loaded,
-- else a capped live MapServer query (see layers.flood).

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS sepa_flood (
    object_id INTEGER NOT NULL,
    layer_id SMALLINT NOT NULL,
    source TEXT NOT NULL,
    probability TEXT NOT NULL,
    scenario TEXT,
    map_type TEXT,
    reference TEXT,
    version TEXT,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL,
    PRIMARY KEY (layer_id, object_id)
);

CREATE INDEX IF NOT EXISTS idx_sepa_flood_geom
    ON sepa_flood USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_sepa_flood_source_prob
    ON sepa_flood (source, probability);
