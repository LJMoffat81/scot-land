"""Add natural-capital REPD onshore wind table (MW/status, no rent).

Matches backend/db/schema/020_nc_repd_onshore_wind.sql.
Fresh databases also pick up via the baseline glob; IF NOT EXISTS keeps
this revision idempotent.

Numbered past main ScotWind 019 / 20261012_0016.

Revision ID: 20261012_0017
Revises: 20261012_0016
Create Date: 2026-10-13
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0017"
down_revision: Union[str, None] = "20261012_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "schema"
    / "020_nc_repd_onshore_wind.sql"
)


def upgrade() -> None:
    # Idempotent: baseline on a fresh DB may already have applied 020 via glob.
    op.get_bind().exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS repd_onshore_wind CASCADE")
