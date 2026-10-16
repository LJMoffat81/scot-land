"""LAYERS-PERF-2: protected sites must not come back as bounding boxes.

A large marine multipolygon used to be replaced with a 5-point envelope at
z6–z8. These checks fail while that fallback exists.
"""

from __future__ import annotations

import re
import time

from tests.test_layers_perf_1 import BUDGET_Z6, _patch_query

_BNG_SIMPLIFY = re.compile(
    r"ST_Transform\(\s*"
    r"ST_SimplifyPreserveTopology\(\s*"
    r"ST_MakeValid\(\s*ST_Transform\(\s*geom\s*,\s*27700\s*\)\s*\)\s*,"
    r".+?4326\s*\)\s*,\s*5\s*\)",
    re.S,
)


def _marine_multipolygon(parts: int = 12000) -> dict:
    """Many triangles whose vertices sit more than a degree apart.

    Degree-based simplification cannot collapse them under the 500 KB budget,
    so the old envelope fallback returns one axis-aligned rectangle.
    """
    polygons = []
    for index in range(parts):
        col = index % 100
        row = index // 100
        x = -40.0 + col * 3.0
        y = 20.0 + row * 3.0
        polygons.append(
            [
                [
                    [x, y],
                    [x + 2.0, y],
                    [x + 0.4, y + 2.0],
                    [x, y],
                ]
            ]
        )
    return {"type": "MultiPolygon", "coordinates": polygons}


def _is_five_point_axis_aligned_rectangle(geom: dict) -> bool:
    if geom.get("type") == "MultiPolygon":
        parts = geom.get("coordinates") or []
        if len(parts) != 1:
            return False
        return _is_five_point_axis_aligned_rectangle(
            {"type": "Polygon", "coordinates": parts[0]}
        )
    if geom.get("type") != "Polygon":
        return False
    rings = geom.get("coordinates") or []
    if len(rings) != 1:
        return False
    ring = rings[0]
    if len(ring) != 5:
        return False
    if ring[0] != ring[-1]:
        return False
    corners = ring[:-1]
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    if len(set(xs)) != 2 or len(set(ys)) != 2:
        return False
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    if min_x == max_x or min_y == max_y:
        return False
    return all(
        (x == min_x or x == max_x) and (y == min_y or y == max_y)
        for x, y in zip(xs, ys)
    )


def _designation_row() -> dict:
    return {
        "site_key": "sac:marine",
        "designation_type": "sac",
        "pa_code": "SAC-MARINE",
        "name": "Marine site",
        "status": "Current",
        "site_type": "SAC",
        "site_ha": 80000.0,
        "european_code": None,
        "geometry": _marine_multipolygon(),
    }


def test_designations_z6_z8_z9_marine_site_is_not_a_bounding_box(client, monkeypatch):
    conn = _patch_query(monkeypatch, "layers.naturescot", _designation_row())
    tolerances: list[float] = []
    view = {"south": 54.7, "west": -7.4, "north": 60.6, "east": -1.2}
    for zoom in (6, 8, 9):
        response = client.get(
            "/layers/open/naturescot-designations",
            params={**view, "z": zoom},
        )
        assert response.status_code == 200, response.text
        assert len(response.content) <= BUDGET_Z6
        payload = response.json()
        features = payload["features"]
        for feature in features:
            assert not _is_five_point_axis_aligned_rectangle(feature["geometry"])
        if features:
            assert payload["meta"].get("hidden_below_zoom") is not True
        else:
            assert payload["meta"].get("hidden_below_zoom") is True
        assert _BNG_SIMPLIFY.search(conn.cursor_obj.sql)
        tolerances.append(float(conn.cursor_obj.params[0]))

    assert tolerances[0] > tolerances[1] > tolerances[2]
    assert tolerances[2] > 50


def test_cap_feature_collection_never_emits_an_envelope():
    from layers.naturescot import cap_feature_collection, dumps_feature_collection

    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": _marine_multipolygon(),
                "properties": {"name": "Marine site"},
            }
        ],
        "meta": {"ok": True, "count": 1},
    }
    capped = cap_feature_collection(payload, BUDGET_Z6)
    assert capped["features"] == []
    assert capped["meta"]["hidden_below_zoom"] is True
    assert len(dumps_feature_collection(capped)) <= BUDGET_Z6
    assert "envelope" not in dumps_feature_collection(capped).decode("utf-8")


def test_designations_z6_z7_z8_warm_under_two_seconds(client, monkeypatch):
    """A repeat view must not run the slow query again.

    The stand-in query sleeps past two seconds, which is what z6 used to cost.
    The warm call has to come back from the z6–z8 cache inside that limit.
    """
    conn = _patch_query(
        monkeypatch,
        "layers.naturescot",
        {
            "site_key": "sac:warm",
            "designation_type": "sac",
            "pa_code": "SAC-WARM",
            "name": "Warm site",
            "status": "Current",
            "site_type": "SAC",
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
        cold = client.get(
            "/layers/open/naturescot-designations",
            params={**view, "z": zoom},
        )
        assert cold.status_code == 200, cold.text
        started = time.perf_counter()
        warm = client.get(
            "/layers/open/naturescot-designations",
            params={**view, "z": zoom},
        )
        elapsed = time.perf_counter() - started
        assert warm.status_code == 200, warm.text
        assert elapsed < 2.0
        assert warm.content == cold.content
        assert len(warm.content) <= BUDGET_Z6
