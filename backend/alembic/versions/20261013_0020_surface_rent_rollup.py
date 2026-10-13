"""Add surface_rent_rollup for internal DZ2022 → IZ → Council → Scotland sums.

Matches backend/db/schema/023_surface_rent_rollup.sql.
publish_level is constrained to internal — never public £ rent aggregates.

Revision ID: 20261013_0020
Revises: 20261012_0019
Create Date: 2026-10-13
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "20261013_0020"
down_revision: Union[str, None] = "20261012_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "schema"
    / "023_surface_rent_rollup.sql"
)


def upgrade() -> None:
    op.get_bind().exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS surface_rent_rollup CASCADE")
