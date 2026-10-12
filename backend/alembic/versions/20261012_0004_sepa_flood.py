"""SEPA flood extents table (OGL MapServer / geodatabase ingest).

Revision ID: 20261012_0004
Revises: 20261012_0003
Create Date: 2026-10-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0004"
down_revision: Union[str, None] = "20261012_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS: fresh DBs already apply 007_sepa_flood.sql via the baseline glob.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sepa_flood (
            object_id INTEGER NOT NULL,
            layer_id SMALLINT NOT NULL,
            source TEXT NOT NULL,
            probability TEXT NOT NULL,
            scenario TEXT,
            map_type TEXT,
            reference TEXT,
            version TEXT,
            geom GEOMETRY(MultiPolygon, 4326) NOT NULL,
            PRIMARY KEY (layer_id, object_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sepa_flood_geom ON sepa_flood USING GIST (geom)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sepa_flood_source_prob "
        "ON sepa_flood (source, probability)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sepa_flood CASCADE")
