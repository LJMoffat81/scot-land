-- Crown Estate Scotland ScotWind Offers + INTOG Application Areas (OGL-3.0).
-- Credit: Contains information from the Crown Estate Scotland licensed under
-- the Open Government Licence v3.0.
-- Polygons + award descriptors only. Option-fee £ are HOLD in
-- data/config/scotwind_option_fees.yaml — never layer attributes.
-- Raw downloads stay under data/external/ces/ (gitignored). Ingest:
--   python -m etl.ingest_scotwind_intog --from-api
-- Natural capital ledger row 4 (seabed & foreshore); no £ rent.
-- Overlay never adds value to surface rent (la-calc).

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS ces_scotwind_intog (
    id TEXT PRIMARY KEY,
    leasing_round TEXT NOT NULL,
    award_id INTEGER,
    lead_applicant TEXT,
    technology TEXT,
    category TEXT,
    innovation_category TEXT,
    capacity_mw DOUBLE PRECISION,
    area_km2 DOUBLE PRECISION,
    evidence_tag TEXT NOT NULL DEFAULT 'market',
    publication_status TEXT NOT NULL DEFAULT 'ok',
    source_id TEXT,
    licence TEXT,
    geom GEOMETRY(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ces_scotwind_intog_geom
    ON ces_scotwind_intog USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_ces_scotwind_intog_round
    ON ces_scotwind_intog (leasing_round);
