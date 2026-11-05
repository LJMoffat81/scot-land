"""DZ-HEATMAP PR-B0: dz2011 registry tile source + DZ2011 preconditions.

Synthetic fixtures only (fake DB connection, tiny synthetic key files, tmp copies
of the committed registry / sources.yaml). No real held-out data is read.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from etl import check_dz2011_boundaries as pre
from etl.check_dz2011_boundaries import (
    PrecheckError,
    check_dz2011_rows,
    check_dz_source,
    load_keys,
)
from layers.credit_check import CreditError, check, load_requirements
from layers.registry.admission import AdmissionError, check_admission
from layers.registry.loader import RegistryError, load_registry

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
REGISTRY = BACKEND / "layers" / "registry"
SOURCES = REPO_ROOT / "data" / "config" / "sources.yaml"
FRONTEND_LIB = REPO_ROOT / "frontend" / "lib"

VINTAGE = (
    "Data Zones 2011 (Census 2011 geography, ref 2011-03-27); "
    "published 2014-11-06, revised 2021-10-04"
)
ATTRIBUTION = (
    "Copyright Scottish Government, contains Ordnance Survey data © Crown copyright "
    "and database right 2026."
)
P = "DZ2011-PRECHECK: REFUSED: "


# --- helpers -------------------------------------------------------------------


def _copy_registry(tmp_path: Path) -> Path:
    d = tmp_path / "registry"
    d.mkdir()
    for src in REGISTRY.glob("*.yaml"):
        shutil.copy(src, d / src.name)
    shutil.copy(REGISTRY / "schema.json", d / "schema.json")
    return d


def _edit(d: Path, layer_id: str, mutate) -> None:
    path = d / f"{layer_id}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _registry_fails(d: Path, message: str) -> None:
    with pytest.raises(RegistryError, match="^" + re.escape(message) + "$"):
        load_registry(d)


def _precheck_fails(message: str):
    return pytest.raises(PrecheckError, match="^" + re.escape(message) + "$")


class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self.conn = conn
        self._last = ""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append(str(sql))
        self._last = str(sql)

    def fetchone(self):
        return (self.conn.count,)

    def fetchall(self):
        return [(c,) for c in self.conn.codes]


class _FakeConn:
    def __init__(self, codes: list[str], count: int | None = None) -> None:
        self.codes = codes
        self.count = len(codes) if count is None else count
        self.executed: list[str] = []
        self.autocommit = False

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        pass

    def close(self):
        pass


def _keys_file(tmp_path: Path, keys) -> tuple[Path, str]:
    path = tmp_path / "keys.json"
    path.write_text(json.dumps(keys), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


SYN = ["S01000001", "S01000002", "S01000003"]


# --- registry entry (positive) ---------------------------------------------------


def test_b0_01_dz2011_entry_matches_gis_signoff():
    raw = load_registry(REGISTRY)["dz2011"].raw
    assert raw["source"] == {
        "type": "postgis_table",
        "table": "dz_boundaries",
        "id_field": "code",
        "where": "vintage = 2011",
    }
    assert raw["unit"] == "dz2011"
    assert raw["geometry"] == "polygon"
    assert raw["clip"] == "land+sea"
    assert raw["clip_keep_all"] is True
    assert raw["serve"] == {"mode": "pmtiles", "simplify_m": 0, "precision_dp": 6, "max_mb": 40}
    assert raw["zoom"] == {"min": 0, "max": 14, "low_zoom": "keep_all"}
    assert raw["tiles"] == {"budget": {"total_mb": 60, "tile_kb": 500, "z0_7_mb": 4}}
    assert raw["licence"] == "OGL-3.0"
    assert raw["vintage"] == VINTAGE
    assert raw["attribution"] == ATTRIBUTION
    assert raw["default_on"] is False
    assert "measure" not in raw
    assert "ladder_level" not in raw and "nests" not in raw
    assert "gated_by" not in raw


def test_b0_02_dz2022_unchanged_max_mb_15():
    raw = load_registry(REGISTRY)["dz2022"].raw
    assert raw["serve"]["max_mb"] == 15
    assert raw["default_on"] is True
    assert raw["source"]["where"] == "vintage = 2022"


def test_b0_03_dz2011_not_wired_into_frontend_map():
    factory = (FRONTEND_LIB / "tileLayerFactory.ts").read_text(encoding="utf-8")
    wanted = re.search(r"TILE_WANTED_IDS = \[(.*?)\] as const", factory, re.DOTALL)
    assert wanted is not None
    assert '"dz2022"' in wanted.group(1)
    assert "dz2011" not in wanted.group(1)
    ctx = (FRONTEND_LIB / "contextLayers.ts").read_text(encoding="utf-8")
    ordered = re.search(r"TILE_LAYER_IDS_ORDERED = \[(.*?)\] as const", ctx, re.DOTALL)
    assert ordered is not None
    assert "dz2011" not in ordered.group(1)
    for name in ("mapLayerRegistry.ts", "layersAddRegistry.ts", "contextLayers.ts"):
        assert '"dz2011"' not in (FRONTEND_LIB / name).read_text(encoding="utf-8"), name


def test_b0_04_admission_and_credit_cover_dz2011():
    entries = load_registry(REGISTRY)
    check_admission(entries)
    assert entries["dz2011"].raw["shows"] == "context"
    reqs = load_requirements(REPO_ROOT / "data" / "config" / "credit_requirements.yaml")
    assert reqs["registry:dz2011"] == ["Scottish Government", "Ordnance Survey"]
    check({"registry:dz2011": reqs["registry:dz2011"]}, REPO_ROOT)


# --- schema / loader negatives ---------------------------------------------------


def test_b0_05_pmtiles_max_mb_above_60_refused(tmp_path):
    d = _copy_registry(tmp_path)
    _edit(d, "dz2011", lambda x: x["serve"].update(max_mb=61))
    _registry_fails(d, "REGISTRY: dz2011: $.serve.max_mb: 61 is greater than the maximum of 60")


def test_b0_06_non_pmtiles_max_mb_above_15_still_refused(tmp_path):
    d = _copy_registry(tmp_path)

    def to_geojson(x):
        x["serve"].update(mode="geojson", max_mb=16)
        x.pop("tiles")

    _edit(d, "dz2011", to_geojson)
    _registry_fails(d, "REGISTRY: dz2011: $.serve.max_mb: 16 is greater than the maximum of 15")


def test_b0_07_pmtiles_max_mb_over_budget_total_refused(tmp_path):
    d = _copy_registry(tmp_path)
    _edit(d, "dz2011", lambda x: x["tiles"]["budget"].update(total_mb=39))
    _registry_fails(
        d, "REGISTRY: dz2011: $.serve.max_mb: 40 exceeds tiles.budget.total_mb 39"
    )


def test_b0_08_pmtiles_max_mb_15_over_small_budget_still_allowed():
    # oil-fields: serve.max_mb 15 with tiles.budget.total_mb 4 (unchanged behaviour).
    raw = load_registry(REGISTRY)["oil-fields"].raw
    assert raw["serve"]["max_mb"] == 15
    assert raw["tiles"]["budget"]["total_mb"] < 15


@pytest.mark.parametrize("key,value", [("ladder_level", "dz2022"), ("nests", False)])
def test_b0_09_off_ladder_unit_refuses_ladder_fields(tmp_path, key, value):
    d = _copy_registry(tmp_path)
    _edit(d, "dz2011", lambda x: x.update({key: value}))
    _registry_fails(d, f"REGISTRY: dz2011: $.{key}: not allowed for off-ladder unit 'dz2011'")


def test_b0_10_dz2011_blank_vintage_refused(tmp_path):
    d = _copy_registry(tmp_path)
    _edit(d, "dz2011", lambda x: x.pop("vintage"))
    entries = load_registry(d)
    with pytest.raises(
        AdmissionError,
        match="^" + re.escape("ADMISSION: dz2011: $.vintage: required (charter v2 §4.5)") + "$",
    ):
        check_admission(entries)


def test_b0_11_dz2011_clip_none_refused(tmp_path):
    d = _copy_registry(tmp_path)
    _edit(d, "dz2011", lambda x: x.update(clip="none"))
    _registry_fails(d, "REGISTRY: dz2011: $.clip: 'none' is only allowed with serve.mode raster")


def test_b0_12_dz2011_credit_missing_os_refused(tmp_path):
    root = tmp_path / "repo"
    reg = root / "backend" / "layers" / "registry"
    reg.mkdir(parents=True)
    shutil.copy(REGISTRY / "dz2011.yaml", reg / "dz2011.yaml")
    _edit(reg, "dz2011", lambda x: x.update(attribution="Copyright Scottish Government."))
    with pytest.raises(
        CreditError, match="^" + re.escape("CREDIT: registry:dz2011: missing phrase 'Ordnance Survey'") + "$"
    ):
        check({"registry:dz2011": ["Scottish Government", "Ordnance Survey"]}, root)


# --- official source check -------------------------------------------------------


@pytest.mark.parametrize("vintage", [2011, 2022])
def test_b0_13_committed_sources_are_official(vintage):
    check_dz_source(vintage)


def _src_copy(tmp_path: Path, mutate) -> Path:
    cfg = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    mutate(cfg["data_zone_boundaries"]["vintages"])
    out = tmp_path / "sources.yaml"
    out.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return out


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("url", "https://example.invalid/dz.zip", "https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip"),
        ("sha256", "0" * 64, "846950b7dc74fdedc8a6c5c3d9fd9c5afeca3477a103505b590613bc9704bed8"),
        ("product", "DataZoneBdry2022", "DataZoneBdry2011"),
        ("expected_count", 6975, 6976),
    ],
)
def test_b0_14_sources_pin_drift_refused(tmp_path, key, value, expected):
    path = _src_copy(tmp_path, lambda v: v[2011].update({key: value}))
    with _precheck_fails(
        f"{P}sources.yaml data_zone_boundaries.vintages.2011.{key}: expected {expected}, got {value}"
    ):
        check_dz_source(2011, sources_path=path)


def test_b0_15_sources_vintage_absent_refused(tmp_path):
    path = _src_copy(tmp_path, lambda v: v.pop(2011))
    with _precheck_fails(f"{P}sources.yaml data_zone_boundaries.vintages.2011: expected mapping, got absent"):
        check_dz_source(2011, sources_path=path)


def test_b0_16_registry_where_wrong_vintage_refused(tmp_path):
    d = _copy_registry(tmp_path)
    _edit(d, "dz2011", lambda x: x["source"].update(where="vintage = 2022"))
    with _precheck_fails(f"{P}dz2011 source.where: expected vintage = 2011, got vintage = 2022"):
        check_dz_source(2011, registry_dir=d)


def test_b0_17_registry_licence_wrong_refused(tmp_path):
    d = _copy_registry(tmp_path)
    _edit(d, "dz2011", lambda x: x.update(licence="CC-BY-4.0"))
    with _precheck_fails(f"{P}dz2011 licence: expected OGL-3.0, got CC-BY-4.0"):
        check_dz_source(2011, registry_dir=d)


def test_b0_18_unknown_vintage_refused():
    with _precheck_fails(f"{P}vintage: expected 2011 or 2022, got 2019"):
        check_dz_source(2019)


# --- rows precondition -----------------------------------------------------------


def test_b0_19_committed_keys_pin_and_count():
    keys = load_keys()
    assert len(keys) == 6976


def test_b0_20_rows_match_passes(tmp_path):
    path, sha = _keys_file(tmp_path, SYN)
    conn = _FakeConn(list(reversed(SYN)))
    check_dz2011_rows(conn, keys_path=path, keys_sha256=sha, expected_count=3)
    assert conn.executed == [
        "SELECT count(*) FROM dz_boundaries WHERE vintage = 2011",
        "SELECT code FROM dz_boundaries WHERE vintage = 2011",
    ]


def test_b0_21_keys_sha_mismatch_refused(tmp_path):
    path, sha = _keys_file(tmp_path, SYN)
    with _precheck_fails(f"{P}dz2011_keys.json sha256: expected {'0' * 64}, got {sha}"):
        check_dz2011_rows(_FakeConn(SYN), keys_path=path, keys_sha256="0" * 64, expected_count=3)


@pytest.mark.parametrize("bad", [SYN + [SYN[0]], {"a": 1}, SYN[:2] + [7]])
def test_b0_22_keys_invalid_refused(tmp_path, bad):
    path, sha = _keys_file(tmp_path, bad)
    with _precheck_fails(f"{P}dz2011_keys.json: expected unique list of str, got invalid"):
        check_dz2011_rows(_FakeConn(SYN), keys_path=path, keys_sha256=sha, expected_count=3)


def test_b0_23_keys_count_refused(tmp_path):
    path, sha = _keys_file(tmp_path, SYN[:2])
    with _precheck_fails(f"{P}dz2011_keys.json count: expected 3, got 2"):
        check_dz2011_rows(_FakeConn(SYN), keys_path=path, keys_sha256=sha, expected_count=3)


@pytest.mark.parametrize("rows", [[], SYN[:2], SYN + ["S01000004"]])
def test_b0_24_table_count_refused(tmp_path, rows):
    path, sha = _keys_file(tmp_path, SYN)
    conn = _FakeConn(rows)
    with _precheck_fails(f"{P}dz_boundaries vintage=2011 count: expected 3, got {len(rows)}"):
        check_dz2011_rows(conn, keys_path=path, keys_sha256=sha, expected_count=3)
    assert len(conn.executed) == 1


def test_b0_25_table_codes_differ_refused(tmp_path):
    path, sha = _keys_file(tmp_path, SYN)
    conn = _FakeConn(SYN[:2] + ["S01000009"])
    with _precheck_fails(
        f"{P}dz_boundaries vintage=2011 codes: expected dz2011_keys.json set, got 1 missing, 1 extra"
    ):
        check_dz2011_rows(conn, keys_path=path, keys_sha256=sha, expected_count=3)


def test_b0_26_default_expected_count_is_6976(tmp_path):
    # Committed key file + a synthetic 3-row table: refuses on the 6976 count.
    with _precheck_fails(f"{P}dz_boundaries vintage=2011 count: expected 6976, got 3"):
        check_dz2011_rows(_FakeConn(SYN))


# --- wiring into run_layer + CLI -------------------------------------------------


def test_b0_27_run_layer_dz2011_refuses_before_fetch(monkeypatch, tmp_path):
    import etl.run_layer as rl

    monkeypatch.setenv("LAYER_RECEIPT_DIR", str(tmp_path / "receipts"))
    called: list[str] = []
    monkeypatch.setattr(rl, "_ensure_helpers", lambda conn: called.append("helpers"))
    monkeypatch.setattr(rl, "_fetch_entry", lambda *a, **k: called.append("fetch"))
    conn = _FakeConn([], count=0)
    with pytest.raises(
        rl.IngestError,
        match="^"
        + re.escape(f"INGEST: dz2011: {P}dz_boundaries vintage=2011 count: expected 6976, got 0")
        + "$",
    ):
        rl.run_layer("dz2011", conn=conn)
    assert called == []
    assert conn.executed[0] == "SELECT count(*) FROM dz_boundaries WHERE vintage = 2011"


def test_b0_28_preconditions_dz2011_and_carbon_peatland():
    import etl.run_layer as rl
    from etl.check_cpm2016 import check_cpm2016_raw

    assert set(rl.PRECONDITIONS) == {"dz2011", "carbon-peatland"}
    assert rl.PRECONDITIONS["dz2011"] is check_dz2011_rows
    assert rl.PRECONDITIONS["carbon-peatland"] is check_cpm2016_raw


def test_b0_29_cli_source_ok(capsys):
    assert pre.main(["--source"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "mode": "source"}


def test_b0_30_cli_rows_refuses_exit_2(monkeypatch, capsys):
    import psycopg2

    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/none")
    monkeypatch.setattr(psycopg2, "connect", lambda dsn: _FakeConn(SYN))
    assert pre.main(["--rows"]) == 2
    err = capsys.readouterr().err
    assert err == f"{P}dz_boundaries vintage=2011 count: expected 6976, got 3\n"
