"""UX10-2 map_builtup_mask + dz2022_masked tables.

Matches backend/db/schema/025_map_builtup_mask.sql.
Fresh databases also pick up via the baseline glob; IF NOT EXISTS keeps
this revision idempotent.

Revision ID: 20261015_0022
Revises: 20261013_0021
Create Date: 2026-10-15
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261015_0022"
down_revision: Union[str, None] = "20261013_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS map_builtup_mask (
            gid BIGSERIAL PRIMARY KEY,
            geom GEOMETRY(Polygon, 4326) NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_map_builtup_mask_geom "
        "ON map_builtup_mask USING GIST (geom)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dz2022_masked (
            code TEXT PRIMARY KEY CHECK (code ~ '^S01[0-9]{6}$'),
            geom GEOMETRY(MultiPolygon, 4326) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dz2022_masked_geom "
        "ON dz2022_masked USING GIST (geom)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dz2022_masked CASCADE")
    op.execute("DROP TABLE IF EXISTS map_builtup_mask CASCADE")
