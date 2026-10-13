-- Scot-LAND Data Zones tables, VENDORED from data/processed/datazones/schema.sql (owner: Data Zones).
-- Only mechanical edits: schema-qualified names, IF NOT EXISTS, named index, no SET search_path.
-- Column names, order and types must match the owner's file (tests/etl/test_datazones_schema.py).
-- Loaded by `python -m etl.load_processed --dataset datazones` (verified bytes, COPY into these typed tables).
CREATE SCHEMA IF NOT EXISTS datazones;


CREATE TABLE IF NOT EXISTS datazones.zone_spine (
    code              char(9)   NOT NULL CHECK (code ~ '^S01[0-9]{6}$'),
    vintage           smallint  NOT NULL CHECK (vintage IN (2011, 2022)),
    name              text      NOT NULL,
    iz_code           char(9)   NOT NULL CHECK (iz_code ~ '^S02[0-9]{6}$'),
    la_code           char(9)   NOT NULL CHECK (la_code ~ '^S12[0-9]{6}$'),   -- council area, 2019 codes
    la_name           text      NOT NULL,
    population        integer   CHECK (population >= 0),       -- NRS small area population estimate (mid-year pop_year)
    pop_year          smallint,                                -- 2022 for DZ2011, 2024 for DZ2022
    households        integer   CHECK (households >= 0),       -- NRS occupied dwellings (household proxy), Sept hh_year
    hh_year           smallint,
    dwellings         integer   CHECK (dwellings >= 0),        -- NRS council-tax dwellings_total, Sept dw_year
    dw_year           smallint,
    vacant_share      double precision CHECK (vacant_share BETWEEN 0 AND 1),
    second_home_share double precision CHECK (second_home_share BETWEEN 0 AND 1),
    share_year        smallint,
    in_ros_price_file boolean,                                 -- DZ2011 only; NULL on DZ2022 (RoS file is DZ2011)
    flags             text,                                    -- ';'-separated; '' = no flags (load with FORCE_NOT_NULL (flags) to keep '' rather than NULL). v0.7 adds zero_dwellings, pop_dwellings_mismatch
    PRIMARY KEY (code, vintage),
    CHECK ((vintage = 2011 AND code BETWEEN 'S01006506' AND 'S01013481') OR (vintage = 2022 AND code BETWEEN 'S01013482' AND 'S01020873'))
);

-- Many-to-many people crosswalk DZ2011 <-> DZ2022 (Census 2022 household population at postcode level)
CREATE TABLE IF NOT EXISTS datazones.dz_crosswalk_people (
    dz2011         char(9) NOT NULL CHECK (dz2011 BETWEEN 'S01006506' AND 'S01013481'),
    dz2022         char(9) NOT NULL CHECK (dz2022 BETWEEN 'S01013482' AND 'S01020873'),
    weight         double precision NOT NULL CHECK (weight > 0 AND weight <= 1),          -- share of dz2011 people in dz2022; sums to 1 per dz2011
    reverse_weight double precision NOT NULL CHECK (reverse_weight >= 0 AND reverse_weight <= 1), -- share of dz2022 people from dz2011; sums to 1 per dz2022
    method         text NOT NULL CHECK (method IN ('pop_hhres_2022', 'fallback_census2011_pop_terminated_postcodes')),
    basis_count    numeric NOT NULL CHECK (basis_count >= 0),
    PRIMARY KEY (dz2011, dz2022)
);
CREATE INDEX IF NOT EXISTS dz_crosswalk_people_dz2022_idx ON datazones.dz_crosswalk_people (dz2022);

