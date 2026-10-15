import pytest

from georgist import surface_rent as sr


def test_remaining_factor_compounding_v13(cfg):
    dep = cfg["depreciation"]
    r = 0.00137 / 0.497
    assert sr.remaining_factor("before 1919", 2025, dep) == pytest.approx((1 - r) ** 68)
    assert sr.remaining_factor("2008 onwards", 2025, dep) == pytest.approx((1 - r) ** 9)
    with pytest.raises(KeyError):
        sr.remaining_factor("not a band", 2025, dep)


def test_depreciated_rebuild_mix_weighted(cfg, rates):
    mix = [
        sr.MixComponent("detached", 0.5, 100.0, "2008 onwards"),
        sr.MixComponent("flat_purpose_built", 0.5, 60.0, "before 1919"),
    ]
    out = sr.depreciated_rebuild(mix, rates_gbp_per_m2=rates, depreciation=cfg["depreciation"], valuation_year=2025, region=1.0)
    new_d, new_f = 100 * 2000, 60 * 1900
    r = 0.00137 / 0.497
    rem_new, rem_old = (1 - r) ** 9, (1 - r) ** 68
    assert out.rebuild_new_gbp == pytest.approx(0.5 * new_d + 0.5 * new_f)
    assert out.drc_gbp == pytest.approx(0.5 * new_d * rem_new + 0.5 * new_f * rem_old)
    with pytest.raises(ValueError):
        sr.depreciated_rebuild(mix[:1], rates_gbp_per_m2=rates, depreciation=cfg["depreciation"], valuation_year=2025, region=1.0)


def test_residual_floor_keeps_raw_and_flags():
    pos = sr.residual_land_value(150_000, 100_000)
    assert (pos.land_value, pos.negative_residual) == (50_000, False)
    neg = sr.residual_land_value(80_000, 120_000)
    assert neg.land_value == 0.0 and neg.raw_residual == -40_000
    assert neg.negative_residual is True and "negative_residual" in neg.tags
    assert sr.COST_AT_OR_ABOVE_PRICE_TAG in neg.tags  # FILL-MEASURED-ZERO internal tag
    eq = sr.residual_land_value(100_000, 100_000)
    assert eq.negative_residual is False  # zero is not negative
    assert sr.COST_AT_OR_ABOVE_PRICE_TAG in eq.tags


def test_band_runs_low_central_high_rebuild(cfg, band):
    mix = [sr.MixComponent("semi_detached", 1.0, 90.0, "1965-1975")]
    rbs = sr.depreciated_rebuild_band(mix, band=band, depreciation=cfg["depreciation"], valuation_year=2025, region=1.0)
    assert rbs["low"].drc_gbp < rbs["central"].drc_gbp < rbs["high"].drc_gbp
    rb = sr.residual_band(150_000, rbs)
    assert rb.land_value_low < rb.central.land_value < rb.land_value_high  # low rebuild -> high land
    assert rb.land_value_high == pytest.approx(150_000 - rbs["low"].drc_gbp)
    tight = sr.residual_band(rbs["central"].drc_gbp + 1000, rbs)
    assert tight.land_value_low == 0.0 and "negative_under_high_rebuild" in tight.tags


def test_pool_prices_widens_then_suppresses():
    obs = [
        sr.YearPrice(2019, 3, 100_000, 95_000),
        sr.YearPrice(2021, None, None, None),  # suppressed: absent, not zero
        sr.YearPrice(2022, 2, 120_000, 110_000),
        sr.YearPrice(2023, 2, 130_000, 125_000),
    ]
    idx = {2019: 1.0, 2020: 1.0, 2021: 1.0, 2022: 1.0, 2023: 1.0}  # SYNTHETIC flat index
    kw = dict(latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5, index_factor=idx, index_to_year=2023)
    p = sr.pool_prices(obs, **kw)
    assert p.evidence_year == 2023
    assert p.sales_n == 7
    assert p.evidence_oldest_year == 2019
    assert "pooled_5y" in p.tags and "evidence_oldest_year:2019" in p.tags
    # 3/7 < 50% → not dominant
    assert "evidence_oldest_year_dominant" not in p.tags
    # Exact pence: (3*100000 + 2*120000 + 2*130000) / 7 = 800000/7
    assert round(p.price_gbp, 2) == round(800_000 / 7, 2)
    none = sr.pool_prices(obs[1:2], **kw)
    assert none.price_gbp is None and "suppressed_all_years" in none.tags
    med = sr.pool_prices(obs, **dict(kw, measure="median"))
    assert "pooled_median_approx" in med.tags
    with pytest.raises(ValueError):  # rules 2: no mixing price years unindexed
        sr.pool_prices(obs, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5)
    with pytest.raises(ValueError):
        sr.pool_prices(obs, **dict(kw, index_to_year=None))


