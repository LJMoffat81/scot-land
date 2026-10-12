-- Natural-capital P1: SEPA hydropower sites + CAR licences (OGL).
-- Data/layers only — no £ rent figures. Overlays never add value.
-- Hydro: ATOM shapefile download (OGL).
-- CAR: public-register CSV export only (download-only — never MapServer scrape).
-- Raw downloads stay out of git (temp or operator path); never data/external in repo.
--   python -m etl.ingest_hydro_sites
--   python -m etl.ingest_sepa_car --csv /path/to/sepa_car_export.csv

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
    authorisation_no TEXT PRIMARY KEY,
    authorisation_holder TEXT,
    authorisation_location TEXT,
    authorisation_level TEXT,
    authorisation_status TEXT,
    regulatory_area TEXT,
    authorisation_activity TEXT,
    ngr TEXT,
    geom GEOMETRY(Point, 4326),
    commons_class TEXT NOT NULL DEFAULT 'extractive',
    value_tier TEXT NOT NULL DEFAULT 'proxy',
    publication_status TEXT NOT NULL DEFAULT 'download_only',
    source TEXT NOT NULL DEFAULT 'SEPA Public Register CAR export',
    licence TEXT NOT NULL DEFAULT 'OGL-3.0',
    retrieved_at DATE
);

CREATE INDEX IF NOT EXISTS idx_sepa_car_licences_geom
    ON sepa_car_licences USING GIST (geom)
    WHERE geom IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sepa_car_licences_level
    ON sepa_car_licences (authorisation_level);
