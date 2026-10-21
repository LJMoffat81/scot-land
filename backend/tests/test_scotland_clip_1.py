"""SCOTLAND-CLIP-1a: shared Scotland clip + NSTA oil/gas wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely import set_precision
from shapely.geometry import Point, shape
from shapely.ops import transform as shapely_transform

from spatial.scotland_clip import (
    ScotlandClipError,
    assert_inside,
    clip_features,
    load_extent,
    reset_process_extent,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "scotland_clip"
EXTENT_SYNTH = FIXTURES / "extent_synth.27700.geojson"
MANIFEST_SYNTH = FIXTURES / "manifest_synth.csv"
EXTENT_SHA = "4c2c1163d4de65c19c2cc00b85b78fc6cafa3d571b644c197b7d92e58f48086e"

_to_bng = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)


def _load_fc(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _extent():
    return load_extent(EXTENT_SYNTH, manifest=MANIFEST_SYNTH)


@pytest.fixture(autouse=True)
def _reset_extent_cache():
    reset_process_extent()
    yield
    reset_process_extent()


def test_c1_inside_kept_unchanged():
    extent = _extent()
    features = _load_fc("inside.geojson")["features"]
    kept, report = clip_features(features, extent)
    assert len(kept) == 3
    assert report["clipped"] == 0
    assert report["dropped_outside"] == 0
    assert report["invalid"] == 0
    assert report["extent_sha256"] == EXTENT_SHA
    for original, result in zip(features, kept, strict=True):
        g0 = shapely_transform(_to_bng.transform, shape(original["geometry"]))
        g1 = shapely_transform(_to_bng.transform, shape(result["geometry"]))
        assert g0.equals_exact(g1, 0.01)


def test_c2_outside_dropped_and_assert_inside():
    extent = _extent()
    features = _load_fc("outside.geojson")["features"]
    kept, report = clip_features(features, extent)
    assert 3 == report["dropped_outside"]
    assert kept == []
    with pytest.raises(ScotlandClipError) as raised:
        assert_inside(features, extent, layer="synth", tol_m=50)
    assert str(raised.value) == (
        "CLIP: synth: 3 feature(s) outside Scotland, first id out-1"
    )


def test_c3_straddle_clipped_to_half():
    extent = _extent()
    features = _load_fc("straddle.geojson")["features"]
    kept, report = clip_features(features, extent)
    assert len(kept) == 2
    poly = next(f for f in kept if (f.get("properties") or {}).get("kind") == "poly")
    area = set_precision(
        shapely_transform(_to_bng.transform, shape(poly["geometry"])), grid_size=1.0
    ).area
    assert abs(area - 50_000_000.0) <= 1.0, f"polygon area {area} != 50000000.0"
    assert 2 == report["clipped"]
    assert_inside(kept, extent, layer="synth", tol_m=0.01)


def test_c4_point_edge_no_tolerance_leak():
    extent = _extent()
    # East edge is E 310000. 10 m outside / inside.
    outside = Point(
        *_Transformer_wgs(310010, 705000)
    )
    inside = Point(
        *_Transformer_wgs(309990, 705000)
    )
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [outside.x, outside.y]},
            "properties": {"id": "edge-out"},
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [inside.x, inside.y]},
            "properties": {"id": "edge-in"},
        },
    ]
    kept, report = clip_features(features, extent)
    assert 1 == report["dropped_outside"]
    assert 1 == report["kept"]
    assert (kept[0].get("properties") or {}).get("id") == "edge-in"


def _Transformer_wgs(easting: float, northing: float) -> tuple[float, float]:
    to_wgs = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    return to_wgs.transform(easting, northing)


def test_c5_empty_layer():
    extent = _extent()
    kept, report = clip_features([], extent)
    assert kept == []
    assert report == {
        "in": 0,
        "kept": 0,
        "clipped": 0,
        "dropped_outside": 0,
        "invalid": 0,
        "extent_sha256": EXTENT_SHA,
    }


def test_c6_missing_boundary(tmp_path, monkeypatch):
    missing = tmp_path / "none.geojson"
    with pytest.raises(ScotlandClipError) as raised:
        load_extent(missing, manifest=MANIFEST_SYNTH)
    assert str(raised.value) == f"CLIP: extent file missing: {missing}"

    from spatial import context_tiles

    def _boom():
        raise ScotlandClipError(f"CLIP: extent file missing: {missing}")

    monkeypatch.setattr(context_tiles, "get_process_extent", _boom)
    with context_tiles._cache_lock:
        context_tiles._cache.pop("oil-fields", None)

    def _features(*_a, **_k):
        return _load_fc("inside.geojson")["features"][:2]

    monkeypatch.setattr(context_tiles, "_arcgis_features", _features)
    payload = context_tiles.fetch_context_geojson("oil-fields")
    assert len(payload["features"]) == 0
    assert payload["meta"]["ok"] is False
    assert payload["meta"]["note"] == "Scotland boundary missing"
    assert payload["meta"]["count"] == 0


def test_c7_sha_mismatch(tmp_path):
    mangled = tmp_path / "extent_synth.27700.geojson"
    # Trailing whitespace changes the sha but keeps the JSON parseable (M6).
    mangled.write_bytes(EXTENT_SYNTH.read_bytes() + b"\n")
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(MANIFEST_SYNTH.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ScotlandClipError) as raised:
        load_extent(mangled, manifest=manifest)
    assert str(raised.value) == "CLIP: extent sha256 mismatch"


def test_c8_invalid_geometries():
    extent = _extent()
    features = _load_fc("invalid.geojson")["features"]
    kept, report = clip_features(features, extent)
    assert 2 == report["invalid"]
    assert 1 == report["kept"]
    assert (kept[0].get("properties") or {}).get("id") == "bad-1"


def test_c9_properties_byte_identical():
    extent = _extent()
    features = _load_fc("inside.geojson")["features"]
    # Attach a nested property that must survive unchanged.
    features[0]["properties"] = {
        "id": "in-1",
        "kind": "poly",
        "nested": {"a": 1, "b": [2, 3]},
        "flag": True,
    }
    original = json.dumps(features[0]["properties"], sort_keys=True, separators=(",", ":"))
    kept, _report = clip_features(features, extent)
    assert len(kept) == 3
    assert json.dumps(kept[0]["properties"], sort_keys=True, separators=(",", ":")) == original


def test_c10_cache_stores_clipped_only(monkeypatch):
    from spatial import context_tiles

    extent = _extent()
    monkeypatch.setattr(context_tiles, "get_process_extent", lambda: extent)

    mixed = [
        *_load_fc("inside.geojson")["features"][:1],
        *_load_fc("outside.geojson")["features"][:1],
    ]
    assert len(mixed) == 2

    def _features(*_a, **_k):
        return list(mixed)

    with context_tiles._cache_lock:
        context_tiles._cache.pop("oil-fields", None)
    monkeypatch.setattr(context_tiles, "_arcgis_features", _features)
    # Avoid the size-cap path hiding features.
    monkeypatch.setattr(
        context_tiles, "cap_feature_collection", lambda geo, _budget: geo
    )

    payload = context_tiles.fetch_context_geojson("oil-fields")
    assert len(payload["features"]) == 1
    with context_tiles._cache_lock:
        cached = context_tiles._cache["oil-fields"]
    assert len(cached["features"]) == 1


def test_c11_nsta_envelope_prefilter(monkeypatch):
    from spatial import context_tiles

    extent = _extent()
    monkeypatch.setattr(context_tiles, "get_process_extent", lambda: extent)
    seen: list[dict] = []

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"type": "FeatureCollection", "features": []}

    class _Client:
        @staticmethod
        def get(url, params=None):
            seen.append(dict(params or {}))
            return _Resp()

    monkeypatch.setattr(context_tiles, "_http", lambda: _Client())
    monkeypatch.setattr(context_tiles, "_object_id_field", lambda _url: None)
    monkeypatch.setattr(context_tiles, "_host_allowed", lambda _url: True)

    for layer_id in ("oil-fields", "platforms", "pipelines"):
        with context_tiles._cache_lock:
            context_tiles._cache.pop(layer_id, None)
        context_tiles.fetch_context_geojson(layer_id)

    assert len(seen) >= 3
    for params in seen:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        if "esriSpatialRelIntersects" not in query:
            raise AssertionError("'esriSpatialRelIntersects' not in query")
        assert params.get("geometryType") == "esriGeometryEnvelope"
        assert params.get("inSR") == "4326"
        assert "geometry" in params
        assert "," in str(params["geometry"])


@pytest.mark.parametrize("layer_id", ["oil-fields", "platforms", "pipelines"])
def test_t_all_clipped_layers_inside(monkeypatch, layer_id):
    from spatial import context_tiles

    extent = _extent()
    monkeypatch.setattr(context_tiles, "get_process_extent", lambda: extent)
    mixed = [
        *_load_fc("inside.geojson")["features"],
        *_load_fc("outside.geojson")["features"][:1],
    ]

    def _features(*_a, **_k):
        return list(mixed)

    with context_tiles._cache_lock:
        context_tiles._cache.pop(layer_id, None)
    monkeypatch.setattr(context_tiles, "_arcgis_features", _features)
    if layer_id == "oil-fields":
        monkeypatch.setattr(
            context_tiles, "cap_feature_collection", lambda geo, _budget: geo
        )
    payload = context_tiles.fetch_context_geojson(layer_id)
    assert_inside(payload["features"], extent, layer=layer_id, tol_m=50)


@pytest.mark.real
def test_t_ext_committed_extent():
    from spatial.scotland_clip import DEFAULT_EXTENT_PATH, DEFAULT_MANIFEST_PATH

    path = DEFAULT_EXTENT_PATH
    assert path.is_file()
    size = path.stat().st_size
    assert size < 8 * 1024 * 1024
    extent = load_extent(path, manifest=DEFAULT_MANIFEST_PATH)
    assert set(extent.zones) == {"land", "inshore_0_12nm", "offshore_12_200nm"}
    area_km2 = extent.geom.area / 1_000_000.0
    assert 690_000.0 <= area_km2 <= 710_000.0
    assert extent.geom.is_valid

    to_bng = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)

    def inside_lonlat(lon: float, lat: float) -> bool:
        x, y = to_bng.transform(lon, lat)
        return extent.geom.contains(Point(x, y)) or extent.geom.covers(Point(x, y))

    # Edinburgh, Lerwick, Rockall inside; Newcastle, Carlisle, Belfast outside.
    assert inside_lonlat(-3.1883, 55.9533)  # Edinburgh
    assert inside_lonlat(-1.145, 60.154)  # Lerwick
    assert inside_lonlat(-13.687, 57.596)  # Rockall
    assert not inside_lonlat(-1.613, 54.978)  # Newcastle
    assert not inside_lonlat(-2.944, 54.895)  # Carlisle
    assert not inside_lonlat(-5.930, 54.597)  # Belfast
