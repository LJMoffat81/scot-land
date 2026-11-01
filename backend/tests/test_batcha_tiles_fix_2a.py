"""BATCHA-TILES-FIX-2A: councils Boundary-Line adapter, empty source, receipts, --all."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import struct
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import psycopg2
import pytest
import yaml
from shapely.geometry import box, shape

from etl.adapters.os_boundary_line import (
    fetch_os_boundary_line,
    gpkg_blob_to_wkb,
)
from etl.build_boundaries import OS_BOUNDARY_SHA256
from etl.build_scotland_extent import load_only
from etl.run_layer import (
    CACHE_DIR,
    RECEIPT_DIR,
    IngestError,
    _cache_dir,
    _receipt_dir,
    _write_receipt,
    run_layer,
)
from layers.registry.loader import (
    REGISTRY_DIR,
    RegistryError,
    load_registry,
    registry,
)
from tiles.build import BuildAllError, TilesError, build_all, main as tiles_main

REPO = Path(__file__).resolve().parents[2]
HOME_DEPLOY = REPO / "docs" / "HOME_DEPLOY.md"
COMPOSE_HOME = REPO / "docker-compose.home.yml"
SOURCES_YAML = REPO / "data" / "config" / "sources.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "arch1"

PIN = "151b027b621ac4cdac3f7a6635cd26dd65fb3b5bf1cb8eb392cc00e1687e3bd4"
COUNCILS_URL = (
    "https://api.os.uk/downloads/v1/products/BoundaryLine/downloads"
    "?area=GB&format=GeoPackage&redirect"
)
LAYER = "district_borough_unitary"
CODE_FIELD = "Census_Code"
NAME_FIELD = "Name"
CODE_PREFIX = "S12"


def _dsn() -> str:
    dsn = os.environ.get("ARCH1_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("ARCH1_TEST_DSN not set")
    return dsn


def _gp_blob(wkb: bytes, *, envelope_type: int = 1, srs_id: int = 27700) -> bytes:
    flags = 0x01 | ((envelope_type & 0x07) << 1)
    sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    header = bytearray(b"GP")
    header.append(0)
    header.append(flags)
    header.extend(struct.pack("<i", int(srs_id)))
    header.extend(b"\x00" * sizes[envelope_type])
    return bytes(header) + wkb


def _build_gpkg_bytes(
    rows: list[tuple[str, str, Any]],
    *,
    srs_id: int = 27700,
    envelope_type: int = 1,
    raw_geom: bytes | None = None,
) -> bytes:
    """Build a minimal GeoPackage with district_borough_unitary rows."""
    fd, name = tempfile.mkstemp(suffix=".gpkg")
    os.close(fd)
    path = Path(name)
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE gpkg_spatial_ref_sys (
              srs_name TEXT NOT NULL,
              srs_id INTEGER NOT NULL PRIMARY KEY,
              organization TEXT NOT NULL,
              organization_coordsys_id INTEGER NOT NULL,
              definition TEXT NOT NULL,
              description TEXT
            );
            INSERT INTO gpkg_spatial_ref_sys VALUES
              ('OSGB', 27700, 'EPSG', 27700, 'undefined', NULL);
            INSERT INTO gpkg_spatial_ref_sys VALUES
              ('WGS 84', 4326, 'EPSG', 4326, 'undefined', NULL);
            CREATE TABLE gpkg_contents (
              table_name TEXT NOT NULL PRIMARY KEY,
              data_type TEXT NOT NULL,
              identifier TEXT,
              description TEXT,
              last_change TEXT NOT NULL,
              min_x REAL, min_y REAL, max_x REAL, max_y REAL,
              srs_id INTEGER
            );
            CREATE TABLE gpkg_geometry_columns (
              table_name TEXT NOT NULL,
              column_name TEXT NOT NULL,
              geometry_type_name TEXT NOT NULL,
              srs_id INTEGER NOT NULL,
              z INTEGER NOT NULL,
              m INTEGER NOT NULL,
              PRIMARY KEY (table_name, column_name)
            );
            CREATE TABLE district_borough_unitary (
              fid INTEGER PRIMARY KEY AUTOINCREMENT,
              geom BLOB NOT NULL,
              Census_Code TEXT,
              Name TEXT
            );
            """
        )
        cur.execute(
            "INSERT INTO gpkg_contents VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                LAYER,
                "features",
                LAYER,
                None,
                "2020-01-01T00:00:00.000Z",
                0,
                0,
                1,
                1,
                srs_id,
            ),
        )
        cur.execute(
            "INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,?,?)",
            (LAYER, "geom", "POLYGON", srs_id, 0, 0),
        )
        for code, name, geom in rows:
            if raw_geom is not None:
                blob = raw_geom
            else:
                wkb = geom.wkb if hasattr(geom, "wkb") else box(0, 0, 1, 1).wkb
                blob = _gp_blob(wkb, envelope_type=envelope_type, srs_id=srs_id)
            cur.execute(
                "INSERT INTO district_borough_unitary (geom, Census_Code, Name) "
                "VALUES (?,?,?)",
                (blob, code, name),
            )
        conn.commit()
    finally:
        conn.close()
    data = path.read_bytes()
    path.unlink(missing_ok=True)
    return data


