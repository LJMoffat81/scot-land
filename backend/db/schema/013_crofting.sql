-- Crofting Commission Register of Crofts (tabular OGL-3.0) for Georgist / Valuation.
-- Spatial extents stay on the RoS Crofting Register map (not OGL redistributable here).
-- Raw downloads stay under data/external/crofting/ (gitignored). Never ingest Individuals.

CREATE TABLE IF NOT EXISTS croft_parishes (
    parish_id INTEGER PRIMARY KEY,
    parish_code TEXT,
    parish_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS croft_holdings (
    holding_id INTEGER PRIMARY KEY,
    croft_name TEXT,
    status_a TEXT,
    status_b TEXT,
    status_c TEXT,
    croft_let INTEGER,
    main_location_code TEXT,
    croft_file_number TEXT,
    register_number TEXT,
    total_area_ha DOUBLE PRECISION,
    parish_id INTEGER REFERENCES croft_parishes (parish_id),
    parish_name TEXT,
    township TEXT,
    crofting_registration_number TEXT,
    consent_to_be_absent_until TEXT
);

CREATE INDEX IF NOT EXISTS idx_croft_holdings_parish
    ON croft_holdings (parish_id);
CREATE INDEX IF NOT EXISTS idx_croft_holdings_reg
    ON croft_holdings (crofting_registration_number);

CREATE TABLE IF NOT EXISTS common_grazings (
    grazing_id INTEGER PRIMARY KEY,
    grazing_name TEXT,
    code TEXT,
    crofting_registration_number TEXT,
    area_name TEXT,
    parish_id INTEGER REFERENCES croft_parishes (parish_id),
    parish_name TEXT,
    current_extent_ha DOUBLE PRECISION,
    current_extent_date TEXT,
    original_extent_ha DOUBLE PRECISION,
    original_extent_date TEXT,
    agricultural_code TEXT,
    committee_end_date TEXT
);

CREATE INDEX IF NOT EXISTS idx_common_grazings_parish
    ON common_grazings (parish_id);
CREATE INDEX IF NOT EXISTS idx_common_grazings_code
    ON common_grazings (code);

CREATE TABLE IF NOT EXISTS crofting_ingest_meta (
    dataset TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    licence TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    row_count INTEGER NOT NULL,
    sha256 TEXT
);
