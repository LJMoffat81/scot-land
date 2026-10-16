"""SEA-EXTENT-1 PR-1: static Scotland land and seas boundaries.

These checks read data/static/sea_extent only. They fail when a file is
missing, too large, invalid, in the wrong CRS, on the wrong side of a
published point, or when the manifest hash does not match the file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import shapely
from pyproj import Transformer
from shapely.geometry import Point, Polygon, shape
from shapely.ops import transform, unary_union

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
TO_BNG = Transformer.from_crs(4326, 27700, always_xy=True)

# Review attempt 1 measured about 3,490 km² of overlap, 185 km² of gaps
# and 79 km² of the 12 nm area outside the outer limit. These caps sit
# under those figures and above the slivers left by 4-decimal rounding.
OVERLAP_MAX_M2 = 50_000
GAP_MAX_M2 = 1_000_000
OUTSIDE_MAX_M2 = 50_000
SG_CREDIT = (
    "Contains information from Scottish Government "
    "licensed under the Open Government Licence v3.0."
)


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


def _bng(name: str):
    return shapely.make_valid(transform(TO_BNG.transform, _geometry(name)))


def _gap_area_m2(land, inshore) -> float:
    """Area of holes in land-plus-12-nm whose centre is not on land."""
    union = shapely.make_valid(unary_union([land, inshore]))
    shapely.prepare(land)
    area = 0.0
    pieces = union.geoms if union.geom_type == "MultiPolygon" else (union,)
    for piece in pieces:
        if piece.geom_type != "Polygon":
            continue
        for ring in piece.interiors:
            hole = Polygon(ring)
            if not land.covers(hole.representative_point()):
                area += hole.area
    return area


def test_overlap_and_gaps_are_under_tolerance_and_outer_contains_12nm():
    land = _bng("land.geojson")
    inshore = _bng("inshore_12nm.geojson")
    waters = _bng("scottish_waters.geojson")
    overlap_m2 = land.intersection(inshore).area
    outside_m2 = inshore.difference(waters).area
    gap_m2 = _gap_area_m2(land, inshore)
    assert overlap_m2 <= OVERLAP_MAX_M2
    assert gap_m2 <= GAP_MAX_M2
    assert outside_m2 <= OUTSIDE_MAX_M2


def test_inshore_feature_is_named_12_nautical_mile_line():
    collection = _load("inshore_12nm.geojson")
    assert collection["features"][0]["properties"]["name"] == "12 nautical mile line"


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
    assert "vertex_grid_m" not in manifest
    assert manifest["simplify_m"] == 300
    assert SG_CREDIT in manifest["attribution"]
    assert "the Scottish Government" not in json.dumps(manifest)
    year = manifest["fetch_date"][:4]
    assert f"Contains OS data © Crown copyright and database right {year}" in manifest["attribution"]
    offshore = next(
        row for row in manifest["inputs"] if row.get("dataset_id") == "Marine_Scotland_FishDAC_12185"
    )
    assert offshore["source_url"] == (
        "https://spatialdata.gov.scot/geonetwork/srv/api/records/"
        "Marine_Scotland_FishDAC_12185/formatters/xml"
    )
    assert offshore["download_url"].startswith("https://")


def test_builder_does_not_hard_code_the_os_year_or_fetch_sectigo_over_http():
    script = (ROOT / "backend" / "scripts" / "build_sea_extent.py").read_text(encoding="utf-8")
    assert "database right 2026" not in script
    assert "http://crt.sectigo.com/" not in script
    assert "sectigo_public_server_auth_dv_r36.pem" in script


def test_no_pound_sign():
    for path in sorted(SEA_DIR.iterdir()):
        assert path.is_file()
        assert "£" not in path.read_text(encoding="utf-8"), path.name
