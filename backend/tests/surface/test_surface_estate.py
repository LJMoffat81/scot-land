"""Rules 6.2 v0.7 estate rate, Georgist guard (weighted parcel bands, never a driver),
one-at-a-time swings, central-only plausibility and the plot-size diagnostic. SYNTHETIC data only."""

import random

import pytest

from georgist import surface_holdout as ho
from georgist import surface_rent as sr


@pytest.fixture(scope="module")
def cfg():
    return sr.load_config()


def _inp(det=0.6, ages=None):
    ts = {**dict.fromkeys(sr.DWELLING_TYPES, 0.0), "detached": det, "terraced": 1 - det}
    return sr.ZoneRebuildInputs(ts, ages or {"1992-1998": 0.5, "before 1919": 0.5}, 100.0, "mean", "all_stock",
                                "epc_all_time", (), {"house": 110.0, "flat": 60.0})


_COLS = sr.load_config()["estate"]["columns"]


def _row(lt, mid, gt, med=0.04):
    """SYNTHETIC GIS dz_detached_plot_bands row (all_ages cohort)."""
    return {"code": "S01013401", "vintage": 2011, _COLS["lt"]: lt, _COLS["mid"]: mid, _COLS["gt"]: gt,
            _COLS["median_parcel_ha"]: med}


def test_estate_rate_basis_generic_estate_same_band(cfg):
    band = sr.rebuild_band(cfg)
    assert band["detached_estate"]["central"] < band["detached"]["central"]
    e = cfg["estate"]
    assert e["status"] == "APPROVED_GENERIC_ESTATE" and "page 1, Table 1" in e["rate_source"]
    rb = sr.rate_basis(cfg)
    assert rb["detached_estate"] == "generic_estate" and set(rb) == set(cfg["rebuild"]["gbp_per_m2"])
    assert all(v in sr.RATE_BASES for v in rb.values()) and rb["semi_detached"] == "bcis_median_type"
    # same band construction as the other rates: base rows x the shared factors
    f = cfg["rebuild"]["factors"]
    rows = cfg["rebuild"]["base_rows_gbp_per_m2"]["detached_estate"]
    assert cfg["rebuild"]["gbp_per_m2"]["detached_estate"]["low"] == round(min(rows) * f["location_scotland"]["low"] * f["on_costs"]["low"])
    assert cfg["rebuild"]["gbp_per_m2"]["detached_estate"]["high"] == round(max(rows) * f["location_scotland"]["high"] * f["on_costs"]["high"])
    tags = sr.with_estate(_inp(), cfg["estate"], mode="epc_age_upper_bound").tags
    assert "rate_basis=generic_estate" in tags and not any("estate_rate_generic" in t for t in tags)


def test_rate_basis_must_be_declared(cfg):
    import copy
    bad = copy.deepcopy(cfg)
    del bad["rebuild"]["rate_basis"]["terraced"]
    with pytest.raises(ValueError):
        sr.rate_basis(bad)
    bad = copy.deepcopy(cfg)
    bad["rebuild"]["rate_basis"]["detached_estate"] = "bcis_median_type"
    with pytest.raises(ValueError):
        sr.rebuild_band(bad)
    assert cfg["rebuild"]["base_rows_gbp_per_m2"]["detached_estate"] == [1718, 1461, 1562]


def test_weighted_blend_not_hard_cutoff(cfg):
    ec = cfg["estate"]
    assert sr.estate_fraction(_row(1, 0, 0), ec)[0] == 1.0
    assert sr.estate_fraction(_row(0, 0, 1), ec)[0] == 0.0
    assert sr.estate_fraction(_row(0, 1, 0), ec)[0] == pytest.approx(0.5)
    assert sr.estate_fraction(_row(0.5, 0.3, 0.2), ec)[0] == pytest.approx(0.5 + 0.15)
    assert sr.estate_fraction(_row(0.5, 0.3, 0.2), ec, mid_weight=0.0)[0] == pytest.approx(0.5)
    assert sr.estate_fraction(_row(0.5, 0.3, 0.2), ec, mid_weight=1.0)[0] == pytest.approx(0.8)


def test_blank_or_missing_falls_back_pending(cfg):
    ec = cfg["estate"]
    e, tags = sr.estate_fraction(_row(None, None, None), ec)
    assert e is None and "estate_share_pending" in tags
    with pytest.raises(sr.PendingSourceError):   # rules 22c35eba: blank never falls back silently
        sr.with_estate(_inp(), ec, mode="plot_bands", estate_row=None)
    assert "estate_share_pending" in sr.with_estate(_inp(), ec, mode="pending").tags


