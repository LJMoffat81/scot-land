"""ARCH-2a-1 registry tests R2-1..R2-15."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from layers.registry.loader import REGISTRY_DIR, RegistryError, load_registry

REGISTRY = REGISTRY_DIR


def _base(**over) -> dict:
    entry = {
        "id": "x",
        "title": "X",
        "geography": "scotland",
        "clip": "land+sea",
        "unit": "dz2022",
        "ladder_level": "dz2022",
        "nests": True,
        "licence": "OGL-3.0",
        "attribution": "Test attribution",
        "source": {
            "type": "postgis_table",
            "table": "dz_boundaries",
            "id_field": "code",
            "where": "vintage = 2022",
        },
        "geometry": "polygon",
        "refresh": {"cron": "0 5 1 * *", "max_mb": 300, "max_s": 600},
        "serve": {
            "mode": "pmtiles",
            "simplify_m": 0,
            "precision_dp": 6,
            "max_mb": 15,
        },
        "zoom": {"min": 0, "max": 14, "low_zoom": "keep_all"},
        "style": {},
        "legend": [],
        "lineage": {
            "derived_from": [],
            "method": "source",
            "roll_up_to": ["council", "scotland"],
        },
        "keep_fields": ["name"],
        "tiles": {"budget": {"total_mb": 60, "tile_kb": 500, "z0_7_mb": 4}},
    }
    entry.update(over)
    return entry


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "x.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return tmp_path


def _raises(tmp_path: Path, data: dict, msg: str) -> None:
    _write(tmp_path, data)
    with pytest.raises(RegistryError, match=re.escape(msg) + "$"):
        load_registry(tmp_path)


def test_r2_1_postgis_table_requires_table(tmp_path):
    data = _base()
    del data["source"]["table"]
    _raises(
        tmp_path,
        data,
        "REGISTRY: x: $.source: 'table' is a required property",
    )


def test_r2_2_postgis_table_forbids_url(tmp_path):
    data = _base()
    data["source"]["url"] = "https://example.com/x"
    _raises(
        tmp_path,
        data,
        "REGISTRY: x: $.source.url: not allowed for postgis_table",
    )


def test_r2_3_table_pattern(tmp_path):
    data = _base()
    data["source"]["table"] = "dz;drop"
    # jsonschema renders the pattern via !r, so the message contains \\.
    msg = (
        "REGISTRY: x: $.source.table: 'dz;drop' does not match "
        "'^[a-z_][a-z0-9_]*(\\\\.[a-z_][a-z0-9_]*)?$'"
    )
    _raises(tmp_path, data, msg)


def test_r2_4_id_field_type(tmp_path):
    data = _base()
    data["source"]["id_field"] = 7
    _raises(
        tmp_path,
        data,
        "REGISTRY: x: $.source.id_field: 7 is not of type 'string'",
    )


def test_r2_5_low_zoom_drop(tmp_path):
    data = _base()
    data["zoom"]["low_zoom"] = "drop"
    msg = (
        "REGISTRY: x: $.zoom.low_zoom: 'drop' is not one of "
        "['keep_all', 'simplify', 'coalesce', 'cluster', "
        "'aggregate:council', 'aggregate:dz2022']"
    )
    _raises(tmp_path, data, msg)


def test_r2_6_tile_kb_bool(tmp_path):
    data = _base()
    data["tiles"]["budget"]["tile_kb"] = True
    _raises(
        tmp_path,
        data,
        "REGISTRY: x: $.tiles.budget.tile_kb: True is not of type 'integer'",
    )


def test_r2_7_tile_kb_float(tmp_path):
    data = _base()
    data["tiles"]["budget"]["tile_kb"] = 512.5
    _raises(
        tmp_path,
        data,
        "REGISTRY: x: $.tiles.budget.tile_kb: 512.5 is not of type 'integer'",
    )


def test_r2_8_tile_kb_below_min(tmp_path):
    data = _base()
    data["tiles"]["budget"]["tile_kb"] = 0
    _raises(
        tmp_path,
        data,
        "REGISTRY: x: $.tiles.budget.tile_kb: 0 is less than the minimum of 1",
    )


def test_r2_9_tile_kb_above_max(tmp_path):
    data = _base()
    data["tiles"]["budget"]["tile_kb"] = 2048
    _raises(
        tmp_path,
        data,
        "REGISTRY: x: $.tiles.budget.tile_kb: 2048 is greater than the maximum of 1024",
    )


def test_r2_10_total_mb_string(tmp_path):
    data = _base()
    data["tiles"]["budget"]["total_mb"] = "60"
    _raises(
        tmp_path,
        data,
        "REGISTRY: x: $.tiles.budget.total_mb: '60' is not of type 'number'",
    )


def test_r2_11_budget_missing_z0_7_mb(tmp_path):
    data = _base()
    del data["tiles"]["budget"]["z0_7_mb"]
    _raises(
        tmp_path,
        data,
        "REGISTRY: x: $.tiles.budget: 'z0_7_mb' is a required property",
    )


def test_r2_12_tiles_unknown_key(tmp_path):
    data = _base()
    data["tiles"]["foo"] = 1
    _raises(
        tmp_path,
        data,
        "REGISTRY: x: $.tiles: Additional properties are not allowed "
        "('foo' was unexpected)",
    )


def test_r2_13_tiles_with_raster(tmp_path):
    data = _base()
    data["serve"]["mode"] = "raster"
    data["clip"] = "none"
    _raises(
        tmp_path,
        data,
        "REGISTRY: x: $.tiles: not allowed with serve.mode raster",
    )


def test_r2_14_keep_fields_non_string(tmp_path):
    data = _base()
    data["keep_fields"] = [5]
    _raises(
        tmp_path,
        data,
        "REGISTRY: x: $.keep_fields[0]: 5 is not of type 'string'",
    )


def test_r2_15_committed_tiled_entries():
    entries = load_registry(REGISTRY)
    tiled = sorted(eid for eid, e in entries.items() if "tiles" in e.raw)
    pmtiles = sorted(
        eid
        for eid, e in entries.items()
        if (e.raw.get("serve") or {}).get("mode") == "pmtiles"
    )
    expected = [
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
    assert tiled == expected
    assert pmtiles == expected
    assert tiled == pmtiles
    assert entries["oil-fields"].raw["keep_fields"] == [
        "FIELDNAME",
        "FIELDTYPE",
        "STATUS",
    ]
