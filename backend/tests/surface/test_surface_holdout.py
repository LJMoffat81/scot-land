"""Holdout harness skeleton on SYNTHETIC zones."""

import statistics

import pytest

from georgist import surface_holdout as sh


def _zones(n=40):
    return {f"S019999{i:02d}": ((i % 2) + 1, "S12999999") for i in range(n)}


def test_stratified_holdout_is_reproducible_and_disjoint():
    z = _zones()
    a = sh.stratified_zone_holdout(z, frac=0.25, seed=7)
    b = sh.stratified_zone_holdout(z, frac=0.25, seed=7)
    assert a.test == b.test and len(a.test) == 10
    assert not set(a.test) & set(a.train) and len(a.test) + len(a.train) == 40


def test_suppression_mimic_and_block():
    s = sh.suppression_mimic({"a": 3, "b": 6, "c": 9, "d": 20})
    assert s.test == ["b", "c"]
    blk = sh.block_holdout({"a": "IZ1", "b": "IZ1", "c": "IZ2", "d": "IZ2"}, frac=0.5, seed=1)
    assert len(blk.test) == 2 and len({"IZ1" if z in "ab" else "IZ2" for z in blk.test}) == 1


def test_metrics_perfect_prediction():
    actual = [100.0, 150.0, 200.0, 300.0]
    m = sh.score(actual, actual, [a * 0.9 for a in actual], [a * 1.1 for a in actual])
    assert m["median_ratio"] == pytest.approx(1.0)
    assert m["cod"] == pytest.approx(0.0)
    assert m["prd"] == pytest.approx(1.0)
    assert m["prb"] == pytest.approx(0.0, abs=1e-12)
    assert m["coverage_80"] == 1.0


def test_run_holdout_with_pluggable_model():
    z = _zones(20)
    rows = {k: {"price_gbp": 100_000 + 1000 * i} for i, k in enumerate(sorted(z))}
    split = sh.stratified_zone_holdout(z, frac=0.2, seed=3)

    def mean_model(train, test):  # SYNTHETIC baseline: predict training mean
        mu = sum(r["price_gbp"] for r in train) / len(train)
        return [(mu, mu * 0.8, mu * 1.2) for _ in test]

    out = sh.run_holdout(split, rows, mean_model)
    assert out["design"] == "H1_zone_stratified" and out["metrics"]["n"] == len(split.test)


# ---- indirect land-share checks (rules 12) and rebuild sensitivity, SYNTHETIC


def test_two_route_check_only_counts_independent_evidence():
    same = [{"sales_route": 50_000, "rent_route": 50_000, "evidence": "prs_same_cell", "brma": "SYN-A"}]
    na = sh.two_route_check(same, max_median_abs_log_ratio=0.25, calibration_brmas={"SYN-A"})
    assert na["status"] == "not_applicable" and na["pass"] is None and na["n_dropped_not_independent"] == 1
    leaked = [{"sales_route": 50_000, "rent_route": 52_000, "evidence": "brma_held_out", "brma": "SYN-A"}]
    assert sh.two_route_check(leaked, max_median_abs_log_ratio=0.25, calibration_brmas={"SYN-A"})["status"] == "not_applicable"
    indep = [
        {"sales_route": 50_000, "rent_route": 52_000, "evidence": "brma_held_out", "brma": "SYN-H"},
        {"sales_route": 40_000, "rent_route": 38_000, "evidence": "saa_rateable_value", "brma": "SYN-A"},
    ]
    ok = sh.two_route_check(indep + same, max_median_abs_log_ratio=0.25, calibration_brmas={"SYN-A"})
    assert ok["status"] == "pass" and ok["n"] == 2 and ok["n_dropped_not_independent"] == 1 and "rebuild" in ok["shared_assumption"]
    bad = [{"sales_route": 50_000, "rent_route": 150_000, "evidence": "saa_rateable_value"}]
    assert sh.two_route_check(bad, max_median_abs_log_ratio=0.25)["status"] == "fail"


def test_negative_residuals_by_class(cfg):
    c = cfg["land_share_checks"]
    rows = [{"ur6_class": 1, "negative_residual": i < 3} for i in range(10)] + [{"ur6_class": 6, "negative_residual": True}] * 5
    out = sh.negative_by_class_check(rows, high_demand_ur6=c["negative_high_demand_ur6"], max_share_high_demand=c["negative_max_share_high_demand"])
    assert not out["pass"] and out["breaches"] == {1: pytest.approx(0.3)} and out["share_negative_by_ur6"][6] == 1.0
    weak_only = [{"ur6_class": 6, "negative_residual": True}]
    assert sh.negative_by_class_check(weak_only, high_demand_ur6=[1, 2], max_share_high_demand=0.1)["pass"]


def test_gradient_monotone_and_reversed(cfg):
    order = cfg["land_share_checks"]["ur6_expected_order"]
    good = {1: [0.6, 0.65], 2: [0.5], 3: [0.4], 4: [0.3], 5: [0.35], 6: [0.2]}
    assert sh.gradient_check(good, expected_order=order)["pass"]
    reversed_ = {1: [0.2], 2: [0.3], 3: [0.4], 4: [0.5], 5: [0.5], 6: [0.6]}
    out = sh.gradient_check(reversed_, expected_order=order)
    assert not out["pass"] and len(out["violations"]) == len(order)
    acc = sh.gradient_check(good, expected_order=order, access_bins={0: [0.6], 1: [0.5], 2: [0.55]})
    assert not acc["pass"] and acc["access_inversions"] == [(1, 2)]


def test_national_share_check(cfg):
    c = cfg["land_share_checks"]
    # v1.3 check 1 band is 10%–40% (PL 15:35); former 49–73% refs are historical only.
    assert c["national_range"] == [0.10, 0.40]
    zones = [{"land_value": 30_000, "mean_price": 120_000, "dwellings": 100}, {"land_value": 25_000, "mean_price": 100_000, "dwellings": 50}]
    out = sh.national_share_check(zones, plausible_range=c["national_range"], tolerance=c["national_tolerance"], sources=c["national_range_sources"])
    assert out["share"] == pytest.approx(0.25) and out["pass"] and out["within_core_range"] and out["range_sources"]
    low = sh.national_share_check([{"land_value": 1, "mean_price": 100, "dwellings": 1}], plausible_range=c["national_range"], tolerance=c["national_tolerance"])
    assert not low["pass"]
    high = sh.national_share_check([{"land_value": 60_000, "mean_price": 100_000, "dwellings": 1}], plausible_range=c["national_range"], tolerance=c["national_tolerance"])
    assert not high["pass"]


def test_rebuild_sensitivity_report():
    zones = [
        {"price": 150_000, "dwellings": 10, "drc": {"low": 60_000, "central": 80_000, "high": 110_000}},
        {"price": 90_000, "dwellings": 10, "drc": {"low": 60_000, "central": 80_000, "high": 110_000}},
    ]
    rep = sh.rebuild_sensitivity(zones)
    assert rep["share_negative_by_rebuild"] == {"low": 0.0, "central": 0.0, "high": 0.5}
    s = rep["national_land_share_by_rebuild"]
    assert s["low"] > s["central"] > s["high"]
    assert rep["median_relative_swing"] == pytest.approx(statistics.median([(90_000 - 40_000) / 70_000, (30_000 - 0) / 10_000]))
