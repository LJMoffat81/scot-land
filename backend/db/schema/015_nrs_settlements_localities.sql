-- NRS Census 2022 Settlements and Localities (OGL).
-- Source: maps.gov.scot NRS/Census2022 WFS (CEN2022:Settlement2022, CEN2022:Locality2022).
-- Raw downloads stay under data/external/ (gitignored). EPSG:4326 for API bbox queries.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS nrs_settlements (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    popcount INTEGER,
    area_m2 DOUBLE PRECISION,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nrs_settlements_geom
    ON nrs_settlements USING GIST (geom);

CREATE TABLE IF NOT EXISTS nrs_localities (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    popcount INTEGER,
    area_m2 DOUBLE PRECISION,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nrs_localities_geom
    ON nrs_localities USING GIST (geom);
