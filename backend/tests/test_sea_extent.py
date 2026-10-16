"""SEA-EXTENT-1 PR-1: static Scotland land and seas boundaries.

These checks read data/static/sea_extent only. They fail when a file is
missing, too large, invalid, in the wrong CRS, on the wrong side of a
published point, or when the manifest hash does not match the file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[2]
SEA_DIR = ROOT / "data" / "static" / "sea_extent"
FILES = ("land.geojson", "inshore_12nm.geojson", "scottish_waters.geojson")
MAX_FILE_BYTES = 300_000
MAX_TOTAL_BYTES = 500_000

# Spec points are latitude, longitude. GeoJSON positions are longitude, latitude.
EDINBURGH = Point(-3.1883, 55.9533)
CARLISLE = Point(-2.9382, 54.8951)
MINCH = Point(-6.05, 58.42)
NORTH_OF_12NM = Point(-1.0, 61.5)


def _load(name: str) -> dict:
    return json.loads((SEA_DIR / name).read_text(encoding="utf-8"))


def _geometry(name: str):
    collection = _load(name)
    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == 1
    return shape(collection["features"][0]["geometry"])


def test_files_exist_and_each_is_at_most_300kb():
    assert SEA_DIR.is_dir()
    for name in FILES:
        path = SEA_DIR / name
        assert path.is_file(), name
        assert path.stat().st_size <= MAX_FILE_BYTES, (name, path.stat().st_size)
    total = sum((SEA_DIR / name).stat().st_size for name in FILES)
    assert total <= MAX_TOTAL_BYTES, total


def test_geometries_are_valid_polygons():
    for name in FILES:
        geometry = _geometry(name)
        assert geometry.geom_type in {"Polygon", "MultiPolygon"}
        assert geometry.is_valid, name
        assert not geometry.is_empty, name


def test_crs_is_4326():
    for name in FILES:
        collection = _load(name)
        crs_name = collection["crs"]["properties"]["name"]
        assert crs_name == "EPSG:4326", (name, crs_name)
        geometry = shape(collection["features"][0]["geometry"])
        min_x, min_y, max_x, max_y = geometry.bounds
        assert -30 <= min_x <= max_x <= 10, (name, geometry.bounds)
        assert 50 <= min_y <= max_y <= 70, (name, geometry.bounds)


def test_land_contains_edinburgh_and_not_carlisle():
    land = _geometry("land.geojson")
    assert land.contains(EDINBURGH)
    assert not land.contains(CARLISLE)


def test_inshore_contains_minch_and_excludes_north_of_12nm():
    inshore = _geometry("inshore_12nm.geojson")
    assert inshore.contains(MINCH)
    assert not inshore.contains(NORTH_OF_12NM)


def test_scottish_waters_contains_north_of_12nm():
    waters = _geometry("scottish_waters.geojson")
    assert waters.contains(NORTH_OF_12NM)


def test_manifest_sha256_matches_files():
    manifest = _load("manifest.json")
    assert manifest["licence"] == "OGL v3"
    assert manifest["fetch_date"]
    outputs = manifest["outputs"]
    assert [row["file"] for row in outputs] == list(FILES)
    for row in outputs:
        path = SEA_DIR / row["file"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert row["sha256"] == digest
        assert row["bytes"] == path.stat().st_size
    for row in manifest["inputs"]:
        assert row["source_url"].startswith("https://")
        assert row["licence"] == "OGL v3"
        assert row["fetch_date"]
        assert len(row["sha256"]) == 64
        assert row["attribution"]
    assert manifest["attribution"]


def test_no_pound_sign():
    for path in sorted(SEA_DIR.iterdir()):
        assert path.is_file()
        assert "£" not in path.read_text(encoding="utf-8"), path.name
