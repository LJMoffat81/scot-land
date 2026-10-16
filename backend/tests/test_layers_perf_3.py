"""LAYERS-PERF-3: SSSI z6–z8 cache, oil size-cap, metre fallback."""

from __future__ import annotations

import time

from layers.naturescot import (
    _CAP_TOLERANCE_ZOOMS,
    _cap_tolerances_m,
    cap_feature_collection,
    dumps_feature_collection,
    simplify_tolerance_m,
)
from tests.test_layers_perf_1 import BUDGET_Z6, _huge_polygon, _patch_query

_OIL_HINT = "Zoom in to see oil and gas"


def test_cap_fallback_tolerances_are_metres_matching_sql():
    """The Python size-cap ladder is metres, the same steps as the SQL simplify."""
    tolerances = _cap_tolerances_m()
    assert tolerances[0] == 0.0
    assert tolerances[1:] == tuple(
        simplify_tolerance_m(zoom) for zoom in _CAP_TOLERANCE_ZOOMS
    )
    assert min(tolerances[1:]) >= 1.0
    assert tolerances[-1] > 50
    assert 0.001 not in tolerances


def test_cap_fallback_keeps_a_dense_ring_in_lon_lat():
    """Metre simplification in EPSG:27700 still returns WGS84 coordinates."""
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": _huge_polygon(8000),
                "properties": {"name": "Highland site"},
            }
        ],
        "meta": {"ok": True, "count": 1},
    }
    assert len(dumps_feature_collection(payload)) > 50_000
    capped = cap_feature_collection(payload, 50_000)
    assert capped["features"]
    assert capped["meta"].get("hidden_below_zoom") is not True
    ring = capped["features"][0]["geometry"]["coordinates"][0]
    assert len(ring) < 8000
    assert all(-8 < point[0] < 0 and 54 < point[1] < 61 for point in ring)


def test_sssi_z6_z7_z8_warm_under_two_seconds(client, monkeypatch):
    """A repeat SSSI view must not run the slow query again.

    The stand-in query sleeps past two seconds. The warm call has to come
    back from the z6–z8 cache inside that limit.
    """
    conn = _patch_query(
        monkeypatch,
        "layers.naturescot",
        {
            "pa_code": "SSSI-WARM",
            "name": "Warm site",
            "status": "Current",
            "site_type": "Biological",
            "site_ha": 12.0,
            "european_code": None,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[-4.4, 57.1], [-4.1, 57.3], [-4.6, 57.5], [-4.4, 57.1]]
                ],
            },
        },
    )
    original_execute = conn.cursor_obj.execute

    def slow_execute(sql, params):
        time.sleep(2.05)
        return original_execute(sql, params)

    conn.cursor_obj.execute = slow_execute
    view = {"south": 54.7, "west": -7.4, "north": 60.6, "east": -1.2}
    for zoom in (6, 7, 8):
        cold = client.get("/layers/open/sssi", params={**view, "z": zoom})
        assert cold.status_code == 200, cold.text
        started = time.perf_counter()
        warm = client.get("/layers/open/sssi", params={**view, "z": zoom})
        elapsed = time.perf_counter() - started
        assert warm.status_code == 200, warm.text
        assert elapsed < 2.0
        assert warm.content == cold.content
        assert len(warm.content) <= BUDGET_Z6


def test_size_capped_oil_and_gas_is_not_cached_empty(client, monkeypatch):
    """A size cap that hides every field must not be stored as an empty success."""
    from spatial import context_tiles

    calls = {"n": 0}

    def _features(_url, _where, extra=None):
        calls["n"] += 1
        return [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-2.0, 58.0], [-1.0, 58.0], [-1.5, 59.0], [-2.0, 58.0]]],
                },
                "properties": {"name": "North Sea"},
            }
        ]

    with context_tiles._cache_lock:
        context_tiles._cache.pop("oil-fields", None)
    monkeypatch.setattr(context_tiles, "_arcgis_features", _features)
    monkeypatch.setattr(context_tiles, "OIL_FIELDS_BYTE_BUDGET", 80)
    try:
        first = client.get("/layers/context/oil-fields")
        second = client.get("/layers/context/oil-fields")
    finally:
        with context_tiles._cache_lock:
            stored = context_tiles._cache.pop("oil-fields", None)

    assert stored is None
    assert calls["n"] == 2
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    payload = first.json()
    assert payload["features"] == []
    assert payload["meta"]["ok"] is True
    assert payload["meta"]["hidden_below_zoom"] is True
    assert payload["meta"]["hint"] == _OIL_HINT
    assert second.json()["meta"]["hint"] == _OIL_HINT
    assert second.json()["meta"]["hidden_below_zoom"] is True