def test_observed_total_uses_mean_same_vintage_and_year():
    kw = dict(mean_price_gbp=150_000, dwellings=400, price_vintage=2011, dwellings_vintage=2011, price_year=2023, dwellings_year=2023)
    assert sr.observed_total_value(**kw) == 60_000_000
    with pytest.raises(sr.VintageMismatchError):
        sr.observed_total_value(**dict(kw, dwellings_vintage=2022))
    with pytest.raises(sr.YearMismatchError):
        sr.observed_total_value(**dict(kw, dwellings_year=2022))
    with pytest.raises(ValueError):
        sr.observed_total_value(**dict(kw, measure="median"))


def test_dwellings_exact_year_never_nearest():
    counts = {("S01013401", 2011, 2022): 400, ("S01013401", 2011, 2024): 410}  # SYNTHETIC
    assert sr.dwellings_for(counts, "S01013401", 2011, 2022).count == 400
    gap = sr.dwellings_for(counts, "S01013401", 2011, 2023)
    assert gap.count is None and "dwellings_missing_year" in gap.tags
    assert sr.dwellings_for(counts, "S01013401", 2022, 2022).count is None


def test_rebuild_mix_prefers_sold_homes():
    sold = [sr.MixComponent("detached", 1.0, 120.0, "2008 onwards")]
    stock = [sr.MixComponent("terraced", 1.0, 80.0, "1950-1964")]
    assert sr.choose_rebuild_mix(sold, stock, sold_records=6, min_sold_records=5) == (sold, "sold")
    assert sr.choose_rebuild_mix(sold, stock, sold_records=2, min_sold_records=5) == (stock, "all_stock")
    assert sr.choose_rebuild_mix(None, stock, sold_records=0, min_sold_records=5)[1] == "all_stock"
    with pytest.raises(ValueError):
        sr.choose_rebuild_mix(None, None, sold_records=0, min_sold_records=5)


def test_price_skew_flag(cfg):
    """Methods M2: pooled mean ÷ count-weighted pooled median; pooled sales_n. Exact pins."""
    sk = cfg["price"]["skew_flag"]
    assert sk["mean_median_ratio_min"] == 1.40
    assert sk["small_sales_n_below"] == 15
    # 1.40 with 14 sales → flagged; 1.40 with 15 → not; 1.399 with 14 → not
    assert sr.price_skew_flag(140_000, 100_000, 14, sk) == (1.4, True)
    assert sr.price_skew_flag(140_000, 100_000, 15, sk) == (1.4, False)
    assert sr.price_skew_flag(139_900, 100_000, 14, sk) == (1.399, False)
    # Prior coverage retained
    assert sr.price_skew_flag(300_000, 150_000, 8, sk) == (2.0, True)
    assert sr.price_skew_flag(300_000, 150_000, 40, sk)[1] is False
    assert sr.price_skew_flag(160_000, 150_000, 8, sk)[1] is False
    assert sr.price_skew_flag(None, 150_000, 8, sk) == (None, False)


def test_price_skew_flag_uses_pooled_mean_and_count_weighted_median(cfg):
    """Ratio inputs are pool_prices(mean) / pool_prices(median) with shared pooled sales_n."""
    obs = [
        sr.YearPrice(2021, 6, 200_000, 150_000),
        sr.YearPrice(2022, 4, 220_000, 160_000),
        sr.YearPrice(2023, 4, 180_000, 140_000),
    ]
    idx = {2021: 1.0, 2022: 1.0, 2023: 1.0}
    kw = dict(
        observations=obs, latest_year=2023, pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=2023,
    )
    pooled_mean = sr.pool_prices(**kw, measure="mean")
    pooled_med = sr.pool_prices(**kw, measure="median")
    assert pooled_mean.sales_n == pooled_med.sales_n == 14
    expected = pooled_mean.price_gbp / pooled_med.price_gbp
    ratio, flag = sr.price_skew_flag(
        pooled_mean.price_gbp, pooled_med.price_gbp, pooled_mean.sales_n, cfg["price"]["skew_flag"],
    )
    assert ratio == expected
    assert flag == (expected >= 1.40)  # 14 < 15


