"""M6b-tiles AMENDMENT-2: outside in clipped checker + production tile gate.

Keeps AMENDMENT-1 assertions. Synthetic fixtures only. Exact R12–R19 strings.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from etl import check_cpm2016 as pre
from etl import cpm2016_provenance as prov
from etl import ingest_cpm2016 as ingest
from etl import run_layer as rl
from etl.build_scotland_extent import load_only
from etl.check_cpm2016 import check_cpm2016_clipped
from etl.check_dz2011_boundaries import PrecheckError
from etl.ingest_cpm2016 import load_fixture, load_national
from georgist import cpm2016_rules as rules
from tiles import build as tiles_build
from tiles.build import TilesError

FIXTURES = Path(__file__).resolve().parent / "fixtures"
STUB = FIXTURES / "cpm2016_importance_stub.geojson"
EXTENT_LAND = FIXTURES / "cpm2016_extent_land.27700.geojson"
DISSOLVE_STUB = FIXTURES / "cpm2016_dissolve_stub.geojson"

P_PRE = "CPM2016-PRECHECK: REFUSED: "
P_TILE = "TILES: carbon-peatland: "


def _require_dsn():
    from tests.fixtures.arch2.helpers import require_dsn

    return require_dsn()


def _connect():
    from tests.fixtures.arch2.helpers import connect

    return connect()


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


def _storage(tmp_path: Path, tiles_name: str = "tiles"):
    tiles_root = tmp_path / tiles_name
    tiles_root.mkdir(exist_ok=True)
    storage_yaml = tmp_path / f"{tiles_name}.storage.yaml"
    storage_yaml.write_text(
        "storage: local\nroot_env: TILES_DIR\nkeep_versions: 2\n",
        encoding="utf-8",
    )
    return tiles_root, storage_yaml


def _spy_tippe(monkeypatch):
    calls: list[object] = []

    def _boom(**kwargs):
        calls.append(kwargs)
        raise AssertionError("tippecanoe must not start")

    monkeypatch.setattr(tiles_build, "_run_tippecanoe", _boom)
    return calls


def _set_pins(monkeypatch, *, sha="abc", layer="cpm", count=8):
    monkeypatch.setattr(rules, "GPKG_SHA256", sha)
    monkeypatch.setattr(rules, "GPKG_LAYER", layer)
    monkeypatch.setattr(rules, "GPKG_FEATURE_COUNT", count)
    monkeypatch.setattr(ingest, "GPKG_SHA256", sha)
    monkeypatch.setattr(ingest, "GPKG_LAYER", layer)
    monkeypatch.setattr(ingest, "GPKG_FEATURE_COUNT", count)
    monkeypatch.setattr(pre, "GPKG_FEATURE_COUNT", count)


# --- R12 outside -------------------------------------------------------------


def test_r12_outside_refuses_direct_tileset(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    tippe = _spy_tippe(monkeypatch)
    try:
        _drop_cpm(conn)
        _load_cpm_extent(conn, monkeypatch, tmp_path)
        load_fixture(conn)
        monkeypatch.setattr(pre, "GPKG_FEATURE_COUNT", 8)
        monkeypatch.setenv("LAYER_RECEIPT_DIR", str(tmp_path / "receipts"))
        rl.run_layer("carbon-peatland", conn=conn)
        # Move one feature far outside the stub extent (259000–264000).
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE layers."carbon-peatland"
                SET geom = ST_SetSRID(
                  ST_Multi(ST_GeomFromText(
                    'POLYGON((100 100,200 100,200 200,100 200,100 100))'
                  )),
                  27700
                )
                WHERE (props->>'importance')::int = 3
                """
            )
        tiles_root, storage_yaml = _storage(tmp_path)
        monkeypatch.setenv("TILES_DIR", str(tiles_root))
        monkeypatch.setenv("CPM2016_ALLOW_FIXTURE_TILES", "1")
        monkeypatch.setenv(
            "CPM2016_PRODUCTION_TILES_ROOT", str(tmp_path / "prod")
        )
        (tmp_path / "prod").mkdir()
        msg = f"{P_TILE}{P_PRE}outside: expected 0, got 1"
        with pytest.raises(TilesError, match="^" + re.escape(msg) + "$"):
            tiles_build.build_tileset(
                "carbon-peatland", conn=conn, storage_path=storage_yaml
            )
        assert tippe == []
        assert list(tiles_root.glob("*.pmtiles")) == []
        assert list((tmp_path / "prod").glob("**/*")) == []
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r12_outside_still_runs_in_fixture_mode(monkeypatch, tmp_path):
    """M-BYPASS-SKIPS-OUTSIDE: fixture mode must not skip outside."""
    test_r12_outside_refuses_direct_tileset(monkeypatch, tmp_path)


