"""Baseline Wealth + Data Zones + INSPIRE parcels schema.

Matches backend/db/schema/*.sql (the former ad hoc CREATE IF NOT EXISTS path).
Fresh databases: `alembic upgrade head`.
Existing databases already created by migrate_to_postgis: `alembic stamp head`.

Revision ID: 20261012_0001
Revises:
Create Date: 2026-10-12
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "db" / "schema"


def upgrade() -> None:
    # Execute numbered SQL files in order (same as the old apply_schema path).
    conn = op.get_bind()
    for sql_file in sorted(SCHEMA_DIR.glob("*.sql")):
        conn.exec_driver_sql(sql_file.read_text(encoding="utf-8"))


def downgrade() -> None:
    # Destructive: drops Wealth / platform tables introduced by this baseline.
    # Safe for throwaway CI DBs; do not run against production without a backup.
    op.execute("DROP TABLE IF EXISTS inspire_parcels CASCADE")
    op.execute("DROP TABLE IF EXISTS eco_wealth CASCADE")
    op.execute("DROP TABLE IF EXISTS resource_wealth CASCADE")
    op.execute("DROP TABLE IF EXISTS planning_sites CASCADE")
    op.execute("DROP TABLE IF EXISTS surface_rent_dz CASCADE")
    op.execute("DROP TABLE IF EXISTS dz_denominators CASCADE")
    op.execute("DROP TABLE IF EXISTS dz_boundaries CASCADE")
    op.execute("DROP SCHEMA IF EXISTS datazones CASCADE")
