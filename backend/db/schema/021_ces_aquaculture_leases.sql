-- Natural-capital P1: Crown Estate Scotland aquaculture seabed leases (OGL).
-- Source: CES Spatial Hub FeatureServer Aquaculture_Crown_Estate_Scotland.
-- Data/layer only — lease attributes/status. No £ rent or fee figures.
-- Overlays never add to Surface Rent / AGR totals. Ledger row 5 evidence.
-- Ingest: python -m etl.ingest_ces_aquaculture
-- Attribution (CES): Contains information from the Crown Estate Scotland
-- licensed under the Open Government Licence v3.0.
-- Numbered past main REPD 020 / 20261012_0017.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS ces_aquaculture_leases (
    id TEXT PRIMARY KEY,
    site_id TEXT,
    lease_description TEXT,
    property_classification TEXT,
    value_tier TEXT NOT NULL CHECK (value_tier IN ('market', 'proxy', 'shadow')),
    publication_status TEXT NOT NULL CHECK (publication_status IN ('ok', 'blocked')),
    unpublished_reason TEXT,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL,
    source TEXT NOT NULL DEFAULT 'Crown Estate Scotland Spatial Hub',
    licence TEXT NOT NULL DEFAULT 'OGL-3.0',
    licence_url TEXT NOT NULL,
    attribution TEXT NOT NULL,
    source_url TEXT,
    retrieved_at DATE
);

CREATE INDEX IF NOT EXISTS idx_ces_aquaculture_leases_geom
    ON ces_aquaculture_leases USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_ces_aquaculture_leases_class
    ON ces_aquaculture_leases (property_classification);
CREATE INDEX IF NOT EXISTS idx_ces_aquaculture_leases_tier
    ON ces_aquaculture_leases (value_tier);
