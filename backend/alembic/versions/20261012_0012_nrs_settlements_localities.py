"""NRS Census 2022 settlements and localities tables.

Matches backend/db/schema/015_nrs_settlements_localities.sql.
Fresh databases also pick up via the baseline glob; IF NOT EXISTS keeps
this revision idempotent.

Revision ID: 20261012_0012
Revises: 20261012_0011
Create Date: 2026-10-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0012"
down_revision: Union[str, None] = "20261012_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS nrs_settlements (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            popcount INTEGER,
            area_m2 DOUBLE PRECISION,
            geom GEOMETRY(MultiPolygon, 4326) NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_nrs_settlements_geom "
        "ON nrs_settlements USING GIST (geom)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS nrs_localities (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            popcount INTEGER,
            area_m2 DOUBLE PRECISION,
            geom GEOMETRY(MultiPolygon, 4326) NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_nrs_localities_geom "
        "ON nrs_localities USING GIST (geom)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS nrs_localities CASCADE")
    op.execute("DROP TABLE IF EXISTS nrs_settlements CASCADE")
