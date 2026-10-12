"""Depreciation settings are read from Valuation's surface.yaml, not copied into the engine."""

from pathlib import Path

import pytest
import yaml

from georgist import surface_rent as sr
from georgist.surface_settings import SettingsError, depreciation_settings, yield_placeholder


def test_read_from_surface_yaml():
    raw = yaml.safe_load(Path(sr.CONFIG_PATH).read_text())["surface_rent"]["depreciation"]
    s = depreciation_settings()
    assert s["life_years"] == {b: raw["life_years"][b] for b in ("low", "central", "high")}
    assert s["remaining_min"] == {b: raw["remaining_min"][b] for b in ("low", "central", "high")}
    assert s["band_combination"]["rule"] == raw["band_combination"]["rule"]


def test_missing_keys_refused():
    with pytest.raises(SettingsError):
        depreciation_settings({"depreciation": {"life_years": {"low": 80, "central": 100}}})


def test_yield_placeholder_from_surface_yaml():
    raw = yaml.safe_load(Path(sr.CONFIG_PATH).read_text())["surface_rent"]["yield"]
    yp = yield_placeholder()
    assert yp["land_yield"] == pytest.approx(float(raw["land_yield"]))
    assert yp["status"] == "placeholder" and yp["owner"] == "Valuation"
    assert yp["source"] == "data/config/surface.yaml yield.land_yield"
    if "land_yield_band" not in raw:
        assert "land_yield_band" not in yp


def test_yield_placeholder_passes_band_when_configured():
    yp = yield_placeholder({"yield": {"land_yield": 0.0399, "land_yield_band": [0.035, 0.045]}})
    assert yp["land_yield"] == pytest.approx(0.0399)
    assert yp["land_yield_band"] == [0.035, 0.045]


def test_yield_placeholder_passes_georgist_signoff_metadata_when_configured():
    """Pass-through only — values come from shared config when Valuation's yield PR lands."""
    yp = yield_placeholder({
        "yield": {
            "land_yield": 0.0399,
            "land_yield_band": [0.0352, 0.0450],
            "clipped_at_cap": True,
            "result_hash": "b3442d47",
            "components": {"r": 0.0262, "p": 0.0237, "g": 0.01},
        },
    })
    assert yp["land_yield"] == pytest.approx(0.0399)
    assert yp["land_yield_band"] == [0.0352, 0.0450]
    assert yp["clipped_at_cap"] is True
    assert yp["result_hash"] == "b3442d47"
    assert yp["components"] == {"r": 0.0262, "p": 0.0237, "g": 0.01}
    assert yp["status"] == "placeholder"


def test_no_copied_values_in_engine_code():
    root = Path(__file__).resolve().parents[2]
    for p in list((root / "georgist").glob("*.py")) + list((root / "api").glob("*.py")):
        if p.name.startswith("surface_") and p.name != "surface_settings.py":
            continue  # Valuation's own modules
        text = p.read_text()
        assert "life_years:" not in text and "remaining_min:" not in text, p
