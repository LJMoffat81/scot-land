"""ARCH-2a-1 ingest tests I-1..I-5."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from etl.run_layer import IngestError, run_layer
from layers.registry.loader import registry

_HELPERS_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "arch2" / "helpers.py"
)
_spec = importlib.util.spec_from_file_location("arch2_helpers", _HELPERS_PATH)
assert _spec and _spec.loader
_helpers = importlib.util.module_from_spec(_spec)
sys.modules["arch2_helpers"] = _helpers
_spec.loader.exec_module(_helpers)

connect = _helpers.connect
drop_dz_boundaries = _helpers.drop_dz_boundaries
drop_layer_tables = _helpers.drop_layer_tables
load_tiny_extent = _helpers.load_tiny_extent
require_dsn = _helpers.require_dsn
seed_dz_grid = _helpers.seed_dz_grid


@pytest.fixture
def conn():
    require_dsn()
    connection = connect()
    yield connection
    connection.close()


@pytest.fixture
def tiny_extent(conn, monkeypatch, tmp_path):
    drop_layer_tables(conn, "dz2022", "oil-fields")
    drop_dz_boundaries(conn)
    load_tiny_extent(conn, monkeypatch, tmp_path)
    seed_dz_grid(conn)
    yield conn
    drop_layer_tables(conn, "dz2022", "oil-fields")
    drop_dz_boundaries(conn)


def test_i1_postgis_where_and_clip(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", require_dsn())
    receipt = run_layer("dz2022", conn=tiny_extent)
    assert receipt["after"] == 10, receipt
    assert receipt["outside"] == 0
    with tiny_extent.cursor() as cur:
        cur.execute(
            """
            SELECT feature_id, ST_Area(geom),
                   source_layer_ids, dataset_version, as_of, method
            FROM layers."dz2022"
            ORDER BY feature_id
            """
        )
        rows = cur.fetchall()
    assert len(rows) == 10
    straddle = next(r for r in rows if r[0] == "S01013491")
    # 1 km² square halved by the extent edge → ~500_000 m²
    assert 400_000 < float(straddle[1]) < 600_000
    for _fid, _area, source_ids, version, as_of, method in rows:
        assert source_ids is not None
        assert version is not None
        assert as_of is not None
        assert method is not None


def test_i2_dataset_version_content_hash(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", require_dsn())
    r1 = run_layer("dz2022", conn=tiny_extent)
    r2 = run_layer("dz2022", conn=tiny_extent)
    assert r1["dataset_version"] == r2["dataset_version"]

    with tiny_extent.cursor() as cur:
        cur.execute(
            """
            UPDATE public.dz_boundaries
            SET geom = ST_Translate(geom, 1, 0)
            WHERE code = 'S01013482'
            """
        )
    r3 = run_layer("dz2022", conn=tiny_extent)
    assert r3["dataset_version"] != r1["dataset_version"]


def test_i3_budget_exceeded(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", require_dsn())
    entry = registry()["dz2022"]
    old = entry.raw["refresh"]["max_mb"]
    entry.raw["refresh"]["max_mb"] = 0.00001
    try:
        msg = "INGEST: dz2022 budget exceeded: mb"
        with pytest.raises(IngestError, match=re.escape(msg) + "$"):
            run_layer("dz2022", conn=tiny_extent)
    finally:
        entry.raw["refresh"]["max_mb"] = old


def test_i4_missing_table(tiny_extent, monkeypatch):
    monkeypatch.setenv("ARCH1_TEST_DSN", require_dsn())
    entry = registry()["dz2022"]
    old = entry.raw["source"]["table"]
    entry.raw["source"]["table"] = "dz_missing"
    try:
        with pytest.raises(
            IngestError,
            match=re.escape("INGEST: dz2022 fetch failed: "),
        ) as excinfo:
            run_layer("dz2022", conn=tiny_extent)
        assert 'relation "dz_missing" does not exist' in str(excinfo.value)
    finally:
        entry.raw["source"]["table"] = old


@pytest.mark.parametrize(
    "kind",
    ["empty_obj", "string", "null", "missing_key", "top_list"],
)
def test_i5_geojson_features_refusals(tiny_extent, monkeypatch, tmp_path, kind):
    monkeypatch.setenv("ARCH1_TEST_DSN", require_dsn())
    path = tmp_path / "bad.geojson"
    if kind == "missing_key":
        body: object = {"type": "FeatureCollection"}
    elif kind == "null":
        body = {"type": "FeatureCollection", "features": None}
    elif kind == "string":
        body = {"type": "FeatureCollection", "features": "x"}
    elif kind == "empty_obj":
        body = {"type": "FeatureCollection", "features": {}}
    else:
        body = ["not", "an", "object"]
    path.write_text(json.dumps(body), encoding="utf-8")

    msg = f"INGEST: oil-fields geojson file not a FeatureCollection: {path}"
    # Non-IngestError outcomes (M10 accepts bad features then clip fails) → DID NOT RAISE.
    try:
        run_layer("oil-fields", from_file=path, conn=tiny_extent)
    except IngestError as exc:
        assert re.search(re.escape(msg) + "$", str(exc))
    except Exception as exc:
        pytest.fail(f"DID NOT RAISE {IngestError}")
    else:
        pytest.fail(f"DID NOT RAISE {IngestError}")


def test_i5_geojson_empty_file(tiny_extent, monkeypatch, tmp_path):
    monkeypatch.setenv("ARCH1_TEST_DSN", require_dsn())
    path = tmp_path / "empty.geojson"
    path.write_text("", encoding="utf-8")
    msg = f"INGEST: oil-fields geojson file not JSON: {path}"
    with pytest.raises(IngestError, match=re.escape(msg) + "$"):
        run_layer("oil-fields", from_file=path, conn=tiny_extent)


def test_i5_geojson_missing_file(tiny_extent, monkeypatch, tmp_path):
    monkeypatch.setenv("ARCH1_TEST_DSN", require_dsn())
    path = tmp_path / "nope.geojson"
    msg = f"INGEST: oil-fields geojson file missing: {path}"
    with pytest.raises(IngestError, match=re.escape(msg) + "$"):
        run_layer("oil-fields", from_file=path, conn=tiny_extent)
