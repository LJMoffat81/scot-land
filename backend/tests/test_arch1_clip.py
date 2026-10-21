"""ARCH-1b clip / check tests C1–C6, K1."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import psycopg2
import pytest

from etl.build_scotland_extent import load_only
from etl.run_layer import (
    CheckError,
    intersection_calls,
    reset_intersection_counter,
    run_layer,
)

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


def _drop_arch1_layer_tables(conn) -> None:
    with conn.cursor() as cur:
        for table in (
            "oil-fields",
            "oil-fields_prev",
            "oil-fields__new",
            "platforms",
            "platforms_prev",
            "platforms__new",
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
        for table in (
            "extent_buf50_sub",
            "extent_sub",
            "extent",
        ):
            cur.execute(f"DROP TABLE IF EXISTS ref.{table} CASCADE")
    _drop_arch1_layer_tables(conn)

    gis = tmp_path / "gis"
    gis.mkdir()
    src = FIXTURES / "extent_tiny.27700.geojson"
    dest = gis / "scotland_extent.27700.geojson"
    dest.write_bytes(src.read_bytes())
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    (gis / "manifest.csv").write_text(
        "file,sha256\n"
        f"scotland_extent.27700.geojson,{sha}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "etl.build_scotland_extent.MANIFEST_PATH", gis / "manifest.csv"
    )
    load_only(dest)
    yield conn
    _drop_arch1_layer_tables(conn)


def _wkb(conn, layer_id: str, feature_id: str) -> bytes:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT ST_AsBinary(geom) FROM layers."{layer_id}" WHERE feature_id=%s',
            (feature_id,),
        )
        row = cur.fetchone()
        assert row is not None, f"missing feature_id={feature_id}"
        return bytes(row[0])


def test_c1_inside_fast_path_no_intersection(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    run_layer("oil-fields", from_file=FEEDS / "inside3.geojson", conn=tiny_extent)
    # Re-stage and clip alone to count intersections for the same inside set.
    reset_intersection_counter(tiny_extent)
    before = {
        fid: _wkb(tiny_extent, "oil-fields", fid) for fid in ("1", "2", "3")
    }
    # Force a second clip of the same stage rows via run_layer again.
    run_layer("oil-fields", from_file=FEEDS / "inside3.geojson", conn=tiny_extent)
    calls = intersection_calls(tiny_extent)
    assert calls == 0, f"intersection calls {calls} != 0"
    for fid, wkb in before.items():
        assert _wkb(tiny_extent, "oil-fields", fid) == wkb


def test_c2_outside_dropped(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    # Mix inside + outside so check still passes (count > 0).
    mixed = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::27700"},
        },
        "features": json.loads((FEEDS / "inside3.geojson").read_text())["features"]
        + json.loads((FEEDS / "outside2.geojson").read_text())["features"],
    }
    path = FEEDS / "_mixed_c2.geojson"
    path.write_text(json.dumps(mixed), encoding="utf-8")
    # Clip only (no check) so M1 surfaces as outside-count assert, not CheckError.
    from datetime import date

    from etl.run_layer import (
        _clip,
        _dataset_version,
        _ensure_helpers,
        _load_stage,
        reset_intersection_counter,
    )
    from layers.registry.loader import registry

    raw = path.read_bytes()
    collection = json.loads(raw.decode("utf-8"))
    entry = registry()["oil-fields"]
    _ensure_helpers(tiny_extent)
    as_of = date.today()
    _load_stage(
        tiny_extent,
        "oil-fields",
        list(collection["features"]),
        as_of=as_of,
        dataset_version=_dataset_version("oil-fields", as_of, raw),
        method="source",
        already_27700=True,
    )
    reset_intersection_counter(tiny_extent)
    _clip(tiny_extent, "oil-fields", entry, new_name="oil-fields")
    with tiny_extent.cursor() as cur:
        cur.execute(
            'SELECT count(*) FROM layers."oil-fields" WHERE props->>\'kind\'=%s',
            ("outside",),
        )
        assert cur.fetchone()[0] == 0


def test_c3_straddlers_half_area(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    mixed = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::27700"},
        },
        "features": json.loads((FEEDS / "inside3.geojson").read_text())["features"]
        + json.loads((FEEDS / "straddle2.geojson").read_text())["features"],
    }
    path = FEEDS / "_mixed_c3.geojson"
    path.write_text(json.dumps(mixed), encoding="utf-8")
    receipt = run_layer("oil-fields", from_file=path, conn=tiny_extent)
    with tiny_extent.cursor() as cur:
        cur.execute(
            """
            SELECT count(*), coalesce(avg(ST_Area(geom)/1e6), 0)
            FROM layers."oil-fields"
            WHERE props->>'kind'='straddle'
            """
        )
        n, avg_area = cur.fetchone()
        assert n == 2  # M2: ST_Within drops straddlers → assert 0 == 2
        assert abs(float(avg_area) - 50.0) <= 0.01, f"area {avg_area} != 50.0"
    assert receipt["after"] == 5


def test_c4_point_30m_outside_dropped(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    receipt = run_layer(
        "platforms", from_file=FEEDS / "points.geojson", conn=tiny_extent
    )
    # 1 inside kept; 30 m and 200 m outside dropped (extent, not buf50).
    with tiny_extent.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM layers."platforms"
            WHERE props->>'name' = 'pt-30m'
            """
        )
        assert cur.fetchone()[0] == 0  # M4: buf50 keep → assert 1 == 0
        cur.execute(
            'SELECT props->>\'name\' FROM layers."platforms" ORDER BY 1'
        )
        names = [r[0] for r in cur.fetchall()]
        assert names == ["pt-inside"]
    assert receipt["after"] == 1


