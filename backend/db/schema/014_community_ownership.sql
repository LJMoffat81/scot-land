-- Community Ownership in Scotland 2024 (SG OGL dataset) — postcode-centroid points.
-- Raw XLSX stays out of git; processed GeoJSON lives under data/processed/gis/.
-- Points are not title polygons. EPSG:4326 matches map bbox queries.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS community_ownership_assets (
    asset_id TEXT PRIMARY KEY,
    group_name TEXT NOT NULL,
    asset_name TEXT,
    postcode TEXT,
    local_authority TEXT,
    la_s_code TEXT,
    area_ha DOUBLE PRECISION,
    asset_type TEXT,
    year_of_ownership INTEGER,
    geometry_source TEXT NOT NULL DEFAULT 'postcode_centroid',
    geom GEOMETRY(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_community_ownership_assets_geom
    ON community_ownership_assets USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_community_ownership_assets_la
    ON community_ownership_assets (la_s_code);
