"""ARCH-1b fail-closed / budget tests F1–F3."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import psycopg2
import pytest

from etl.build_scotland_extent import load_only
from etl.run_layer import IngestError, run_layer
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


@pytest.fixture
def tiny_extent(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS ref")
        cur.execute("CREATE SCHEMA IF NOT EXISTS stage")
        cur.execute("CREATE SCHEMA IF NOT EXISTS layers")
        for table in ("extent_buf50_sub", "extent_sub", "extent"):
            cur.execute(f"DROP TABLE IF EXISTS ref.{table} CASCADE")
        for table in (
            "oil-fields",
            "oil-fields_prev",
            "oil-fields__new",
        ):
            cur.execute(f'DROP TABLE IF EXISTS layers."{table}" CASCADE')
            cur.execute(f'DROP TABLE IF EXISTS stage."{table}" CASCADE')

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
    return conn


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
        assert cur.fetchone()[0] == good
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema='layers' AND table_name='oil-fields_prev'
            )
            """
        )
        # _prev unchanged relative to pre-failed-run state (still absent after
        # the first successful run which had no prior live table).
        assert cur.fetchone()[0] == had_prev


def test_f2_no_table_and_no_extent_notes(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    with _cache_lock:
        _cache.pop("oil-fields", None)

    # Table absent → layer not built.
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


def test_f3_budget_mb_exceeded(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())

    def fat_fetch(*_a, **_k):
        raise RuntimeError("budget exceeded: mb")

    monkeypatch.setattr("etl.run_layer.fetch_arcgis", fat_fetch)
    # Force arcgis path (no --from-file).
    with pytest.raises(
        IngestError, match=r"INGEST: pipelines budget exceeded: mb"
    ):
        run_layer("pipelines", conn=tiny_extent)
