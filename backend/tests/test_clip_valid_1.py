"""CLIP-VALID-1: make polygons valid before clip (V1–V7)."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pytest

from etl.run_layer import (
    SQL_DIR,
    CheckError,
    IngestError,
    _ensure_helpers,
    _load_stage,
    _make_valid,
    run_layer,
)

_HELPERS_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "arch2" / "helpers.py"
)
_spec = importlib.util.spec_from_file_location("arch2_helpers_cv1", _HELPERS_PATH)
assert _spec and _spec.loader
_helpers = importlib.util.module_from_spec(_spec)
sys.modules["arch2_helpers_cv1"] = _helpers
_spec.loader.exec_module(_helpers)

connect = _helpers.connect
drop_dz_boundaries = _helpers.drop_dz_boundaries
drop_layer_tables = _helpers.drop_layer_tables
load_tiny_extent = _helpers.load_tiny_extent
make_entry = _helpers.make_entry
require_dsn = _helpers.require_dsn
seed_dz_grid = _helpers.seed_dz_grid

BOWTIE_WKT = (
    "POLYGON((3000 9500,4000 10500,4000 9500,3000 10500,3000 9500))"
)
COLLAPSED_WKT = "POLYGON((3000 3000,4000 4000,3000 3000,3000 3000))"
SPIKE_WKT = (
    "POLYGON((6000 6000,7000 6000,7000 7000,6500 7000,"
    "6500 7500,6500 7000,6000 7000,6000 6000))"
)
OUTSIDE_WKT = (
    "POLYGON((40000 40000,41000 40000,41000 41000,40000 41000,40000 40000))"
)

INGEST_S01013492 = (
    "INGEST: dz2022: 1 geometries invalid or empty after ST_MakeValid: "
    "S01013492"
)


@pytest.fixture
def conn():
    require_dsn()
    connection = connect()
    yield connection
    connection.close()


@pytest.fixture
def tiny_extent(conn, monkeypatch, tmp_path):
    drop_layer_tables(
        conn,
        "dz2022",
        "oil-fields",
        "cv1-poly",
        "cv1-line",
        "cv1-point",
    )
    drop_dz_boundaries(conn)
    load_tiny_extent(conn, monkeypatch, tmp_path)
    seed_dz_grid(conn)
    monkeypatch.setenv("ARCH1_TEST_DSN", require_dsn())
    monkeypatch.setattr(
        "etl.run_layer.RECEIPT_DIR", tmp_path / "receipts"
    )
    yield conn
    drop_layer_tables(
        conn,
        "dz2022",
        "oil-fields",
        "cv1-poly",
        "cv1-line",
        "cv1-point",
    )
    drop_dz_boundaries(conn)


def _insert_dz(conn, code: str, name: str, wkt: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.dz_boundaries (code, name, vintage, geom)
            VALUES (
              %s, %s, 2022,
              ST_Multi(ST_GeomFromText(%s, 27700))
            )
            """,
            (code, name, wkt),
        )


def _layer_count(conn, layer_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM layers."{layer_id}"')
        return int(cur.fetchone()[0])


def _table_exists(conn, schema: str, name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema=%s AND table_name=%s
            )
            """,
            (schema, name),
        )
        return bool(cur.fetchone()[0])


def _stage_wkb(conn, layer_id: str) -> dict[str, bytes]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT feature_id, ST_AsBinary(geom)
            FROM stage."{layer_id}"
            ORDER BY feature_id
            """
        )
        return {str(fid): bytes(wkb) for fid, wkb in cur.fetchall()}


def _geojson_27700(features: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::27700"},
        },
        "features": features,
    }


def _write_geojson(path: Path, features: list[dict]) -> Path:
    path.write_text(json.dumps(_geojson_27700(features)), encoding="utf-8")
    return path


def _install_registry(monkeypatch, *entries) -> None:
    mapping = {e.id: e for e in entries}
    monkeypatch.setattr("etl.run_layer.registry", lambda: mapping)


def test_v1_bowtie_repaired_layer_builds(tiny_extent, monkeypatch):
    _insert_dz(tiny_extent, "S01013492", "bowtie", BOWTIE_WKT)
    receipt = run_layer("dz2022", conn=tiny_extent)
    assert receipt["after"] == receipt["before"] == 11
    assert receipt["outside"] == 0
    with tiny_extent.cursor() as cur:
        cur.execute(
            """
            SELECT ST_IsValid(geom), GeometryType(geom)
            FROM layers."dz2022"
            WHERE feature_id = 'S01013492'
            """
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] is True
    assert row[1] == "MULTIPOLYGON"


