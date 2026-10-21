"""ARCH-1b S1 clip timing against the committed Scotland extent."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import psycopg2
import pytest

from etl.build_scotland_extent import OUT_PATH, load_only
from etl.run_layer import run_layer

REPO = Path(__file__).resolve().parents[2]
FEEDS = Path(__file__).resolve().parent / "fixtures" / "arch1" / "feeds"


def _dsn() -> str:
    dsn = os.environ.get("ARCH1_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("ARCH1_TEST_DSN not set")
    return dsn


@pytest.fixture
def real_extent(monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    if not OUT_PATH.is_file():
        pytest.skip(f"committed extent missing: {OUT_PATH}")
    conn = psycopg2.connect(_dsn())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cur.execute("CREATE SCHEMA IF NOT EXISTS ref")
        cur.execute("CREATE SCHEMA IF NOT EXISTS stage")
        cur.execute("CREATE SCHEMA IF NOT EXISTS layers")
        for table in ("extent_buf50_sub", "extent_sub", "extent"):
            cur.execute(f"DROP TABLE IF EXISTS ref.{table} CASCADE")
        for table in ("oil-fields", "oil-fields_prev", "oil-fields__new"):
            cur.execute(f'DROP TABLE IF EXISTS layers."{table}" CASCADE')
            cur.execute(f'DROP TABLE IF EXISTS stage."{table}" CASCADE')
    load_only(OUT_PATH)
    yield conn
    conn.close()


def _synthetic_feed(conn, path: Path) -> Path:
    """500 random 2–10 km squares (seed 248) over the Scotland extent bbox."""
    with conn.cursor() as cur:
        cur.execute("SELECT setseed(0.248)")
        cur.execute(
            """
            WITH b AS (
              SELECT ST_Extent(geom) AS e FROM ref.extent WHERE geography='scotland'
            ),
            pts AS (
              SELECT
                ST_SetSRID(
                  ST_MakePoint(
                    ST_XMin(e) + random() * (ST_XMax(e) - ST_XMin(e)),
                    ST_YMin(e) + random() * (ST_YMax(e) - ST_YMin(e))
                  ),
                  27700
                ) AS pt,
                2000 + random() * 8000 AS half
              FROM b, generate_series(1, 500)
            )
            SELECT
              ST_AsGeoJSON(
                ST_MakeEnvelope(
                  ST_X(pt) - half, ST_Y(pt) - half,
                  ST_X(pt) + half, ST_Y(pt) + half,
                  27700
                )
              ),
              row_number() OVER ()
            FROM pts
            """
        )
        features = []
        for geom_json, oid in cur.fetchall():
            features.append(
                {
                    "type": "Feature",
                    "properties": {"OBJECTID": int(oid)},
                    "geometry": json.loads(geom_json),
                }
            )
    coll = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::27700"},
        },
        "features": features,
    }
    path.write_text(json.dumps(coll), encoding="utf-8")
    return path


def test_s1_clip_check_under_2s(real_extent, monkeypatch, tmp_path):
    """Clip + check wall time against subdivided extent must stay under 2.0 s."""
    from datetime import date

    from etl.run_layer import (
        _check,
        _clip,
        _dataset_version,
        _ensure_helpers,
        _load_stage,
        reset_intersection_counter,
    )
    from layers.registry.loader import registry

    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    feed = _synthetic_feed(real_extent, tmp_path / "synthetic500.geojson")
    raw = feed.read_bytes()
    collection = json.loads(raw.decode("utf-8"))
    entry = registry()["oil-fields"]
    _ensure_helpers(real_extent)
    as_of = date.today()
    version = _dataset_version("oil-fields", as_of, raw)
    _load_stage(
        real_extent,
        "oil-fields",
        list(collection["features"]),
        as_of=as_of,
        dataset_version=version,
        method="source",
        already_27700=True,
    )
    reset_intersection_counter(real_extent)
    t0 = time.perf_counter()
    after = _clip(
        real_extent, "oil-fields", entry, new_name="oil-fields__new"
    )
    outside = _check(real_extent, "oil-fields", "oil-fields__new")
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"clip took {elapsed:.3f}s >= 2.0s"
    assert outside == 0
    assert after > 0
