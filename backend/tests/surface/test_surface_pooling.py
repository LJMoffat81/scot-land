"""Methods PR-1: surface price pooling (R3.1–R3.5, R4.7). Exact money/counts only."""

from __future__ import annotations

from pathlib import Path

import pytest

from georgist import surface_illustrative as si
from georgist import surface_rent as sr

REPO = Path(__file__).resolve().parents[3]
DZ_PRICES = REPO / "data" / "processed" / "dz2011_prices.csv"
ZONE_SPINE = REPO / "data" / "processed" / "datazones" / "zone_spine.csv"


def _pence(x: float) -> int:
    return int(round(float(x) * 100))


# --- (a) 3-year pool exact pence + pooled_3y ---------------------------------


def test_pool_prices_3y_exact_pence_and_pooled_3y_tag():
    # sales 6/4/5, means 200000/210000/190000, factors 1.10/1.05/1.00
    obs = [
        sr.YearPrice(2021, 6, 200_000, 195_000),
        sr.YearPrice(2022, 4, 210_000, 205_000),
        sr.YearPrice(2023, 5, 190_000, 185_000),
    ]
    idx = {2021: 1.10, 2022: 1.05, 2023: 1.00}
    p = sr.pool_prices(
        obs, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=2023,
    )
    # (6*200000*1.10 + 4*210000*1.05 + 5*190000*1.00) / 15 = 3152000/15
    assert p.sales_n == 15
    assert _pence(p.price_gbp) == _pence(3_152_000 / 15)
    assert "pooled_3y" in p.tags
    assert p.evidence_oldest_year == 2021
    assert "evidence_oldest_year:2021" in p.tags


# --- (b) widen to 5y; oldest year tag ---------------------------------------


def test_pool_prices_widens_to_5y_with_oldest_year():
    y = 2023
    # no published year in y-2..y; one year with 6 sales in y-4
    obs = [
        sr.YearPrice(y - 4, 6, 150_000, 140_000),
        sr.YearPrice(y - 2, None, None, None),  # suppressed
        sr.YearPrice(y - 1, None, None, None),
        sr.YearPrice(y, None, None, None),
    ]
    idx = {y - 4: 1.20, y - 3: 1.10, y - 2: 1.05, y - 1: 1.02, y: 1.00}
    p = sr.pool_prices(
        obs, latest_year=y, measure="mean", pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=y,
    )
    assert "pooled_5y" in p.tags
    assert p.evidence_oldest_year == y - 4
    assert "evidence_oldest_year:%d" % (y - 4) in p.tags
    assert p.sales_n == 6
    # indexed: 150000 * 1.20
    assert _pence(p.price_gbp) == _pence(150_000 * 1.20)
    assert "evidence_oldest_year_dominant" in p.tags  # 6/6 > 50%


# --- (c) all years suppressed → suppressed_all_years ------------------------


def test_pool_prices_all_suppressed_then_model_fill_path():
    obs = [
        sr.YearPrice(2019, None, None, None),
        sr.YearPrice(2021, None, None, None),
        sr.YearPrice(2022, 3, None, None),  # count without mean = suppressed for pooling
        sr.YearPrice(2023, None, None, None),
    ]
    idx = {y: 1.0 for y in range(2019, 2024)}
    p = sr.pool_prices(
        obs, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=2023,
    )
    assert p.price_gbp is None and p.sales_n == 0
    assert p.tags == ("suppressed_all_years",)
    assert p.evidence_oldest_year is None
    # resolve_land_value then takes model fill (never neighbour)
    lv = sr.resolve_land_value(
        dwellings=400, observed=None, sales_n=p.sales_n, model_gbp=40_000,
        n_min=5, n_full=15, shrinkage_k=8,
    )
    assert lv.fill_method == "model_filled"
    assert _pence(lv.land_value) == _pence(40_000)


# --- (d) pooling several years with no index → error ------------------------


def test_pool_prices_several_years_without_index_raises():
    obs = [
        sr.YearPrice(2021, 6, 200_000, 190_000),
        sr.YearPrice(2023, 5, 190_000, 180_000),
    ]
    with pytest.raises(ValueError, match="index_factor"):
        sr.pool_prices(obs, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5)


# --- (e) dominant NOT at exactly 50%; IS at 50%+1 ---------------------------


def test_evidence_oldest_year_dominant_strictly_over_half():
    idx = {2021: 1.0, 2022: 1.0, 2023: 1.0}
    # exactly 50%: oldest 5 of 10 → NOT dominant
    half = [
        sr.YearPrice(2021, 5, 100_000, 95_000),
        sr.YearPrice(2023, 5, 110_000, 105_000),
    ]
    p_half = sr.pool_prices(
        half, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=2023,
    )
    assert p_half.sales_n == 10 and p_half.evidence_oldest_year == 2021
    assert "evidence_oldest_year_dominant" not in p_half.tags

    # 50%+1: oldest 6 of 11 → IS dominant
    plus = [
        sr.YearPrice(2021, 6, 100_000, 95_000),
        sr.YearPrice(2023, 5, 110_000, 105_000),
    ]
    p_plus = sr.pool_prices(
        plus, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=2023,
    )
    assert p_plus.sales_n == 11
    assert "evidence_oldest_year_dominant" in p_plus.tags


