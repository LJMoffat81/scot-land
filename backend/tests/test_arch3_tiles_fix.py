"""ARCH3-TILES-FIX: serve.mode=pmtiles is the one tiling predicate (T1–T10)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from etl.refresh_registry import run_weekly_refresh
from layers.registry.loader import REGISTRY_DIR, RegistryError, load_registry
from tiles.build import TilesError, build_all, build_tileset, is_tiled

REPO = Path(__file__).resolve().parents[2]
HOME_DEPLOY = REPO / "docs" / "HOME_DEPLOY.md"
ETL_DIR = REPO / "backend" / "etl"
SCHEMA_DIR = REPO / "backend" / "db" / "schema"

BATCH_A_IDS = (
    "ces-aquaculture",
    "crown-estate-leases",
    "scotwind-intog",
    "repd",
    "repd-onshore-wind",
    "naturescot-sssi",
    "naturescot-designations",
    "sepa-flood",
    "hydro-sites",
    "sepa-car",
    "nfi",
    "native-woodland",
)

ARCH3_FIX_IDS = BATCH_A_IDS + ("councils", "settlements-2022")

EXPECTED_UNGATED_PMTILES = [
    "ces-aquaculture",
    "councils",
    "crown-estate-leases",
    "dz2022",
    "hydro-sites",
    "native-woodland",
    "naturescot-designations",
    "naturescot-sssi",
    "nfi",
    "oil-fields",
    "pipelines",
    "platforms",
    "repd",
    "repd-onshore-wind",
    "scotland-extent",
    "scotwind-intog",
    "sepa-car",
    "sepa-flood",
    "settlements-2022",
]


def _copy_registry(tmp_path: Path) -> Path:
    dest = tmp_path / "registry"
    dest.mkdir()
    for src in REGISTRY_DIR.glob("*.yaml"):
        shutil.copy(src, dest / src.name)
    return dest


def _install_entries(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, Any]) -> None:
    monkeypatch.setattr("tiles.build.registry", lambda: mapping)


class _RawEntry:
    def __init__(self, layer_id: str, raw: dict[str, Any]) -> None:
        self.id = layer_id
        self.raw = raw


def test_t1_build_all_selects_ungated_pmtiles(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[str] = []

    def fake_build(layer_id: str, **_kwargs: Any) -> dict[str, Any]:
        built.append(layer_id)
        return {"id": layer_id}

    monkeypatch.setattr("tiles.build.build_tileset", fake_build)
    ids = build_all()
    assert ids == EXPECTED_UNGATED_PMTILES
    assert built == EXPECTED_UNGATED_PMTILES
    assert len(ids) == 19
    for lid in ARCH3_FIX_IDS:
        assert lid in ids


@pytest.mark.parametrize("layer_id", list(ARCH3_FIX_IDS))
def test_t2_build_tileset_selection_passes(
    layer_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("SENTINEL_STORAGE")

    monkeypatch.setattr("tiles.build.load_storage", boom)
    with pytest.raises(RuntimeError, match=r"^SENTINEL_STORAGE$"):
        build_tileset(layer_id)


def test_t3_schema_requires_tiles_for_pmtiles(tmp_path: Path) -> None:
    reg = _copy_registry(tmp_path)
    path = reg / "naturescot-sssi.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "tiles" in data
    del data["tiles"]
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(
        RegistryError,
        match=r"^REGISTRY: naturescot-sssi: \$: 'tiles' is a required property$",
    ):
        load_registry(reg)


def test_t4_schema_requires_pmtiles_when_tiles_present(tmp_path: Path) -> None:
    reg = _copy_registry(tmp_path)
    path = reg / "repd.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "tiles" in data
    data["serve"]["mode"] = "geojson"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(
        RegistryError,
        match=re.escape("REGISTRY: repd: $.serve.mode: 'pmtiles' was expected") + "$",
    ):
        load_registry(reg)


def test_t5_build_tileset_rejects_non_pmtiles(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = {
        "id": "x",
        "serve": {"mode": "geojson", "simplify_m": 0, "precision_dp": 6, "max_mb": 15},
        "tiles": {"budget": {"total_mb": 15, "tile_kb": 500, "z0_7_mb": 2}},
        "keep_fields": [],
    }
    _install_entries(monkeypatch, {"x": _RawEntry("x", raw)})
    with pytest.raises(
        TilesError, match=r"^TILES: x: serve\.mode is not pmtiles$"
    ):
        build_tileset("x")


def test_t6_refresh_tiles_on_serve_mode_not_tiles_key() -> None:
    entries = {
        "aa": {
            "id": "aa",
            "refresh": {"cron": "0 4 * * 1", "max_mb": 10, "max_s": 60},
            "serve": {"mode": "pmtiles"},
            # deliberately no tiles key — selection must still tile via serve.mode
        },
        "bb": {
            "id": "bb",
            "refresh": {"cron": "0 5 * * 1", "max_mb": 10, "max_s": 60},
            "serve": {"mode": "geojson"},
            "tiles": {"budget": {"total_mb": 15, "tile_kb": 500, "z0_7_mb": 2}},
        },
    }
    tiled: list[str] = []

    def fake_runner(lid: str) -> dict[str, Any]:
        return {
            "id": lid,
            "before": 1,
            "after": 1,
            "outside": 0,
            "repaired": 0,
            "url": "https://example.test/x?token=***",
            "as_of": "2026-10-31",
            "dataset_version": f"{lid}@2026-10-31-deadbeef",
            "extent_sha256": "e" * 64,
        }

    def fake_tiler(lid: str) -> dict[str, Any]:
        tiled.append(lid)
        return {"id": lid}

    summary = run_weekly_refresh(
        entries=entries, runner=fake_runner, tile_builder=fake_tiler
    )
    assert summary["tiles_built"] == ["aa"]
    assert tiled == ["aa"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"serve": {"mode": "pmtiles"}}, True),
        ({"serve": {"mode": "pmtiles"}, "tiles": {"budget": {}}}, True),
        ({"tiles": {"budget": {"total_mb": 15, "tile_kb": 500, "z0_7_mb": 2}}}, False),
        ({"serve": {"mode": "geojson"}, "tiles": {"budget": {}}}, False),
        ({"serve": {"mode": "raster"}}, False),
        ({}, False),
        (None, False),
        ({"serve": "pmtiles"}, False),
        ({"serve": {"mode": "PMTiles"}}, False),
    ],
)
def test_t7_is_tiled_truth_table(raw: dict[str, Any] | None, expected: bool) -> None:
    assert is_tiled(raw) is expected


def test_t8_pmtiles_postgis_tables_have_ingest_and_ddl() -> None:
    entries = load_registry(REGISTRY_DIR)
    ingest_texts = {
        path.name: path.read_text(encoding="utf-8")
        for path in ETL_DIR.glob("ingest_*.py")
    }
    schema_texts = {
        path.name: path.read_text(encoding="utf-8")
        for path in SCHEMA_DIR.glob("*.sql")
    }
    for lid, entry in sorted(entries.items()):
        raw = entry.raw
        if (raw.get("serve") or {}).get("mode") != "pmtiles":
            continue
        source = raw.get("source") or {}
        if source.get("type") != "postgis_table":
            continue
        table = source.get("table") or ""
        if "." in table:
            continue  # qualified (e.g. ref.extent) — out of T8 scope
        assert re.fullmatch(r"[a-z_][a-z0-9_]*", table), f"{lid}: bad table {table!r}"
        ingest_hits = [name for name, text in ingest_texts.items() if table in text]
        assert ingest_hits, f"{lid}: no etl/ingest_*.py names table {table}"
        ddl_hits = [
            name
            for name, text in schema_texts.items()
            if re.search(rf"CREATE TABLE\b[^;]*\b{re.escape(table)}\b", text, re.I)
        ]
        assert ddl_hits, f"{lid}: no CREATE TABLE for {table} in db/schema"


def test_t9_home_deploy_tiles_rw_mount() -> None:
    text = HOME_DEPLOY.read_text(encoding="utf-8")
    assert "£" not in text
    # Scope to the tiles.build --all one-off block.
    marker = "api python -m tiles.build --all"
    assert marker in text
    before, _, after = text.partition(marker)
    block_start = before.rfind("```")
    assert block_start != -1
    block = before[block_start:] + marker + after[: after.find("```") + 3]
    assert ':/app/tiles-rw"' in block
    assert "TILES_DIR=/app/tiles-rw" in block
    assert ':/app/tiles"' not in block


def test_t10_build_all_skips_gated_pmtiles(monkeypatch: pytest.MonkeyPatch) -> None:
    mapping = {
        "repd": _RawEntry(
            "repd",
            {
                "id": "repd",
                "serve": {
                    "mode": "pmtiles",
                    "simplify_m": 0,
                    "precision_dp": 6,
                    "max_mb": 15,
                },
                "tiles": {
                    "budget": {"total_mb": 15, "tile_kb": 500, "z0_7_mb": 2}
                },
            },
        ),
        "secret-layer": _RawEntry(
            "secret-layer",
            {
                "id": "secret-layer",
                "serve": {
                    "mode": "pmtiles",
                    "simplify_m": 0,
                    "precision_dp": 6,
                    "max_mb": 15,
                },
                "tiles": {
                    "budget": {"total_mb": 15, "tile_kb": 500, "z0_7_mb": 2}
                },
                "gated_by": "NMPI_LICENCE",
            },
        ),
    }
    _install_entries(monkeypatch, mapping)
    built: list[str] = []

    def fake_build(layer_id: str, **_kwargs: Any) -> dict[str, Any]:
        built.append(layer_id)
        return {"id": layer_id}

    monkeypatch.setattr("tiles.build.build_tileset", fake_build)
    assert build_all() == ["repd"]
    assert built == ["repd"]
