-- Provenance for SG Data Zone boundary loads (2011 / 2022).
-- Polygons live in public.dz_boundaries (002); this table records URL, vintage,
-- sha256 and load scope so empty-DB national loads and CI fixtures stay honest.
-- Ingest: python -m etl.ingest_dz_boundaries
-- Licence: OGL v3.0 — © Scottish Government, contains OS data © Crown copyright.
-- No £ rent figures.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS dz_boundaries_meta (
    vintage       SMALLINT PRIMARY KEY CHECK (vintage IN (2011, 2022)),
    source_url    TEXT NOT NULL,
    sha256        TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    row_count     INTEGER NOT NULL CHECK (row_count > 0),
    licence       TEXT NOT NULL,
    licence_url   TEXT NOT NULL,
    attribution   TEXT NOT NULL,
    load_scope    TEXT NOT NULL CHECK (load_scope IN ('production', 'fixture')),
    retrieved_at  DATE NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