def test_split_applies_only_to_post1980_detached(cfg):
    band = sr.rebuild_band(cfg)
    dep = cfg["depreciation"]
    base = sr.with_estate(_inp(), cfg["estate"], mode="pending")
    ub = sr.with_estate(_inp(), cfg["estate"], mode="epc_age_upper_bound")
    assert "estate_upper_bound_epc_age_only" in ub.tags
    r0 = sr.zone_rebuild_band(base, band=band, depreciation=dep, valuation_year=2025)["central"]
    r1 = sr.zone_rebuild_band(ub, band=band, depreciation=dep, valuation_year=2025)["central"]
    # post-1980 detached -> estate rate; the rest of detached -> one-off rate (non-estate share)
    diff = 0.6 * 0.5 * 110 * (band["detached"]["central"] - band["detached_estate"]["central"]) \
        + 0.6 * 0.5 * 110 * (band["detached"]["central"] - band["detached_one_off"]["central"])
    assert r0.rebuild_new_gbp - r1.rebuild_new_gbp == pytest.approx(diff)
    assert "oneoff_rate=detached_one_off" in ub.tags and "oneoff_rate=detached_one_off" not in base.tags
    pre = _inp(ages={"before 1919": 1.0})
    a = sr.zone_rebuild_band(sr.with_estate(pre, cfg["estate"], mode="epc_age_upper_bound"), band=band, depreciation=dep, valuation_year=2025)
    b = sr.zone_rebuild_band(pre, band=band, depreciation=dep, valuation_year=2025)
    assert a["central"].rebuild_new_gbp - b["central"].rebuild_new_gbp == pytest.approx(
        0.6 * 110 * (band["detached_one_off"]["central"] - band["detached"]["central"]))
    generic = sr.with_estate(pre, {**cfg["estate"], "oneoff_rate_type": "detached"}, mode="epc_age_upper_bound")
    g = sr.zone_rebuild_band(generic, band=band, depreciation=dep, valuation_year=2025)
    assert g["central"].drc_gbp == pytest.approx(b["central"].drc_gbp)
    with pytest.raises(ValueError):
        sr.with_estate(pre, {**cfg["estate"], "oneoff_rate_type": "semi_detached"}, mode="epc_age_upper_bound")
    straddle = _inp(ages={"1976-1983": 1.0})   # straddles 1980 -> kept on the one-off/blended rate
    assert "1976-1983" not in cfg["estate"]["post_1980_bands"]
    assert sr.oneoff_detached_share(sr.with_estate(straddle, cfg["estate"], mode="epc_age_upper_bound")) == pytest.approx(0.6)
    assert sr.oneoff_detached_share(ub) == pytest.approx(0.3)


def test_plot_size_never_a_driver(cfg):
    for d in ("median_parcel_ha", "plot_size_ha", "post1980_share_lt005", "all_ages_share_lt005", "all_ages_median_parcel_ha",
              "estate_share", "parcel_band_mix", "share_gt010"):
        with pytest.raises(sr.ForbiddenDriverError):
            sr.validate_drivers([d], cfg)
    assert sr.validate_drivers(cfg["drivers"]["allowed"], cfg)
    assert cfg["estate"]["never_a_driver"] is True


def test_one_at_a_time_swings(cfg):
    band = sr.rebuild_band(cfg)
    dep = cfg["depreciation"]
    inp = _inp()
    sw = sr.one_at_a_time_drc(inp, band=band, depreciation=dep, valuation_year=2025)
    assert set(sw) == {"central"} | {f"{p}_{l}" for p in sr.SWING_PARAMS for l in ("low", "high")}
    corners = sr.zone_rebuild_band(inp, band=band, depreciation=dep, valuation_year=2025)
    assert sw["central"] == pytest.approx(corners["central"].drc_gbp)
    for p in sr.SWING_PARAMS:
        assert sw[f"{p}_low"] <= sw["central"] <= sw[f"{p}_high"]
        assert corners["low"].drc_gbp <= sw[f"{p}_low"] and sw[f"{p}_high"] <= corners["high"].drc_gbp
    assert "drc_swing_gbp" in sr.INTERNAL_ONLY_COLUMNS and "drc_swing_gbp" in sr.OUTPUT_COLUMNS


def _zones(share, neg):
    return [{"land_value": share * 100, "mean_price": 100, "dwellings": 1, "ur6_class": 1 + i % 2,
             "negative_residual": i < neg} for i in range(100)]


