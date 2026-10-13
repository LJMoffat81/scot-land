"""Add dz_boundaries_meta provenance table for SG Data Zone loads.

Matches backend/db/schema/022_dz_boundaries_meta.sql.
Fresh databases also pick up via the baseline glob; IF NOT EXISTS keeps
this revision idempotent.

Revision ID: 20261012_0019
Revises: 20261012_0018
Create Date: 2026-10-13
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0019"
down_revision: Union[str, None] = "20261012_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "schema"
    / "022_dz_boundaries_meta.sql"
)


def upgrade() -> None:
    # Idempotent: baseline on a fresh DB may already have applied 022 via glob.
    op.get_bind().exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dz_boundaries_meta CASCADE")
