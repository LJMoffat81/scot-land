"""ARCH-1a registry tests R1–R9, U1–U3, M13/M14/M22/M23 targets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from layers.registry.loader import RegistryError, load_registry

REGISTRY = Path(__file__).resolve().parents[1] / "layers" / "registry"
SCHEMA_PATH = REGISTRY / "schema.json"


def _base_entry(**over) -> dict:
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
    }
    entry.update(over)
    return entry


def _write_dir(tmp_path: Path, files: dict[str, dict]) -> Path:
    for name, data in files.items():
        (tmp_path / f"{name}.yaml").write_text(
            yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
        )
    return tmp_path


def test_r1_committed_registry_validates():
    entries = load_registry(REGISTRY)
    assert set(entries) >= {"oil-fields", "platforms", "pipelines"}
    assert entries["oil-fields"].raw["clip"] == "sea"
    assert entries["platforms"].raw["unit"] == "point"
    assert entries["pipelines"].raw["serve"]["simplify_m"] == 5
    assert entries["oil-fields"].raw["lineage"]["method"] == "source"


def test_r2_missing_clip(tmp_path):
    data = _base_entry()
    del data["clip"]
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(
        RegistryError,
        match=r"REGISTRY: sample: \$: 'clip' is a required property",
    ):
        load_registry(tmp_path)


def test_r3_unknown_top_level_field(tmp_path):
    data = _base_entry(foo="bar")
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(RegistryError, match=r"REGISTRY: sample:.*foo"):
        load_registry(tmp_path)


def test_r4_unknown_nested_source_field(tmp_path):
    data = _base_entry()
    data["source"] = dict(data["source"], bar="x")
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(
        RegistryError,
        match=r"REGISTRY: sample: \$\.source: Additional properties are not allowed "
        r"\('bar' was unexpected\)",
    ):
        load_registry(tmp_path)


def test_r5_licence_proprietary(tmp_path):
    data = _base_entry(licence="Proprietary")
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(RegistryError, match=r"REGISTRY: sample:.*licence"):
        load_registry(tmp_path)


def test_r6_clip_none_with_geojson(tmp_path):
    data = _base_entry(clip="none")
    data["serve"]["mode"] = "geojson"
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(
        RegistryError,
        match=r"REGISTRY: sample: \$\.clip: 'none' is only allowed with serve\.mode raster",
    ):
        load_registry(tmp_path)


def test_r7_zoom_min_not_zero(tmp_path):
    data = _base_entry()
    data["zoom"]["min"] = 8
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(RegistryError, match=r"REGISTRY: sample:.*zoom"):
        load_registry(tmp_path)


def test_r8_token_env_literal(tmp_path):
    data = _base_entry()
    data["source"]["token_env"] = "abc123-literal"
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(RegistryError, match=r"REGISTRY: sample:.*token_env"):
        load_registry(tmp_path)


def test_r9_http_url(tmp_path):
    data = _base_entry()
    data["source"]["url"] = "http://example.com/layer"
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(RegistryError, match=r"REGISTRY: sample:.*url"):
        load_registry(tmp_path)


def test_r_duplicate_id(tmp_path, monkeypatch):
    """Duplicate-id guard: id must equal file stem, so a real two-stem collision
    cannot pass validation. Exercise the branch by returning the same path twice.
    """
    a = _base_entry(id="dup")
    path = tmp_path / "dup.yaml"
    path.write_text(yaml.safe_dump(a), encoding="utf-8")
    real_glob = Path.glob

    def fake_glob(self, pattern):
        paths = list(real_glob(self, pattern))
        if self == tmp_path and pattern == "*.yaml" and paths:
            return [paths[0], paths[0]]
        return paths

    monkeypatch.setattr(Path, "glob", fake_glob)
    with pytest.raises(RegistryError, match=r"REGISTRY: duplicate id dup"):
        load_registry(tmp_path)


def test_u1_unit_ward_refused(tmp_path):
    data = _base_entry(unit="ward")
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(
        RegistryError,
        match=r"REGISTRY: sample: \$\.unit: 'ward' is not one of",
    ):
        load_registry(tmp_path)


def test_u2_unknown_derived_from(tmp_path):
    data = _base_entry()
    data["lineage"]["derived_from"] = ["nope"]
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(
        RegistryError,
        match=r"REGISTRY: sample: lineage\.derived_from: unknown layer nope",
    ):
        load_registry(tmp_path)


def test_u3_lineage_cycle(tmp_path):
    a = _base_entry(id="a", title="A")
    a["lineage"]["derived_from"] = ["b"]
    b = _base_entry(id="b", title="B")
    b["lineage"]["derived_from"] = ["a"]
    _write_dir(tmp_path, {"a": a, "b": b})
    with pytest.raises(
        RegistryError, match=r"REGISTRY: lineage cycle: a -> b -> a"
    ):
        load_registry(tmp_path)


def test_m22_missing_lineage(tmp_path):
    data = _base_entry()
    del data["lineage"]
    _write_dir(tmp_path, {"sample": data})
    with pytest.raises(RegistryError, match=r"REGISTRY: sample:"):
        load_registry(tmp_path)


def test_schema_additional_properties_false():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema.get("additionalProperties") is False
    assert schema["properties"]["source"]["additionalProperties"] is False