def test_plausibility_central_decides_corners_stress():
    kw = dict(plausible_range=[0.49, 0.73], tolerance=0.10, high_demand_ur6=[1, 2], max_share_high_demand=0.10)
    r = ho.plausibility_checks({"central": _zones(0.62, 2), "low": _zones(0.40, 2), "high": _zones(0.78, 30)}, **kw)
    assert r["pass"] is True and r["decided_on"] == "central"
    assert r["corners_stress"]["low"]["status"] == "stress_inside"
    assert r["corners_stress"]["high"]["status"] == "stress_outside"
    r2 = ho.plausibility_checks({"central": _zones(0.30, 2), "low": _zones(0.6, 0), "high": _zones(0.6, 0)}, **kw)
    assert r2["pass"] is False and r2["status"] == "fail"
    with pytest.raises(ValueError):
        ho.plausibility_checks({"low": _zones(0.6, 0)}, **kw)


def _diag_data(rate_effect_only):
    rnd = random.Random(1)
    zones, land, est = [], [], []
    for i in range(80):
        code = f"S0101{3400 + i}"
        parcel = rnd.uniform(0.02, 0.2)
        loc = rnd.uniform(0.8, 1.2) * 40_000
        uniform = loc if rate_effect_only else loc * (0.3 / parcel) ** 0.5
        actual = uniform - 60_000 * parcel     # higher one-off rate on big plots lowers land value
        oneoff = min(1.0, parcel / 0.2)
        zones.append({"code": code, "vintage": 2011, "ur6_class": 1, "fill_method": "observed_pooled", "sales_n": 20,
                      "dwellings": 400, "observed_land_value": actual, "observed_land_value_uniform_rate": uniform,
                      "oneoff_share": oneoff})
        land.append({"code": code, "vintage": 2011, "residential_land_ha": 20.0, "method": "parcel_based"})
        est.append(_row(None, None, None, med=parcel) | {"code": code})
    return zones, land, est


def test_plot_size_diagnostic_flags_rate_only_dip(cfg):
    cols = cfg["estate"]["columns"]
    z, land, est = _diag_data(True)
    r = ho.plot_size_rate_diagnostic(z, residential_land_rows=land, estate_rows=est, estate_columns=cols)
    assert r["status"] == "flagged" and (1, "median_parcel_ha") in r["flagged"] and r["publish_level"] == "internal"
    c = r["classes"][1]["median_parcel_ha"]
    assert c["rho_actual"] <= -0.10 < c["rho_uniform_rate"]
    z, land, est = _diag_data(False)   # big plots lower under the uniform rate too: location, not the rate
    r = ho.plot_size_rate_diagnostic(z, residential_land_rows=land, estate_rows=est, estate_columns=cols)
    assert r["status"] == "ok" and not r["flagged"]


def test_plot_size_diagnostic_pending_and_insufficient(cfg):
    cols = cfg["estate"]["columns"]
    z, land, est = _diag_data(True)
    assert ho.plot_size_rate_diagnostic(z, residential_land_rows=None, estate_rows=est, estate_columns=cols)["status"] == "pending"
    r = ho.plot_size_rate_diagnostic(z, residential_land_rows=land, estate_rows=None, estate_columns=cols)
    assert r["status"] == "pending" and "estate" in r["reason"]
    r = ho.plot_size_rate_diagnostic(z[:10], residential_land_rows=land, estate_rows=est, estate_columns=cols)
    assert r["status"] == "pending" and r["classes"][1]["median_parcel_ha"]["status"] == "insufficient_n"


