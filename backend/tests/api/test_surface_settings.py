"""Depreciation settings are read from Valuation's surface.yaml, not copied into the engine."""

from pathlib import Path

import pytest
import yaml

from georgist import surface_rent as sr
from georgist.surface_settings import SettingsError, depreciation_settings


def test_read_from_surface_yaml():
    raw = yaml.safe_load(Path(sr.CONFIG_PATH).read_text())["surface_rent"]["depreciation"]
    s = depreciation_settings()
    assert s["life_years"] == {b: raw["life_years"][b] for b in ("low", "central", "high")}
    assert s["remaining_min"] == {b: raw["remaining_min"][b] for b in ("low", "central", "high")}
    assert s["band_combination"]["rule"] == raw["band_combination"]["rule"]


def test_missing_keys_refused():
    with pytest.raises(SettingsError):
        depreciation_settings({"depreciation": {"life_years": {"low": 80, "central": 100}}})


def test_no_copied_values_in_engine_code():
    root = Path(__file__).resolve().parents[2]
    for p in list((root / "georgist").glob("*.py")) + list((root / "api").glob("*.py")):
        if p.name.startswith("surface_") and p.name != "surface_settings.py":
            continue  # Valuation's own modules
        text = p.read_text()
        assert "life_years:" not in text and "remaining_min:" not in text, p
