import pytest

from georgist import surface_rent as sr


def test_gross_and_land_yield(cfg):
    g = sr.gross_yield(800, 160_000)
    assert g == pytest.approx(0.06)
    y = sr.land_yield(g, building_share=0.5, deductions=cfg["yield"]["deductions"], life_years=cfg["depreciation"]["life_years"])
    assert y == pytest.approx(0.06 * 0.96 * 0.75 - 0.5 / 100)
    assert y < g  # rules 6.4


def test_mix_weighted_rent_same_mix():
    rent = {"1": 600.0, "2": 800.0, "3": 1000.0}  # SYNTHETIC
    assert sr.mix_weighted(rent, {"1": 0.2, "2": 0.5, "3": 0.3}) == pytest.approx(820.0)
    with pytest.raises(KeyError):
        sr.mix_weighted(rent, {"4": 1.0})


def _cell(cfg, cell_y, brma_y, prs_n=100, price_n=100, gross=None):
    return sr.resolve_cell_yield(
        brma_id="SYN-B", ur6_class=6, cell_y=cell_y, prs_n=prs_n, price_n=price_n,
        brma_wide_y=brma_y, yield_cfg=cfg["yield"], cell_gross=gross,
    )


def test_class_cap_bounds_and_flags(cfg):
    hi = _cell(cfg, 0.09, 0.04)
    assert hi.y_land == pytest.approx(1.4 * 0.04) and "yield_class_capped" in hi.tags
    lo = _cell(cfg, 0.01, 0.04)
    assert lo.y_land == pytest.approx(0.7 * 0.04) and "yield_class_capped" in lo.tags
    ok = _cell(cfg, 0.045, 0.04)
    assert ok.y_land == 0.045 and ok.tags == ()


def test_land_yield_not_below_gross_flagged(cfg):
    assert "land_yield_not_below_gross" in _cell(cfg, 0.05, 0.05, gross=0.05).tags


def test_fallback_chain(cfg):
    thin = _cell(cfg, 0.05, 0.04, prs_n=3)
    assert thin.source == "brma_wide" and thin.y_land == 0.04
    none = _cell(cfg, None, None)
    assert none.source == "config_fallback" and none.y_land == sr.configured_land_yield(cfg["yield"])


def test_blend_weights_sum_to_one():
    cells = {"A": sr.YieldCell("A", 1, 0.04, "cell"), "B": sr.YieldCell("B", 1, 0.06, "brma_wide", ("yield_fallback:brma",))}
    z = sr.blend_zone_yield({"A": 0.25, "B": 0.75}, cells)
    assert z.y_land == pytest.approx(0.25 * 0.04 + 0.75 * 0.06)
    assert "yield_fallback:brma" in z.tags and sum(z.brma_mix.values()) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        sr.blend_zone_yield({"A": 0.3, "B": 0.6}, cells)
    with pytest.raises(KeyError):
        sr.blend_zone_yield({"A": 0.5, "C": 0.5}, cells)


def test_rent_route_equals_sales_route_when_same_cell(cfg):
    """Documents why check 12.1 is weak: same-cell rent and yield make the routes identical."""
    d, life = cfg["yield"]["deductions"], cfg["depreciation"]["life_years"]
    P, drc, rent = 160_000.0, 70_000.0, 800.0
    y = sr.land_yield(sr.gross_yield(rent, P), building_share=drc / P, deductions=d, life_years=life)
    assert sr.rent_route_land_value(monthly_rent_gbp=rent, drc_gbp=drc, y_land=y, deductions=d, life_years=life) == pytest.approx(P - drc)


def test_land_yield_is_single_config_figure(cfg):
    y = sr.configured_land_yield(cfg["yield"])
    assert y == pytest.approx(cfg["yield"]["central"])
    assert abs(y - 0.05) > 1e-12
    for k in ("r", "g"):
        bad = dict(cfg["yield"], **{k: 0.07})
        with pytest.raises(sr.YieldIdentityError):
            sr.configured_land_yield(bad)
    missing = {k: v for k, v in cfg["yield"].items() if k not in ("central", "land_yield")}
    with pytest.raises(sr.PendingSourceError):
        sr.configured_land_yield(missing)
    # Legacy land_yield key still accepted when central absent.
    assert sr.configured_land_yield({"land_yield": 0.04}) == pytest.approx(0.04)


def test_scenario_r_g_must_equal_land_yield(cfg):
    y = sr.configured_land_yield(cfg["yield"])
    assert sr.scenario_r_g(cfg["scenarios"]["illustrative_r_g"], y) == (0.06499, 0.02)
    with pytest.raises(sr.YieldIdentityError):
        sr.scenario_r_g({"r": 0.08, "g": 0.02}, y)
    assert sr.capital_value(500.0, y) == pytest.approx(500.0 / y)
    assert sr.capital_value(500.0, y, scenario={"r": 0.06499, "g": 0.02}) == pytest.approx(500.0 / y)
    with pytest.raises(sr.YieldIdentityError):
        sr.capital_value(500.0, y, scenario={"r": 0.06, "g": 0.02})