def test_residential_land_adapter_exclusions_and_low_confidence():
    rows = [
        {"code": "S01013401", "vintage": 2011, "residential_parcel_ha": 5.0, "share_res_uprn_in_parcels": 0.8,
         "mask_too_big_parcel": "False", "res_uprn_exceeds_dwellings": "False", "method_flags": "parcel_residential_uprn=x;area=y"},
        {"code": "S01013402", "vintage": 2011, "residential_parcel_ha": 0.1, "share_res_uprn_in_parcels": 0.3,
         "mask_too_big_parcel": "False", "res_uprn_exceeds_dwellings": "False", "method_flags": "parcel_residential_uprn=x;low_parcel_coverage_lt0.5"},
        {"code": "S01013403", "vintage": 2011, "residential_parcel_ha": 4.0, "share_res_uprn_in_parcels": 0.9,
         "mask_too_big_parcel": "True", "res_uprn_exceeds_dwellings": "False", "method_flags": "parcel_residential_uprn=x"},
        {"code": "S01013404", "vintage": 2011, "residential_parcel_ha": 4.0, "share_res_uprn_in_parcels": 0.9,
         "mask_too_big_parcel": "", "res_uprn_exceeds_dwellings": "True", "method_flags": "parcel_residential_uprn=x;res_uprn_exceeds_dwellings"},
        {"code": "S01013405", "vintage": 2011, "residential_parcel_ha": 2.0, "share_res_uprn_in_parcels": 0.9,
         "mask_too_big_parcel": "", "res_uprn_exceeds_dwellings": "False", "method_flags": "parcel_residential_uprn=x;zero_dwellings"},
        {"code": "S01013406", "vintage": 2011, "residential_parcel_ha": 2.0, "share_res_uprn_in_parcels": 0.9,
         "mask_too_big_parcel": "False", "res_uprn_exceeds_dwellings": "False", "method_flags": "parcel_residential_uprn=x"},
    ]
    out = {r["code"]: r for r in ho.residential_land_rows_from_gis(rows, zero_codes={"S01013406"})}
    assert out["S01013401"]["gradient_exclude"] == () and out["S01013401"]["low_confidence"] == ()
    assert out["S01013402"]["gradient_exclude"] == ("weak_match",) and "weak_match" in out["S01013402"]["low_confidence"]
    assert out["S01013403"]["gradient_exclude"] == ("mask_too_big_parcel",) and "mask_too_big" in out["S01013403"]["low_confidence"]
    assert out["S01013404"]["gradient_exclude"] == ("res_uprn_exceeds_dwellings",)
    assert out["S01013405"]["gradient_exclude"] == ("zero_dwellings",)
    assert out["S01013406"]["gradient_exclude"] == ("zero_dwellings",)       # Data Zones zero codes too
    assert all(r["residential_land_ha"] is not None for r in out.values())    # area kept; denominator only
    keep = {r["code"]: r for r in ho.residential_land_rows_from_gis(rows, low_coverage="keep")}
    assert keep["S01013402"]["gradient_exclude"] == () and "weak_match" in keep["S01013402"]["low_confidence"]
    land = ho.residential_land(list(out.values()))
    assert land["S01013401"] == {"ha": 5.0, "method": "parcel_based", "exclude": ()}


def test_plot_bands_split_all_ages_and_fallback(cfg):
    """Rules 3b273073: plot evidence splits EVERY detached home, whatever its age; blank must be borrowed."""
    band = sr.rebuild_band(cfg)
    dep = cfg["depreciation"]
    old = _inp(ages={"before 1919": 0.5, "1976-1983": 0.5})          # no post-1980 homes at all
    pb = sr.with_estate(old, cfg["estate"], mode="plot_bands", estate_row=_row(1, 0, 0))
    assert pb.estate_fraction == 1.0 and "estate_split_all_ages" in pb.tags and "estate_share_gis" in pb.tags
    assert sr.oneoff_detached_share(pb) == pytest.approx(0.0)
    r_pb = sr.zone_rebuild_band(pb, band=band, depreciation=dep, valuation_year=2025)["central"]
    r_0 = sr.zone_rebuild_band(old, band=band, depreciation=dep, valuation_year=2025)["central"]
    assert r_0.rebuild_new_gbp - r_pb.rebuild_new_gbp == pytest.approx(0.6 * 110 * (band["detached"]["central"] - band["detached_estate"]["central"]))
    # the EPC-age-only sensitivity still gates on age: no post-1980 homes -> no change
    ub = sr.with_estate(old, cfg["estate"], mode="epc_age_upper_bound")
    assert sr.oneoff_detached_share(ub) == pytest.approx(0.6) and "estate_upper_bound_epc_age_only" in ub.tags
    with pytest.raises(sr.PendingSourceError):
        sr.with_estate(old, cfg["estate"], mode="plot_bands", estate_row=_row(None, None, None))
    mid = sr.with_estate(old, cfg["estate"], mode="plot_bands", estate_row=_row(0.2, 0.6, 0.2), mid_weight=0.0)
    assert mid.estate_fraction == pytest.approx(0.2)


def _pb(code, lt, mid, gt, n):
    r = _row(lt, mid, gt) | {"code": code}
    r[_COLS["n_matched"]] = n
    return r


