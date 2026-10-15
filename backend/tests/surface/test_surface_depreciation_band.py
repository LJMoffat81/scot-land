"""v1.3 F7: compounding rate_building corners with the rebuild band. SYNTHETIC mixes."""

import itertools

import pytest

from georgist import surface_rent as sr

MIX = [
    sr.MixComponent("terraced", 0.4, 95.0, "before 1919"),
    sr.MixComponent("flat_purpose_built", 0.3, 60.0, "1965-1975"),
    sr.MixComponent("detached", 0.3, 140.0, "2008 onwards"),
]


def _drc(cfg, band, rebuild, rate):
    dep = sr.depreciation_at(cfg["depreciation"], rate=rate)
    return sr.depreciated_rebuild(
        MIX,
        rates_gbp_per_m2={t: b[rebuild] for t, b in band.items()},
        depreciation=dep,
        valuation_year=2025,
        region=1.0,
    ).drc_gbp


def test_config_keys_exposed_for_engine(cfg):
    dep = cfg["depreciation"]
    assert dep["method"] == "compounding_v13"
    assert dep["rate_building"]["low"] == pytest.approx(0.011179)
    assert dep["rate_building"]["high"] == 0.0
    assert dep["rate_building"]["central"] == pytest.approx(0.00137 / 0.497)
    assert dep["age_cap_years"] == 68
    assert dep["band_combination"]["rule"] == "corner"
    assert sr.depreciation_param(dep, "rate_building") == pytest.approx(0.00137 / 0.497)
    assert sr.depreciation_param(dep, "rate_building", "high") == 0.0


def test_corners_are_the_exact_extremes(cfg, band):
    rbs = sr.depreciated_rebuild_band(
        MIX, band=band, depreciation=cfg["depreciation"], valuation_year=2025, region=1.0
    )
    grid = [_drc(cfg, band, r, rate) for r, rate in itertools.product(sr.SCENARIOS, repeat=2)]
    assert rbs["high"].drc_gbp == pytest.approx(max(grid))
    assert rbs["low"].drc_gbp == pytest.approx(min(grid))
    assert rbs["high"].drc_gbp == pytest.approx(_drc(cfg, band, "high", "high"))  # maintained
    assert rbs["low"].drc_gbp == pytest.approx(_drc(cfg, band, "low", "low"))  # unmaintained
    assert rbs["central"].drc_gbp == pytest.approx(_drc(cfg, band, "central", "central"))


def test_land_value_low_pairs_high_rebuild_maintained(cfg, band):
    # Price high enough that even the maintained (high DRC) corner leaves positive land.
    P = 400_000.0
    rbs = sr.depreciated_rebuild_band(
        MIX, band=band, depreciation=cfg["depreciation"], valuation_year=2025, region=1.0
    )
    rb = sr.residual_band(P, rbs)
    assert rb.land_value_low == pytest.approx(max(0.0, P - _drc(cfg, band, "high", "high")))
    assert rb.land_value_high == pytest.approx(P - _drc(cfg, band, "low", "low"))
    assert rb.land_value_low < rb.central.land_value < rb.land_value_high


def test_wrong_direction_or_quadrature_rejected(cfg, band):
    dep = cfg["depreciation"]
    swapped = {
        **dep,
        "band_combination": {
            **dep["band_combination"],
            "drc_high_land_low": {"rebuild": "high", "rate_building": "low"},
        },
    }
    with pytest.raises(ValueError):
        sr.depreciated_rebuild_band(
            MIX, band=band, depreciation=swapped, valuation_year=2025, region=1.0
        )
    with pytest.raises(ValueError):
        sr.band_corners({**dep, "band_combination": {"rule": "quadrature"}})
    with pytest.raises(ValueError):
        # rate_building must be low >= central >= high
        sr.depreciation_param(
            {"rate_building": {"low": 0.0, "central": 0.002, "high": 0.01}}, "rate_building"
        )


def test_row_band_carries_depreciation(cfg, band):
    from .test_surface_output import _row

    row = _row(cfg, band)
    assert row["drc_low_gbp"] < row["drc_gbp"] < row["drc_high_gbp"]
    assert row["land_value_low"] <= row["land_value"] <= row["land_value_high"]
    assert row["uncertainty_low"] <= row["measured_rent"] <= row["uncertainty_high"]


def test_old_stock_capped_new_stock_moves_with_rate(cfg):
    dep = cfg["depreciation"]
    old = [
        sr.remaining_factor("before 1919", 2025, sr.depreciation_at(dep, rate=r))
        for r in sr.SCENARIOS
    ]
    # Cap at 68 for all three rate corners; maintained -> 1.0
    assert old[2] == pytest.approx(1.0)  # high = maintained
    assert old[0] < old[1] < old[2]  # unmaintained < central < maintained
    new = {r: sr.remaining_factor("2008 onwards", 2025, sr.depreciation_at(dep, rate=r)) for r in sr.SCENARIOS}
    assert new["low"] < new["central"] < new["high"]
    assert new["high"] == pytest.approx(1.0)
