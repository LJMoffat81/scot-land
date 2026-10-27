"""MAP-VISION-1b: Backend registry tests for default_on and W-1b-1 dz2022 legend labels."""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml

from layers.registry.loader import REGISTRY_DIR, RegistryError, load_registry

_BARE_NUM_RE = re.compile(r"^\d+([.,]\d+)?$")

_EXPECTED_DZ2022_LEGEND = [
    {"label": "Up to 10 people per km²", "color": "#eff3ff"},
    {"label": "10–100 people per km²", "color": "#bdd7e7"},
    {"label": "100–500 people per km²", "color": "#6baed6"},
    {"label": "500–1,500 people per km²", "color": "#3182bd"},
    {"label": "1,500–3,000+ people per km²", "color": "#08519c"},
    {"label": "No value", "color": "#d9d9d9"},
]


def test_dz2022_and_councils_default_on_and_w1b1_legend() -> None:
    entries = load_registry(REGISTRY_DIR)
    assert entries["dz2022"].raw.get("default_on") is True
    assert entries["councils"].raw.get("default_on") is False
    assert entries["dz2022"].raw["legend"] == _EXPECTED_DZ2022_LEGEND


def test_no_registry_yaml_has_bare_numeric_legend_label() -> None:
    entries = load_registry(REGISTRY_DIR)
    for eid, entry in sorted(entries.items()):
        legend = entry.raw.get("legend") or []
        assert len(legend) >= 1, f"{eid} must have at least one legend item"
        for item in legend:
            label = str(item.get("label") or "").strip()
            assert label, f"{eid} has empty legend label"
            assert not _BARE_NUM_RE.fullmatch(label), (
                f"{eid} has bare numeric legend label {label!r}"
            )


@pytest.mark.parametrize("bad_val", [None, 0, 1, 1.5, "true", [], {}])
def test_registry_schema_rejects_non_boolean_default_on(
    tmp_path, bad_val: Any
) -> None:
    base = yaml.safe_load(
        (REGISTRY_DIR / "councils.yaml").read_text(encoding="utf-8")
    )
    base["id"] = "x"
    base["default_on"] = bad_val
    (tmp_path / "x.yaml").write_text(
        yaml.safe_dump(base, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(
        RegistryError,
        match=r"^REGISTRY: x: \$\.default_on: .* is not of type 'boolean'$",
    ):
        load_registry(tmp_path)
