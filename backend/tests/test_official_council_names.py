"""All 32 council display names must match the official NRS/SG list."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from spatial.council_names import (
    OFFICIAL_COUNCIL_NAMES,
    assert_official_council_set,
    official_council_name,
)
from spatial.polygons import _council_index

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_official_list_has_exactly_32_unique_names():
    assert len(OFFICIAL_COUNCIL_NAMES) == 32
    assert len(set(OFFICIAL_COUNCIL_NAMES.values())) == 32
    assert "City of Edinburgh" in OFFICIAL_COUNCIL_NAMES.values()
    assert "City of Ediburgh" not in OFFICIAL_COUNCIL_NAMES.values()
    assert OFFICIAL_COUNCIL_NAMES["S12000049"] == "Glasgow City"
    assert OFFICIAL_COUNCIL_NAMES["S12000033"] == "Aberdeen City"
    assert OFFICIAL_COUNCIL_NAMES["S12000042"] == "Dundee City"


def test_ediburgh_typo_alias_canonicalises():
    assert (
        official_council_name(None, "City of Ediburgh") == "City of Edinburgh"
    )
    assert official_council_name("S12000036", "City of Ediburgh") == "City of Edinburgh"
    assert official_council_name("S12000049", "City of Glasgow") == "Glasgow City"


def test_zone_spine_matches_official_32():
    path = REPO_ROOT / "data" / "processed" / "datazones" / "zone_spine.csv"
    names: set[str] = set()
    codes: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            codes[row["la_code"]] = row["la_name"]
            names.add(row["la_name"])
    assert_official_council_set(names)
    assert codes == OFFICIAL_COUNCIL_NAMES


def test_scotland_councils_geojson_matches_official_32():
    path = REPO_ROOT / "data" / "processed" / "scotland_councils.geojson"
    payload = json.loads(path.read_text(encoding="utf-8"))
    names = {f["properties"]["name"] for f in payload["features"]}
    codes = {
        f["properties"]["hpi_code"]: f["properties"]["name"]
        for f in payload["features"]
    }
    assert_official_council_set(names)
    assert codes == OFFICIAL_COUNCIL_NAMES


def test_councils_json_matches_official_32():
    path = REPO_ROOT / "data" / "processed" / "councils.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    names = {row["name"] for row in payload["councils"]}
    codes = {row["code"]: row["name"] for row in payload["councils"]}
    assert_official_council_set(names)
    assert codes == OFFICIAL_COUNCIL_NAMES


def test_boundary_lookup_index_uses_official_names():
    names = {match.name for match, _prep in _council_index()}
    assert_official_council_set(names)
