"""ARCH-2b-r3a G3 — clip_keep_all required (boolean) for polygon registry entries."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from layers.registry.loader import REGISTRY_DIR, RegistryError, load_registry

REGISTRY = REGISTRY_DIR


def _polygon_base(**over) -> dict:
    entry = {
        "id": "sample",
        "title": "Sample",
        "geography": "scotland",
        "clip": "sea",
        "unit": "none",
        "licence": "NSTA-OGL",
        "attribution": "Test attribution",
        "source": {
            "type": "arcgis",
            "url": "https://example.com/FeatureServer/0/query",
            "where": "1=1",
        },
        "geometry": "polygon",
        "refresh": {"cron": "0 4 * * 1", "max_mb": 10, "max_s": 60},
        "serve": {
            "mode": "geojson",
            "simplify_m": 0,
            "precision_dp": 6,
            "max_mb": 15,
        },
        "zoom": {"min": 0, "max": 14, "low_zoom": "simplify"},
        "style": {},
        "legend": [],
        "lineage": {
            "derived_from": [],
            "method": "source",
            "roll_up_to": [],
        },
        "clip_keep_all": False,
    }
    entry.update(over)
    return entry


def _write_dir(tmp_path: Path, files: dict[str, dict]) -> Path:
    for name, data in files.items():
        (tmp_path / f"{name}.yaml").write_text(
            yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
        )
    return tmp_path


def test_g3a_polygon_missing_clip_keep_all_raises(tmp_path):
    data = _polygon_base()
    del data["clip_keep_all"]
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(
        RegistryError,
        match=r"REGISTRY: sample: \$: 'clip_keep_all' is a required property",
    ):
        load_registry(tmp_path)


def test_g3b_clip_keep_all_string_raises(tmp_path):
    data = _polygon_base(clip_keep_all="true")
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(
        RegistryError,
        match=r"REGISTRY: sample: \$\.clip_keep_all: 'true' is not of type 'boolean'",
    ):
        load_registry(tmp_path)


def test_g3b_clip_keep_all_integer_raises(tmp_path):
    data = _polygon_base(clip_keep_all=1)
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(
        RegistryError,
        match=r"REGISTRY: sample: \$\.clip_keep_all: 1 is not of type 'boolean'",
    ):
        load_registry(tmp_path)


def test_g3c_shipped_polygons_have_clip_keep_all_and_dz2022_true():
    entries = load_registry(REGISTRY)
    polygons = {
        eid: e for eid, e in entries.items() if e.raw.get("geometry") == "polygon"
    }
    assert polygons, "expected at least one shipped polygon registry entry"
    for eid, entry in polygons.items():
        assert "clip_keep_all" in entry.raw, f"{eid} missing clip_keep_all"
        assert isinstance(entry.raw["clip_keep_all"], bool), (
            f"{eid} clip_keep_all must be boolean"
        )
    assert entries["dz2022"].raw["clip_keep_all"] is True
