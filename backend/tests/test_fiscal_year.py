from agr.config import load_config
from agr.fiscal_year import compare_gers, load_gers


def test_gers_2025_26_refreshes_the_half_of_income_rule_without_moving_the_signed_pool():
    config = load_config()
    snapshot = load_gers()
    result = compare_gers(snapshot, config)

    assert result["revenue_gbp"] == 98_262_000_000
    assert result["spending_gbp"] == 123_566_000_000
    assert result["net_fiscal_balance_gbp"] == -25_304_000_000
    assert result["signed_pool_gbp"] == 90_000_000_000
    assert result["rent_share_of_gdp"] == 0.50
    assert result["refreshed_rent_gbp"] == result["gdp_gbp"] * 0.50
    assert result["above_taxes_gbp"] > 0
    assert result["above_spending_gbp"] < 0
    assert "All Taxes Come Out of Rent" in result["atcor"]
    assert "no extra billion" in result["ebcor"]
    assert "margin" in result["ricardo"]
    assert config["macro"]["estimated_scotland_annual_rent_gbp"] == 90_000_000_000
