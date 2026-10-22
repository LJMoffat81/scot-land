"""LAYERS-PERF-1: protected-site payload budgets and oil-and-gas cache headers.

These checks fail on the pre-change routes: full-resolution GeoJSON, a one-hour
cache, and no ETag.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import date
from pathlib import Path

import psycopg2
import pytest

from etl.build_scotland_extent import load_only
from etl.run_layer import _ensure_helpers
from layers.naturescot import dumps_feature_collection
from spatial import context_tiles

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


def _seed_oil_fields_clipped_table(monkeypatch, *, dense: bool = False) -> None:
    """Seed ``layers.oil-fields`` + tiny Scotland extent for ARCH-1 serve path.

    ARCH-1 removed the live NSTA request-path fetch; these LAYERS-PERF tests
    now read a seeded clipped table with the same response assertions.
    """
    dsn = (
        os.environ.get("ARCH1_TEST_DSN")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if not dsn:
        pytest.skip("ARCH1_TEST_DSN / DATABASE_URL not set")
    monkeypatch.setenv("ARCH1_TEST_DSN", dsn)

    fixtures = Path(__file__).resolve().parent / "fixtures" / "arch1"
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            cur.execute("CREATE SCHEMA IF NOT EXISTS ref")
            cur.execute("CREATE SCHEMA IF NOT EXISTS layers")
            for table in ("extent_buf50_sub", "extent_sub", "extent"):
                cur.execute(f"DROP TABLE IF EXISTS ref.{table} CASCADE")
            cur.execute('DROP TABLE IF EXISTS layers."oil-fields" CASCADE')

        src = fixtures / "extent_tiny.27700.geojson"
        body = src.read_bytes()
        sha = hashlib.sha256(body).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            gis = Path(tmp)
            dest = gis / "scotland_extent.27700.geojson"
            dest.write_bytes(body)
            (gis / "manifest.csv").write_text(
                f"file,sha256\nscotland_extent.27700.geojson,{sha}\n",
                encoding="utf-8",
            )
            monkeypatch.setattr(
                "etl.build_scotland_extent.MANIFEST_PATH", gis / "manifest.csv"
            )
            load_only(dest)

        _ensure_helpers(conn)
        # Sea square of the tiny extent: x 10–20 km, y 0–10 km (EPSG:27700).
        if dense:
            coords = []
            for i in range(400):
                angle = 2 * math.pi * i / 400
                coords.append(
                    [
                        15000 + 2000 * math.cos(angle),
                        5000 + 2000 * math.sin(angle),
                    ]
                )
            coords.append(coords[0])
            wkt_ring = ", ".join(f"{x} {y}" for x, y in coords)
            geom_sql = f"ST_GeomFromText('POLYGON(({wkt_ring}))', 27700)"
        else:
            geom_sql = "ST_MakeEnvelope(11000, 1000, 18000, 8000, 27700)"
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE layers."oil-fields" (
                  feature_id text NOT NULL,
                  props jsonb NOT NULL,
                  geom geometry(Geometry, 27700) NOT NULL,
                  source_layer_ids text[] NOT NULL,
                  dataset_version text NOT NULL,
                  as_of date NOT NULL,
                  method text NOT NULL,
                  child_unit_ids text[] NULL
                )
                """
            )
            cur.execute(
                f"""
                INSERT INTO layers."oil-fields" (
                  feature_id, props, geom,
                  source_layer_ids, dataset_version, as_of, method, child_unit_ids
                )
                VALUES (
                  '1',
                  %s::jsonb,
                  {geom_sql},
                  ARRAY['oil-fields'],
                  %s,
                  %s,
                  'source',
                  NULL
                )
                """,
                (
                    json.dumps({"name": "North Sea"}),
                    f"oil-fields@{date.today().isoformat()}-perfseed",
                    date.today(),
                ),
            )
    finally:
        conn.close()


def test_oil_fields_budget_cache_and_etag(client, monkeypatch):
    _seed_oil_fields_clipped_table(monkeypatch, dense=False)

    calls = {"n": 0}
    real_fetch = context_tiles._fetch_registry_geojson

    def _counted(layer_id):
        calls["n"] += 1
        return real_fetch(layer_id)

    with context_tiles._cache_lock:
        context_tiles._cache.pop("oil-fields", None)
    monkeypatch.setattr(context_tiles, "_fetch_registry_geojson", _counted)
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
