"""candidates_v15 tables for LAYERS-ADD-2 aggregates.

Revision ID: 20261016_0024
Revises: 20261016_0023
Create Date: 2026-10-16

v1.5 candidate inputs only. No currency columns. Geometry, where stored, is
EPSG:27700. Address keys are not columns.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261016_0024"
down_revision: Union[str, None] = "20261016_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES: tuple[str, ...] = (
    "agg_epc",
    "agg_uprn_density",
    "agg_ofcom",
    "agg_nrs",
    "agg_ur",
    "agg_roads",
    "agg_greenspace",
    "agg_fls",
    "agg_vdl_council",
    "agg_ldp_council",
    "agg_contam_dz",
    "geom_os_open_roads",
    "geom_os_open_greenspace",
    "geom_os_open_rivers",
    "geom_fls_estate",
    "geom_ces_assets",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS candidates_v15")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_epc (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            certificate_count INTEGER,
            median_floor_area_m2 DOUBLE PRECISION,
            share_property_type TEXT,
            share_age_band TEXT,
            median_epc_band TEXT,
            suppressed BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_uprn_density (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            point_count INTEGER NOT NULL DEFAULT 0,
            points_per_ha DOUBLE PRECISION,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_ofcom (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            share_full_fibre DOUBLE PRECISION,
            share_gigabit DOUBLE PRECISION,
            share_below_10 DOUBLE PRECISION,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_nrs (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            population DOUBLE PRECISION,
            households DOUBLE PRECISION,
            per_ha DOUBLE PRECISION,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_ur (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            fold6 TEXT,
            fold8 TEXT,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_roads (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            metres_motorway_junction DOUBLE PRECISION,
            metres_a_road DOUBLE PRECISION,
            metres_trunk DOUBLE PRECISION,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_greenspace (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            metres_public_park DOUBLE PRECISION,
            greenspace_ha DOUBLE PRECISION,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_fls (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            share_estate DOUBLE PRECISION,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_vdl_council (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            coverage TEXT NOT NULL,
            source_council TEXT NOT NULL,
            site_count_label TEXT,
            hectares DOUBLE PRECISION,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_ldp_council (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            coverage TEXT NOT NULL,
            source_council TEXT NOT NULL,
            use_class TEXT NOT NULL,
            hectares DOUBLE PRECISION,
            PRIMARY KEY (zone_id, dz_vintage, use_class)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates_v15.agg_contam_dz (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            coverage TEXT NOT NULL,
            source_council TEXT NOT NULL,
            site_count_label TEXT,
            hectares DOUBLE PRECISION,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    for table in (
        "geom_os_open_roads",
        "geom_os_open_greenspace",
        "geom_os_open_rivers",
        "geom_fls_estate",
        "geom_ces_assets",
    ):
        op.execute(
            f"""
            CREATE TABLE IF NOT EXISTS candidates_v15.{table} (
                fid INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                geom geometry(Geometry, 27700) NOT NULL
            )
            """
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS candidates_v15.{table} CASCADE")