def test_suppressed_zone_needs_model_never_neighbour():
    kw = dict(n_min=5, n_full=15, shrinkage_k=8)
    with pytest.raises(ValueError):
        sr.resolve_land_value(dwellings=400, observed=None, sales_n=0, model_gbp=None, **kw)
    assert sr.resolve_land_value(dwellings=400, observed=None, sales_n=0, model_gbp=40_000, **kw).fill_method == "model_filled"
    thin = sr.resolve_land_value(dwellings=400, observed=sr.residual_land_value(100_000, 60_000), sales_n=8, model_gbp=20_000, **kw)
    assert thin.fill_method == "shrunk_to_model"
    assert thin.land_value == pytest.approx((8 * 40_000 + 8 * 20_000) / 16)
    assert sr.resolve_land_value(dwellings=0, observed=None, sales_n=0, model_gbp=None, **kw).fill_method == "no_residential"


def test_forbidden_drivers_rejected(cfg):
    sr.validate_drivers(["bus_accessibility", "broadband", "crime_vandalism"], cfg)
    for bad in ("simd_income_rank", "employment_rate", "deprivation_decile", "simd_rank"):
        with pytest.raises(sr.ForbiddenDriverError):
            sr.validate_drivers(["broadband", bad], cfg)


def test_reconciliation_ceiling():
    ok = sr.reconciliation_check(module_rents={"surface": (900, 1000, 1100)}, observed_total_value_gbp=30_000, gross_yield_value=0.05)
    assert ok.ok and ok.ceiling_rent_gbp == pytest.approx(1500)
    bad = sr.reconciliation_check(
        module_rents={"surface": (900, 1000, 1100), "extractive": (700, 800, 900)}, observed_total_value_gbp=30_000, gross_yield_value=0.05
    )
    assert not bad.ok


def _syn_hpi():  # SYNTHETIC council index points, not real UK HPI values
    return sr.CouncilHPI(
        "S12999999", "2023", "2025-04",
        base_index={"all": 100.0, "detached": 100.0, "semi_detached": 100.0, "terraced": 100.0, "flat": 100.0},
        target_index={"all": 110.0, "detached": 110.0, "semi_detached": 108.0, "terraced": 105.0, "flat": 104.0},
        base_price={"all": 200_000, "detached": 400_000, "semi_detached": 250_000, "terraced": 180_000, "flat": 120_000},
    )


def test_hpi_factor_by_type_value_weighted_else_all():
    h = _syn_hpi()
    f, series, tags = sr.hpi_factor(h, {"detached": 0.5, "flat": 0.5})
    assert f == pytest.approx((0.5 * 400_000 * 1.10 + 0.5 * 120_000 * 1.04) / (0.5 * 400_000 + 0.5 * 120_000))
    assert "type indices" in series and "hpi_by_property_type" in tags and "indexed_council_hpi" in tags
    f_all, series_all, tags_all = sr.hpi_factor(h, None)
    assert f_all == pytest.approx(1.10) and "all-dwellings" in series_all and "hpi_all_dwellings" in tags_all
    assert sr.hpi_factor(h, {"detached": 0, "flat": 0})[0] == pytest.approx(1.10)  # unknown mix -> all-dwellings


def test_index_price_keeps_raw():
    pooled = sr.PooledPrice(100_000, 20, "2023-2023", "mean", (), 2023)
    f, series, tags = sr.hpi_factor(_syn_hpi(), None)
    ip = sr.index_price(pooled, price_year=2025, factor=f, series=series, tags=tags)
    assert ip.price_raw_gbp == 100_000 and ip.evidence_year == 2023
    assert ip.price_indexed_gbp == pytest.approx(110_000) and ip.price_year == 2025
    assert pooled.price_gbp == 100_000  # untouched


def test_base_alignment_policy():
    kw = dict(price_year=2025, rebuild_base_year=2025, price_vintage=2011, dwelling_vintage=2011)
    assert sr.assert_base_alignment(dwelling_year=2025, **kw) == 0
    with pytest.raises(sr.YearMismatchError):
        sr.assert_base_alignment(dwelling_year=2024, **kw)  # strict default
    assert sr.assert_base_alignment(dwelling_year=2024, policy="lag_allowed", max_lag_years=1, **kw) == 1
    with pytest.raises(sr.YearMismatchError):
        sr.assert_base_alignment(dwelling_year=2025, **dict(kw, rebuild_base_year=2024))
    with pytest.raises(ValueError):
        sr.assert_base_alignment(dwelling_year=2025, policy="nearest", **kw)
