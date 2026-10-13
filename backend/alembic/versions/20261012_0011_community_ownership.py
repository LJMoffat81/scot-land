"""Community ownership assets PostGIS table (SG OGL 2024).

Revision ID: 20261012_0011
Revises: 20261012_0010
Create Date: 2026-10-12
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0011"
down_revision: Union[str, None] = "20261012_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2] / "db" / "schema" / "014_community_ownership.sql"
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS community_ownership_assets CASCADE")
