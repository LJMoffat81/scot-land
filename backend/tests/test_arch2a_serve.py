"""ARCH-2a-2 serve tests V-1..V-11 and pin P-T5.

Requires a throwaway PostGIS database in ARCH1_TEST_DSN: these tests (and the
shared ARCH-2a helpers) drop and replace ``ref.extent*`` and ``layers.*``.
Do not point ARCH1_TEST_DSN at a dry-run or production database.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import mapbox_vector_tile
import pytest
from fastapi.testclient import TestClient
from pmtiles.reader import MmapSource, Reader, all_tiles

from layers.registry.loader import LayerEntry
from tiles.build import build_tileset

_HELPERS_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "arch2" / "helpers.py"
)
_spec = importlib.util.spec_from_file_location("arch2_helpers_serve", _HELPERS_PATH)
assert _spec and _spec.loader
_helpers = importlib.util.module_from_spec(_spec)
sys.modules["arch2_helpers_serve"] = _helpers
_spec.loader.exec_module(_helpers)

connect = _helpers.connect
make_entry = _helpers.make_entry
require_dsn = _helpers.require_dsn
seed_layer_table = _helpers.seed_layer_table
square = _helpers.square
write_storage_yaml = _helpers.write_storage_yaml

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"


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
    # Drop any open readers from prior tests (paths are immutable but tmp dirs go away).
    import api.tiles_routes as tr

    with tr._reader_lock:
        for _key, (fh, _reader) in list(tr._reader_cache.items()):
            try:
                fh.close()
            except OSError:
                pass
        tr._reader_cache.clear()
    return {"dir": tiles_dir, "storage": storage_yaml}


def _dz_grid_features() -> list[dict]:
    """9 synthetic 1 km squares (codes S01013482–S01013490)."""
    feats: list[dict] = []
    for idx, code_n in enumerate(range(482, 491)):
        col, row = idx % 3, idx // 3
        x0 = 1000 + col * 1000
        y0 = 1000 + row * 1000
        code = f"S01013{code_n}"
        feats.append(
            {
                "id": code,
                "properties": {"name": f"DZ {code}"},
                "geometry": square(x0, y0, 1000),
            }
        )
    return feats


def _install_registry(monkeypatch, *entries: LayerEntry) -> None:
    mapping = {e.id: e for e in entries}
    monkeypatch.setattr("api.tiles_routes.registry", lambda: mapping)
    monkeypatch.setattr("tiles.build.registry", lambda: mapping)


@pytest.fixture
def built_dz(conn, tiles_env, monkeypatch):
    """Build a dz2022 keep_all tileset into TILES_DIR."""
    entry = make_entry("dz2022")
    _install_registry(monkeypatch, entry)
    seed_layer_table(
        conn,
        "dz2022",
        _dz_grid_features(),
        dataset_version="dz2022@2026-10-22-abcd1234",
        as_of="2026-10-22",
    )
    result = build_tileset(
        "dz2022", conn=conn, storage_path=tiles_env["storage"]
    )
    return {"entry": entry, "result": result, **tiles_env}


@pytest.fixture
def client(built_dz, monkeypatch):
    """TestClient against the live app with TILES_DIR already set."""
    # Ensure optional router stayed loaded (publication rules must declare routes).
    from api.main import ROUTER_STATUS, app

    assert ROUTER_STATUS.get("api.tiles_routes", {}).get("loaded") is True
    return TestClient(app)


def _first_tile_xyz(pmtiles_path: Path) -> tuple[int, int, int]:
    with pmtiles_path.open("rb") as fh:
        for (z, x, y), data in all_tiles(MmapSource(fh)):
            if data:
                return int(z), int(x), int(y)
    raise AssertionError("no tiles in fixture pmtiles")


def _empty_in_range_xyz(pmtiles_path: Path, maxzoom: int) -> tuple[int, int, int]:
    """Pick a z/x/y inside [0, maxzoom] / [0, 2^z) with no tile bytes."""
    with pmtiles_path.open("rb") as fh:
        reader = Reader(MmapSource(fh))
        for z in range(0, maxzoom + 1):
            for x in range(1 << z):
                for y in range(1 << z):
                    if reader.get(z, x, y) is None:
                        return z, x, y
    raise AssertionError("every in-range tile has data")


def test_v1_manifest_ok(client, built_dz):
    r = client.get("/v1/tiles/manifest.json")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "public, max-age=60"
    body = r.json()
    assert "dz2022" in body["tilesets"]
    entry = body["tilesets"]["dz2022"]
    assert entry["version"] == built_dz["result"]["version"]
    assert entry["tiles"] == (
        f"/v1/tiles/dz2022/{entry['version']}/{{z}}/{{x}}/{{y}}.mvt"
    )


def test_v1_gated_absent_from_manifest(client, built_dz, monkeypatch):
    gated = make_entry("dz2022", gated_by="money_flag")
    monkeypatch.setattr("api.tiles_routes.registry", lambda: {"dz2022": gated})
    r = client.get("/v1/tiles/manifest.json")
    assert r.status_code == 200
    assert "dz2022" not in r.json()["tilesets"]


def test_v2_no_manifest(tiles_env, monkeypatch):
    from api.main import app

    client = TestClient(app)
    r = client.get("/v1/tiles/manifest.json")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    body = r.json()
    assert body["ok"] is False
    assert body["note"] == "no tiles built"
    assert body["tilesets"] == {}


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        "[]",
        '{"tilesets": []}',
        "",
    ],
)
def test_v3_unreadable_manifest(tiles_env, monkeypatch, payload):
    (tiles_env["dir"] / "manifest.json").write_text(payload, encoding="utf-8")
    from api.main import app

    client = TestClient(app)
    r = client.get("/v1/tiles/manifest.json")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    assert r.json()["note"] == "tiles manifest unreadable"


def test_v4_tile_200(client, built_dz):
    version = built_dz["result"]["version"]
    pmtiles = built_dz["dir"] / built_dz["result"]["file"]
    z, x, y = _first_tile_xyz(pmtiles)
    r = client.get(f"/v1/tiles/dz2022/{version}/{z}/{x}/{y}.mvt")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith(
        "application/vnd.mapbox-vector-tile"
    )
    assert r.headers.get("content-encoding") == "gzip"
    assert r.headers.get("cache-control") == "public, max-age=31536000, immutable"
    sha8 = version.rsplit(".", 1)[-1]
    assert r.headers.get("etag") == f'"{sha8}-{z}-{x}-{y}"'
    raw = r.content
    # TestClient/httpx may auto-decompress; accept either form.
    if len(raw) >= 2 and raw[0] == 0x1F and raw[1] == 0x8B:
        raw = gzip.decompress(raw)
    decoded = mapbox_vector_tile.decode(raw)
    assert "dz2022" in decoded


def test_v5_if_none_match_304(client, built_dz):
    version = built_dz["result"]["version"]
    pmtiles = built_dz["dir"] / built_dz["result"]["file"]
    z, x, y = _first_tile_xyz(pmtiles)
    sha8 = version.rsplit(".", 1)[-1]
    etag = f'"{sha8}-{z}-{x}-{y}"'
    r = client.get(
        f"/v1/tiles/dz2022/{version}/{z}/{x}/{y}.mvt",
        headers={"If-None-Match": etag},
    )
    assert r.status_code == 304
    assert r.content == b""


def test_v6_empty_tile_204(client, built_dz):
    version = built_dz["result"]["version"]
    pmtiles = built_dz["dir"] / built_dz["result"]["file"]
    z, x, y = _empty_in_range_xyz(pmtiles, int(built_dz["result"]["maxzoom"]))
    r = client.get(f"/v1/tiles/dz2022/{version}/{z}/{x}/{y}.mvt")
    assert r.status_code == 204
    assert r.headers.get("cache-control") == "public, max-age=31536000, immutable"
    assert r.content == b""


def test_v7_unknown_and_gated(client, built_dz, monkeypatch):
    version = built_dz["result"]["version"]
    r = client.get(f"/v1/tiles/nope/{version}/0/0/0.mvt")
    assert r.status_code == 404
    assert r.json() == {"detail": "unknown tileset"}

    # Gated id with the built file still on disk → still 404 unknown tileset.
    gated = make_entry("dz2022", gated_by="money_flag")
    monkeypatch.setattr("api.tiles_routes.registry", lambda: {"dz2022": gated})
    r = client.get(f"/v1/tiles/dz2022/{version}/0/0/0.mvt")
    assert r.status_code == 404
    assert r.json() == {"detail": "unknown tileset"}


def test_v8_unknown_version(client, built_dz):
    # Plant a stray pmtiles that a loose "serve any file" implementation might find.
    stray = built_dz["dir"] / "stray-not-canonical.pmtiles"
    stray.write_bytes((built_dz["dir"] / built_dz["result"]["file"]).read_bytes())

    r = client.get("/v1/tiles/dz2022/2026-10-22.deadbeef/0/0/0.mvt")
    assert r.status_code == 404
    assert r.json() == {"detail": "unknown version"}

    r = client.get("/v1/tiles/dz2022/..%2F..%2Fetc/0/0/0.mvt")
    assert r.status_code == 404

    r = client.get("/v1/tiles/dz2022/2026-10-22.DEADBEEF/0/0/0.mvt")
    assert r.status_code == 404
    assert r.json() == {"detail": "unknown version"}


def test_v9_tile_out_of_range(client, built_dz):
    version = built_dz["result"]["version"]
    r = client.get(f"/v1/tiles/dz2022/{version}/15/0/0.mvt")
    assert r.status_code == 404
    assert r.json() == {"detail": "tile out of range"}

    r = client.get(f"/v1/tiles/dz2022/{version}/-1/0/0.mvt")
    assert r.status_code == 404
    assert r.json() == {"detail": "tile out of range"}

    r = client.get(f"/v1/tiles/dz2022/{version}/1/2/0.mvt")  # x == 2^z
    assert r.status_code == 404
    assert r.json() == {"detail": "tile out of range"}

    r = client.get(f"/v1/tiles/dz2022/{version}/1.5/0/0.mvt")
    assert r.status_code == 422


def test_v10_no_db_or_tippecanoe(client, built_dz, monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("serve path must not connect")

    monkeypatch.setattr("psycopg2.connect", _boom)
    monkeypatch.setattr("subprocess.run", _boom)
    version = built_dz["result"]["version"]
    pmtiles = built_dz["dir"] / built_dz["result"]["file"]
    z, x, y = _first_tile_xyz(pmtiles)

    r = client.get("/v1/tiles/manifest.json")
    assert r.status_code == 200
    assert "dz2022" in r.json()["tilesets"]

    r = client.get(f"/v1/tiles/dz2022/{version}/{z}/{x}/{y}.mvt")
    assert r.status_code == 200


def test_v11_publication_rules_and_check_router():
    from georgist.publication_rules import PUBLIC_ROUTE_RULES, check_router
    from api import tiles_routes
    from api.main import registered_routes

    check_router(
        "api.tiles_routes",
        [p for _, p in registered_routes(tiles_routes.router)],
    )
    assert "/v1/tiles/manifest.json" in PUBLIC_ROUTE_RULES
    assert (
        "/v1/tiles/{layer_id}/{version}/{z}/{x}/{y}.mvt" in PUBLIC_ROUTE_RULES
    )
    assert (
        "/v1/tiles/{layer_id}/{version}/values/{measure}.json"
        in PUBLIC_ROUTE_RULES
    )
    tiles_keys = [k for k in PUBLIC_ROUTE_RULES if k.startswith("/v1/tiles/")]
    assert len(tiles_keys) == 3


def test_p_t5_publication_rules_diff_only_v1_tiles():
    """P-T5: vs main, publication_rules.py only adds /v1/tiles/ keys."""
    proc = subprocess.run(
        [
            "git",
            "diff",
            "origin/main...HEAD",
            "--",
            "backend/georgist/publication_rules.py",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    # Before first commit on this branch, compare against merge-base tip.
    if not proc.stdout.strip():
        proc = subprocess.run(
            [
                "git",
                "diff",
                "91a4e36e",
                "--",
                "backend/georgist/publication_rules.py",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            check=False,
        )
    diff = proc.stdout
    if not diff.strip():
        # Working tree vs base (uncommitted).
        proc = subprocess.run(
            [
                "git",
                "diff",
                "91a4e36e",
                "--",
                "backend/georgist/publication_rules.py",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            check=False,
        )
        diff = proc.stdout
    added_rule_lines = []
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        body = line[1:]
        # Ignore pure comment / blank additions outside the dict.
        if '"/v1/tiles/' in body or "'/v1/tiles/" in body:
            added_rule_lines.append(body)
            continue
        if "LayerRule(" in body and "/v1/tiles/" not in body:
            # A LayerRule added on a non-tiles key line (key may be previous line).
            pass
        # Any other added code line that looks like a new PUBLIC_ROUTE_RULES key.
        key_match = re.match(r'\s*"/([^"]+)":\s*LayerRule', body)
        if key_match and not key_match.group(1).startswith("v1/tiles/"):
            pytest.fail(
                "P-T5: publication_rules change outside /v1/tiles declarations"
            )
        key_match = re.match(r"\s*'/([^']+)':\s*LayerRule", body)
        if key_match and not key_match.group(1).startswith("v1/tiles/"):
            pytest.fail(
                "P-T5: publication_rules change outside /v1/tiles declarations"
            )
    # Keys may be on the line before LayerRule; accept either form.
    # Min added /v1/tiles/ diff-line count is 1 (was 2 on 2a) because P-T5'
    # below asserts the live table has exactly three /v1/tiles keys — that
    # exact-count check is stricter than requiring two diff hunks.
    key_lines = [
        ln for ln in diff.splitlines()
        if ln.startswith("+") and "/v1/tiles/" in ln
    ]
    if len(key_lines) < 1:
        pytest.fail(
            "P-T5: publication_rules change outside /v1/tiles declarations"
        )
    # P-T5': live rules table must have exactly three /v1/tiles keys.
    from georgist.publication_rules import PUBLIC_ROUTE_RULES

    live = [k for k in PUBLIC_ROUTE_RULES if k.startswith("/v1/tiles/")]
    assert len(live) == 3, f"P-T5': expected 3 /v1/tiles keys, got {live}"
    assert (
        "/v1/tiles/{layer_id}/{version}/values/{measure}.json" in live
    )