-- Many-to-many address-point (UPRN) crosswalk DZ2011 <-> DZ2022 (OS Open UPRN point-in-polygon)
-- weight = share of DZ2011 UPRNs in DZ2022; sums to 1 per DZ2011. hh2022_share may be NULL (5 rows).
-- Runtime min-share filter (default ON) may drop sub-1% & <5 UPRN pairs before surface conversion.
CREATE TABLE IF NOT EXISTS datazones.dz2011_dz2022_uprn_weights (
    dz2011          char(9) NOT NULL CHECK (dz2011 BETWEEN 'S01006506' AND 'S01013481'),
    dz2022          char(9) NOT NULL CHECK (dz2022 BETWEEN 'S01013482' AND 'S01020873'),
    uprn_count      integer NOT NULL CHECK (uprn_count > 0),
    weight          double precision NOT NULL CHECK (weight > 0 AND weight <= 1),
    hh2022_share    double precision CHECK (hh2022_share IS NULL OR (hh2022_share >= 0 AND hh2022_share <= 1)),
    share_diff_flag boolean NOT NULL,
    method          text NOT NULL CHECK (method IN ('uprn_point_in_polygon')),
    PRIMARY KEY (dz2011, dz2022)
);
CREATE INDEX IF NOT EXISTS dz2011_dz2022_uprn_weights_dz2022_idx ON datazones.dz2011_dz2022_uprn_weights (dz2022);

CREATE TABLE IF NOT EXISTS datazones.simd2020v2_dz2011 (
    code char(9) NOT NULL, vintage smallint NOT NULL CHECK (vintage = 2011),
    simd_rank smallint NOT NULL CHECK (simd_rank BETWEEN 1 AND 6976),
    simd_vigintile smallint NOT NULL CHECK (simd_vigintile BETWEEN 1 AND 20),
    simd_decile smallint NOT NULL CHECK (simd_decile BETWEEN 1 AND 10),
    simd_quintile smallint NOT NULL CHECK (simd_quintile BETWEEN 1 AND 5),
    -- domain ranks: official file uses half-ranks for ties (e.g. 5955.5)
    income_rank numeric(6,1), employment_rank numeric(6,1), education_rank numeric(6,1), health_rank numeric(6,1),
    access_rank numeric(6,1), crime_rank numeric(6,1), housing_rank numeric(6,1),
    simd_population_2017 integer, simd_working_age_population_2017 integer,
    PRIMARY KEY (code, vintage), FOREIGN KEY (code, vintage) REFERENCES datazones.zone_spine (code, vintage)
);

-- SIMD 2020v2 access-domain raw indicators, DZ2011 ONLY (not crosswalked). Minutes; broadband is a 0-1 proportion.
CREATE TABLE IF NOT EXISTS datazones.simd2020v2_access_indicators_dz2011 (
    code char(9) NOT NULL, vintage smallint NOT NULL CHECK (vintage = 2011),
    drive_petrol double precision, drive_gp double precision, drive_post double precision, drive_primary double precision,
    drive_retail double precision, drive_secondary double precision,
    pt_gp double precision, pt_post double precision, pt_retail double precision,
    broadband double precision CHECK (broadband BETWEEN 0 AND 1),  -- share of premises without superfast (>=30Mb/s); NULL where source shows '*'
    flags text,
    PRIMARY KEY (code, vintage), FOREIGN KEY (code, vintage) REFERENCES datazones.zone_spine (code, vintage)
);

-- Population shares by SIMD 2020v2 band on DZ2022 (derived via crosswalk reverse_weight; ranks never averaged)
CREATE TABLE IF NOT EXISTS datazones.simd2020v2_on_dz2022 (
    code char(9) NOT NULL, vintage smallint NOT NULL CHECK (vintage = 2022),
    decile_1_share double precision, decile_2_share double precision, decile_3_share double precision, decile_4_share double precision,
    decile_5_share double precision, decile_6_share double precision, decile_7_share double precision, decile_8_share double precision,
    decile_9_share double precision, decile_10_share double precision,
    quintile_1_share double precision, quintile_2_share double precision, quintile_3_share double precision,
    quintile_4_share double precision, quintile_5_share double precision,
    modal_decile smallint CHECK (modal_decile BETWEEN 1 AND 10), modal_decile_share double precision,
    n_dz2011_sources smallint, method text NOT NULL,
    PRIMARY KEY (code, vintage), FOREIGN KEY (code, vintage) REFERENCES datazones.zone_spine (code, vintage)
);

