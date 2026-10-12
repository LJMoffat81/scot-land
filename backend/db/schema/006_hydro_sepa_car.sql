-- Natural-capital P1: SEPA hydropower sites + CAR licences (OGL).
-- Data/layers only — no £ rent figures. Overlays never add value.
-- Hydro: ATOM shapefile download (OGL).
-- CAR: Open/SEPA_Reference MapServer layers 194/195 → PostGIS at ingest.
--       API serves PostGIS only — never proxies MapServer to clients.
-- Raw downloads stay out of git; never data/external in repo.
--   python -m etl.ingest_hydro_sites
--   python -m etl.ingest_sepa_car

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS hydro_sites (
    lic_no TEXT PRIMARY KEY,
    auth_id INTEGER,
    site_name TEXT,
    licence_start_date DATE,
    geom GEOMETRY(Point, 4326) NOT NULL,
    commons_class TEXT NOT NULL DEFAULT 'extractive',
    value_tier TEXT NOT NULL DEFAULT 'proxy',
    publication_status TEXT NOT NULL DEFAULT 'ok',
    source TEXT NOT NULL DEFAULT 'SEPA Hydropower Sites',
    licence TEXT NOT NULL DEFAULT 'OGL-3.0',
    retrieved_at DATE
);

CREATE INDEX IF NOT EXISTS idx_hydro_sites_geom ON hydro_sites USING GIST (geom);

CREATE TABLE IF NOT EXISTS sepa_car_licences (
    authorisation_no TEXT NOT NULL,
    car_layer TEXT NOT NULL,
    authorisation_holder TEXT,
    authorisation_description TEXT,
    authorisation_level TEXT,
    authorisation_status TEXT,
    regulatory_area TEXT,
    authorisation_activity TEXT,
    category TEXT,
    ngr TEXT,
    easting INTEGER,
    northing INTEGER,
    commons_class TEXT NOT NULL DEFAULT 'extractive',
    value_tier TEXT NOT NULL DEFAULT 'market'
        CHECK (value_tier IN ('market', 'proxy', 'shadow')),
    publication_status TEXT NOT NULL DEFAULT 'ok'
        CHECK (publication_status IN ('ok', 'blocked')),
    geom GEOMETRY(Point, 4326),
    source TEXT NOT NULL DEFAULT 'SEPA_Reference MapServer CAR layers',
    licence TEXT NOT NULL DEFAULT 'OGL-3.0',
    retrieved_at DATE,
    PRIMARY KEY (authorisation_no, car_layer)
);

CREATE INDEX IF NOT EXISTS idx_sepa_car_licences_geom
    ON sepa_car_licences USING GIST (geom)
    WHERE geom IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sepa_car_licences_level
    ON sepa_car_licences (authorisation_level);
CREATE INDEX IF NOT EXISTS idx_sepa_car_licences_layer
    ON sepa_car_licences (car_layer);
