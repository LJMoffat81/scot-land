"""ARCH-1a: schemas ref/stage/layers plus empty unit tables.

Revision ID: 20261021_0026
Revises: 20261016_0025
Create Date: 2026-10-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261021_0026"
down_revision: Union[str, None] = "20261016_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ref")
    op.execute("CREATE SCHEMA IF NOT EXISTS stage")
    op.execute("CREATE SCHEMA IF NOT EXISTS layers")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ref.unit (
            unit_type text NOT NULL,
            unit_id text NOT NULL,
            geography text NOT NULL,
            name text,
            valid_from date NOT NULL,
            valid_to date,
            geom geometry(MultiPolygon, 27700),
            PRIMARY KEY (unit_type, unit_id, valid_from)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ref.unit_hierarchy (
            child_type text NOT NULL,
            child_id text NOT NULL,
            parent_type text NOT NULL,
            parent_id text NOT NULL,
            weight numeric NOT NULL DEFAULT 1
                CHECK (weight > 0 AND weight <= 1),
            version text NOT NULL,
            valid_from date NOT NULL,
            PRIMARY KEY (
                child_type, child_id, parent_type, parent_id, version
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ref.unit_hierarchy")
    op.execute("DROP TABLE IF EXISTS ref.unit")
    # Leave schemas in place; other objects may exist.
