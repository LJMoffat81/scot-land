"""M6b-tiles AMENDMENT-1: runnable loader, precondition, dissolve-before-tile.

Synthetic fixtures only. No national GPKG in git. No assertion loosened.
Exact ``REFUSED`` strings from AMENDMENT-1 §6.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest
import yaml
from shapely.geometry import box
from shapely import wkb as shapely_wkb

from etl import check_cpm2016 as pre
from etl import ingest_cpm2016 as ingest
from etl import run_layer as rl
from etl.build_scotland_extent import load_only
from etl.check_cpm2016 import check_cpm2016_clipped, check_cpm2016_raw
from etl.check_dz2011_boundaries import PrecheckError
from etl.ingest_cpm2016 import Cpm2016IngestError, load_fixture, load_national
from georgist import cpm2016_rules as rules
from layers.registry.loader import load_registry
from tiles import build as tiles_build
from tiles.build import TilesError, _export_geojsonseq

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
STUB = FIXTURES / "cpm2016_importance_stub.geojson"
DISSOLVE_STUB = FIXTURES / "cpm2016_dissolve_stub.geojson"
EXTENT_LAND = FIXTURES / "cpm2016_extent_land.27700.geojson"
REGISTRY = BACKEND / "layers" / "registry"

P_INGEST = "CPM2016-INGEST: REFUSED: "
P_PRE = "CPM2016-PRECHECK: REFUSED: "


def _require_dsn():
    from tests.fixtures.arch2.helpers import require_dsn

    return require_dsn()


def _connect():
    from tests.fixtures.arch2.helpers import connect

    return connect()


def _raises_ingest(message: str):
    return pytest.raises(Cpm2016IngestError, match="^" + re.escape(message) + "$")


def _raises_pre(message: str):
    return pytest.raises(PrecheckError, match="^" + re.escape(message) + "$")


def _load_cpm_extent(conn, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARCH1_TEST_DSN", _require_dsn())
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS ref")
        cur.execute("CREATE SCHEMA IF NOT EXISTS stage")
        cur.execute("CREATE SCHEMA IF NOT EXISTS layers")
        for table in ("extent_buf50_sub", "extent_sub", "extent"):
            cur.execute(f"DROP TABLE IF EXISTS ref.{table} CASCADE")
    gis = tmp_path / "gis"
    gis.mkdir(exist_ok=True)
    dest = gis / "scotland_extent.27700.geojson"
    dest.write_bytes(EXTENT_LAND.read_bytes())
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    (gis / "manifest.csv").write_text(
        f"file,sha256\nscotland_extent.27700.geojson,{sha}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "etl.build_scotland_extent.MANIFEST_PATH", gis / "manifest.csv"
    )
    load_only(dest)


def _drop_cpm(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS carbon_peatland CASCADE")
        for suffix in ("", "_prev", "__new"):
            cur.execute(
                f'DROP TABLE IF EXISTS layers."carbon-peatland{suffix}" CASCADE'
            )
            cur.execute(
                f'DROP TABLE IF EXISTS stage."carbon-peatland{suffix}" CASCADE'
            )


def _write_minimal_gpkg(path: Path, *, layer: str, n: int, srs_id: int = 27700) -> None:
    """Synthetic GPKG for national-path count/CRS tests (not the national zip)."""
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE gpkg_contents ("
            "table_name TEXT, data_type TEXT, identifier TEXT, "
            "description TEXT, last_change TEXT, min_x REAL, min_y REAL, "
            "max_x REAL, max_y REAL, srs_id INTEGER)"
        )
        conn.execute(
            "CREATE TABLE gpkg_geometry_columns ("
            "table_name TEXT, column_name TEXT, geometry_type_name TEXT, "
            "srs_id INTEGER, z INTEGER, m INTEGER)"
        )
        conn.execute(
            f'CREATE TABLE "{layer}" ('
            "id INTEGER PRIMARY KEY, geom BLOB, importance INTEGER)"
        )
        conn.execute(
            "INSERT INTO gpkg_contents (table_name, data_type, srs_id) "
            "VALUES (?, 'features', ?)",
            (layer, srs_id),
        )
        conn.execute(
            "INSERT INTO gpkg_geometry_columns "
            "(table_name, column_name, geometry_type_name, srs_id, z, m) "
            "VALUES (?, 'geom', 'POLYGON', ?, 0, 0)",
            (layer, srs_id),
        )
        # GeoPackageBinary header (empty envelope) + WKB for a tiny square.
        for i in range(n):
            geom = box(260000 + i * 20, 670000, 260010 + i * 20, 670010)
            wkb = shapely_wkb.dumps(geom, hex=False)
            # GP magic + version + flags(envelope=0) + srs_id(le) + wkb
            header = bytearray(b"GP\x00\x00")
            header += (27700).to_bytes(4, "little", signed=True)
            blob = bytes(header) + wkb
            # importance cycles official set so national IMPORTANCE checks pass
            # when count matches; R11 only needs the count mismatch path.
            importance = [-2, -1, 0, 1, 2, 3, 4, 5][i % 8]
            conn.execute(
                f'INSERT INTO "{layer}" (id, geom, importance) VALUES (?, ?, ?)',
                (i + 1, blob, importance),
            )
        conn.commit()
    finally:
        conn.close()


# --- R1–R4 / R11 national refusals (no write) ---------------------------------


def test_r1_national_refuses_when_sha_pin_none(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        ingest.ensure_table(conn)
        before = ingest._row_count(conn)
        monkeypatch.setattr(rules, "GPKG_SHA256", None)
        monkeypatch.setattr(ingest, "GPKG_SHA256", None)
        monkeypatch.setattr(rules, "GPKG_LAYER", "layer")
        monkeypatch.setattr(ingest, "GPKG_LAYER", "layer")
        monkeypatch.setattr(rules, "GPKG_FEATURE_COUNT", 8)
        monkeypatch.setattr(ingest, "GPKG_FEATURE_COUNT", 8)
        msg = f"{P_INGEST}GPKG_SHA256: expected pinned sha256, got None"
        with _raises_ingest(msg):
            load_national(conn, source=tmp_path / "missing.gpkg")
        assert ingest._row_count(conn) == before
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r2_national_refuses_when_layer_pin_none(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        ingest.ensure_table(conn)
        before = ingest._row_count(conn)
        monkeypatch.setattr(ingest, "GPKG_SHA256", "abc")
        monkeypatch.setattr(ingest, "GPKG_LAYER", None)
        monkeypatch.setattr(ingest, "GPKG_FEATURE_COUNT", 8)
        msg = f"{P_INGEST}GPKG_LAYER: expected pinned inner layer name, got None"
        with _raises_ingest(msg):
            load_national(conn, source=tmp_path / "missing.gpkg")
        assert ingest._row_count(conn) == before
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r3_national_refuses_when_count_pin_none(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        ingest.ensure_table(conn)
        before = ingest._row_count(conn)
        monkeypatch.setattr(ingest, "GPKG_SHA256", "abc")
        monkeypatch.setattr(ingest, "GPKG_LAYER", "layer")
        monkeypatch.setattr(ingest, "GPKG_FEATURE_COUNT", None)
        msg = f"{P_INGEST}GPKG_FEATURE_COUNT: expected pinned integer, got None"
        with _raises_ingest(msg):
            load_national(conn, source=tmp_path / "missing.gpkg")
        assert ingest._row_count(conn) == before
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r4_national_refuses_when_source_absent(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        ingest.ensure_table(conn)
        before = ingest._row_count(conn)
        monkeypatch.setattr(ingest, "GPKG_SHA256", "abc")
        monkeypatch.setattr(ingest, "GPKG_LAYER", "layer")
        monkeypatch.setattr(ingest, "GPKG_FEATURE_COUNT", 8)
        msg = f"{P_INGEST}source: expected pinned GPKG at data/external/, got absent"
        with _raises_ingest(msg):
            load_national(conn, source=tmp_path / "nope.gpkg")
        assert ingest._row_count(conn) == before
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r11_national_refuses_count_mismatch_before_insert(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        ingest.ensure_table(conn)
        before = ingest._row_count(conn)
        before_max = ingest._max_feature_id(conn)
        gpkg = tmp_path / "tiny.gpkg"
        _write_minimal_gpkg(gpkg, layer="cpm", n=3)
        sha = hashlib.sha256(gpkg.read_bytes()).hexdigest()
        monkeypatch.setattr(ingest, "GPKG_SHA256", sha)
        monkeypatch.setattr(ingest, "GPKG_LAYER", "cpm")
        monkeypatch.setattr(ingest, "GPKG_FEATURE_COUNT", 8)  # pin ≠ 3
        msg = f"{P_INGEST}GPKG_FEATURE_COUNT: expected 8, got 3"
        with _raises_ingest(msg):
            load_national(conn, source=gpkg)
        assert ingest._row_count(conn) == before
        assert ingest._max_feature_id(conn) == before_max
    finally:
        _drop_cpm(conn)
        conn.close()


# --- R5 / R6 fixture refusals -------------------------------------------------


def test_r5_fixture_refuses_non_27700_crs(tmp_path):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        ingest.ensure_table(conn)
        before = ingest._row_count(conn)
        bad = json.loads(STUB.read_text(encoding="utf-8"))
        bad["crs"]["properties"]["name"] = "EPSG:4326"
        path = tmp_path / "bad_crs.geojson"
        path.write_text(json.dumps(bad), encoding="utf-8")
        msg = f"{P_INGEST}CRS: expected EPSG:27700, got EPSG:4326"
        with _raises_ingest(msg):
            load_fixture(conn, path=path)
        assert ingest._row_count(conn) == before
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r6_fixture_refuses_out_of_domain_importance(tmp_path):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        ingest.ensure_table(conn)
        before = ingest._row_count(conn)
        bad = json.loads(STUB.read_text(encoding="utf-8"))
        bad["features"][0]["properties"]["IMPORTANCE"] = 6
        path = tmp_path / "bad_class.geojson"
        path.write_text(json.dumps(bad), encoding="utf-8")
        msg = (
            f"{P_INGEST}IMPORTANCE 6 is outside the official class set "
            "[-2, -1, 0, 1, 2, 3, 4, 5]"
        )
        with _raises_ingest(msg):
            load_fixture(conn, path=path)
        assert ingest._row_count(conn) == before
    finally:
        _drop_cpm(conn)
        conn.close()


# --- P1 / P2 positive fixture path -------------------------------------------


def test_p1_fixture_loads_eight_classes():
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        n = load_fixture(conn)
        assert n == 8
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT ST_SRID(geom) FROM carbon_peatland"
            )
            assert [int(r[0]) for r in cur.fetchall()] == [27700]
            cur.execute(
                "SELECT importance FROM carbon_peatland ORDER BY importance"
            )
            assert [int(r[0]) for r in cur.fetchall()] == [
                -2,
                -1,
                0,
                1,
                2,
                3,
                4,
                5,
            ]
    finally:
        _drop_cpm(conn)
        conn.close()


def test_p2_run_layer_clip_with_injected_raw_count(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        _load_cpm_extent(conn, monkeypatch, tmp_path)
        load_fixture(conn)
        monkeypatch.setattr(pre, "GPKG_FEATURE_COUNT", 8)
        monkeypatch.setattr(rules, "GPKG_FEATURE_COUNT", 8)
        monkeypatch.setenv("LAYER_RECEIPT_DIR", str(tmp_path / "receipts"))
        receipt = rl.run_layer("carbon-peatland", conn=conn)
        assert receipt["before"] == 8
        # after may differ from before under clip_keep_all: false
        assert receipt["after"] >= 1
        assert receipt["outside"] == 0
        check_cpm2016_clipped(conn)
        with conn.cursor() as cur:
            cur.execute(
                'SELECT DISTINCT ST_SRID(geom) FROM layers."carbon-peatland"'
            )
            assert [int(r[0]) for r in cur.fetchall()] == [27700]
            cur.execute(
                """
                SELECT (props->>'importance')::int
                FROM layers."carbon-peatland"
                ORDER BY 1
                """
            )
            codes = [int(r[0]) for r in cur.fetchall()]
            assert set(codes) <= set(range(-2, 6))
            assert 1 in codes and 2 in codes
    finally:
        _drop_cpm(conn)
        conn.close()


# --- R7 / R8 / R10 precheck --------------------------------------------------


def test_r7_raw_refuses_wrong_srid(monkeypatch):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        load_fixture(conn)
        with conn.cursor() as cur:
            # Column is typed MultiPolygon,27700 — widen then retag SRID.
            cur.execute(
                "ALTER TABLE carbon_peatland "
                "ALTER COLUMN geom TYPE geometry USING geom"
            )
            cur.execute(
                "UPDATE carbon_peatland SET geom = ST_SetSRID(geom, 4326)"
            )
        monkeypatch.setattr(pre, "GPKG_FEATURE_COUNT", 8)
        msg = f"{P_PRE}SRID: expected 27700, got 4326"
        with _raises_pre(msg):
            check_cpm2016_raw(conn)
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r8_raw_refuses_missing_class_1_or_2(monkeypatch):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        load_fixture(conn)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM carbon_peatland WHERE importance IN (1, 2)")
            cur.execute("SELECT count(*) FROM carbon_peatland")
            n = int(cur.fetchone()[0])
        monkeypatch.setattr(pre, "GPKG_FEATURE_COUNT", n)
        # actual present classes after delete
        with conn.cursor() as cur:
            cur.execute(
                "SELECT importance FROM carbon_peatland ORDER BY importance"
            )
            present = [int(r[0]) for r in cur.fetchall()]
        msg = (
            f"{P_PRE}classes 1 and 2: expected both present, got {present}"
        )
        with _raises_pre(msg):
            check_cpm2016_raw(conn)
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r10_raw_refuses_null_importance(monkeypatch):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        load_fixture(conn)
        with conn.cursor() as cur:
            # Bypass NOT NULL for the NULL-importance mutant path.
            cur.execute(
                "ALTER TABLE carbon_peatland ALTER COLUMN importance DROP NOT NULL"
            )
            cur.execute(
                "UPDATE carbon_peatland SET importance = NULL "
                "WHERE importance = 0"
            )
        monkeypatch.setattr(pre, "GPKG_FEATURE_COUNT", 8)
        msg = (
            f"{P_PRE}IMPORTANCE: expected integer code in "
            "[-2, -1, 0, 1, 2, 3, 4, 5], got None"
        )
        with _raises_pre(msg):
            check_cpm2016_raw(conn)
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r9_direct_tile_refuses_when_clipped_checks_fail(
    monkeypatch, tmp_path
):
    _require_dsn()
    conn = _connect()
    tippe_calls: list[object] = []
    try:
        _drop_cpm(conn)
        _load_cpm_extent(conn, monkeypatch, tmp_path)
        load_fixture(conn)
        monkeypatch.setattr(pre, "GPKG_FEATURE_COUNT", 8)
        monkeypatch.setenv("LAYER_RECEIPT_DIR", str(tmp_path / "receipts"))
        rl.run_layer("carbon-peatland", conn=conn)
        # Break clipped importance so build_tileset refuses before tippecanoe.
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE layers."carbon-peatland"
                SET props = props - 'importance'
                WHERE (props->>'importance')::int = 0
                """
            )
        tiles_root = tmp_path / "tiles"
        tiles_root.mkdir()
        storage_yaml = tmp_path / "storage.yaml"
        storage_yaml.write_text(
            "storage: local\nroot_env: TILES_DIR\nkeep_versions: 2\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TILES_DIR", str(tiles_root))
        # Fixture mode skips pin gate so R9 still exercises clipped checker.
        monkeypatch.setenv("CPM2016_ALLOW_FIXTURE_TILES", "1")
        monkeypatch.setenv(
            "CPM2016_PRODUCTION_TILES_ROOT", str(tmp_path / "prod_tiles")
        )
        (tmp_path / "prod_tiles").mkdir()
        monkeypatch.setattr(
            tiles_build,
            "_run_tippecanoe",
            lambda **kwargs: tippe_calls.append(kwargs) or (_ for _ in ()).throw(
                AssertionError("tippecanoe must not start")
            ),
        )
        with pytest.raises(
            TilesError,
            match=r"^TILES: carbon-peatland: CPM2016-PRECHECK: REFUSED:",
        ):
            tiles_build.build_tileset(
                "carbon-peatland", conn=conn, storage_path=storage_yaml
            )
        assert tippe_calls == []
        assert list(tiles_root.glob("*.pmtiles")) == []
    finally:
        _drop_cpm(conn)
        conn.close()


