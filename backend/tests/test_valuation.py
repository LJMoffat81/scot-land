import pytest

from agr.areas import lookup_council
from agr.config import load_config
from agr.engine import calculate_square_agr
from agr.valuation import assess_for_agr_roll, residual_site_capital_per_sqm
from spatial.grid import snap_to_w3w_grid


def setup_function():
    load_config.cache_clear()


def test_edinburgh_residual_above_rural():
    edinburgh = lookup_council(55.9533, -3.1883)
    cairngorms = lookup_council(57.08, -3.65)

    ed_capital, _, _, _ = residual_site_capital_per_sqm(edinburgh)
    rural_capital, _, _, _ = residual_site_capital_per_sqm(cairngorms)

    assert edinburgh.rural is False
    assert cairngorms.rural is True
    assert ed_capital > rural_capital * 10


def test_urban_uses_residual_drc():
    edinburgh = lookup_council(55.9533, -3.1883)
    assessment = assess_for_agr_roll(edinburgh)

    assert assessment.method == "residual_drc"
    assert assessment.habu == "existing_residential"
    assert assessment.hope_value_excluded is True
    assert assessment.market_value_gbp is not None
    assert assessment.drc_improvements_gbp is not None
    assert assessment.rebuild_cost_new_gbp is not None
    # Residual: MV − DRC ≈ site (before clamp)
    assert assessment.site_capital_market_gbp > 0
    assert 0.15 <= (assessment.site_share_implied or 0) <= 0.85
    # Economic < market after Pickard urban factor
    assert assessment.site_capital_economic_per_sqm_gbp < assessment.site_capital_market_per_sqm_gbp
    # Rent is stored to 4 or 6 decimals and capital per m² is rounded, so allow 0.0001.
    assert assessment.annual_rent_economic_per_sqm_gbp == pytest.approx(
        assessment.site_capital_economic_per_sqm_gbp * assessment.yield_rate,
        abs=1.5e-4,
    )


def test_rural_uses_productive_path():
    cairngorms = lookup_council(57.08, -3.65)
    assessment = assess_for_agr_roll(cairngorms)

    assert assessment.method == "productive_land_use"
    assert assessment.habu == "existing_agriculture"
    assert assessment.pickard_label == "farmland_market_to_productive"
    assert assessment.pickard_factor == 0.20
    assert assessment.roll_annual_rent_notional_plot_gbp == 43.64


def test_edinburgh_agr_is_positive_and_reasonable():
    square = snap_to_w3w_grid(55.9533, -3.1883)
    breakdown = calculate_square_agr(square)

    assert breakdown.annual_ground_rent_gbp > 10
    assert breakdown.annual_ground_rent_gbp < 5000
    assert breakdown.method == "residual_drc"
    assert breakdown.council_code == "S12000036"
    assert breakdown.habu == "existing_residential"
    assert breakdown.drc_improvements_gbp is not None
    assert breakdown.roll_annual_rent_notional_plot_gbp > breakdown.annual_ground_rent_gbp
    assert "assessment" in breakdown_to_keys(breakdown)


def breakdown_to_keys(breakdown):
    from dataclasses import asdict

    return asdict(breakdown)


def test_notional_plot_scales_from_per_sqm():
    edinburgh = lookup_council(55.9533, -3.1883)
    assessment = assess_for_agr_roll(edinburgh)
    expected = assessment.roll_annual_rent_per_sqm_gbp * assessment.notional_plot_sqm
    assert abs(assessment.roll_annual_rent_notional_plot_gbp - expected) < 0.05
