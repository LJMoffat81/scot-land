"""ARCH-1b fail-closed / budget tests F1–F3."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import httpx
import psycopg2
import pytest

from etl.adapters.arcgis import fetch_arcgis
from etl.build_scotland_extent import load_only
from etl.run_layer import IngestError, run_layer
from layers.registry.loader import registry
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


def _drop_oil_tables(conn) -> None:
    with conn.cursor() as cur:
        for table in ("oil-fields", "oil-fields_prev", "oil-fields__new"):
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
    _drop_oil_tables(conn)

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
    yield conn
    _drop_oil_tables(conn)


def test_f1_failed_fetch_keeps_last_good(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    run_layer(
        "oil-fields", from_file=FEEDS / "inside3.geojson", conn=tiny_extent
    )
    with tiny_extent.cursor() as cur:
        cur.execute('SELECT count(*) FROM layers."oil-fields"')
        good = cur.fetchone()[0]
        assert good == 3
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema='layers' AND table_name='oil-fields_prev'
            )
            """
        )
        had_prev = cur.fetchone()[0]

    def boom(*_a, **_k):
        raise RuntimeError("upstream down")

    monkeypatch.setattr("etl.run_layer.fetch_geojson_file", boom)
    with pytest.raises(IngestError):
        run_layer(
            "oil-fields", from_file=FEEDS / "inside3.geojson", conn=tiny_extent
        )

    with tiny_extent.cursor() as cur:
        cur.execute('SELECT count(*) FROM layers."oil-fields"')
        # M12 non-atomic swap can wipe live → assert 0 == 3
        assert cur.fetchone()[0] == 3
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema='layers' AND table_name='oil-fields_prev'
            )
            """
        )
        assert cur.fetchone()[0] == had_prev
        assert good == 3


def test_f2_no_table_and_no_extent_notes(tiny_extent, monkeypatch):
    """Fail-closed without monkeypatching FEATURES / upstream fetch away."""
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    with _cache_lock:
        _cache.pop("oil-fields", None)

    # Table absent → layer not built (no live NSTA fallthrough).
    geo = fetch_context_geojson("oil-fields")
    assert geo["meta"]["ok"] is False
    assert geo["meta"]["note"] == "layer not built"
    assert geo["features"] == []

    # Drop extent → Scotland boundary missing.
    with tiny_extent.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS ref.extent_sub CASCADE")
        cur.execute("DROP TABLE IF EXISTS ref.extent CASCADE")
        cur.execute("DROP TABLE IF EXISTS ref.extent_buf50_sub CASCADE")
    with _cache_lock:
        _cache.pop("oil-fields", None)
    geo2 = fetch_context_geojson("oil-fields")
    assert geo2["meta"]["ok"] is False
    assert geo2["meta"]["note"] == "Scotland boundary missing"


def test_f3_budget_mb_exceeded(tiny_extent, monkeypatch, tmp_path):
    """Budget check must live in the adapters; deleting it turns this red.

    Covers both the ArcGIS paging path and ``--from-file``.
    """
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    entry = registry()["pipelines"]
    original_max = entry.raw["refresh"]["max_mb"]
    entry.raw["refresh"]["max_mb"] = 1  # 1 MB budget
    try:
        fat_body = b"x" * (2 * 1024 * 1024)

        class _Resp:
            content = fat_body
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"type": "FeatureCollection", "features": []}

        class _Client:
            def __init__(self, *args, **kwargs) -> None:
                return None

            def get(self, *args, **kwargs):
                return _Resp()

            def close(self) -> None:
                return None

        # Direct adapter first: deleting the size check in adapters/arcgis.py
        # makes this assertion fail (no RuntimeError).
        with pytest.raises(RuntimeError, match=r"budget exceeded: mb"):
            fetch_arcgis(
                "https://example.invalid/FeatureServer/0/query",
                max_mb=1,
                max_s=60,
                client=_Client(),
            )

        # ArcGIS ingest path via run_layer (httpx Client patched).
        monkeypatch.setattr(httpx, "Client", _Client)
        with pytest.raises(
            IngestError, match=r"INGEST: pipelines budget exceeded: mb"
        ):
            run_layer("pipelines", conn=tiny_extent)

        # --- from-file path: same budget applied to local GeoJSON bytes ---
        fat_file = tmp_path / "fat_pipelines.geojson"
        pad = " " * (1024 * 1024)
        fat_file.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "crs": {
                        "type": "name",
                        "properties": {"name": "urn:ogc:def:crs:EPSG::27700"},
                    },
                    "features": [],
                    "pad": pad,
                }
            ),
            encoding="utf-8",
        )
        assert fat_file.stat().st_size > 1024 * 1024
        with pytest.raises(
            IngestError, match=r"INGEST: pipelines budget exceeded: mb"
        ):
            run_layer("pipelines", from_file=fat_file, conn=tiny_extent)
    finally:
        entry.raw["refresh"]["max_mb"] = original_max
