"""Model fill for null Data Zones + plumbing. SYNTHETIC fixtures only."""

import random

import pytest

from georgist import surface_model as sm
from georgist import surface_rent as sr


@pytest.fixture(scope="module")
def cfg():
    return sr.load_config()


def _observed(n=80, ur6=(1, 2, 3), seed=11):
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        c = ur6[i % len(ur6)]
        access = rnd.uniform(10, 100)
        lv = 20_000 + 400 * access + rnd.gauss(0, 2_000)
        rows.append({
            "code": f"S0101{3000 + i}",
            "ur6_class": c,
            "land_value": max(1_000.0, lv),
            "sales_n": 20,
            "dwellings": 300,
            "drive_GP": access,
        })
    return rows


def test_null_dz_fill_target_documented(cfg):
    assert sm.null_dz_fill_target_n() == 129
    assert cfg["model_fill"]["null_dz_fill_target_n"] == 129
    assert sm.PRE_POOLING_NULL_DZ_FILL_TARGET_N == 727
    assert cfg["model_fill"]["publication"] == "internal_calibration_only"
    assert cfg["model_fill"]["status"] == "research_estimate"
    # Valuation owns r−g; model-fill must not rewrite the calibrated central yield.
    assert "land_yield" not in cfg["yield"]
    assert cfg["yield"]["central"] == pytest.approx(0.04499)
    assert abs(cfg["yield"]["central"] - 0.05) > 1e-12


def test_fill_null_zones_never_copies_neighbour(cfg):
    observed = _observed()
    # Null zones: distinct codes, no land_value; must not receive a neighbour's exact value.
    nulls = []
    for i in range(12):
        nulls.append({
            "code": f"S0101{4000 + i}",
            "ur6_class": (i % 3) + 1,
            "dwellings": 250,
            "sales_n": 0,
            "drive_GP": 40.0 + i,
            "flags": "absent_from_ros_price_file" if i < 2 else "",
            "absent_from_ros_price_file": i < 2,
        })
    c = {**cfg, "model_fill": {**cfg["model_fill"], "drivers": []}}
    out = sm.fill_null_zones(observed_rows=observed, null_rows=nulls, config=c)
    assert out["n_filled"] == 12
    assert out["null_dz_fill_target_n"] == 129
    assert out["publication"] == "internal_calibration_only"
    assert out["quality"] == "research_estimate"
    # Never copies a neighbour: each fill is a model prediction (tag + own interval), not a donor code.
    donor_codes = {r["code"] for r in observed}
    for code, fill in out["fills"].items():
        assert code not in donor_codes
        assert fill["fill_method"] == "model_filled"
        assert fill["land_value"] > 0
        assert fill["land_value_low"] <= fill["land_value"] <= fill["land_value_high"]
        assert "research_estimate" in fill["proxy_tags"]
        assert "model_filled" in fill["proxy_tags"]
        assert "model_fill_pending" not in fill["proxy_tags"]
        assert fill["note"] == "research_estimate_internal_calibration"
    assert sum(1 for f in out["fills"].values() if "absent_from_ros_price_file" in f["proxy_tags"]) == 2


def test_zero_dwellings_excluded_from_fill(cfg):
    observed = _observed(n=30, ur6=(1, 2))
    nulls = [
        {"code": "S01010206", "ur6_class": 1, "dwellings": 0, "sales_n": 0, "flags": "zero_dwellings"},
        {"code": "S01013499", "ur6_class": 1, "dwellings": 200, "sales_n": 0},
    ]
    out = sm.fill_null_zones(
        observed_rows=observed, null_rows=nulls, config=cfg,
        exclude_zero=("S01010206", "S01010226", "S01010227"),
    )
    assert "S01010206" not in out["fills"]
    assert "S01013499" in out["fills"]


def test_thin_class_borrows_adjacent(cfg):
    # Class 4 has only a few zones → must borrow from adjacency.
    rows = _observed(n=40, ur6=(3,), seed=3)
    rows += [
        {"code": f"S0101{5000 + i}", "ur6_class": 4, "land_value": 15_000.0 + 100 * i,
         "sales_n": 20, "dwellings": 200}
        for i in range(5)
    ]
    c = {**cfg, "class_min_zones": 20}
    model = sm.fit_land_value_model(rows, config=c)
    assert 4 in model.class_fits
    assert model.class_fits[4].borrowed_from  # borrowed from class 3 (and maybe 6 if present)
    preds = sm.predict_land_value(model, [{"code": "S01015099", "ur6_class": 4, "dwellings": 200}])
    assert preds[0].land_value > 0
    assert any(t.startswith("borrowed_class:") for t in preds[0].tags)


def test_forbidden_driver_refused(cfg):
    rows = _observed(n=20)
    with pytest.raises(sr.ForbiddenDriverError):
        sm.fit_land_value_model(rows, config=cfg, driver_keys=["simd_income_rank"])


def test_fit_predict_holdout_pluggable(cfg):
    rows = _observed(n=40, ur6=(1, 2))
    for r in rows:
        r["price_gbp"] = r["land_value"] + 80_000
        r["drc_gbp"] = 80_000
    train, test = rows[:30], rows[30:]
    preds = sm.fit_predict(train, test, config=cfg)
    assert len(preds) == len(test)
    assert all(lo <= mid <= hi for mid, lo, hi in preds)
