"""Add Common Good sites table (OGL council open layers).

Matches backend/db/schema/018_common_good_sites.sql.
Fresh databases also pick up via the baseline glob; IF NOT EXISTS keeps
this revision idempotent.

Revision ID: 20261012_0015
Revises: 20261012_0014
Create Date: 2026-10-13
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0015"
down_revision: Union[str, None] = "20261012_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "schema"
    / "018_common_good_sites.sql"
)


def upgrade() -> None:
    # Idempotent: baseline on a fresh DB may already have applied 018 via glob.
    op.get_bind().exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS common_good_sites CASCADE")