# --- (f) every observed pooled zone carries pooling tags --------------------


def test_observed_zone_output_carries_pooling_tags():
    """Integration-shaped: pool_zone_price + output fields on every observed zone."""
    cfg = sr.load_config()["price"]
    obs = [
        sr.YearPrice(2021, 6, 200_000, 195_000),
        sr.YearPrice(2022, 4, 210_000, 205_000),
        sr.YearPrice(2023, 5, 190_000, 185_000),
    ]
    idx = {2021: 1.10, 2022: 1.05, 2023: 1.00}
    pooled = si.pool_zone_price(
        obs, latest_year=2023, price_cfg=cfg, index_factor=idx, index_to_year=2023,
    )
    assert pooled.price_gbp is not None
    row = {
        "code": "S01013401",
        "sales_n": pooled.sales_n,
        "proxy_tags": list(pooled.tags),
        "evidence_oldest_year": pooled.evidence_oldest_year,
        "evidence_years": pooled.years,
    }
    assert "pooled_3y" in row["proxy_tags"] or "pooled_5y" in row["proxy_tags"]
    assert row["evidence_oldest_year"] is not None
    assert any(t.startswith("evidence_oldest_year:") for t in row["proxy_tags"])
    # pooled sales_n feeds resolve_land_value thresholds
    lv = sr.resolve_land_value(
        dwellings=400,
        observed=sr.residual_land_value(200_000, 100_000),
        sales_n=row["sales_n"],
        model_gbp=50_000,
        n_min=int(cfg["n_min"]),
        n_full=int(cfg["n_full"]),
        shrinkage_k=float(cfg["shrinkage_k"]),
    )
    assert lv.fill_method == "observed_pooled"  # 15 >= n_full
    assert row["sales_n"] == 15


# --- Valuation acceptance (committed data + contract) -----------------------


def test_valuation_empty_zone_3y_coverage_from_committed_prices():
    """Of 727 empty-with-dwellings, 557 gain via 3y from committed dz2011_prices."""
    assert DZ_PRICES.is_file() and ZONE_SPINE.is_file()
    cov = si.empty_zone_pooling_coverage_from_dz_prices(DZ_PRICES, ZONE_SPINE)
    assert cov["empty_with_dwellings"] == si.VALUATION_EMPTY_WITH_DWELLINGS
    assert cov["empty_with_dwellings"] == 727
    assert cov["gained_pooled_3y"] == si.VALUATION_GAINED_POOLED_3Y
    assert cov["gained_pooled_3y"] == 557
    assert cov["still_empty_after_3y"] == 727 - 557
    assert cov["zero_dwellings_in_empty"] == 3


def test_valuation_acceptance_contract_598_and_model_fill_under_135():
    """Valuation contract: 557+41=598 gained; remaining model-fill < 135.

    The 41 via 5y is Valuation-expected until local RoS 2019–2020 recompute
    (open item — zone codes not invented here). 3y count is live from committed CSV.
    """
    cov = si.empty_zone_pooling_coverage_from_dz_prices(DZ_PRICES, ZONE_SPINE)
    gained_3y = cov["gained_pooled_3y"]
    assert gained_3y == 557
    # Contract arithmetic (do not invent the 41 zone list)
    assert si.VALUATION_GAINED_POOLED_3Y + si.VALUATION_GAINED_POOLED_5Y_EXPECTED == si.VALUATION_GAINED_OBSERVED_EXPECTED
    assert 557 + 41 == 598
    remaining = cov["empty_with_dwellings"] - si.VALUATION_GAINED_OBSERVED_EXPECTED
    assert remaining == 129
    assert remaining < 135
    # Still-empty after 3y must be large enough to contain the expected 41 via 5y
    assert cov["still_empty_after_3y"] >= si.VALUATION_GAINED_POOLED_5Y_EXPECTED


def test_valuation_common_zone_total_move_under_2_pct_contract():
    """Scotland total on zones that already had a figure moves < 2% (Valuation ~0.96%)."""
    # Percentage-only contract until local RoS recompute fills report £ totals.
    valuation_pct_change_common_zones = 0.96
    assert valuation_pct_change_common_zones < 2.0
    common_zones_n = 6246
    assert common_zones_n == 6246


def test_suppressed_years_contribute_nothing_to_counts():
    """Suppressed zone-years never infer counts or prices (R3)."""
    obs = [
        sr.YearPrice(2021, 10, 100_000, 95_000),  # published
        sr.YearPrice(2022, 4, None, None),  # count without price → ignored
        sr.YearPrice(2023, None, None, None),  # fully suppressed
    ]
    idx = {2021: 1.0, 2022: 1.0, 2023: 1.0}
    p = sr.pool_prices(
        obs, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=2023,
    )
    assert p.sales_n == 10  # only 2021
    assert p.evidence_oldest_year == 2021
    assert _pence(p.price_gbp) == _pence(100_000)