# --- P3 dissolve export ------------------------------------------------------


def test_p3_dissolve_export_merges_same_class_keeps_live_rows(
    monkeypatch, tmp_path
):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        _load_cpm_extent(conn, monkeypatch, tmp_path)
        n = load_fixture(conn, path=DISSOLVE_STUB)
        assert n == 3
        monkeypatch.setattr(pre, "GPKG_FEATURE_COUNT", 3)
        monkeypatch.setenv("LAYER_RECEIPT_DIR", str(tmp_path / "receipts"))
        rl.run_layer("carbon-peatland", conn=conn)
        with conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM layers."carbon-peatland"')
            live = int(cur.fetchone()[0])
        assert live == 3
        out = tmp_path / "dissolved.geojsonl"
        exported = _export_geojsonseq(
            conn,
            "carbon-peatland",
            keep_fields=["importance"],
            precision_dp=6,
            dest=out,
            simplify_m=10.0,
            dissolve_by="importance",
        )
        assert exported == 2
        rows = [
            json.loads(line)
            for line in out.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 2
        keys = sorted(int(r["properties"]["importance"]) for r in rows)
        assert keys == [1, 2]
        for row in rows:
            assert set(row["properties"]) == {"importance"}
            assert "feature_id" not in row["properties"]
        with conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM layers."carbon-peatland"')
            assert int(cur.fetchone()[0]) == 3
    finally:
        _drop_cpm(conn)
        conn.close()


# --- registration / yaml / mutants-as-tests ----------------------------------


def test_preconditions_registers_carbon_peatland():
    assert "carbon-peatland" in rl.PRECONDITIONS
    assert rl.PRECONDITIONS["carbon-peatland"] is check_cpm2016_raw


def test_yaml_sets_dissolve_by_importance():
    raw = yaml.safe_load(
        (REGISTRY / "carbon-peatland.yaml").read_text(encoding="utf-8")
    )
    assert raw["tiles"]["dissolve_by"] == "importance"
    assert "importance" in raw["keep_fields"]
    assert raw.get("coming") is not False  # layer 8 stays coming via frontend
    entries = load_registry(REGISTRY)
    assert entries["carbon-peatland"].raw["tiles"]["dissolve_by"] == "importance"


def test_p5_no_frontend_layer_still_coming():
    # Frontend map-layer registry is out of this PR; yaml has no coming key
    # (coming lives on frontend switch "8"). Guard: no frontend files in this
    # amendment and carbon-peatland remains a backend tiles admission only.
    from layers.registry.loader import REGISTRY_DIR

    text = (REGISTRY_DIR / "carbon-peatland.yaml").read_text(encoding="utf-8")
    assert "dissolve_by: importance" in text
    # Attempt-1 frontend non-touch still holds: no new frontend path here.
    assert not (BACKEND.parent / "frontend" / "lib" / "cpm2016.ts").exists()


def test_national_pins_still_pending():
    assert rules.GPKG_SHA256 is None
    assert rules.GPKG_LAYER is None
    assert rules.GPKG_FEATURE_COUNT is None
