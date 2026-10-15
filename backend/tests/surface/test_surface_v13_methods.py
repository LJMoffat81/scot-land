"""v1.3 methods: synthetic formula and gate tests. No real RoS £ fixtures."""

from __future__ import annotations

import pytest

from georgist import surface_rent as sr
from georgist import surface_v13 as v13


def test_prereg_sha_pinned(cfg):
    assert v13.assert_prereg_sha(cfg) == v13.PREREG_SHA256
    assert cfg["v13"]["prereg_sha256"] == "ce9404455134c3dd96828bdc200832629a2c4e8932ad4bea2438e7a938907ead"


def test_oncost_1425_replaces_not_stacked(cfg):
    rebuild = cfg["rebuild"]
    assert sr.oncost_factor_v13(rebuild) == pytest.approx(1.425)
    # 1 + 0.125 + 0.25 + 0.05
    assert 1 + 0.125 + 0.25 + 0.05 == pytest.approx(1.425)
    replace = sr.oncost_replace_factor(rebuild)
    assert replace == pytest.approx(1.425 / 1.15)
    # Never 1.15 × 1.425 (stacked would be ~1.639; replace factor is ~1.239)
    assert replace == pytest.approx(1.425 / 1.15)
    assert replace != pytest.approx(1.15 * 1.425)
    assert 1.15 * 1.425 == pytest.approx(1.63875)
    assert replace < 1.3
    # Published on_costs match the additive factor (de-embedded).
    assert rebuild["factors"]["on_costs"]["central"] == pytest.approx(1.425)
    derived = sr.derive_rebuild_band(rebuild)
    assert derived["terraced"]["central"] == rebuild["gbp_per_m2"]["terraced"]["central"]


def test_oncost_sensitivities_default_off(cfg):
    rebuild = cfg["rebuild"]
    assert sr.oncost_factor_v13(rebuild, externals=0.15) == pytest.approx(1.325)
    assert sr.oncost_factor_v13(rebuild, contingency=0.025) == pytest.approx(1.400)
    assert sr.oncost_factor_v13(rebuild, contingency=0.15) == pytest.approx(1.525)
    assert sr.oncost_factor_v13(rebuild, demolition=0.15) == pytest.approx(1.575)
    # Central still excludes demolition
    assert rebuild["factors"]["on_costs_v13"]["demolition"] == 0.0


def test_flat_gia_110_houses_unchanged(cfg):
    assert sr.flat_gia_factor(cfg) == pytest.approx(1.10)
    inp = sr.ZoneRebuildInputs(
        type_shares={"terraced": 0.5, "flat_purpose_built": 0.5},
        age_shares={"2008 onwards": 1.0},
        floor_area_m2=80.0,
        floor_area_basis="mean",
        mix_basis="all_stock",
        source="test",
        tags=(),
        area_by_group={"house": 100.0, "flat": 60.0},
    )
    assert inp.area_for("terraced", flat_gia=1.10) == 100.0
    assert inp.area_for("flat_purpose_built", flat_gia=1.10) == 66.0
    assert inp.area_for("flat_purpose_built", flat_gia=1.0) == 60.0


def test_age_cap_68_and_depreciation_factors(cfg):
    dep = cfg["depreciation"]
    assert dep["method"] == "compounding_v13"
    assert dep["age_cap_years"] == 68
    # Cap binds for pre-1950 bands
    assert sr.capped_age("before 1919", 2025, dep) == 68
    assert sr.capped_age("1919-1929", 2025, dep) == 68
    assert sr.capped_age("1930-1949", 2025, dep) == 68
    assert sr.capped_age("1950-1964", 2025, dep) == 68
    assert sr.capped_age("2008 onwards", 2025, dep) == 9
    r = 0.00137 / 0.497
    assert sr.building_rate(sr.depreciation_at(dep)) == pytest.approx(r)
    # Spec: 0.829 / 0.883 / 0.946 at ages 68 / 45 / 20
    assert (1 - r) ** 68 == pytest.approx(0.829, abs=0.001)
    assert (1 - r) ** 45 == pytest.approx(0.883, abs=0.001)
    assert (1 - r) ** 20 == pytest.approx(0.946, abs=0.001)
    assert sr.remaining_factor("before 1919", 2025, dep) == pytest.approx((1 - r) ** 68)
    # 1984-1991 midpoint 1988 -> age 37; use a band that gives ~20 and ~45 via midpoint
    # Direct: remaining at central rate for age 20 / 45 via temporary midpoint override
    dep20 = {**dep, "age_band_midpoint_year": {**dep["age_band_midpoint_year"], "2008 onwards": 2005}}
    assert sr.remaining_factor("2008 onwards", 2025, dep20) == pytest.approx((1 - r) ** 20)
    dep45 = {**dep, "age_band_midpoint_year": {**dep["age_band_midpoint_year"], "1965-1975": 1980}}
    assert sr.remaining_factor("1965-1975", 2025, dep45) == pytest.approx((1 - r) ** 45)


