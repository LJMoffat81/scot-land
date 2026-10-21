"""ARCH-1b serve / lineage tests E1–E2, L1–L2."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import httpx
import psycopg2
import pytest

from etl.build_scotland_extent import load_only
from etl.run_layer import run_layer
from spatial.context_tiles import _cache, _cache_lock, fetch_context_geojson

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "arch1"
FEEDS = FIXTURES / "feeds"


def _dsn() -> str:
    dsn = os.environ.get("ARCH1_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("ARCH1_TEST_DSN not set")
    return dsn


@pytest.fixture
def conn():
    connection = psycopg2.connect(_dsn())
    connection.autocommit = True
    with connection.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    yield connection
    connection.close()


def _drop_serve_tables(conn) -> None:
    with conn.cursor() as cur:
        for table in (
            "oil-fields",
            "oil-fields_prev",
            "oil-fields__new",
            "pipelines",
            "pipelines_prev",
            "pipelines__new",
        ):
            cur.execute(f'DROP TABLE IF EXISTS layers."{table}" CASCADE')
            cur.execute(f'DROP TABLE IF EXISTS stage."{table}" CASCADE')


@pytest.fixture
def tiny_extent(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS ref")
        cur.execute("CREATE SCHEMA IF NOT EXISTS stage")
        cur.execute("CREATE SCHEMA IF NOT EXISTS layers")
        for table in ("extent_buf50_sub", "extent_sub", "extent"):
            cur.execute(f"DROP TABLE IF EXISTS ref.{table} CASCADE")
    _drop_serve_tables(conn)

    gis = tmp_path / "gis"
    gis.mkdir()
    src = FIXTURES / "extent_tiny.27700.geojson"
    dest = gis / "scotland_extent.27700.geojson"
    dest.write_bytes(src.read_bytes())
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    (gis / "manifest.csv").write_text(
        f"file,sha256\nscotland_extent.27700.geojson,{sha}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "etl.build_scotland_extent.MANIFEST_PATH", gis / "manifest.csv"
    )
    load_only(dest)
    with _cache_lock:
        _cache.clear()
    yield conn
    _drop_serve_tables(conn)
    with _cache_lock:
        _cache.clear()


def test_e1_endpoint_serves_from_table_no_httpx(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    run_layer(
        "oil-fields", from_file=FEEDS / "inside3.geojson", conn=tiny_extent
    )

    def ban(*_a, **_k):
        raise RuntimeError("upstream fetch in request path")

    monkeypatch.setattr(httpx.Client, "get", ban)
    monkeypatch.setattr(httpx, "get", ban)
    # Also ban the legacy ArcGIS helper so M5 (serve upstream) trips the same error.
    import spatial.context_tiles as ct

    monkeypatch.setattr(
        ct,
        "_arcgis_features",
        lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("upstream fetch in request path")
        ),
    )
    with _cache_lock:
        _cache.pop("oil-fields", None)
    geo = fetch_context_geojson("oil-fields")
    assert geo["meta"]["ok"] is True
    assert geo["meta"]["count"] == 3
    assert len(geo["features"]) == 3


def _write_dense_pipelines(path: Path, n: int = 2000) -> Path:
    """2000 long dense lines in the tiny sea box (unsimplified GeoJSON > 15 MB)."""
    crs = {
        "type": "name",
        "properties": {"name": "urn:ogc:def:crs:EPSG::27700"},
    }
    features = []
    for i in range(n):
        y = 1000 + (i % 8000)
        coords = [
            [11000 + j * 50, y + (2 if j % 2 else -2)] for j in range(800)
        ]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "OBJECTID": 1000 + i,
                    "pipename": f"p{i}",
                    "fluid": "oil",
                },
                "geometry": {"type": "LineString", "coordinates": coords},
            }
        )
    path.write_text(
        json.dumps(
            {"type": "FeatureCollection", "crs": crs, "features": features}
        ),
        encoding="utf-8",
    )
    return path


def test_e2_pipelines_under_15mb_with_simplify(tiny_extent, monkeypatch, tmp_path):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    feed = _write_dense_pipelines(tmp_path / "dense_pipelines.geojson")
    run_layer(
        "pipelines",
        from_file=feed,
        conn=tiny_extent,
    )
    with _cache_lock:
        _cache.pop("pipelines", None)
    geo = fetch_context_geojson("pipelines")
    assert geo["meta"]["ok"] is True
    body = json.dumps(geo).encode("utf-8")
    mb = len(body) / (1024 * 1024)
    assert mb < 15, f"body {mb:.2f} MB >= 15"
    json.loads(body)  # valid JSON


def test_l1_lineage_columns_and_meta(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    receipt = run_layer(
        "oil-fields", from_file=FEEDS / "inside3.geojson", conn=tiny_extent
    )
    with tiny_extent.cursor() as cur:
        cur.execute(
            """
            SELECT source_layer_ids, dataset_version, as_of, method
            FROM layers."oil-fields"
            """
        )
        rows = cur.fetchall()
        assert rows
        for source_ids, version, as_of, method in rows:
            if as_of is None:
                pytest.fail("null as_of in layers.oil-fields")
            assert source_ids is not None
            assert version is not None
            assert method is not None
            assert source_ids == ["oil-fields"]
            assert method == "source"
            assert version.startswith("oil-fields@")
    with _cache_lock:
        _cache.pop("oil-fields", None)
    geo = fetch_context_geojson("oil-fields")
    assert geo["meta"].get("dataset_version") == receipt["dataset_version"]
    assert geo["meta"].get("as_of") == receipt["as_of"]


def test_l2_dataset_version_tracks_body(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    r1 = run_layer(
        "oil-fields", from_file=FEEDS / "inside3.geojson", conn=tiny_extent
    )
    r1b = run_layer(
        "oil-fields", from_file=FEEDS / "inside3.geojson", conn=tiny_extent
    )
    assert r1["dataset_version"] == r1b["dataset_version"]

    # Change body → version changes.
    alt = json.loads((FEEDS / "inside3.geojson").read_text(encoding="utf-8"))
    alt["features"][0]["properties"]["name"] = "changed"
    path = FEEDS / "_l2_changed.geojson"
    path.write_text(json.dumps(alt), encoding="utf-8")
    r2 = run_layer("oil-fields", from_file=path, conn=tiny_extent)
    assert r2["dataset_version"] != r1["dataset_version"]
