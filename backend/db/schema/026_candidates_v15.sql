-- LAYERS-ADD-1 candidates_v15 DZ aggregates (v1.5 isolation).
-- Also applied by alembic 20261016_0023. IF NOT EXISTS for idempotency.

CREATE SCHEMA IF NOT EXISTS candidates_v15;

CREATE TABLE IF NOT EXISTS candidates_v15.agg_simd2020_domains (
    zone_id TEXT NOT NULL,
    dz_vintage INTEGER NOT NULL,
    topic TEXT NOT NULL,
    q INTEGER,
    PRIMARY KEY (zone_id, dz_vintage, topic)
);

CREATE TABLE IF NOT EXISTS candidates_v15.agg_naptan (
    zone_id TEXT NOT NULL,
    dz_vintage INTEGER NOT NULL,
    n_bus_active INTEGER NOT NULL DEFAULT 0,
    n_ferry_active INTEGER NOT NULL DEFAULT 0,
    n_tram_subway_active INTEGER NOT NULL DEFAULT 0,
    dist_rail_m DOUBLE PRECISION,
    n_rail_1000m INTEGER NOT NULL DEFAULT 0,
    dist_ferry_m DOUBLE PRECISION,
    naptan_extract_date TEXT,
    PRIMARY KEY (zone_id, dz_vintage)
);

CREATE TABLE IF NOT EXISTS candidates_v15.agg_hes_ca (
    zone_id TEXT NOT NULL,
    dz_vintage INTEGER NOT NULL,
    share DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (zone_id, dz_vintage)
);

CREATE TABLE IF NOT EXISTS candidates_v15.agg_hes_lb (
    zone_id TEXT NOT NULL,
    dz_vintage INTEGER NOT NULL,
    category TEXT NOT NULL,
    n_listings INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (zone_id, dz_vintage, category)
);

CREATE TABLE IF NOT EXISTS candidates_v15.agg_sepa_nfra (
    zone_id TEXT NOT NULL,
    dz_vintage INTEGER NOT NULL,
    score_mean_areaw DOUBLE PRECISION,
    score_max INTEGER,
    n_cells INTEGER NOT NULL DEFAULT 0,
    grid_coarser_than_zone BOOLEAN,
    reason TEXT,
    PRIMARY KEY (zone_id, dz_vintage)
);

CREATE TABLE IF NOT EXISTS candidates_v15.agg_vdl (
    zone_id TEXT NOT NULL,
    dz_vintage INTEGER NOT NULL,
    site_count INTEGER NOT NULL DEFAULT 0,
    hectares DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (zone_id, dz_vintage)
);

CREATE TABLE IF NOT EXISTS candidates_v15.agg_green_belt (
    zone_id TEXT NOT NULL,
    dz_vintage INTEGER NOT NULL,
    share DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (zone_id, dz_vintage)
);

CREATE TABLE IF NOT EXISTS candidates_v15.agg_school_catch (
    zone_id TEXT NOT NULL,
    dz_vintage INTEGER NOT NULL,
    stage TEXT NOT NULL,
    catchment_id TEXT,
    school_name TEXT,
    data_year TEXT,
    PRIMARY KEY (zone_id, dz_vintage, stage)
);

CREATE TABLE IF NOT EXISTS candidates_v15.agg_contam (
    zone_id TEXT NOT NULL,
    dz_vintage INTEGER NOT NULL,
    site_count INTEGER NOT NULL DEFAULT 0,
    present BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (zone_id, dz_vintage)
);

CREATE TABLE IF NOT EXISTS candidates_v15.agg_ldp (
    zone_id TEXT NOT NULL,
    dz_vintage INTEGER NOT NULL,
    use_class TEXT NOT NULL,
    hectares DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (zone_id, dz_vintage, use_class)
);

CREATE TABLE IF NOT EXISTS candidates_v15.agg_hls (
    zone_id TEXT NOT NULL,
    dz_vintage INTEGER NOT NULL,
    effective_units DOUBLE PRECISION,
    hectares DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (zone_id, dz_vintage)
);
