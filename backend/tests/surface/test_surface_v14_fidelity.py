"""v1.4 fidelity (F1–F4 + kickoff): synthetic only. No real RoS £ fixtures."""

from __future__ import annotations

import math

import pytest

from georgist import dz2022_fill as fill
from georgist import surface_rent as sr
from georgist import surface_v13 as v13
from georgist import surface_v14 as v14


def test_v14_config_keys_and_v13_untouched(cfg):
    assert cfg["depreciation"]["method"] == "compounding_v13"
    assert cfg["depreciation"]["rate_building"]["central"] == pytest.approx(0.002756539235412475)
    v = cfg["v14"]
    assert v["prereg_sha256_prefix"] == "e1ab6d0a"
    assert v["fidelity_fix_spec_sha256_prefix"] == "1694c8ad"
    assert v["gbp_display"] is False
    dep = v["depreciation"]
    assert dep["method"] == "straight_line_v14"
    assert dep["age_cap_years"] == 68
    assert dep["rate_building"] == {"low": 0.010, "central": 0.0035, "high": 0.0}
    assert dep["max_depreciation"] == {"low": 0.60, "central": 0.55, "high": 0.55}
    assert v["no_age_mix"]["central_remaining_factor"] == pytest.approx(0.762)
    assert cfg["rebuild_inputs"]["default_remaining_factor"] == 0.55


def test_f3_straight_line_v14_1957_band_at_2025(cfg):
    """1950-1964 midpoint 1957 → age_c 68 → 1 − 0.0035×68."""
    dep = v14.v14_depreciation(cfg)
    assert dep["method"] == "straight_line_v14"
    assert "rate_building" in dep  # must not force compounding
    rem = sr.remaining_factor("1950-1964", 2025, dep)
    assert rem == pytest.approx(1.0 - 0.0035 * 68)
    assert rem == pytest.approx(0.762)
    # Method-first: even with rate_building present, not compounding
    r_b = 0.0035
    assert rem != pytest.approx((1 - r_b) ** 68)


def test_f3_age_cap_and_max_depreciation_floor(cfg):
    dep = v14.v14_depreciation(cfg)
    # Age 100 still capped at 68 → same as 68; floor 0.45 not binding at central
    assert sr.remaining_factor("before 1919", 2025, dep) == pytest.approx(0.762)
    # High rate corner: 0.010 × 68 = 0.68 > 0.60 → floor binds at 0.40
    unmaint = sr.depreciation_at(dep, rate="low")
    assert sr.remaining_factor("before 1919", 2025, unmaint) == pytest.approx(0.40)


def test_no_age_mix_uses_central_not_055(cfg, band):
    dep = v14.v14_depreciation(cfg)
    inp = sr.ZoneRebuildInputs(
        type_shares={"terraced": 1.0},
        age_shares=None,
        floor_area_m2=90.0,
        floor_area_basis="mean",
        mix_basis="all_stock",
        source="test",
        tags=(),
    )
    # Caller still passes 0.55 (legacy surface default) — v14 must ignore it.
    out = sr.zone_rebuild_band(
        inp,
        band=band,
        depreciation=dep,
        valuation_year=2025,
        default_remaining_factor=0.55,
    )
    assert out["central"].remaining_factor == pytest.approx(0.762)
    assert v14.no_age_mix_remaining(cfg) == pytest.approx(0.762)
    assert cfg["rebuild_inputs"]["default_remaining_factor"] == 0.55


def test_f1_unavailable_in_1d_and_post_fill_gate():
    """Unavailable row counts in 1d n and n_at_0; gate does not raise."""
    rows = [
        {
            "code": "S01013401",
            "estimate_label": fill.ESTIMATE_UNAVAILABLE,
            "fill_method": "observed_pooled",
            "measured_rent": 0.0,
            "land_value": 0.0,
            "price_indexed_gbp": 200_000.0,
            "negative_residual": True,
            "publication_status": "blocked",
            "value_tier": "proxy",
            "proxy_tags": "model_fill_dz2022;estimate_label=unavailable",
        },
        {
            "code": "S01013402",
            "estimate_label": "measured",
            "fill_method": "observed_pooled",
            "measured_rent": 1000.0,
            "land_value": 40_000.0,
            "price_indexed_gbp": 200_000.0,
            "negative_residual": False,
            "publication_status": "blocked",
            "value_tier": "proxy",
            "proxy_tags": "model_fill_dz2022",
        },
    ]
    shares = v14.shares_for_gating(rows)
    assert shares[0] == 0.0
    assert shares[1] == pytest.approx(0.20)
    c1d = v13.check_1d_zero_mass(shares, max_share=0.10)
    assert c1d["n"] == 2
    assert c1d["n_at_0"] == 1
    # Conservation: same total on both vintages; unavailable kept in the set.
    rows_2011 = [
        {**rows[0], "code": "S01013401"},
        {**rows[1], "code": "S01013402"},
    ]
    fill.assert_post_fill_gate(rows_2011, rows)  # must not raise


def test_f1_negative_residual_tags_unavailable():
    neg = sr.residual_land_value(100_000.0, 150_000.0)
    assert neg.negative_residual is True
    assert sr.estimate_label_for_residual(neg) == "unavailable"
    assert f"estimate_label={sr.ESTIMATE_LABEL_UNAVAILABLE}" in neg.tags
    pos = sr.residual_land_value(200_000.0, 100_000.0)
    assert sr.estimate_label_for_residual(pos) is None


def test_f2_zero_residual_median_fails_check4():
    out = v13.check_4_two_route_gap(
        [0.1, -0.1, 0.0],
        residual_median=0.0,
    )
    assert out["status"] == "fail"
    assert out["pass"] is False
    assert out["reason"] == "residual_route_median_non_positive"

    via = v14.check_4_from_routes(
        residual_lands=[0.0, 0.0, 0.0],
        capitalised_lands=[100.0, 110.0, 90.0],
    )
    assert via["status"] == "fail"
    assert via["pass"] is False


def test_f2_non_finite_gap_fails():
    out = v13.check_4_two_route_gap([0.1, float("nan")], residual_median=50.0)
    assert out["status"] == "fail"
    assert out["reason"] == "non_finite_gap"
    gap = v13.two_route_relative_gap(10.0, 0.0)
    assert math.isnan(gap)


def test_f4_scorer_pins_and_no_switch(cfg):
    pins = v14.pin_frozen_inputs(cfg)
    assert pins["prereg_sha256_prefix"] == "e1ab6d0a"
    assert pins["fidelity_fix_spec_sha256_prefix"] == "1694c8ad"
    # Primary fails 1d (many zeros); secondary passes — must NOT publish secondary alone.
    primary = [0.0] * 3 + [0.25] * 7  # 30% at 0 → 1d fail
    secondary = [0.20] * 10
    scored = v14.score_estimators(
        primary_shares=primary, secondary_shares=secondary, cfg=cfg
    )
    assert scored["gbp_display"] is False
    assert scored["publication"]["never_switch_to_passing"] is True
    assert scored["publication"]["outcome"] == "primary_fail_secondary_pass_publish_neither_until_v15"
    assert scored["publication"]["publish_primary"] is False
    assert scored["publication"]["publish_secondary"] is False


def test_model_fill_n_computed_not_magic(cfg):
    n = fill.computed_model_fill_n(cfg)
    recon = cfg["dz2022_empty_fill"]["reconciled"]
    assert n == recon["suppressed_after_pooling_n"] + len(recon["not_in_price_file"])
    assert n == fill.null_dz_fill_target_from_config(cfg)
    facts = fill.reconciled_facts(cfg)
    assert facts["model_fill_n"] == n
