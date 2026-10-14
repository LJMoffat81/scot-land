"""Add datazones.dz2011_dz2022_uprn_weights (OS Open UPRN address-point crosswalk).

Matches backend/db/schema/024_dz2011_dz2022_uprn_weights.sql (also vendored into
004_datazones.sql). Fresh DBs get the table from the baseline; this revision
covers already-stamped databases.

Revision ID: 20261013_0021
Revises: 20261013_0020
Create Date: 2026-10-13
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "20261013_0021"
down_revision: Union[str, None] = "20261013_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2]
    / "db"
    / "schema"
    / "024_dz2011_dz2022_uprn_weights.sql"
)


def upgrade() -> None:
    op.get_bind().exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS datazones.dz2011_dz2022_uprn_weights CASCADE")