-- Council tax bands A-H, NRS dwelling estimates (Assessors' portal, December of year)
CREATE TABLE IF NOT EXISTS datazones.dwellings_ct_band (
    code char(9) NOT NULL, vintage smallint NOT NULL CHECK (vintage IN (2011, 2022)), count_year smallint NOT NULL,
    band_a integer, band_b integer, band_c integer, band_d integer, band_e integer, band_f integer, band_g integer, band_h integer,
    total_dwellings integer,
    PRIMARY KEY (code, vintage, count_year), FOREIGN KEY (code, vintage) REFERENCES datazones.zone_spine (code, vintage)
);

-- Canonical dwellings by year: NRS council-tax household & dwelling estimates (September of year)
CREATE TABLE IF NOT EXISTS datazones.dwellings_by_year (
    code char(9) NOT NULL, vintage smallint NOT NULL CHECK (vintage IN (2011, 2022)), count_year smallint NOT NULL,
    dwellings_total integer, occupied integer, vacant integer, second_homes integer, long_term_empty integer,
    unoccupied_exempt integer, occupied_exempt integer, single_adult_discount integer,
    vacant_share double precision, second_home_share double precision,
    assessor_dwellings_dec integer,          -- Assessors' portal count, December (same as dwellings_ct_band.total_dwellings)
    source_file text, source_sheet text, flags text,
    PRIMARY KEY (code, vintage, count_year), FOREIGN KEY (code, vintage) REFERENCES datazones.zone_spine (code, vintage)
);

CREATE TABLE IF NOT EXISTS datazones.dwellings_by_year_coverage (
    vintage smallint NOT NULL CHECK (vintage IN (2011, 2022)), count_year smallint NOT NULL,
    ctax_split_published boolean NOT NULL, ctax_source text,
    assessor_ct_band_published boolean NOT NULL, assessor_source text,
    PRIMARY KEY (vintage, count_year)
);

-- HISTORIC FALLBACK ONLY: dwelling type and rooms on DZ2011, 2014-2017 (NRS stopped publishing after 2017)
CREATE TABLE IF NOT EXISTS datazones.nrs_dwelling_mix_2011_fallback (
    code char(9) NOT NULL, vintage smallint NOT NULL CHECK (vintage = 2011), count_year smallint NOT NULL CHECK (count_year BETWEEN 2014 AND 2017),
    type_all integer, type_detached integer, type_semi_detached integer, type_terraced integer, type_flat integer, type_unknown integer,
    rooms_1 integer, rooms_2 integer, rooms_3 integer, rooms_4 integer, rooms_5 integer, rooms_6 integer, rooms_7 integer,
    rooms_8 integer, rooms_9 integer, rooms_10_plus integer, rooms_unknown integer,
    status text NOT NULL CHECK (status = 'historic_fallback_dz2011_only'),
    PRIMARY KEY (code, vintage, count_year), FOREIGN KEY (code, vintage) REFERENCES datazones.zone_spine (code, vintage)
);

-- Planning authority per zone (34 authorities: 32 councils + LLTNP S21000002 + CNPA S21000003)
CREATE TABLE IF NOT EXISTS datazones.dz_planning_authority (
    code char(9) NOT NULL, vintage smallint NOT NULL CHECK (vintage IN (2011, 2022)),
    plan_making_authority char(9) NOT NULL CHECK (plan_making_authority ~ '^S(12|21)[0-9]{6}$'),
    plan_making_authority_name text NOT NULL,
    deciding_authority char(9) NOT NULL CHECK (deciding_authority ~ '^S(12|21)[0-9]{6}$'),
    deciding_authority_name text NOT NULL,
    share double precision NOT NULL CHECK (share BETWEEN 0 AND 1),   -- Census 2022 household share; sums to 1 per zone
    area_share double precision,                                     -- polygon area share (from GIS overlay), NULL outside parks
    hh_2022 integer, hh_2022_zone_total integer,
    method text NOT NULL CHECK (method IN ('council_outside_park', 'park_split_census2022_postcode_households', 'wholly_in_park')),
    note text,
    PRIMARY KEY (code, vintage, plan_making_authority), FOREIGN KEY (code, vintage) REFERENCES datazones.zone_spine (code, vintage)
);
