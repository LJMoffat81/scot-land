"""backend/db/schema/004_datazones.sql is Data Zones' schema.sql, vendored with mechanical edits only."""

import re
from pathlib import Path

import pytest

from paths import PROCESSED_DIR

VENDORED = Path(__file__).resolve().parents[2] / "db" / "schema" / "004_datazones.sql"
OWNER = PROCESSED_DIR / "datazones" / "schema.sql"
TABLE_RE = re.compile(r"CREATE TABLE (?:IF NOT EXISTS )?(?:datazones\.)?(\w+) \((.*?)\n\);", re.S)


def _tables(text: str) -> dict[str, str]:
    return {name: body.replace("REFERENCES datazones.zone_spine", "REFERENCES zone_spine")
            for name, body in TABLE_RE.findall(text)}


def test_vendored_tables_match_owner_schema_exactly():
    if not OWNER.is_file():
        pytest.skip("data/processed/datazones/schema.sql not present")
    owner, vendored = _tables(OWNER.read_text()), _tables(VENDORED.read_text())
    assert len(owner) == 11 and owner.keys() == vendored.keys()
    for name in owner:
        assert vendored[name] == owner[name], f"datazones.{name} drifted from Data Zones' schema.sql"


def test_vendored_schema_is_qualified_and_idempotent():
    text = VENDORED.read_text()
    code = "\n".join(ln.split("--")[0] for ln in text.splitlines())
    assert "search_path" not in code
    assert "CREATE TABLE datazones" not in text and "CREATE TABLE IF NOT EXISTS datazones.zone_spine" in text
    assert "vintage IN (2011, 2022)" in text and "'DZ2011'" not in text