def test_c5_line_clipped_stays_line(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    receipt = run_layer(
        "pipelines", from_file=FEEDS / "line_edge.geojson", conn=tiny_extent
    )
    assert receipt["after"] == 1
    with tiny_extent.cursor() as cur:
        cur.execute(
            """
            SELECT GeometryType(geom), ST_XMin(geom), ST_XMax(geom)
            FROM layers."pipelines"
            """
        )
        gtype, xmin, xmax = cur.fetchone()
        assert gtype.upper().endswith("LINESTRING")
        assert xmin >= 10000 - 1e-6
        assert xmax <= 20000 + 1e-6


def test_c6_feature_id_and_properties_kept(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    run_layer("oil-fields", from_file=FEEDS / "c6_props.geojson", conn=tiny_extent)
    with tiny_extent.cursor() as cur:
        cur.execute('SELECT row_to_json(t) FROM layers."oil-fields" t')
        row = cur.fetchone()[0]
        if "feature_id" not in row:
            raise KeyError("feature_id")
        assert row["feature_id"] == "99"
        assert row["props"]["fieldname"] == "Alpha"
        assert row["props"]["status"] == "Active"


def test_k1_check_passes_and_rejects_outside(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    run_layer("oil-fields", from_file=FEEDS / "inside3.geojson", conn=tiny_extent)
    # Forced bad row well outside buf50.
    with tiny_extent.cursor() as cur:
        cur.execute(
            """
            INSERT INTO layers."oil-fields" (
              feature_id, props, geom,
              source_layer_ids, dataset_version, as_of, method, child_unit_ids
            )
            VALUES (
              'bad',
              '{}'::jsonb,
              ST_SetSRID(ST_MakeEnvelope(50000, 50000, 51000, 51000), 27700),
              ARRAY['oil-fields'],
              'oil-fields@1970-01-01-deadbeef',
              CURRENT_DATE,
              'source',
              NULL
            )
            """
        )
    from etl.run_layer import _check

    with pytest.raises(
        CheckError,
        match=r"CHECK: oil-fields: 1 features outside scotland\+50m",
    ):
        _check(tiny_extent, "oil-fields", "oil-fields")