def _zip_gpkg(gpkg_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data/bdline_gb.gpkg", gpkg_bytes)
    return buf.getvalue()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _client_for(zip_bytes: bytes, counter: list[int] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if counter is not None:
            counter.append(1)
        return httpx.Response(200, content=zip_bytes)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _default_rows() -> list[tuple[str, str, Any]]:
    return [
        ("S12000036", "City of Edinburgh", box(1000, 1000, 2000, 2000)),
        ("S12000049", "Glasgow City", box(3000, 3000, 4000, 4000)),
        ("E06000001", "English Unitary", box(5000, 5000, 6000, 6000)),
    ]


def test_a1_s12_filter_crs_props_redacted_one_http(tmp_path: Path) -> None:
    zip_bytes = _zip_gpkg(_build_gpkg_bytes(_default_rows()))
    pin = _sha(zip_bytes)
    calls: list[int] = []
    client = _client_for(zip_bytes, calls)
    collection, raw, redacted = fetch_os_boundary_line(
        COUNCILS_URL,
        sha256=pin,
        layer=LAYER,
        code_field=CODE_FIELD,
        name_field=NAME_FIELD,
        code_prefix=CODE_PREFIX,
        expected_count=2,
        download_max_mb=10,
        cache_dir=tmp_path / "cache",
        max_mb=10,
        client=client,
    )
    assert len(calls) == 1
    assert redacted == urlsplit(COUNCILS_URL)._replace(query="", fragment="").geturl()
    assert "?" not in redacted
    assert collection["crs"]["properties"]["name"].endswith("27700")
    feats = collection["features"]
    assert len(feats) == 2
    codes = {f["properties"]["code"] for f in feats}
    assert codes == {"S12000036", "S12000049"}
    for feat in feats:
        props = feat["properties"]
        assert set(props) == {"id", "code", "name"}
        assert props["id"] == props["code"]
        assert props["code"].startswith("S12")
        geom = shape(feat["geometry"])
        assert geom.bounds[0] >= 1000
        assert geom.bounds[2] <= 4000
    assert json.loads(raw.decode("utf-8"))["type"] == "FeatureCollection"


def test_a2_sha_mismatch_removes_cache(tmp_path: Path) -> None:
    zip_bytes = _zip_gpkg(_build_gpkg_bytes(_default_rows()))
    wrong = "0" * 64
    cache = tmp_path / "cache"
    client = _client_for(zip_bytes)
    with pytest.raises(
        RuntimeError,
        match=re.escape(
            f"Boundary-Line sha256 mismatch: expected {wrong}, got {_sha(zip_bytes)}"
        ),
    ):
        fetch_os_boundary_line(
            COUNCILS_URL,
            sha256=wrong,
            layer=LAYER,
            code_field=CODE_FIELD,
            name_field=NAME_FIELD,
            code_prefix=CODE_PREFIX,
            expected_count=2,
            download_max_mb=10,
            cache_dir=cache,
            client=client,
        )
    assert list(cache.glob("os_boundary_line_*.zip")) == []


def test_a3_expected_count_message(tmp_path: Path) -> None:
    zip_bytes = _zip_gpkg(_build_gpkg_bytes(_default_rows()))
    pin = _sha(zip_bytes)
    client = _client_for(zip_bytes)
    with pytest.raises(
        RuntimeError,
        match=re.escape(
            "expected 3 features with Census_Code S12*, got 2"
        ),
    ):
        fetch_os_boundary_line(
            COUNCILS_URL,
            sha256=pin,
            layer=LAYER,
            code_field=CODE_FIELD,
            name_field=NAME_FIELD,
            code_prefix=CODE_PREFIX,
            expected_count=3,
            download_max_mb=10,
            cache_dir=tmp_path / "cache",
            client=client,
        )


def test_a4_download_budget_empties_cache(tmp_path: Path) -> None:
    zip_bytes = _zip_gpkg(_build_gpkg_bytes(_default_rows()))
    pin = _sha(zip_bytes)
    cache = tmp_path / "cache"
    # download_max_mb tiny so stream budget trips
    client = _client_for(zip_bytes)
    with pytest.raises(RuntimeError, match=r"^budget exceeded: download_mb$"):
        fetch_os_boundary_line(
            COUNCILS_URL,
            sha256=pin,
            layer=LAYER,
            code_field=CODE_FIELD,
            name_field=NAME_FIELD,
            code_prefix=CODE_PREFIX,
            expected_count=2,
            download_max_mb=0.000001,
            cache_dir=cache,
            client=client,
        )
    assert list(cache.glob("*")) == []


def test_a5_cached_zip_zero_http(tmp_path: Path) -> None:
    zip_bytes = _zip_gpkg(_build_gpkg_bytes(_default_rows()))
    pin = _sha(zip_bytes)
    cache = tmp_path / "cache"
    cache.mkdir()
    dest = cache / f"os_boundary_line_{pin[:12]}.zip"
    dest.write_bytes(zip_bytes)
    calls: list[int] = []
    client = _client_for(b"SHOULD_NOT_FETCH", calls)
    collection, _, _ = fetch_os_boundary_line(
        COUNCILS_URL,
        sha256=pin,
        layer=LAYER,
        code_field=CODE_FIELD,
        name_field=NAME_FIELD,
        code_prefix=CODE_PREFIX,
        expected_count=2,
        download_max_mb=10,
        cache_dir=cache,
        client=client,
    )
    assert calls == []
    assert len(collection["features"]) == 2


@pytest.mark.parametrize("envelope_type", [0, 1, 2, 3, 4])
def test_a6_gp_envelopes_and_non_gp_and_srs(
    envelope_type: int, tmp_path: Path
) -> None:
    wkb = box(10, 20, 30, 40).wkb
    blob = _gp_blob(wkb, envelope_type=envelope_type)
    assert gpkg_blob_to_wkb(blob) == wkb

    with pytest.raises(
        RuntimeError,
        match=r"^geometry blob is not GeoPackage \(GP\) encoded$",
    ):
        gpkg_blob_to_wkb(b"\x01\x03" + wkb)

    zip_bytes = _zip_gpkg(
        _build_gpkg_bytes(_default_rows()[:2], srs_id=4326)
    )
    pin = _sha(zip_bytes)
    with pytest.raises(
        RuntimeError,
        match=re.escape(
            "Boundary-Line layer district_borough_unitary srs_id 4326 != 27700"
        ),
    ):
        fetch_os_boundary_line(
            COUNCILS_URL,
            sha256=pin,
            layer=LAYER,
            code_field=CODE_FIELD,
            name_field=NAME_FIELD,
            code_prefix=CODE_PREFIX,
            expected_count=2,
            download_max_mb=10,
            cache_dir=tmp_path / "cache",
            client=_client_for(zip_bytes),
        )


def test_a7_councils_pin_matches_sources_and_constant() -> None:
    entry = registry()["councils"].raw
    src = entry["source"]
    assert src["type"] == "os_boundary_line"
    assert src["sha256"] == PIN
    assert src["sha256"] == OS_BOUNDARY_SHA256
    sources = yaml.safe_load(SOURCES_YAML.read_text(encoding="utf-8"))
    assert sources["boundaries"]["councils"]["sha256"] == PIN
    assert src["url"] == COUNCILS_URL
    assert src["layer"] == LAYER
    assert src["code_prefix"] == CODE_PREFIX
    assert src["expected_count"] == 32
    assert src["code_field"] == CODE_FIELD
    assert src["name_field"] == NAME_FIELD
    assert src["download_max_mb"] == 900


def _base_entry(**over: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": "x",
        "title": "X",
        "geography": "scotland",
        "clip": "land",
        "unit": "none",
        "licence": "OGL-3.0",
        "attribution": "Test attribution",
        "source": {
            "type": "os_boundary_line",
            "url": COUNCILS_URL,
            "sha256": PIN,
            "layer": LAYER,
            "code_field": CODE_FIELD,
            "name_field": NAME_FIELD,
            "code_prefix": CODE_PREFIX,
            "expected_count": 32,
            "download_max_mb": 900,
        },
        "geometry": "polygon",
        "clip_keep_all": True,
        "refresh": {"cron": "0 5 1 1 *", "max_mb": 100, "max_s": 600},
        "serve": {
            "mode": "pmtiles",
            "simplify_m": 25,
            "precision_dp": 6,
            "max_mb": 15,
        },
        "zoom": {"min": 0, "max": 12, "low_zoom": "simplify"},
        "style": {},
        "legend": [],
        "lineage": {
            "derived_from": [],
            "method": "source",
            "roll_up_to": [],
        },
        "tiles": {"budget": {"total_mb": 15, "tile_kb": 500, "z0_7_mb": 2}},
    }
    entry.update(over)
    return entry


def test_a8_schema_os_boundary_line_rules(tmp_path: Path) -> None:
    missing = _base_entry()
    del missing["source"]["sha256"]
    path = tmp_path / "miss"
    path.mkdir()
    (path / "x.yaml").write_text(
        yaml.safe_dump(missing, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(
        RegistryError,
        match=re.escape("REGISTRY: x: $.source: 'sha256' is a required property"),
    ):
        load_registry(path)

    bad = _base_entry()
    bad["source"]["sha256"] = "deadbeef"
    path2 = tmp_path / "bad"
    path2.mkdir()
    (path2 / "x.yaml").write_text(
        yaml.safe_dump(bad, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(
        RegistryError,
        match=re.escape(
            "REGISTRY: x: $.source.sha256: 'deadbeef' does not match "
            "'^[0-9a-f]{64}$'"
        ),
    ):
        load_registry(path2)

    stray = _base_entry(
        source={
            "type": "postgis_table",
            "table": "ces_aquaculture_leases",
            "id_field": "id",
            "where": "TRUE",
            "expected_count": 3,
        }
    )
    path3 = tmp_path / "stray"
    path3.mkdir()
    (path3 / "x.yaml").write_text(
        yaml.safe_dump(stray, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(
        RegistryError,
        match=re.escape(
            "REGISTRY: x: $.source: False schema does not allow 3"
        ),
    ):
        load_registry(path3)


def test_a9_geojson_file_https_refused(tiny_extent, monkeypatch, tmp_path) -> None:
    entry = {
        "id": "probe-remote",
        "title": "Probe",
        "geography": "scotland",
        "clip": "land",
        "unit": "none",
        "licence": "OGL-3.0",
        "attribution": "Test",
        "source": {
            "type": "geojson_file",
            "url": "https://example.com/x.geojson",
        },
        "geometry": "polygon",
        "clip_keep_all": True,
        "refresh": {"cron": "0 5 1 1 *", "max_mb": 10, "max_s": 60},
        "serve": {
            "mode": "geojson",
            "simplify_m": 0,
            "precision_dp": 6,
            "max_mb": 15,
        },
        "zoom": {"min": 0, "max": 12, "low_zoom": "simplify"},
        "style": {},
        "legend": [],
        "lineage": {"derived_from": [], "method": "source", "roll_up_to": []},
    }
    reg = tmp_path / "reg"
    reg.mkdir()
    (reg / "probe-remote.yaml").write_text(
        yaml.safe_dump(entry, sort_keys=False), encoding="utf-8"
    )
    mapping = load_registry(reg)
    monkeypatch.setattr("etl.run_layer.registry", lambda: mapping)
    monkeypatch.setenv("LAYER_RECEIPT_DIR", str(tmp_path / "receipts"))
    with pytest.raises(
        IngestError,
        match=re.escape(
            "INGEST: probe-remote geojson_file reads local files only; "
            "source.url is remote (use --from-file or a fetching source type)"
        ),
    ):
        run_layer("probe-remote", conn=tiny_extent)


@pytest.fixture
def tiny_extent(monkeypatch, tmp_path):
    connection = psycopg2.connect(_dsn())
    connection.autocommit = True
    with connection.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cur.execute("CREATE SCHEMA IF NOT EXISTS ref")
        cur.execute("CREATE SCHEMA IF NOT EXISTS stage")
        cur.execute("CREATE SCHEMA IF NOT EXISTS layers")
        for table in ("extent_buf50_sub", "extent_sub", "extent"):
            cur.execute(f"DROP TABLE IF EXISTS ref.{table} CASCADE")
        for table in (
            "councils",
            "councils_prev",
            "councils__new",
            "ces-aquaculture",
            "ces-aquaculture_prev",
            "ces-aquaculture__new",
            "probe-remote",
            "probe-remote_prev",
            "probe-remote__new",
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
        "file,sha256\n"
        f"scotland_extent.27700.geojson,{sha}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "etl.build_scotland_extent.MANIFEST_PATH", gis / "manifest.csv"
    )
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    load_only(dest)
    yield connection
    connection.close()


def test_a10_councils_run_layer_env_dirs(
    tiny_extent, monkeypatch, tmp_path
) -> None:
    rows = [
        ("S12000036", "City of Edinburgh", box(1000, 1000, 2000, 2000)),
        ("S12000049", "Glasgow City", box(3000, 3000, 4000, 4000)),
    ]
    zip_bytes = _zip_gpkg(_build_gpkg_bytes(rows))
    pin = _sha(zip_bytes)
    receipt_dir = tmp_path / "state" / "receipts"
    cache_dir = tmp_path / "state" / "cache"
    monkeypatch.setenv("LAYER_RECEIPT_DIR", str(receipt_dir))
    monkeypatch.setenv("LAYER_CACHE_DIR", str(cache_dir))

    entry = yaml.safe_load(
        (REGISTRY_DIR / "councils.yaml").read_text(encoding="utf-8")
    )
    entry["source"]["sha256"] = pin
    entry["source"]["expected_count"] = 2
    entry["source"]["download_max_mb"] = 10
    entry["refresh"]["max_mb"] = 10
    reg = tmp_path / "reg"
    reg.mkdir()
    (reg / "councils.yaml").write_text(
        yaml.safe_dump(entry, sort_keys=False), encoding="utf-8"
    )
    mapping = load_registry(reg)
    monkeypatch.setattr("etl.run_layer.registry", lambda: mapping)

    client = _client_for(zip_bytes)
    real_fetch = fetch_os_boundary_line

    def wrapped(*args: Any, **kwargs: Any):
        kwargs["client"] = client
        return real_fetch(*args, **kwargs)

    monkeypatch.setattr("etl.run_layer.fetch_os_boundary_line", wrapped)

    receipt = run_layer("councils", conn=tiny_extent)
    assert receipt["before"] == 2
    assert receipt["after"] == 2
    assert receipt["outside"] == 0
    written = receipt_dir / "councils.receipt.json"
    assert written.is_file()
    assert json.loads(written.read_text(encoding="utf-8"))["after"] == 2
    # Env receipt dir is used; path is not under the repo RECEIPT_DIR.
    assert written.resolve().parent != RECEIPT_DIR.resolve()
    zips = list(cache_dir.glob("os_boundary_line_*.zip"))
    assert len(zips) == 1
    assert zips[0].read_bytes() == zip_bytes


def test_a11_empty_ces_source_refused(tiny_extent, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LAYER_RECEIPT_DIR", str(tmp_path / "receipts"))
    with tiny_extent.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS ces_aquaculture_leases CASCADE")
        cur.execute(
            """
            CREATE TABLE ces_aquaculture_leases (
              id text PRIMARY KEY,
              publication_status text,
              site_id text,
              lease_description text,
              property_classification text,
              geom geometry(MultiPolygon, 4326)
            )
            """
        )
    with pytest.raises(
        IngestError,
        match=re.escape(
            "INGEST: ces-aquaculture: source returned 0 features "
            "(postgis://ces_aquaculture_leases)"
        ),
    ):
        run_layer("ces-aquaculture", conn=tiny_extent)
    with tiny_extent.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='layers'
              AND table_name IN ('ces-aquaculture', 'ces-aquaculture__new')
            """
        )
        assert cur.fetchall() == []


def test_a12_receipt_preflight_before_stage(
    tiny_extent, monkeypatch, tmp_path
) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("LAYER_RECEIPT_DIR", str(blocker / "receipts"))
    with pytest.raises(
        IngestError,
        match=re.escape(
            f"INGEST: ces-aquaculture: receipt dir not writable: "
            f"{blocker / 'receipts'} "
            f"(set LAYER_RECEIPT_DIR to a read-write path)"
        ),
    ):
        run_layer("ces-aquaculture", conn=tiny_extent)
    with tiny_extent.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='stage' AND table_name='ces-aquaculture'
            """
        )
        assert cur.fetchall() == []
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='layers'
              AND table_name IN ('ces-aquaculture', 'ces-aquaculture__new')
            """
        )
        assert cur.fetchall() == []


def test_a13_write_receipt_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAYER_RECEIPT_DIR", raising=False)
    monkeypatch.delenv("LAYER_CACHE_DIR", raising=False)
    assert _receipt_dir() == RECEIPT_DIR
    assert _cache_dir() == CACHE_DIR

    env_dir = tmp_path / "env-receipts"
    monkeypatch.setenv("LAYER_RECEIPT_DIR", str(env_dir))
    path = _write_receipt("probe", {"id": "probe", "after": 1})
    assert path.parent == env_dir
    assert path.is_file()

    monkeypatch.delenv("LAYER_RECEIPT_DIR", raising=False)
    monkeypatch.setattr("etl.run_layer.RECEIPT_DIR", tmp_path / "repo-receipts")
    path2 = _write_receipt("probe2", {"id": "probe2", "after": 1})
    assert path2.parent == tmp_path / "repo-receipts"

    cache_env = tmp_path / "env-cache"
    monkeypatch.setenv("LAYER_CACHE_DIR", str(cache_env))
    assert _cache_dir() == cache_env


def test_a14_build_all_continues_and_summarises(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _E:
        def __init__(self, lid: str) -> None:
            self.id = lid
            self.raw = {
                "serve": {"mode": "pmtiles"},
                "tiles": {"budget": {"total_mb": 15, "tile_kb": 500, "z0_7_mb": 2}},
            }

    mapping = {lid: _E(lid) for lid in ("a", "b", "c", "d")}
    monkeypatch.setattr("tiles.build.registry", lambda: mapping)

    def fake_build(layer_id: str, **_kwargs: Any) -> dict[str, Any]:
        if layer_id in ("b", "d"):
            raise TilesError(f"TILES: {layer_id}: layer not built")
        return {"id": layer_id}

    monkeypatch.setattr("tiles.build.build_tileset", fake_build)
    with pytest.raises(
        BuildAllError,
        match=re.escape("TILES: --all: built 2, failed 2: b, d"),
    ):
        build_all()
    err = capsys.readouterr().err
    assert "TILES: b: layer not built\n" in err
    assert "TILES: d: layer not built\n" in err

    assert tiles_main(["--all"]) == 2
    err2 = capsys.readouterr().err
    assert "TILES: --all: built 2, failed 2: b, d" in err2


def test_a15_build_all_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class _E:
        def __init__(self, lid: str) -> None:
            self.id = lid
            self.raw = {
                "serve": {"mode": "pmtiles"},
                "tiles": {"budget": {"total_mb": 15, "tile_kb": 500, "z0_7_mb": 2}},
            }

    mapping = {lid: _E(lid) for lid in ("a", "b")}
    monkeypatch.setattr("tiles.build.registry", lambda: mapping)
    monkeypatch.setattr(
        "tiles.build.build_tileset", lambda layer_id, **_k: {"id": layer_id}
    )
    assert build_all() == ["a", "b"]
    assert tiles_main(["--all"]) == 0


def test_a16_nfi_compose_docs_no_pound() -> None:
    nfi = yaml.safe_load(
        (REGISTRY_DIR / "nfi.yaml").read_text(encoding="utf-8")
    )
    assert nfi["refresh"]["max_mb"] == 600

    compose = COMPOSE_HOME.read_text(encoding="utf-8")
    assert "./data:/app/data:ro" in compose
    assert (
        "${SCOT_LAND_STATE_DIR:-../scot-land-state}:/app/state" in compose
    )
    assert "LAYER_RECEIPT_DIR: /app/state/receipts" in compose
    assert "LAYER_CACHE_DIR: /app/state/cache" in compose

    docs = HOME_DEPLOY.read_text(encoding="utf-8")
    assert "Layer ingest state" in docs
    assert "LAYER_RECEIPT_DIR=/app/state/receipts" in docs
    assert "LAYER_CACHE_DIR=/app/state/cache" in docs
    assert "--from-wfs --replace --check-counts" in docs
    assert "Never" in docs and "--fixture" in docs
    assert "councils needs **no** prior ingest" in docs or (
        "councils needs" in docs and "no" in docs and "ingest" in docs
    )
    assert "TILES: --all: built <n>, failed <m>: <ids>" in docs
    assert "source returned 0 features" in docs
    pound = "\u00a3"
    assert pound not in docs
    assert pound not in compose
