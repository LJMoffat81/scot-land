"""Rules 6.2 (v0.6): depreciation life/floor bands combined with the rebuild band by CORNERS. SYNTHETIC mixes."""

import itertools

import pytest

from georgist import surface_rent as sr

MIX = [sr.MixComponent("terraced", 0.4, 95.0, "before 1919"), sr.MixComponent("flat_purpose_built", 0.3, 60.0, "1965-1975"),
       sr.MixComponent("detached", 0.3, 140.0, "2008 onwards")]


def _drc(cfg, band, rebuild, life, floor):
    dep = sr.depreciation_at(cfg["depreciation"], life=life, floor=floor)
    return sr.depreciated_rebuild(MIX, rates_gbp_per_m2={t: b[rebuild] for t, b in band.items()}, depreciation=dep,
                                  valuation_year=2025, region=1.0).drc_gbp


def test_config_keys_exposed_for_engine(cfg):
    dep = cfg["depreciation"]
    assert dep["life_years"] == {"low": 80, "central": 100, "high": 120}
    assert dep["remaining_min"] == {"low": 0.20, "central": 0.30, "high": 0.40}
    assert dep["band_combination"]["rule"] == "corner"
    assert sr.depreciation_param(dep, "life_years") == 100 and sr.depreciation_param(dep, "remaining_min", "high") == 0.40


def test_corners_are_the_exact_extremes(cfg, band):
    rbs = sr.depreciated_rebuild_band(MIX, band=band, depreciation=cfg["depreciation"], valuation_year=2025, region=1.0)
    grid = [_drc(cfg, band, r, l, f) for r, l, f in itertools.product(sr.SCENARIOS, repeat=3)]
    assert rbs["high"].drc_gbp == pytest.approx(max(grid)) and rbs["low"].drc_gbp == pytest.approx(min(grid))
    assert rbs["high"].drc_gbp == pytest.approx(_drc(cfg, band, "high", "high", "high"))   # high rebuild, 120 y, 0.40
    assert rbs["low"].drc_gbp == pytest.approx(_drc(cfg, band, "low", "low", "low"))       # low rebuild, 80 y, 0.20
    assert rbs["central"].drc_gbp == pytest.approx(_drc(cfg, band, "central", "central", "central"))


def test_land_value_low_pairs_high_rebuild_long_life_high_floor(cfg, band):
    P = 150_000.0
    rbs = sr.depreciated_rebuild_band(MIX, band=band, depreciation=cfg["depreciation"], valuation_year=2025, region=1.0)
    rb = sr.residual_band(P, rbs)
    assert rb.land_value_low == pytest.approx(max(0.0, P - _drc(cfg, band, "high", "high", "high")))
    assert rb.land_value_high == pytest.approx(P - _drc(cfg, band, "low", "low", "low"))
    # wider than the rebuild band alone, and wider than quadrature would give
    scalar = {**cfg["depreciation"], "life_years": 100, "remaining_min": 0.30}
    only = sr.residual_band(P, sr.depreciated_rebuild_band(MIX, band=band, depreciation=scalar, valuation_year=2025, region=1.0))
    assert rb.land_value_low < only.land_value_low and rb.land_value_high > only.land_value_high
    c = rb.central.raw_residual
    d_reb = (only.raw_by_rebuild["central"] - only.raw_by_rebuild["high"])
    d_dep = c - (P - _drc(cfg, band, "central", "high", "high"))
    assert c - rb.raw_by_rebuild["high"] > (d_reb ** 2 + d_dep ** 2) ** 0.5   # corner, not quadrature


def test_wrong_direction_or_quadrature_rejected(cfg, band):
    dep = cfg["depreciation"]
    swapped = {**dep, "band_combination": {**dep["band_combination"], "drc_high_land_low": {"rebuild": "high", "life_years": "low", "remaining_min": "low"}}}
    with pytest.raises(ValueError):
        sr.depreciated_rebuild_band(MIX, band=band, depreciation=swapped, valuation_year=2025, region=1.0)
    with pytest.raises(ValueError):
        sr.band_corners({**dep, "band_combination": {"rule": "quadrature"}})
    with pytest.raises(ValueError):
        sr.depreciation_param({"life_years": {"low": 120, "central": 100, "high": 80}}, "life_years")


def test_row_band_carries_depreciation(cfg, band):
    from .test_surface_output import _row
    row = _row(cfg, band)
    assert row["drc_low_gbp"] < row["drc_gbp"] < row["drc_high_gbp"]
    assert row["land_value_low"] <= row["land_value"] <= row["land_value_high"]
    assert row["uncertainty_low"] <= row["measured_rent"] <= row["uncertainty_high"]


def test_old_stock_moves_with_floor_new_stock_with_life(cfg):
    dep = cfg["depreciation"]
    old = [sr.remaining_factor("before 1919", 2025, sr.depreciation_at(dep, life=l, floor=f)) for l in sr.SCENARIOS for f in sr.SCENARIOS]
    assert sorted(set(round(x, 6) for x in old)) == [0.2, 0.3, 0.4]   # pre-1919 is on the floor at every life
    new = {l: sr.remaining_factor("2008 onwards", 2025, sr.depreciation_at(dep, life=l)) for l in sr.SCENARIOS}
    assert new["low"] < new["central"] < new["high"] and new["low"] == pytest.approx(1 - 9 / 80)
