"""NFI woodland and Native Woodland Survey PostGIS tables.

Matches backend/db/schema/016_woodland_layers.sql.
Fresh databases also pick up via the baseline glob; IF NOT EXISTS keeps
this revision idempotent.

Revision ID: 20261012_0013
Revises: 20261012_0012
Create Date: 2026-10-12
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0013"
down_revision: Union[str, None] = "20261012_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "schema"
    / "016_woodland_layers.sql"
)


def upgrade() -> None:
    # Idempotent: baseline on a fresh DB may already have applied 016 via glob.
    op.get_bind().exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS native_woodland CASCADE")
    op.execute("DROP TABLE IF EXISTS nfi_woodland CASCADE")
