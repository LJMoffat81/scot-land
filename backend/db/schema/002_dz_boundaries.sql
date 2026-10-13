-- Data zone boundaries for point -> (code, vintage) lookup.
-- Preferred load: `python -m etl.ingest_dz_boundaries --fetch` (SG ATOM shapefiles →
-- EPSG:27700; provenance in dz_boundaries_meta). CI: `--fixture`.
-- Also: `python -m etl.load_processed` for manifest-listed GeoJSON.
-- Source: Scottish Government data zone boundaries 2011 / 2022 (OGL v3.0).
CREATE TABLE IF NOT EXISTS dz_boundaries (
  code        TEXT NOT NULL CHECK (code ~ '^S01[0-9]{6}$'),
  vintage     SMALLINT NOT NULL CHECK (vintage IN (2011, 2022)),
  name        TEXT,
  geom        geometry(MultiPolygon, 27700) NOT NULL,
  source_id   TEXT,
  licence     TEXT,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (code, vintage),
  CHECK (
    (vintage = 2011 AND substr(code, 4)::int BETWEEN 6506 AND 13481)
    OR (vintage = 2022 AND substr(code, 4)::int BETWEEN 13482 AND 20873)
  )
);
CREATE INDEX IF NOT EXISTS dz_boundaries_geom_idx ON dz_boundaries USING GIST (geom);
CREATE INDEX IF NOT EXISTS dz_boundaries_vintage_idx ON dz_boundaries (vintage);
