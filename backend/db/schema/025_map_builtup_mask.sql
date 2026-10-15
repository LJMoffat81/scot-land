-- UX10-2 built-up display mask (DISPLAY ONLY — never changes any figure).
-- Sources: NRS Settlements 2022 (OGL v3) ∪ OS Open UPRN buffers; DZ2022 ∩ mask.
-- Delivery GeoJSON/GPKG stay under data/external/builtup/ (gitignored) or BUILTUP_MASK_DIR.
-- EPSG:4326 for API bbox / MapLibre vector layers (zoom-simplified viewport geometry).

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS map_builtup_mask (
    gid BIGSERIAL PRIMARY KEY,
    geom GEOMETRY(Polygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_map_builtup_mask_geom
    ON map_builtup_mask USING GIST (geom);

CREATE TABLE IF NOT EXISTS dz2022_masked (
    code TEXT PRIMARY KEY CHECK (code ~ '^S01[0-9]{6}$'),
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dz2022_masked_geom
    ON dz2022_masked USING GIST (geom);