def test_depreciation_band_ends_maintained_unmaintained(cfg):
    dep = cfg["depreciation"]
    maint = sr.depreciation_at(dep, rate="high")
    unmaint = sr.depreciation_at(dep, rate="low")
    assert sr.building_rate(maint) == 0.0
    assert sr.remaining_factor("before 1919", 2025, maint) == 1.0
    assert sr.building_rate(unmaint) == pytest.approx(0.011179)
    assert sr.remaining_factor("before 1919", 2025, unmaint) == pytest.approx((1 - 0.011179) ** 68)


def test_check_1d_zero_mass_gate_at_10_pct():
    # 10% at bound -> pass; >10% -> fail
    shares_ok = [0.0] + [0.2] * 9  # 10% at 0
    out_ok = v13.check_1d_zero_mass(shares_ok, max_share=0.10)
    assert out_ok["pass"] is True and out_ok["share_at_bound"] == pytest.approx(0.10)
    shares_fail = [0.0] * 2 + [0.2] * 8  # 20% at 0
    out_fail = v13.check_1d_zero_mass(shares_fail, max_share=0.10)
    assert out_fail["pass"] is False
    assert out_fail["info_1e_zones_at_0"] == 2


def test_check_1_band_10_to_40(cfg):
    assert cfg["land_share_checks"]["national_range"] == [0.10, 0.40]
    assert v13.check_1_median_land_share([0.2, 0.3, 0.25], band=(0.10, 0.40))["pass"] is True
    assert v13.check_1_median_land_share([0.0, 0.0, 0.0], band=(0.10, 0.40))["pass"] is False


def test_check_3_30m_decides_fragile_flag():
    # 30 m passes; 20 m passes; 40 m fails -> FRAGILE, but 30 m decides pass
    zones = [{"pass_at": {20: True, 30: True, 40: False}} for _ in range(10)]
    out = v13.check_3_plot_comparison(zones, decide_radius_m=30, report_radii_m=(20, 40), min_pass_share=0.80)
    assert out["pass"] is True and out["fragile"] is True
    # 30 m fails -> fail regardless of fragility
    zones_fail = [{"pass_at": {20: True, 30: False, 40: False}} for _ in range(10)]
    out2 = v13.check_3_plot_comparison(zones_fail)
    assert out2["pass"] is False


def test_check4_plus4_mapping_and_factor():
    assert v13.map_bedroom_band_to_rent_beds("4+") == "4 Bedroom"
    rents = {"1 Bedroom": 500.0, "2 Bedroom": 600.0, "3 Bedroom": 700.0, "4 Bedroom": 800.0}
    shares = {"1": 0.25, "2": 0.25, "3": 0.25, "4+": 0.25}
    base = v13.expected_rent_for_zone(shares, rents, ur6_class=1, plus4_factor=1.15)
    # class 1: no ×1.15
    assert base == pytest.approx(0.25 * (500 + 600 + 700 + 800))
    rural = v13.expected_rent_for_zone(shares, rents, ur6_class=5, plus4_factor=1.15)
    assert rural == pytest.approx(0.25 * (500 + 600 + 700 + 800 * 1.15))
    sens = v13.expected_rent_for_zone(shares, rents, ur6_class=5, plus4_factor=1.00)
    assert sens == pytest.approx(base)


def test_price_year_label(cfg):
    assert sr.price_year_label(cfg) == "2025-04 indexed"
    assert v13.holdout_gating_label(cfg) == "temporal holdout, seen in v1.2, not out-of-sample"


def test_rural_uplift_f6(cfg):
    assert sr.rural_uplift_factor(cfg, 1) == 1.0
    assert sr.rural_uplift_factor(cfg, 5) == pytest.approx(1.064)
    assert sr.rural_uplift_factor(cfg, 6) == pytest.approx(1.224)


def test_corners_use_rate_building(cfg, band):
    mix = [sr.MixComponent("terraced", 1.0, 90.0, "before 1919")]
    rbs = sr.depreciated_rebuild_band(
        mix, band=band, depreciation=cfg["depreciation"], valuation_year=2025, region=1.0
    )
    # Unmaintained (low) => lower remaining => lower DRC; maintained (high) => higher DRC
    assert rbs["low"].drc_gbp < rbs["central"].drc_gbp < rbs["high"].drc_gbp
    assert rbs["high"].remaining_factor == pytest.approx(1.0)
