"""Add Land Capability for Agriculture (Hutton LCA 1:250k) table.

Matches backend/db/schema/018_lca_agriculture.sql.
Fresh databases also pick up via the baseline glob; IF NOT EXISTS keeps
this revision idempotent.

Numbered past main open_energy_leases 017 / 20261012_0014. Held PR #33's
018/0015 is not on main — do not stack on it.

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
    / "018_lca_agriculture.sql"
)


def upgrade() -> None:
    # Idempotent: baseline on a fresh DB may already have applied 018 via glob.
    op.get_bind().exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lca_agriculture CASCADE")
