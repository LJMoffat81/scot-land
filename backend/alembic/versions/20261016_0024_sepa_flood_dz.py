"""Data Zone shares of SEPA Flood Maps v3.0 medium present-day extents.

Matches backend/db/schema/027_sepa_flood_dz.sql. No flood polygons.

Revision ID: 20261016_0024
Revises: 20261016_0023
Create Date: 2026-10-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261016_0024"
down_revision: Union[str, None] = "20261016_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sepa_flood_dz (
            data_zone         TEXT PRIMARY KEY CHECK (data_zone ~ '^S01[0-9]{6}$'),
            pct_area_river    SMALLINT NOT NULL CHECK (pct_area_river BETWEEN 0 AND 100),
            pct_area_coastal  SMALLINT NOT NULL CHECK (pct_area_coastal BETWEEN 0 AND 100),
            pct_area_surface  SMALLINT NOT NULL CHECK (pct_area_surface BETWEEN 0 AND 100),
            source_version    TEXT NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sepa_flood_dz")
