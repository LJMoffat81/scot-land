"""candidates_v15 schema for LAYERS-ADD-1 DZ aggregates (v1.5 isolation).

Revision ID: 20261016_0023
Revises: 20261015_0022
Create Date: 2026-10-16

Tables are written here only. v1.4 model code must not import this schema (L14).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261016_0023"
down_revision: Union[str, None] = "20261015_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS candidates_v15")
    # Strict keys: zone_id S01######, dz_vintage 2011|2022. No currency columns.
    op.create_table(
        "agg_simd2020_domains",
        sa.Column("zone_id", sa.Text(), nullable=False),
        sa.Column("dz_vintage", sa.Integer(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("q", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("zone_id", "dz_vintage", "topic"),
        schema="candidates_v15",
    )
    op.create_table(
        "agg_naptan",
        sa.Column("zone_id", sa.Text(), nullable=False),
        sa.Column("dz_vintage", sa.Integer(), nullable=False),
        sa.Column("n_bus_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_ferry_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "n_tram_subway_active", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("dist_rail_m", sa.Float(), nullable=True),
        sa.Column("n_rail_1000m", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dist_ferry_m", sa.Float(), nullable=True),
        sa.Column("naptan_extract_date", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("zone_id", "dz_vintage"),
        schema="candidates_v15",
    )
    op.create_table(
        "agg_hes_ca",
        sa.Column("zone_id", sa.Text(), nullable=False),
        sa.Column("dz_vintage", sa.Integer(), nullable=False),
        sa.Column("share", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("zone_id", "dz_vintage"),
        schema="candidates_v15",
    )
    op.create_table(
        "agg_hes_lb",
        sa.Column("zone_id", sa.Text(), nullable=False),
        sa.Column("dz_vintage", sa.Integer(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("n_listings", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("zone_id", "dz_vintage", "category"),
        schema="candidates_v15",
    )
    op.create_table(
        "agg_sepa_nfra",
        sa.Column("zone_id", sa.Text(), nullable=False),
        sa.Column("dz_vintage", sa.Integer(), nullable=False),
        sa.Column("score_mean_areaw", sa.Float(), nullable=True),
        sa.Column("score_max", sa.Integer(), nullable=True),
        sa.Column("n_cells", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("grid_coarser_than_zone", sa.Boolean(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("zone_id", "dz_vintage"),
        schema="candidates_v15",
    )
    op.create_table(
        "agg_vdl",
        sa.Column("zone_id", sa.Text(), nullable=False),
        sa.Column("dz_vintage", sa.Integer(), nullable=False),
        sa.Column("site_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hectares", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("zone_id", "dz_vintage"),
        schema="candidates_v15",
    )
    op.create_table(
        "agg_green_belt",
        sa.Column("zone_id", sa.Text(), nullable=False),
        sa.Column("dz_vintage", sa.Integer(), nullable=False),
        sa.Column("share", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("zone_id", "dz_vintage"),
        schema="candidates_v15",
    )
    op.create_table(
        "agg_school_catch",
        sa.Column("zone_id", sa.Text(), nullable=False),
        sa.Column("dz_vintage", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("catchment_id", sa.Text(), nullable=True),
        sa.Column("school_name", sa.Text(), nullable=True),
        sa.Column("data_year", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("zone_id", "dz_vintage", "stage"),
        schema="candidates_v15",
    )
    op.create_table(
        "agg_contam",
        sa.Column("zone_id", sa.Text(), nullable=False),
        sa.Column("dz_vintage", sa.Integer(), nullable=False),
        sa.Column("site_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("present", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("zone_id", "dz_vintage"),
        schema="candidates_v15",
    )
    op.create_table(
        "agg_ldp",
        sa.Column("zone_id", sa.Text(), nullable=False),
        sa.Column("dz_vintage", sa.Integer(), nullable=False),
        sa.Column("use_class", sa.Text(), nullable=False),
        sa.Column("hectares", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("zone_id", "dz_vintage", "use_class"),
        schema="candidates_v15",
    )
    op.create_table(
        "agg_hls",
        sa.Column("zone_id", sa.Text(), nullable=False),
        sa.Column("dz_vintage", sa.Integer(), nullable=False),
        sa.Column("effective_units", sa.Float(), nullable=True),
        sa.Column("hectares", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("zone_id", "dz_vintage"),
        schema="candidates_v15",
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
        op.drop_table(table, schema="candidates_v15")
    op.execute("DROP SCHEMA IF EXISTS candidates_v15 CASCADE")