def test_v2_empty_after_repair_refused(tiny_extent, monkeypatch):
    run_layer("dz2022", conn=tiny_extent)
    live_before = _layer_count(tiny_extent, "dz2022")
    assert live_before == 10
    _insert_dz(tiny_extent, "S01013492", "collapsed", COLLAPSED_WKT)
    with pytest.raises(IngestError) as excinfo:
        run_layer("dz2022", conn=tiny_extent)
    assert str(excinfo.value) == INGEST_S01013492
    assert _layer_count(tiny_extent, "dz2022") == live_before
    assert not _table_exists(tiny_extent, "layers", "dz2022__new")


def test_v2b_still_invalid_after_repair_refused(
    tiny_extent, monkeypatch, tmp_path
):
    sql_dir = tmp_path / "sql"
    shutil.copytree(SQL_DIR, sql_dir)
    (sql_dir / "make_valid.sql").write_text(
        "SELECT NULL::text AS feature_id WHERE FALSE;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("etl.run_layer.SQL_DIR", sql_dir)
    _insert_dz(tiny_extent, "S01013492", "bowtie", BOWTIE_WKT)
    with pytest.raises(IngestError) as excinfo:
        run_layer("dz2022", conn=tiny_extent)
    assert str(excinfo.value) == INGEST_S01013492


def test_v3_collection_extracted_to_polygon(tiny_extent, monkeypatch):
    _insert_dz(tiny_extent, "S01013492", "spike", SPIKE_WKT)
    receipt = run_layer("dz2022", conn=tiny_extent)
    assert receipt["after"] == 11
    with tiny_extent.cursor() as cur:
        cur.execute(
            """
            SELECT GeometryType(geom), ST_NumGeometries(geom),
                   round(ST_Area(geom))
            FROM layers."dz2022"
            WHERE feature_id = 'S01013492'
            """
        )
        gtype, ngeoms, area = cur.fetchone()
    assert gtype == "MULTIPOLYGON"
    assert int(ngeoms) == 1
    assert int(area) == 1_000_000


def test_v4_repaired_count_recorded(tiny_extent, monkeypatch, tmp_path):
    receipt_dir = tmp_path / "receipts"
    monkeypatch.setattr("etl.run_layer.RECEIPT_DIR", receipt_dir)
    _insert_dz(tiny_extent, "S01013492", "bowtie", BOWTIE_WKT)
    _insert_dz(tiny_extent, "S01013493", "spike", SPIKE_WKT)
    receipt = run_layer("dz2022", conn=tiny_extent)
    assert receipt["repaired"] == 2
    assert receipt["repaired_ids"] == ["S01013492", "S01013493"]
    written = json.loads(
        (receipt_dir / "dz2022.receipt.json").read_text(encoding="utf-8")
    )
    assert written["repaired"] == 2
    assert written["repaired_ids"] == ["S01013492", "S01013493"]

    drop_dz_boundaries(tiny_extent)
    seed_dz_grid(tiny_extent)
    clean = run_layer("dz2022", conn=tiny_extent)
    assert clean["repaired"] == 0
    assert clean["repaired_ids"] == []


def test_v5_valid_input_byte_identical(tiny_extent, monkeypatch, tmp_path):
    entry = make_entry(
        "cv1-poly",
        clip="land",
        unit="none",
        source={"type": "geojson_file", "url": "unused"},
    )
    features = [
        {
            "type": "Feature",
            "properties": {"id": "plain", "name": "plain"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [1500, 1500],
                        [2500, 1500],
                        [2500, 2500],
                        [1500, 2500],
                        [1500, 1500],
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {"id": "multi", "name": "multi"},
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [3500, 1500],
                            [4500, 1500],
                            [4500, 2500],
                            [3500, 2500],
                            [3500, 1500],
                        ]
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {"id": "bowtie", "name": "bowtie"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [3000, 9500],
                        [4000, 10500],
                        [4000, 9500],
                        [3000, 10500],
                        [3000, 9500],
                    ]
                ],
            },
        },
    ]
    _ensure_helpers(tiny_extent)
    _load_stage(
        tiny_extent,
        "cv1-poly",
        features,
        as_of=date(2026, 10, 22),
        dataset_version="cv1-poly@test",
        method="source",
        already_27700=True,
    )
    before = _stage_wkb(tiny_extent, "cv1-poly")
    repaired, repaired_ids = _make_valid(tiny_extent, "cv1-poly", entry)
    after = _stage_wkb(tiny_extent, "cv1-poly")
    assert repaired == 1
    assert repaired_ids == ["bowtie"]
    assert after["plain"] == before["plain"]
    assert after["multi"] == before["multi"]
    assert after["bowtie"] != before["bowtie"]


