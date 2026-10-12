-- Common Good sites (OGL council open layers). Raw downloads stay out of git.
-- EPSG:4326 matches other open map overlays. Not a title plan.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS common_good_sites (
    site_id TEXT PRIMARY KEY,
    council_code TEXT NOT NULL,
    council_name TEXT,
    name TEXT,
    site_kind TEXT,
    account TEXT,
    description TEXT,
    area_ha DOUBLE PRECISION,
    source_id TEXT NOT NULL,
    licence TEXT NOT NULL,
    source_url TEXT,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_common_good_sites_geom
    ON common_good_sites USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_common_good_sites_council
    ON common_good_sites (council_code);
