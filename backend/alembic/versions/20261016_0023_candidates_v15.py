"""candidates_v15 schema for LAYERS-ADD-1 DZ aggregates (v1.5 isolation).

Revision ID: 20261016_0023
Revises: 20261015_0022
Create Date: 2026-10-16

Tables are written here only. v1.4 model code must not import this schema (L14).
IF NOT EXISTS keeps this revision idempotent when CI/test DBs already have
objects from a prior partial upgrade or schema SQL.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261016_0023"
down_revision: Union[str, None] = "20261015_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS candidates_v15")
    # Strict keys: zone_id S01######, dz_vintage 2011|2022. No currency columns.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_simd2020_domains (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            topic TEXT NOT NULL,
            q INTEGER,
            PRIMARY KEY (zone_id, dz_vintage, topic)
        )
        """
    )
    op.execute(
        """
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
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_hes_ca (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            share DOUBLE PRECISION NOT NULL DEFAULT 0,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_hes_lb (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            category TEXT NOT NULL,
            n_listings INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (zone_id, dz_vintage, category)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_sepa_nfra (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            score_mean_areaw DOUBLE PRECISION,
            score_max INTEGER,
            n_cells INTEGER NOT NULL DEFAULT 0,
            grid_coarser_than_zone BOOLEAN,
            reason TEXT,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_vdl (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            site_count INTEGER NOT NULL DEFAULT 0,
            hectares DOUBLE PRECISION NOT NULL DEFAULT 0,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_green_belt (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            share DOUBLE PRECISION NOT NULL DEFAULT 0,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_school_catch (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            stage TEXT NOT NULL,
            catchment_id TEXT,
            school_name TEXT,
            data_year TEXT,
            PRIMARY KEY (zone_id, dz_vintage, stage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_contam (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            site_count INTEGER NOT NULL DEFAULT 0,
            present BOOLEAN NOT NULL DEFAULT false,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_ldp (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            use_class TEXT NOT NULL,
            hectares DOUBLE PRECISION NOT NULL DEFAULT 0,
            PRIMARY KEY (zone_id, dz_vintage, use_class)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_hls (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            effective_units DOUBLE PRECISION,
            hectares DOUBLE PRECISION NOT NULL DEFAULT 0,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )


def downgrade() -> None:
    for table in (
        "agg_hls",
        "agg_ldp",
        "agg_contam",
        "agg_school_catch",
        "agg_green_belt",
        "agg_vdl",
        "agg_sepa_nfra",
        "agg_hes_lb",
        "agg_hes_ca",
        "agg_naptan",
        "agg_simd2020_domains",
    ):
        op.execute(f"DROP TABLE IF EXISTS candidates_v15.{table} CASCADE")
    op.execute("DROP SCHEMA IF EXISTS candidates_v15 CASCADE")