def test_v6_point_and_line_unaffected(tiny_extent, monkeypatch, tmp_path):
    line_entry = make_entry(
        "cv1-line",
        geometry="line",
        clip="land",
        unit="none",
        source={"type": "geojson_file", "url": "unused"},
        keep_fields=["name"],
    )
    point_entry = make_entry(
        "cv1-point",
        geometry="point",
        clip="land",
        unit="point",
        source={"type": "geojson_file", "url": "unused"},
        keep_fields=["name"],
    )
    _install_registry(monkeypatch, line_entry, point_entry)

    line_path = _write_geojson(
        tmp_path / "lines.geojson",
        [
            {
                "type": "Feature",
                "properties": {"id": "degen", "name": "degen"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[5000, 5000], [5000, 5000]],
                },
            },
            {
                "type": "Feature",
                "properties": {"id": "ok", "name": "ok"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[1000, 1000], [2000, 1000]],
                },
            },
        ],
    )
    point_path = _write_geojson(
        tmp_path / "points.geojson",
        [
            {
                "type": "Feature",
                "properties": {"id": "p1", "name": "p1"},
                "geometry": {"type": "Point", "coordinates": [1500, 1500]},
            },
            {
                "type": "Feature",
                "properties": {"id": "p2", "name": "p2"},
                "geometry": {"type": "Point", "coordinates": [2500, 2500]},
            },
        ],
    )

    # Stage WKB identity for both layers via _make_valid (no-op for non-polygon).
    for layer_id, path, entry, n_feats in (
        ("cv1-line", line_path, line_entry, 2),
        ("cv1-point", point_path, point_entry, 2),
    ):
        collection = json.loads(path.read_text(encoding="utf-8"))
        _ensure_helpers(tiny_extent)
        _load_stage(
            tiny_extent,
            layer_id,
            list(collection["features"]),
            as_of=date(2026, 10, 22),
            dataset_version=f"{layer_id}@test",
            method="source",
            already_27700=True,
        )
        before = _stage_wkb(tiny_extent, layer_id)
        repaired, repaired_ids = _make_valid(tiny_extent, layer_id, entry)
        after = _stage_wkb(tiny_extent, layer_id)
        assert repaired == 0
        assert repaired_ids == []
        assert after == before
        assert len(before) == n_feats

    line_receipt = run_layer(
        "cv1-line", from_file=line_path, conn=tiny_extent
    )
    point_receipt = run_layer(
        "cv1-point", from_file=point_path, conn=tiny_extent
    )
    assert line_receipt["repaired"] == 0
    assert line_receipt["repaired_ids"] == []
    assert point_receipt["repaired"] == 0
    assert point_receipt["repaired_ids"] == []
    with tiny_extent.cursor() as cur:
        cur.execute(
            """
            SELECT feature_id FROM layers."cv1-line"
            ORDER BY feature_id
            """
        )
        line_ids = [r[0] for r in cur.fetchall()]
    assert "degen" in line_ids


def test_v7_clip_keep_all_counts(tiny_extent, monkeypatch):
    msg = "CHECK: dz2022: clip kept 10 of 11 features (clip_keep_all)"
    run_layer("dz2022", conn=tiny_extent)
    live_count = _layer_count(tiny_extent, "dz2022")
    assert live_count == 10
    _insert_dz(tiny_extent, "S01013494", "outside", OUTSIDE_WKT)
    with pytest.raises(CheckError) as excinfo:
        run_layer("dz2022", conn=tiny_extent)
    assert str(excinfo.value) == msg
    assert _layer_count(tiny_extent, "dz2022") == live_count
    assert not _table_exists(tiny_extent, "layers", "dz2022__new")
