"""NatureScot SSSI + SPA/SAC/NNR designation tables.

Adds PostGIS tables for OGL NatureScot protected-area overlays.
DDL source: backend/db/schema/007_naturescot_designations.sql.

Revision ID: 20261012_0004
Revises: 20261012_0003
Create Date: 2026-10-12
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0004"
down_revision: Union[str, None] = "20261012_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "schema"
    / "007_naturescot_designations.sql"
)


def upgrade() -> None:
    # Idempotent: baseline on a fresh DB may already have applied 006 via glob.
    op.get_bind().exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS naturescot_designations CASCADE")
    op.execute("DROP TABLE IF EXISTS naturescot_sssi CASCADE")
