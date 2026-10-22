"""ARCH-2a-1 tile build tests B-1..B-21."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from layers.registry.loader import LayerEntry
from tiles.build import TilesError, build_all, build_tileset
from tiles.measure import decode_tile_properties, distinct_ids_at_zoom

_HELPERS_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "arch2" / "helpers.py"
)
_spec = importlib.util.spec_from_file_location("arch2_helpers_build", _HELPERS_PATH)
assert _spec and _spec.loader
_helpers = importlib.util.module_from_spec(_spec)
sys.modules["arch2_helpers_build"] = _helpers
_spec.loader.exec_module(_helpers)

ARCH2_BIN = _helpers.ARCH2_BIN
connect = _helpers.connect
dense_features = _helpers.dense_features
drop_layer_tables = _helpers.drop_layer_tables
line_features = _helpers.line_features
make_entry = _helpers.make_entry
pts_close_features = _helpers.pts_close_features
require_dsn = _helpers.require_dsn
seed_layer_table = _helpers.seed_layer_table
square = _helpers.square
write_storage_yaml = _helpers.write_storage_yaml

PYTHON = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)


@pytest.fixture
def conn():
    require_dsn()
    connection = connect()
    yield connection
    connection.close()


@pytest.fixture
def tiles_env(tmp_path, monkeypatch):
    tiles_dir = tmp_path / "tiles"
    tiles_dir.mkdir()
    (tiles_dir / ".tmp").mkdir()
    storage_yaml = write_storage_yaml(tmp_path / "storage.yaml", keep_versions=3)
    monkeypatch.setenv("TILES_DIR", str(tiles_dir))
    monkeypatch.setenv("ARCH1_TEST_DSN", require_dsn())
    return {"dir": tiles_dir, "storage": storage_yaml}


def _install_registry(monkeypatch, *entries: LayerEntry) -> None:
    mapping = {e.id: e for e in entries}
    monkeypatch.setattr("tiles.build.registry", lambda: mapping)


def _raises_tiles(msg: str):
    return pytest.raises(TilesError, match=re.escape(msg) + "$")


def test_b1_unknown_id(monkeypatch):
    _install_registry(monkeypatch)  # empty
    with _raises_tiles("TILES: unknown layer nope"):
        build_tileset("nope")


def test_b2_no_tiles_block(monkeypatch):
    entry = make_entry("x")
    del entry.raw["tiles"]
    _install_registry(monkeypatch, entry)
    with _raises_tiles("TILES: x: no tiles block"):
        build_tileset("x")


def test_b3_gated(conn, tiles_env, monkeypatch):
    # Seed a valid layer so removing the gated check (M12) yields DID NOT RAISE
    # rather than a later STORAGE/layer error.
    seed_layer_table(
        conn,
        "x",
        [
            {
                "id": "1",
                "properties": {"name": "a"},
                "geometry": square(1000, 1000, 500),
            }
        ],
    )
    entry = make_entry("x", gated_by="money_flag")
    _install_registry(monkeypatch, entry)
    with _raises_tiles("TILES: x: gated by money_flag"):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])


def test_b4_layer_not_built(conn, tiles_env, monkeypatch):
    drop_layer_tables(conn, "x")
    _install_registry(monkeypatch, make_entry("x"))
    with _raises_tiles("TILES: x: layer not built"):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])


def test_b5_zero_features(conn, tiles_env, monkeypatch):
    seed_layer_table(conn, "x", [])
    _install_registry(monkeypatch, make_entry("x"))
    with _raises_tiles("TILES: x: 0 features"):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])


def test_b6_mixed_dataset_version(conn, tiles_env, monkeypatch):
    feats = [
        {
            "id": "1",
            "properties": {"name": "a"},
            "geometry": square(1000, 1000, 100),
            "dataset_version": "x@2026-10-22-aaaaaaaa",
        },
        {
            "id": "2",
            "properties": {"name": "b"},
            "geometry": square(2000, 2000, 100),
            "dataset_version": "x@2026-10-22-bbbbbbbb",
        },
    ]
    seed_layer_table(conn, "x", feats)
    _install_registry(monkeypatch, make_entry("x"))
    with _raises_tiles("TILES: x: mixed dataset_version"):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])


def test_b7_keep_field_case(conn, tiles_env, monkeypatch):
    feats = [
        {
            "id": "1",
            "properties": {"FIELDNAME": "Forties"},
            "geometry": square(1000, 1000, 100),
        }
    ]
    seed_layer_table(conn, "x", feats)
    entry = make_entry("x", keep_fields=["fieldname"])
    _install_registry(monkeypatch, entry)
    with _raises_tiles(
        "TILES: x: keep_field fieldname not in layer properties"
    ):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])


def test_b8_tippecanoe_missing(conn, tiles_env, monkeypatch, tmp_path):
    feats = [
        {
            "id": "1",
            "properties": {"name": "a"},
            "geometry": square(1000, 1000, 100),
        }
    ]
    seed_layer_table(conn, "x", feats)
    _install_registry(monkeypatch, make_entry("x"))
    empty = tmp_path / "empty_bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    with _raises_tiles("TILES: tippecanoe not found"):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])


def test_b9_tippecanoe_exit_3(conn, tiles_env, monkeypatch, tmp_path):
    feats = [
        {
            "id": "1",
            "properties": {"name": "a"},
            "geometry": square(1000, 1000, 100),
        }
    ]
    seed_layer_table(conn, "x", feats)
    _install_registry(monkeypatch, make_entry("x"))
    wrap_bin = tmp_path / "bin"
    wrap_bin.mkdir()
    stub = wrap_bin / "tippecanoe"
    shutil.copy(ARCH2_BIN / "tippecanoe-exit3", stub)
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", str(wrap_bin))
    with _raises_tiles("TILES: x: tippecanoe exit 3"):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])


def test_b10_tile_kb_budget(conn, tiles_env, monkeypatch):
    # dz_grid-scale polygons alone gzip under 1 KB at z0; use dense so a tile
    # exceeds tile_kb:1 (message still names the first oversize tile).
    seed_layer_table(conn, "x", dense_features(20000))
    entry = make_entry(
        "x",
        tiles={"budget": {"total_mb": 60, "tile_kb": 1, "z0_7_mb": 4}},
    )
    _install_registry(monkeypatch, entry)
    with pytest.raises(
        TilesError,
        match=r"^TILES: x: budget exceeded: tile 0/0/0 \d+ KB > 1 KB$",
    ):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])


def test_b11_z0_7_budget(conn, tiles_env, monkeypatch):
    seed_layer_table(conn, "x", dense_features(20000))
    entry = make_entry(
        "x",
        tiles={"budget": {"total_mb": 60, "tile_kb": 1024, "z0_7_mb": 0.01}},
    )
    _install_registry(monkeypatch, entry)
    with pytest.raises(
        TilesError,
        match=r"^TILES: x: budget exceeded: z0-7 \d+\.\d{2} MB > 0\.01 MB$",
    ):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])


def test_b12_total_budget(conn, tiles_env, monkeypatch):
    seed_layer_table(conn, "x", dense_features(20000))
    entry = make_entry(
        "x",
        tiles={"budget": {"total_mb": 0.1, "tile_kb": 500, "z0_7_mb": 4}},
    )
    _install_registry(monkeypatch, entry)
    with pytest.raises(
        TilesError,
        match=r"^TILES: x: budget exceeded: total \d+\.\d{2} MB > 0\.1 MB$",
    ):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])


def test_b13_keep_all_vs_coalesce(conn, tiles_env, monkeypatch):
    # 200 m squares: four-flag keep_all keeps all 20k at z5; coalesce drops
    # (20 m squares need tippecanoe detail flags the production profile must not
    # carry — see ARCH-2a §4 / review B1).
    seed_layer_table(conn, "x", dense_features(20000, size=200.0))
    entry = make_entry(
        "x",
        zoom={"min": 0, "max": 14, "low_zoom": "keep_all"},
        tiles={"budget": {"total_mb": 60, "tile_kb": 500, "z0_7_mb": 4}},
    )
    _install_registry(monkeypatch, entry)
    result = build_tileset("x", conn=conn, storage_path=tiles_env["storage"])
    assert result["distinct_z5"] == 20000

    with pytest.raises(
        TilesError,
        match=r"^TILES: x: z5 shows \d+ of 20000 features \(keep_all\)$",
    ):
        build_tileset(
            "x",
            conn=conn,
            storage_path=tiles_env["storage"],
            low_zoom_override="coalesce",
            force_keep_all_check=True,
        )


def test_b14_cluster_pts_close(conn, tiles_env, monkeypatch):
    seed_layer_table(conn, "x", pts_close_features())
    entry = make_entry(
        "x",
        geometry="point",
        unit="point",
        zoom={"min": 0, "max": 14, "low_zoom": "cluster"},
        keep_fields=["NAME", "INF_TYPE"],
        tiles={"budget": {"total_mb": 1, "tile_kb": 500, "z0_7_mb": 0.1}},
    )
    _install_registry(monkeypatch, entry)
    result = build_tileset("x", conn=conn, storage_path=tiles_env["storage"])
    pmtiles = tiles_env["dir"] / result["file"]
    assert len(distinct_ids_at_zoom(pmtiles, layer_id="x", zoom=14)) == 2
    assert len(distinct_ids_at_zoom(pmtiles, layer_id="x", zoom=0)) == 1


def test_b15_properties_flattened(conn, tiles_env, monkeypatch):
    feats = [
        {
            "id": "1",
            "properties": {
                "PIPE_NAME": "A",
                "FLUID": "oil",
                "DESCRIPTIO": "one",
                "SECRET": "nope",
            },
            "geometry": line_features()[0]["geometry"],
        }
    ]
    seed_layer_table(conn, "x", feats)
    keep = ["PIPE_NAME", "FLUID", "DESCRIPTIO"]
    entry = make_entry(
        "x",
        geometry="line",
        zoom={"min": 0, "max": 14, "low_zoom": "coalesce"},
        keep_fields=keep,
        tiles={"budget": {"total_mb": 15, "tile_kb": 500, "z0_7_mb": 2}},
    )
    _install_registry(monkeypatch, entry)
    result = build_tileset("x", conn=conn, storage_path=tiles_env["storage"])
    pmtiles = tiles_env["dir"] / result["file"]
    from pmtiles.reader import MmapSource, all_tiles

    props_list: list[dict] = []
    with pmtiles.open("rb") as fh:
        for (z, x, y), _data in all_tiles(MmapSource(fh)):
            props_list = decode_tile_properties(
                pmtiles, layer_id="x", z=z, x=x, y=y
            )
            if props_list:
                break
    assert props_list
    expected = {"feature_id"} | set(keep)
    for props in props_list:
        assert set(props.keys()) == expected
        assert "SECRET" not in props


def test_b16_minzoom_override(conn, tiles_env, monkeypatch, tmp_path):
    feats = [
        {
            "id": "1",
            "properties": {"name": "a"},
            "geometry": square(1000, 1000, 100),
        }
    ]
    seed_layer_table(conn, "x", feats)
    _install_registry(monkeypatch, make_entry("x"))
    wrap_bin = tmp_path / "bin"
    wrap_bin.mkdir()
    stub = wrap_bin / "tippecanoe"
    shutil.copy(ARCH2_BIN / "tippecanoe-z3", stub)
    stub.chmod(0o755)
    real = shutil.which("tippecanoe")
    assert real, "tippecanoe must be on PATH before B-16 override"
    monkeypatch.setenv("PATH", f"{wrap_bin}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("REAL_TIPPECANOE", real)
    with _raises_tiles("TILES: x: minzoom 3 != 0"):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])


def test_b17_fail_closed(conn, tiles_env, monkeypatch):
    feats = [
        {
            "id": "1",
            "properties": {"name": "a"},
            "geometry": square(1000, 1000, 500),
        }
    ]
    seed_layer_table(conn, "x", feats)
    entry = make_entry("x")
    _install_registry(monkeypatch, entry)
    good = build_tileset("x", conn=conn, storage_path=tiles_env["storage"])
    pmtiles_path = tiles_env["dir"] / good["file"]
    manifest_path = tiles_env["dir"] / "manifest.json"
    prev_pmtiles = pmtiles_path.read_bytes()
    prev_manifest = manifest_path.read_bytes()

    # Fail at budget: swap in dense content so tile_kb:1 is exceeded.
    seed_layer_table(
        conn,
        "x",
        dense_features(5000),
        dataset_version="x@2026-10-22-bad00001",
    )
    entry.raw["tiles"]["budget"]["tile_kb"] = 1
    with pytest.raises(TilesError, match=r"budget exceeded"):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])

    assert pmtiles_path.read_bytes() == prev_pmtiles
    assert manifest_path.read_bytes() == prev_manifest
    tmp_dir = tiles_env["dir"] / ".tmp"
    leftovers = list(tmp_dir.iterdir()) if tmp_dir.is_dir() else []
    assert leftovers == [], leftovers


def test_b18_retention(conn, tiles_env, monkeypatch):
    storage = write_storage_yaml(
        tiles_env["storage"], keep_versions=3
    )
    entry = make_entry("x")
    _install_registry(monkeypatch, entry)
    for i in range(5):
        feats = [
            {
                "id": "1",
                "properties": {"name": f"v{i}"},
                "geometry": square(1000 + i, 1000, 100),
            }
        ]
        version = f"x@2026-10-22-{i:08x}"
        seed_layer_table(conn, "x", feats, dataset_version=version)
        build_tileset("x", conn=conn, storage_path=storage)
        time.sleep(0.05)  # distinct mtime for prune ordering
    files = sorted(tiles_env["dir"].glob("x.*.pmtiles"))
    assert len(files) == 3
    manifest = json.loads(
        (tiles_env["dir"] / "manifest.json").read_text(encoding="utf-8")
    )
    current = manifest["tilesets"]["x"]["file"]
    assert (tiles_env["dir"] / current).is_file()
    assert current in {p.name for p in files}


def test_b19_filename_matches_dataset_version(conn, tiles_env, monkeypatch):
    version = "x@2026-10-22-deadbeef"
    feats = [
        {
            "id": "1",
            "properties": {"name": "a"},
            "geometry": square(1000, 1000, 100),
        }
    ]
    seed_layer_table(conn, "x", feats, dataset_version=version, as_of="2026-10-22")
    _install_registry(monkeypatch, make_entry("x"))
    result = build_tileset("x", conn=conn, storage_path=tiles_env["storage"])
    assert result["file"] == "x.2026-10-22.deadbeef.pmtiles"
    assert result["dataset_version"] == version
    assert (tiles_env["dir"] / result["file"]).is_file()


def test_b20_aggregate_refused(conn, tiles_env, monkeypatch):
    feats = [
        {
            "id": "1",
            "properties": {"name": "a"},
            "geometry": square(1000, 1000, 100),
        }
    ]
    seed_layer_table(conn, "x", feats)
    entry = make_entry(
        "x",
        zoom={"min": 0, "max": 14, "low_zoom": "aggregate:council"},
    )
    _install_registry(monkeypatch, entry)
    with _raises_tiles(
        "TILES: x: low_zoom aggregate:council not built until ARCH-4a"
    ):
        build_tileset("x", conn=conn, storage_path=tiles_env["storage"])


def test_b21_cli_subprocess(conn, tiles_env, monkeypatch, tmp_path):
    # Seed the four committed tiled layers with tiny synthetic geoms.
    as_of = "2026-10-22"
    specs = {
        "dz2022": {
            "feats": [
                {
                    "id": "S01013482",
                    "properties": {"name": "A"},
                    "geometry": square(1000, 1000, 500),
                }
            ],
            "keep": ["name"],
        },
        "oil-fields": {
            "feats": [
                {
                    "id": "1",
                    "properties": {
                        "FIELDNAME": "F",
                        "FIELDTYPE": "OIL",
                        "STATUS": "PRODUCING",
                    },
                    "geometry": square(12000, 1000, 500),
                }
            ],
            "keep": ["FIELDNAME", "FIELDTYPE", "STATUS"],
        },
        "platforms": {
            "feats": [
                {
                    "id": "1",
                    "properties": {"NAME": "P", "INF_TYPE": "PLATFORM"},
                    "geometry": {"type": "Point", "coordinates": [15000, 2000]},
                }
            ],
            "keep": ["NAME", "INF_TYPE"],
        },
        "pipelines": {
            "feats": line_features(),
            "keep": ["PIPE_NAME", "FLUID", "DESCRIPTIO"],
        },
    }
    for layer_id, spec in specs.items():
        seed_layer_table(
            conn,
            layer_id,
            spec["feats"],
            dataset_version=f"{layer_id}@{as_of}-abcd1234",
            as_of=as_of,
        )

    env = os.environ.copy()
    env["ARCH1_TEST_DSN"] = require_dsn()
    env["TILES_DIR"] = str(tiles_env["dir"])
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])

    bad = subprocess.run(
        [str(PYTHON), "-m", "tiles.build", "nope"],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        env=env,
    )
    assert bad.returncode == 2
    assert bad.stderr.strip() == "TILES: unknown layer nope"

    # --all uses committed registry; stub storage path via TILES_DIR only
    # (default layers/storage.yaml). Copy keep_versions config into env dir.
    good = subprocess.run(
        [str(PYTHON), "-m", "tiles.build", "--all"],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        env=env,
    )
    assert good.returncode == 0, good.stderr
    manifest = json.loads(
        (tiles_env["dir"] / "manifest.json").read_text(encoding="utf-8")
    )
    assert sorted(manifest["tilesets"]) == [
        "dz2022",
        "oil-fields",
        "pipelines",
        "platforms",
    ]
    # build_all returns sorted ids; rebuild via import to assert order
    ids = build_all(conn=conn, storage_path=tiles_env["storage"])
    assert ids == ["dz2022", "oil-fields", "pipelines", "platforms"]