def test_borrow_plot_bands_council_ur6_then_national_never_0_or_1(cfg):
    ec = cfg["estate"]
    rows = {"S01013401": _pb("S01013401", 0.8, 0.2, 0.0, 30), "S01013402": _pb("S01013402", 0.2, 0.4, 0.4, 10),
            "S01013403": _pb("S01013403", None, None, None, 3), "S01013404": _pb("S01013404", 0.1, 0.3, 0.6, 40),
            "S01013406": _pb("S01013406", None, None, None, 0)}
    meta = {"S01013401": ("C1", 1), "S01013402": ("C1", 1), "S01013403": ("C1", 1),   # blank -> borrows C1 x UR6 1
            "S01013404": ("C2", 3), "S01013405": ("C3", 1), "S01013406": ("C3", 3)}   # no row / blank, empty cells -> national
    out = sr.borrow_plot_bands(rows, meta, ec)
    assert set(out) == set(meta)
    src = {c: r["_plot_bands_source"] for c, r in out.items()}
    assert src == {"S01013401": "filled", "S01013402": "filled", "S01013403": "borrowed", "S01013404": "filled",
                   "S01013405": "borrowed_national", "S01013406": "borrowed_national"}
    lt = out["S01013403"][_COLS["lt"]]
    assert lt == pytest.approx((30 * 0.8 + 10 * 0.2) / 40)              # dwelling-weighted (matched detached homes)
    assert _COLS["median_parcel_ha"] not in out["S01013403"]             # no own plot evidence
    fr = {c: sr.estate_fraction(r, ec) for c, r in out.items()}
    assert "plot_bands_borrowed" in fr["S01013403"][1] and "plot_bands_borrowed_national" in fr["S01013405"][1]
    assert fr["S01013406"][0] == pytest.approx(fr["S01013404"][0])       # = UR6 3 national evidence, not a default
    for c in ("S01013403", "S01013405", "S01013406"):                    # borrowed zones never default to 0 or 1
        e = fr[c][0]
        assert e is not None and 0.0 < e < 1.0, (c, e)
    for c in meta:
        inp = sr.with_estate(_inp(), ec, mode="plot_bands", estate_row=out[c])
        assert inp.estate_fraction is not None and "estate_share_pending" not in inp.tags


def test_one_off_rate_published_row(cfg):
    """One-off detached rate from a free published row ([S1] p.1 'One off detached houses 3 Units or less')."""
    rb = cfg["rebuild"]
    assert rb["rate_basis"]["detached_one_off"] == "one_off_detached"
    assert rb["base_rows_gbp_per_m2"]["detached_one_off"] == [2383, 2498]
    assert sr.derive_rebuild_band(rb)["detached_one_off"] == rb["gbp_per_m2"]["detached_one_off"]
    band = sr.rebuild_band(cfg)
    assert band["detached_estate"]["central"] < band["detached"]["central"] < band["detached_one_off"]["central"]
    assert cfg["estate"]["oneoff_rate_type"] == "detached_one_off"
    assert "page 1" in cfg["estate"]["oneoff_rate_source"] and "One off detached" in cfg["estate"]["oneoff_rate_source"]
    bad = {**cfg, "rebuild": {**rb, "rate_basis": {**rb["rate_basis"], "detached_one_off": "generic_detached"}}}
    with pytest.raises(ValueError):
        sr.rate_basis(bad)


def test_plot_bands_non_estate_share_uses_one_off(cfg):
    band = sr.rebuild_band(cfg)
    dep = cfg["depreciation"]
    old = _inp(ages={"before 1919": 0.5, "1976-1983": 0.5})
    pb = sr.with_estate(old, cfg["estate"], mode="plot_bands", estate_row=_row(0.2, 0.6, 0.2), mid_weight=0.0)
    mix = {c.dwelling_type for c in sr._zone_mix(pb)}
    assert {"detached_estate", "detached_one_off"} <= mix and "detached" not in mix
    assert sr.oneoff_detached_share(pb) == pytest.approx(0.6 * 0.8)
    r = sr.zone_rebuild_band(pb, band=band, depreciation=dep, valuation_year=2025)["central"]
    r0 = sr.zone_rebuild_band(old, band=band, depreciation=dep, valuation_year=2025)["central"]
    assert r.rebuild_new_gbp - r0.rebuild_new_gbp == pytest.approx(
        0.6 * 110 * (0.2 * band["detached_estate"]["central"] + 0.8 * band["detached_one_off"]["central"] - band["detached"]["central"]))
    none = sr.with_estate(old, cfg["estate"], mode="plot_bands", estate_row=_row(0, 0, 1), mid_weight=0.0)
    assert none.estate_fraction == 0.0 and {c.dwelling_type for c in sr._zone_mix(none)} >= {"detached_one_off"}
    assert "detached" not in {c.dwelling_type for c in sr._zone_mix(none)}
    pend = sr.with_estate(old, cfg["estate"], mode="pending")
    assert "detached" in {c.dwelling_type for c in sr._zone_mix(pend)} and "detached_one_off" not in {c.dwelling_type for c in sr._zone_mix(pend)}
