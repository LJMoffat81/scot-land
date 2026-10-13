"""Unit tests for repeatable SEPA flood + woodland loader conversion helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon, shape

from etl import ingest_sepa_flood as flood
from etl import ingest_woodland_layers as woodland


def test_flood_vintage_defaults_to_release_notes_not_placeholder():
    assert flood.RELEASE_NOTES_DATE == "2025-02-25"
    assert flood.RELEASE_NOTES_DATE != "2025-01-01"
    assert "flood-map-version-3_0-release-notes" in flood.RELEASE_NOTES_URL


def test_flood_keep_polygons_from_mixed_geometry():
    poly = Polygon([(-4.28, 55.85), (-4.27, 55.85), (-4.27, 55.86), (-4.28, 55.86), (-4.28, 55.85)])
    mixed = GeometryCollection([poly, LineString([(-4.28, 55.85), (-4.27, 55.86)]), Point(-4.275, 55.855)])
    out = flood.keep_polygons(mixed)
    assert out is not None
    geom = shape(out)
    assert geom.geom_type == "MultiPolygon"
    assert not geom.is_empty


def test_flood_keep_polygons_drops_non_polygon_only():
    assert flood.keep_polygons(LineString([(0, 0), (1, 1)])) is None
    assert flood.keep_polygons(Point(0, 0)) is None


def test_flood_merge_stamps_layer_ids():
    river = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"SOURCE": "River", "OBJECTID": 1},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            }
        ],
    }
    coastal = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"SOURCE": "Coastal", "OBJECTID": 1},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]],
                },
            }
        ],
    }
    merged = flood.merge_feature_collections([(river, 1), (coastal, 7)])
    assert [f["properties"]["layer_id"] for f in merged["features"]] == [1, 7]


def test_flood_check_counts_within_tolerance():
    flood.check_counts({"river": 47_093, "coastal": 16})
    flood.check_counts({"river": 47_100, "coastal": 16})  # well under 0.1%
    with pytest.raises(SystemExit):
        flood.check_counts({"river": 40_000, "coastal": 16})


def test_flood_export_coastal_gdb_if_present(tmp_path):
    gdb = Path("/tmp/sepa-coastal/coastal_extract/Data/FRM_Coastal_Flood_Hazard_Layers_v3_0.gdb")
    if not gdb.is_dir():
        pytest.skip("coastal FileGDB fixture not present on this runner")
    out = tmp_path / "coastal.geojson"
    flood.export_gdb_layer(gdb, "FRM_FH_COASTAL_EXTENT_M", out, simplify_metres=2.0)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert len(payload["features"]) == 16
    # ISSUE_DATE on the product matches release-notes vintage
    issue = (payload["features"][0].get("properties") or {}).get("ISSUE_DATE") or ""
    assert issue.startswith("2025-02-25")


def test_woodland_keep_polygons_from_mixed_geometry():
    poly = Polygon([(-4.28, 55.85), (-4.27, 55.85), (-4.27, 55.86), (-4.28, 55.86), (-4.28, 55.85)])
    mixed = GeometryCollection([MultiPolygon([poly]), LineString([(-4.28, 55.85), (-4.27, 55.86)])])
    out = woodland.keep_polygons(mixed)
    assert out is not None
    assert shape(out).geom_type == "MultiPolygon"


def test_woodland_geometry_json_skips_lines():
    feature = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
    }
    assert woodland._geometry_json(feature) is None


def test_woodland_check_count_baseline():
    woodland.check_count("nfi", 207_640)
    woodland.check_count("native_woodland", 95_814)
    with pytest.raises(SystemExit):
        woodland.check_count("nfi", 100)


def test_woodland_fetch_wfs_pages(monkeypatch):
    calls: list[int] = []

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        def get(self, url, params=None):
            start = int((params or {}).get("startIndex") or 0)
            calls.append(start)
            poly = {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            }
            if start == 0:
                feats = [
                    {"type": "Feature", "properties": {"OBJECTID": i}, "geometry": poly}
                    for i in range(2)
                ]
                return _Resp(
                    {
                        "type": "FeatureCollection",
                        "features": feats,
                        "numberMatched": 3,
                        "numberReturned": 2,
                    }
                )
            return _Resp(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {"type": "Feature", "properties": {"OBJECTID": 2}, "geometry": poly}
                    ],
                    "numberMatched": 3,
                    "numberReturned": 1,
                }
            )

        def close(self):
            return None

    monkeypatch.setattr(woodland.httpx, "Client", _Client)
    payload = woodland.fetch_wfs_geojson("nfi", page_size=2)
    assert len(payload["features"]) == 3
    assert calls == [0, 2]


def test_regen_layer_guide_patcher():
    import importlib.util

    sample = (
        "| SEPA flood extent (medium likelihood) | `/layers/open/flood` | SEPA Flood Maps v3.0, river and coastal | OGL v3.0 | 1 river + 1 coastal | `converted` (simplified ~2 m), `context` |\n"
        "| National Forest Inventory | `/layers/open/nfi` | Forestry Commission, NFI Scotland 2025 | OGL v3.0 | 1 | `converted` (via WFS) |\n"
        "| Native Woodland Survey | `/layers/open/native-woodland` | Scottish Forestry, NWSS | OGL v3.0 | 1 | `converted` (via WFS) |\n"
    )
    path = Path(__file__).resolve().parents[2] / "scripts" / "data" / "regen_layer_guide_counts.py"
    spec = importlib.util.spec_from_file_location("regen_layer_guide_counts", path)
    assert spec and spec.loader
    regen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regen)
    out = regen.patch_guide(sample, river=47093, coastal=16, nfi=207640, nwss=95814)
    assert "47,093 river + 16 coastal" in out
    assert "207,640" in out
    assert "95,814" in out
