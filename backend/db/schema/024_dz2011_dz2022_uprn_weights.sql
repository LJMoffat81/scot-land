-- Incremental: address-UPRN DZ2011→DZ2022 crosswalk (also in 004_datazones.sql).
-- Applied by alembic 20261013_0021 on DBs already past the baseline.
CREATE SCHEMA IF NOT EXISTS datazones;

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
