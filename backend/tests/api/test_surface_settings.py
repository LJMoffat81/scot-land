"""Depreciation settings are read from Valuation's surface.yaml, not copied into the engine."""

from pathlib import Path

import pytest
import yaml

from georgist import surface_rent as sr
from georgist.surface_settings import SettingsError, depreciation_settings, yield_placeholder


def test_read_from_surface_yaml():
    raw = yaml.safe_load(Path(sr.CONFIG_PATH).read_text())["surface_rent"]["depreciation"]
    s = depreciation_settings()
    assert s["method"] == "compounding_v13"
    assert s["rate_building"] == {b: raw["rate_building"][b] for b in ("low", "central", "high")}
    assert s["age_cap_years"] == 68
    assert s["building_share_sb"] == pytest.approx(0.497)
    assert s["band_combination"]["rule"] == raw["band_combination"]["rule"]
    # life_years still present for the yield path
    assert s["life_years"] == {b: raw["life_years"][b] for b in ("low", "central", "high")}


def test_missing_keys_refused():
    with pytest.raises(SettingsError):
        depreciation_settings({"depreciation": {"life_years": {"low": 80, "central": 100}}})


def test_yield_placeholder_from_surface_yaml():
    raw = yaml.safe_load(Path(sr.CONFIG_PATH).read_text())["surface_rent"]["yield"]
    yp = yield_placeholder()
    central = float(raw.get("central", raw.get("land_yield")))
    assert yp["central"] == pytest.approx(central)
    assert yp["land_yield"] == pytest.approx(central)
    assert yp["status"] == "placeholder" and yp["owner"] == "Valuation"
    assert yp["source"] == "data/config/surface.yaml yield.central"
    assert "land_yield" not in raw  # bare land_yield: 0.05 removed
    assert abs(central - 0.05) > 1e-12
    assert yp["land_yield_band"] == [float(raw["band"]["low"]), float(raw["band"]["high"])]


def test_yield_placeholder_passes_band_when_configured():
    yp = yield_placeholder({"yield": {"central": 0.0399, "land_yield_band": [0.035, 0.045]}})
    assert yp["land_yield"] == pytest.approx(0.0399)
    assert yp["land_yield_band"] == [0.035, 0.045]


def test_yield_placeholder_passes_georgist_v3_signoff_when_configured():
    """Pass-through only — v3 values come from shared config when Valuation publishes them."""
    yp = yield_placeholder({
        "yield": {
            "central": 0.04499,
            "band": {"low": 0.0398, "high": 0.0450, "high_clipped_at_cap": True},
            "result_hash": "4654e513",
            "calibration_version": 3,
            "central_at_cap": True,
            "band_clipped_outer": True,
            "bed_mapping_sensitive": True,
            "components": {"r": 0.0262, "p": 0.0237, "g": 0.01},
        },
    })
    assert yp["land_yield"] == pytest.approx(0.04499)
    assert yp["central"] == pytest.approx(0.04499)
    assert yp["land_yield_band"] == [0.0398, 0.0450]
    assert yp["result_hash"] == "4654e513"
    assert yp["calibration_version"] == 3
    assert yp["central_at_cap"] is True
    assert yp["band_clipped_outer"] is True
    assert yp["bed_mapping_sensitive"] is True
    assert set(yp["flags"]) == {
        "central_at_cap", "band_clipped_outer", "bed_mapping_sensitive",
    }
    assert yp["status"] == "placeholder"


def test_no_copied_values_in_engine_code():
    root = Path(__file__).resolve().parents[2]
    for p in list((root / "georgist").glob("*.py")) + list((root / "api").glob("*.py")):
        if p.name.startswith("surface_") and p.name != "surface_settings.py":
            continue  # Valuation's own modules
        text = p.read_text()
        assert "life_years:" not in text and "remaining_min:" not in text, p