# --- R13–R17 production pin/provenance gates ---------------------------------


def _clipped_ready(monkeypatch, tmp_path, conn):
    _load_cpm_extent(conn, monkeypatch, tmp_path)
    monkeypatch.setenv("LAYER_RECEIPT_DIR", str(tmp_path / "receipts"))
    load_fixture(conn)
    monkeypatch.setattr(pre, "GPKG_FEATURE_COUNT", 8)
    rl.run_layer("carbon-peatland", conn=conn)


def test_r13_production_refuses_sha_none(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    tippe = _spy_tippe(monkeypatch)
    try:
        _drop_cpm(conn)
        _clipped_ready(monkeypatch, tmp_path, conn)
        _set_pins(monkeypatch, sha="abc", layer="cpm", count=8)
        monkeypatch.setattr(rules, "GPKG_SHA256", None)
        tiles_root, storage_yaml = _storage(tmp_path)
        monkeypatch.setenv("TILES_DIR", str(tiles_root))
        monkeypatch.delenv("CPM2016_ALLOW_FIXTURE_TILES", raising=False)
        # Write a fake national provenance so only SHA is the trigger.
        prov.write_national_provenance(
            conn, rows=8, gpkg_sha256="abc", gpkg_layer="cpm", gpkg_feature_count=8
        )
        msg = (
            f"{P_TILE}CPM2016-INGEST: REFUSED: GPKG_SHA256: "
            "expected pinned sha256, got None"
        )
        with pytest.raises(TilesError, match="^" + re.escape(msg) + "$"):
            tiles_build.build_tileset(
                "carbon-peatland", conn=conn, storage_path=storage_yaml
            )
        assert tippe == []
        assert list(tiles_root.glob("*.pmtiles")) == []
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r14_production_refuses_layer_none(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    tippe = _spy_tippe(monkeypatch)
    try:
        _drop_cpm(conn)
        _clipped_ready(monkeypatch, tmp_path, conn)
        _set_pins(monkeypatch)
        monkeypatch.setattr(rules, "GPKG_LAYER", None)
        tiles_root, storage_yaml = _storage(tmp_path)
        monkeypatch.setenv("TILES_DIR", str(tiles_root))
        monkeypatch.delenv("CPM2016_ALLOW_FIXTURE_TILES", raising=False)
        msg = (
            f"{P_TILE}CPM2016-INGEST: REFUSED: GPKG_LAYER: "
            "expected pinned inner layer name, got None"
        )
        with pytest.raises(TilesError, match="^" + re.escape(msg) + "$"):
            tiles_build.build_tileset(
                "carbon-peatland", conn=conn, storage_path=storage_yaml
            )
        assert tippe == []
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r15_production_refuses_count_none(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    tippe = _spy_tippe(monkeypatch)
    try:
        _drop_cpm(conn)
        _clipped_ready(monkeypatch, tmp_path, conn)
        _set_pins(monkeypatch)
        monkeypatch.setattr(rules, "GPKG_FEATURE_COUNT", None)
        tiles_root, storage_yaml = _storage(tmp_path)
        monkeypatch.setenv("TILES_DIR", str(tiles_root))
        monkeypatch.delenv("CPM2016_ALLOW_FIXTURE_TILES", raising=False)
        msg = (
            f"{P_TILE}CPM2016-INGEST: REFUSED: GPKG_FEATURE_COUNT: "
            "expected pinned integer, got None"
        )
        with pytest.raises(TilesError, match="^" + re.escape(msg) + "$"):
            tiles_build.build_tileset(
                "carbon-peatland", conn=conn, storage_path=storage_yaml
            )
        assert tippe == []
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r16_production_refuses_missing_provenance(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    tippe = _spy_tippe(monkeypatch)
    try:
        _drop_cpm(conn)
        _clipped_ready(monkeypatch, tmp_path, conn)
        _set_pins(monkeypatch)
        # load_fixture wrote path=fixture; delete it so provenance is absent.
        prov.provenance_path().unlink(missing_ok=True)
        tiles_root, storage_yaml = _storage(tmp_path)
        monkeypatch.setenv("TILES_DIR", str(tiles_root))
        monkeypatch.delenv("CPM2016_ALLOW_FIXTURE_TILES", raising=False)
        msg = (
            f"{P_TILE}CPM2016-TILE: REFUSED: provenance: "
            "expected national validated receipt, got absent"
        )
        with pytest.raises(TilesError, match="^" + re.escape(msg) + "$"):
            tiles_build.build_tileset(
                "carbon-peatland", conn=conn, storage_path=storage_yaml
            )
        assert tippe == []
    finally:
        _drop_cpm(conn)
        conn.close()


def test_r17_production_refuses_fixture_provenance(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    tippe = _spy_tippe(monkeypatch)
    try:
        _drop_cpm(conn)
        _clipped_ready(monkeypatch, tmp_path, conn)
        _set_pins(monkeypatch)
        # Fixture load already wrote path=fixture.
        assert prov.read_provenance()["path"] == "fixture"
        tiles_root, storage_yaml = _storage(tmp_path)
        monkeypatch.setenv("TILES_DIR", str(tiles_root))
        monkeypatch.delenv("CPM2016_ALLOW_FIXTURE_TILES", raising=False)
        msg = (
            f"{P_TILE}CPM2016-TILE: REFUSED: provenance: "
            "expected path national, got fixture"
        )
        with pytest.raises(TilesError, match="^" + re.escape(msg) + "$"):
            tiles_build.build_tileset(
                "carbon-peatland", conn=conn, storage_path=storage_yaml
            )
        assert tippe == []
    finally:
        _drop_cpm(conn)
        conn.close()


# --- R18 / P8 fixture confinement --------------------------------------------


def test_r18_fixture_mode_refuses_production_root(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    tippe = _spy_tippe(monkeypatch)
    try:
        _drop_cpm(conn)
        _clipped_ready(monkeypatch, tmp_path, conn)
        prod = tmp_path / "production_tiles"
        prod.mkdir()
        storage_yaml = tmp_path / "prod.storage.yaml"
        storage_yaml.write_text(
            "storage: local\nroot_env: TILES_DIR\nkeep_versions: 2\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TILES_DIR", str(prod))
        monkeypatch.setenv("CPM2016_ALLOW_FIXTURE_TILES", "1")
        monkeypatch.setenv("CPM2016_PRODUCTION_TILES_ROOT", str(prod))
        msg = (
            f"{P_TILE}CPM2016-TILE: REFUSED: fixture mode: "
            "production tiles root or publisher forbidden"
        )
        with pytest.raises(TilesError, match="^" + re.escape(msg) + "$"):
            tiles_build.build_tileset(
                "carbon-peatland", conn=conn, storage_path=storage_yaml
            )
        assert tippe == []
        assert list(prod.glob("*.pmtiles")) == []
    finally:
        _drop_cpm(conn)
        conn.close()


def _stub_tile_pipeline(monkeypatch, tippe_calls: list | None = None):
    from types import SimpleNamespace

    def _tippe(**kwargs):
        if tippe_calls is not None:
            tippe_calls.append(kwargs)
        Path(kwargs["out_pmtiles"]).write_bytes(b"PM")

    monkeypatch.setattr(tiles_build, "_run_tippecanoe", _tippe)
    monkeypatch.setattr(
        tiles_build,
        "measure_pmtiles",
        lambda *a, **k: SimpleNamespace(
            bytes=10,
            sha256="0" * 64,
            z0_7_bytes=1,
            max_tile_gz_bytes=1,
            max_tile_zoom=0,
            distinct_z5=None,
        ),
    )
    monkeypatch.setattr(tiles_build, "report_culled", lambda *a, **k: None)
    monkeypatch.setattr(tiles_build, "distinct_ids_at_zoom", lambda *a, **k: set())


def test_p8_fixture_tmp_root_allows_export_prod_clean(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    publishes: list[object] = []
    tippe_calls: list[object] = []
    try:
        _drop_cpm(conn)
        _clipped_ready(monkeypatch, tmp_path, conn)
        tiles_root, storage_yaml = _storage(tmp_path, "tmp_tiles")
        prod = tmp_path / "production_tiles"
        prod.mkdir()
        monkeypatch.setenv("TILES_DIR", str(tiles_root))
        monkeypatch.setenv("CPM2016_ALLOW_FIXTURE_TILES", "1")
        monkeypatch.setenv("CPM2016_PRODUCTION_TILES_ROOT", str(prod))
        _stub_tile_pipeline(monkeypatch, tippe_calls)
        real_publish = tiles_build.LocalStorage.publish

        def _wrap_publish(self, tmp, layer_id, version):
            publishes.append((str(self.config.root), layer_id, version))
            return real_publish(self, tmp, layer_id, version)

        monkeypatch.setattr(tiles_build.LocalStorage, "publish", _wrap_publish)
        result = tiles_build.build_tileset(
            "carbon-peatland", conn=conn, storage_path=storage_yaml
        )
        assert result["layer"] == "carbon-peatland"
        assert tippe_calls
        assert publishes and Path(publishes[0][0]).resolve() == tiles_root.resolve()
        assert list(prod.glob("**/*")) == []
        assert prov.read_provenance()["path"] == "fixture"
    finally:
        _drop_cpm(conn)
        conn.close()


# --- R19 stale provenance ----------------------------------------------------


def test_r19_stale_national_after_fixture_replace(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    tippe = _spy_tippe(monkeypatch)
    try:
        _drop_cpm(conn)
        _load_cpm_extent(conn, monkeypatch, tmp_path)
        monkeypatch.setenv("LAYER_RECEIPT_DIR", str(tmp_path / "receipts"))
        _set_pins(monkeypatch, sha="deadbeef", layer="cpm", count=8)
        # Simulate a prior national receipt bound to stub rows.
        load_fixture(conn)
        monkeypatch.setattr(pre, "GPKG_FEATURE_COUNT", 8)
        # Forge national provenance matching pins + current fingerprint.
        path = prov.write_national_provenance(
            conn,
            rows=8,
            gpkg_sha256="deadbeef",
            gpkg_layer="cpm",
            gpkg_feature_count=8,
        )
        rl.run_layer("carbon-peatland", conn=conn)
        # Bind clipped into that forged national receipt.
        receipt = json.loads(prov.layer_receipt_path().read_text(encoding="utf-8"))
        data = json.loads(path.read_text(encoding="utf-8"))
        data["path"] = "national"
        data["clipped_dataset_version"] = receipt["dataset_version"]
        data["raw_fingerprint"] = prov.raw_fingerprint(conn)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        # Replace raw via fixture → must invalidate national and write fixture.
        load_fixture(conn, path=DISSOLVE_STUB)
        monkeypatch.setattr(pre, "GPKG_FEATURE_COUNT", 3)
        monkeypatch.setattr(rules, "GPKG_FEATURE_COUNT", 3)
        rl.run_layer("carbon-peatland", conn=conn)
        assert prov.read_provenance()["path"] == "fixture"

        # Restore pin-matching OLD national JSON without rebinding live table.
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        _set_pins(monkeypatch, sha="deadbeef", layer="cpm", count=8)

        tiles_root, storage_yaml = _storage(tmp_path)
        monkeypatch.setenv("TILES_DIR", str(tiles_root))
        monkeypatch.delenv("CPM2016_ALLOW_FIXTURE_TILES", raising=False)
        msg = (
            f"{P_TILE}CPM2016-TILE: REFUSED: provenance: "
            "expected bound current ingest+clipped receipt, got stale"
        )
        with pytest.raises(TilesError, match="^" + re.escape(msg) + "$"):
            tiles_build.build_tileset(
                "carbon-peatland", conn=conn, storage_path=storage_yaml
            )
        assert tippe == []
        assert list(tiles_root.glob("*.pmtiles")) == []
    finally:
        _drop_cpm(conn)
        conn.close()


# --- P6 / P7 -----------------------------------------------------------------


def test_p6_fixture_mode_export_no_national_provenance(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    try:
        _drop_cpm(conn)
        _clipped_ready(monkeypatch, tmp_path, conn)
        tiles_root, storage_yaml = _storage(tmp_path)
        prod = tmp_path / "production_tiles"
        prod.mkdir()
        monkeypatch.setenv("TILES_DIR", str(tiles_root))
        monkeypatch.setenv("CPM2016_ALLOW_FIXTURE_TILES", "1")
        monkeypatch.setenv("CPM2016_PRODUCTION_TILES_ROOT", str(prod))
        _stub_tile_pipeline(monkeypatch)
        tiles_build.build_tileset(
            "carbon-peatland", conn=conn, storage_path=storage_yaml
        )
        assert prov.read_provenance()["path"] == "fixture"
        assert list(prod.glob("**/*")) == []
    finally:
        _drop_cpm(conn)
        conn.close()


def test_p7_production_gate_passes_with_bound_national(monkeypatch, tmp_path):
    _require_dsn()
    conn = _connect()
    tippe_calls: list[object] = []
    try:
        _drop_cpm(conn)
        _load_cpm_extent(conn, monkeypatch, tmp_path)
        monkeypatch.setenv("LAYER_RECEIPT_DIR", str(tmp_path / "receipts"))
        _set_pins(monkeypatch, sha="cafebabe", layer="cpm", count=8)
        load_fixture(conn)
        # Treat fixture rows as a mocked national ingest receipt.
        prov.write_national_provenance(
            conn,
            rows=8,
            gpkg_sha256="cafebabe",
            gpkg_layer="cpm",
            gpkg_feature_count=8,
        )
        monkeypatch.setattr(pre, "GPKG_FEATURE_COUNT", 8)
        rl.run_layer("carbon-peatland", conn=conn)
        assert prov.read_provenance()["path"] == "national"
        assert prov.read_provenance()["clipped_dataset_version"]

        tiles_root, storage_yaml = _storage(tmp_path)
        monkeypatch.setenv("TILES_DIR", str(tiles_root))
        monkeypatch.delenv("CPM2016_ALLOW_FIXTURE_TILES", raising=False)
        _stub_tile_pipeline(monkeypatch, tippe_calls)
        result = tiles_build.build_tileset(
            "carbon-peatland", conn=conn, storage_path=storage_yaml
        )
        assert result["layer"] == "carbon-peatland"
        assert tippe_calls  # gate passed; tippecanoe stub invoked
    finally:
        _drop_cpm(conn)
        conn.close()
