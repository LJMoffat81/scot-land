"""Smoke tests for restored valuer residual roll (agr.valuation)."""

from __future__ import annotations

from agr.areas import CouncilArea
from agr.config import load_config
from agr.valuation import assess_for_agr_roll


def _glasgow() -> CouncilArea:
    return CouncilArea(
        code="S12000049",
        name="Glasgow City",
        average_price_gbp=180_000,
        annual_change_pct=2.0,
        rural=False,
        distance_km=0.0,
        lookup_method="test",
    )


def test_urban_residual_returns_positive_rent():
    assessment = assess_for_agr_roll(_glasgow(), load_config())
    assert assessment.annual_rent_economic_per_sqm_gbp > 0
    assert assessment.market_value_gbp is not None
    assert assessment.hope_value_excluded is True


def test_rural_productive_path():
    rural = CouncilArea(
        code="S12000017",
        name="Highland",
        average_price_gbp=0,
        annual_change_pct=None,
        rural=True,
        distance_km=0.0,
        lookup_method="test",
    )
    assessment = assess_for_agr_roll(rural, load_config())
    assert "agricult" in assessment.habu.lower() or assessment.method == "productive_land_use"
    assert assessment.annual_rent_economic_per_sqm_gbp >= 0
