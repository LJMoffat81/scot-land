-- Land Capability for Agriculture (James Hutton Institute LCA 1:250k).
-- James Hutton Open Data Licence (not OGL) — PSI under OGL v2.0 per attribution.
-- Raw downloads stay under data/external/lca/ (gitignored). Ingest:
--   python -m etl.ingest_lca
-- Ledger constraint (£0) — changes best permitted use only; not a rent or title.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS lca_agriculture (
    id SERIAL PRIMARY KEY,
    lccode DOUBLE PRECISION NOT NULL,
    class_label TEXT NOT NULL,
    prime TEXT,
    scale TEXT,
    hectares DOUBLE PRECISION,
    sqmid TEXT,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lca_agriculture_geom
    ON lca_agriculture USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_lca_agriculture_lccode
    ON lca_agriculture (lccode);
