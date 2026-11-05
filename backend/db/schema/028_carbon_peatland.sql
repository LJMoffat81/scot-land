-- NatureScot Carbon and Peatland 2016 (NCGL). Raw GPKG stays out of git
-- (data/external/). Ingest in EPSG:27700; field IMPORTANCE -> importance.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS carbon_peatland (
    feature_id TEXT PRIMARY KEY,
    importance SMALLINT NOT NULL,
    geom GEOMETRY(MultiPolygon, 27700) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_carbon_peatland_geom
    ON carbon_peatland USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_carbon_peatland_importance
    ON carbon_peatland (importance);
