"""Add ces_aquaculture_leases (natural-capital P1; no £ rent).

Matches backend/db/schema/021_ces_aquaculture_leases.sql.
Fresh databases also pick up via the baseline glob; IF NOT EXISTS keeps
this revision idempotent.

Numbered past main REPD onshore wind 020 / 20261012_0017.

Revision ID: 20261012_0018
Revises: 20261012_0017
Create Date: 2026-10-13
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0018"
down_revision: Union[str, None] = "20261012_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "schema"
    / "021_ces_aquaculture_leases.sql"
)


def upgrade() -> None:
    # Idempotent: baseline on a fresh DB may already have applied 021 via glob.
    op.get_bind().exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ces_aquaculture_leases CASCADE")
