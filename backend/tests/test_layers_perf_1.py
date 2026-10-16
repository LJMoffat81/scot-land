"""LAYERS-PERF-1: protected-site payload budgets and oil-and-gas cache headers.

These checks fail on the pre-change routes: full-resolution GeoJSON, a one-hour
cache, and no ETag.
"""

from __future__ import annotations

import math
import re

from layers.naturescot import dumps_feature_collection

SCOTLAND_Z6 = {
    "south": 54.7,
    "west": -7.4,
    "north": 60.6,
    "east": -1.2,
    "z": 6,
}
BUDGET_Z6 = 500 * 1024
BUDGET_ANY = 1024 * 1024

_SIMPLIFY_SQL = re.compile(
    r"ST_Transform\(\s*"
    r"ST_SimplifyPreserveTopology\(\s*"
    r"ST_MakeValid\(\s*ST_Transform\(\s*geom\s*,\s*27700\s*\)\s*\)\s*,"
    r".+?4326\s*\)\s*,\s*5\s*\)",
    re.S,
)


def _huge_polygon(points: int = 30000) -> dict:
    ring = []
    for index in range(points):
        angle = 2 * math.pi * index / points
        ring.append(
            [
                round(-4.2 + 0.35 * math.cos(angle), 8),
                round(57.2 + 0.25 * math.sin(angle), 8),
            ]
        )
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


class _Cursor:
    def __init__(self, row: dict):
        self.row = row
        self.sql = ""
        self.params: tuple = ()

    def execute(self, sql, params):
        self.sql = sql
        self.params = tuple(params)

    def fetchall(self):
        return [self.row]

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _Conn:
    def __init__(self, row: dict):
        self.cursor_obj = _Cursor(row)

    def cursor(self, cursor_factory=None):
        return self.cursor_obj

    def close(self):
        return None


def _patch_query(monkeypatch, module_name: str, row: dict) -> _Conn:
    conn = _Conn(row)
    monkeypatch.setattr(f"{module_name}.require_sssi_loaded", lambda: None)
    monkeypatch.setattr(f"{module_name}.require_designations_loaded", lambda: None)
    monkeypatch.setattr(f"{module_name}._connect", lambda: conn)
    return conn


def _assert_budget(body: bytes, payload: dict, limit: int) -> None:
    assert len(body) <= limit
    assert len(payload["features"]) >= 1
    assert len(dumps_feature_collection(payload)) <= limit


def test_sssi_z6_scotland_is_within_budget_and_simplified(client, monkeypatch):
    conn = _patch_query(
        monkeypatch,
        "layers.naturescot",
        {
            "pa_code": "1",
            "name": "Highland site",
            "status": "Current",
            "site_type": "Biological",
            "site_ha": 12.0,
            "european_code": None,
            "geometry": _huge_polygon(),
        },
    )
    response = client.get("/layers/open/sssi", params=SCOTLAND_Z6)
    assert response.status_code == 200, response.text
    payload = response.json()
    _assert_budget(response.content, payload, BUDGET_Z6)
    assert _SIMPLIFY_SQL.search(conn.cursor_obj.sql)
    assert float(conn.cursor_obj.params[0]) >= 0.01


def test_designations_z6_scotland_is_within_budget_and_simplified(client, monkeypatch):
    conn = _patch_query(
        monkeypatch,
        "layers.naturescot",
        {
            "site_key": "spa:1",
            "designation_type": "spa",
            "pa_code": "1",
            "name": "Highland site",
            "status": "Current",
            "site_type": "SPA",
            "site_ha": 20.0,
            "european_code": None,
            "geometry": _huge_polygon(),
        },
    )
    response = client.get("/layers/open/naturescot-designations", params=SCOTLAND_Z6)
    assert response.status_code == 200, response.text
    payload = response.json()
    _assert_budget(response.content, payload, BUDGET_Z6)
    assert _SIMPLIFY_SQL.search(conn.cursor_obj.sql)
    assert float(conn.cursor_obj.params[0]) >= 0.01


def test_sssi_fine_zoom_stays_within_one_megabyte(client, monkeypatch):
    _patch_query(
        monkeypatch,
        "layers.naturescot",
        {
            "pa_code": "1",
            "name": "Highland site",
            "status": "Current",
            "site_type": "Biological",
            "site_ha": 12.0,
            "european_code": None,
            "geometry": _huge_polygon(),
        },
    )
    params = {"south": 57.0, "west": -5.0, "north": 57.4, "east": -4.4, "z": 12}
    response = client.get("/layers/open/sssi", params=params)
    assert response.status_code == 200, response.text
    assert len(response.content) <= BUDGET_ANY
    assert len(response.json()["features"]) >= 1


def test_oil_fields_budget_cache_and_etag(client, monkeypatch):
    from spatial import context_tiles

    calls = {"n": 0}

    def _features(_url, _where, extra=None):
        calls["n"] += 1
        return [
            {
                "type": "Feature",
                "geometry": _huge_polygon(),
                "properties": {"name": "North Sea"},
            }
        ]

    with context_tiles._cache_lock:
        context_tiles._cache.pop("oil-fields", None)
    monkeypatch.setattr(context_tiles, "_arcgis_features", _features)
    first = client.get("/layers/context/oil-fields")
    second = client.get("/layers/context/oil-fields")
    with context_tiles._cache_lock:
        context_tiles._cache.pop("oil-fields", None)

    assert first.status_code == 200, first.text
    payload = first.json()
    _assert_budget(first.content, payload, BUDGET_Z6)
    cache = first.headers["cache-control"]
    assert "public" in cache
    match = re.search(r"max-age=(\d+)", cache)
    assert match is not None
    assert int(match.group(1)) >= 86400
    assert first.headers["etag"]
    assert second.headers["etag"] == first.headers["etag"]
    assert calls["n"] == 1
