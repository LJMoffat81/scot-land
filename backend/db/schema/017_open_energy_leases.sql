-- Open energy / seabed lease layers (OGL).
-- REPD: DESNZ Renewable Energy Planning Database (Scotland points).
-- Crown Estate Scotland leases: Spatial Hub FeatureServer polygons (OGL v3).
-- Raw downloads stay out of git (data/external or ephemeral); ingest via:
--   python -m etl.ingest_repd
--   python -m etl.ingest_crown_estate_leases

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS repd_sites (
    ref_id TEXT PRIMARY KEY,
    site_name TEXT,
    operator_name TEXT,
    technology_type TEXT,
    development_status TEXT,
    development_status_short TEXT,
    installed_capacity_mw DOUBLE PRECISION,
    country TEXT,
    region TEXT,
    postcode TEXT,
    planning_authority TEXT,
    geom GEOMETRY(Point, 4326) NOT NULL,
    source TEXT NOT NULL DEFAULT 'DESNZ REPD',
    licence TEXT NOT NULL DEFAULT 'OGL-3.0',
    retrieved_at DATE
);

CREATE INDEX IF NOT EXISTS idx_repd_sites_geom ON repd_sites USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_repd_sites_tech ON repd_sites (technology_type);

CREATE TABLE IF NOT EXISTS crown_estate_leases (
    id TEXT PRIMARY KEY,
    lease_theme TEXT NOT NULL,
    description TEXT,
    tenant_name TEXT,
    agreement_type TEXT,
    property_classification TEXT,
    project_phase TEXT,
    capacity_mw DOUBLE PRECISION,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL,
    source TEXT NOT NULL DEFAULT 'Crown Estate Scotland Spatial Hub',
    licence TEXT NOT NULL DEFAULT 'OGL-3.0',
    retrieved_at DATE
);

CREATE INDEX IF NOT EXISTS idx_crown_estate_leases_geom
    ON crown_estate_leases USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_crown_estate_leases_theme
    ON crown_estate_leases (lease_theme);
