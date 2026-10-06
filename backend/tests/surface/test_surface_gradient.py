"""Rules 12.2 (v0.6): per-residential-hectare gradient on observed zones only. SYNTHETIC rows."""

import pytest

from georgist import surface_holdout as sh

ORDER = [[1, 2], [2, 3], [3, 4], [3, 5], [4, 6], [5, 6]]
KW = dict(expected_order=ORDER, min_zones_per_class=5, access_rho_max=-0.1)


def _acc(code, minutes):
    return {"code": code, "vintage": 2011, **{c: minutes for c in sh.ACCESS_DRIVE}, **{c: minutes * 2 for c in sh.ACCESS_PT},
            "broadband": 0.1, "flags": "dz2011_only_not_crosswalked"}


def _world(n=8, fill="observed_pooled", sales=10, method="parcel_based", reverse_access=False):
    """Class c: value per ha falls with c; inside a class value falls with minutes."""
    zones, land, acc = [], [], []
    for c in range(1, 7):
        for i in range(n):
            code = f"S01{7000 + c * 100 + i:06d}"
            minutes = 2 + i
            lv = (7 - c) * 10_000 - (i if not reverse_access else -i) * 500
            zones.append({"code": code, "vintage": 2011, "ur6_class": c, "fill_method": fill, "sales_n": sales,
                          "observed_land_value": lv, "dwellings": 100})
            land.append({"code": code, "vintage": 2011, "residential_land_ha": 10.0, "method": method})
            acc.append(_acc(code, minutes))
    return zones, land, acc


def test_passes_on_good_gradient_and_records_n():
    z, l, a = _world()
    out = sh.per_hectare_gradient_check(z, residential_land_rows=l, access_rows=a, **KW)
    assert out["status"] == "pass" and out["uses_land_share"] is False
    assert out["n_used_by_class"] == {c: 8 for c in range(1, 7)}
    assert out["classes"][1]["rho_drive"] == pytest.approx(-1.0)


def test_fails_when_access_reversed_or_order_reversed():
    z, l, a = _world(reverse_access=True)
    assert sh.per_hectare_gradient_check(z, residential_land_rows=l, access_rows=a, **KW)["status"] == "fail"
    z, l, a = _world()
    for r in z:
        r["observed_land_value"] = r["ur6_class"] * 10_000 - int(r["code"][-2:]) * 500
    out = sh.per_hectare_gradient_check(z, residential_land_rows=l, access_rows=a, **KW)
    assert out["status"] == "fail" and any(p["status"] == "fail" for p in out["between_class"])


def test_model_filled_zones_are_excluded():
    """Filled zones that would 'pass' by construction (value built from the access drivers) never enter the test."""
    z, l, a = _world(n=3)  # 3 observed per class < min 5
    filled = []
    for c in range(1, 7):
        for i in range(10):
            code = f"S01{8000 + c * 100 + i:06d}"
            filled.append({"code": code, "vintage": 2011, "ur6_class": c, "fill_method": "model_filled", "sales_n": 0,
                           "observed_land_value": (7 - c) * 10_000 - i * 500, "dwellings": 100})
            l.append({"code": code, "vintage": 2011, "residential_land_ha": 10.0, "method": "parcel_based"})
            a.append(_acc(code, 2 + i))
    thin = [{**r, "code": f"S01{9000 + int(r['code'][-6:]) % 1000:06d}", "fill_method": "shrunk_to_model", "sales_n": 4} for r in z]  # <5 sales
    out = sh.per_hectare_gradient_check(z + filled + thin, residential_land_rows=l, access_rows=a, **KW)
    assert out["n_excluded_model_filled"] == 60 + len(thin)
    assert out["n_used_by_class"] == {c: 3 for c in range(1, 7)}
    assert out["status"] == "pending" and out["reason"] == "insufficient_n"
    assert all(v["reason"] == "insufficient_n" for v in out["classes"].values())
    assert all(p["status"] == "pending" for p in out["between_class"])


def test_pending_on_settlement_area_or_missing_inputs():
    z, l, a = _world(method="settlement_area")
    out = sh.per_hectare_gradient_check(z, residential_land_rows=l, access_rows=a, **KW)
    assert out["status"] == "pending" and "settlement_area" in out["reason"]
    z, l, a = _world()
    assert "residential_land_missing" in sh.per_hectare_gradient_check(z, residential_land_rows=None, access_rows=a, **KW)["reason"]
    assert "access_indicators_missing" in sh.per_hectare_gradient_check(z, residential_land_rows=l, access_rows=None, **KW)["reason"]
    out = sh.per_hectare_gradient_check(z, residential_land_rows=l[: len(l) // 2], access_rows=a, **KW)
    assert out["status"] == "pending" and "missing residential land" in out["reason"]


def test_raw_minutes_only_never_ranks():
    with pytest.raises(ValueError, match="never used"):
        sh.access_minutes([{"code": "S01013401", "vintage": 2011, "access_rank": 12, "access_score": 0.3}])
    with pytest.raises(ValueError):
        sh.access_minutes([{**_acc("S01013401", 3), "vintage": 2022}])
    m = sh.access_minutes([_acc("S01013401", 3)])
    assert m["S01013401"] == {"drive_min": 3.0, "pt_min": 6.0}


def test_spearman_ties():
    assert sh.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert sh.spearman([1, 1, 2, 3], [4, 3, 2, 1]) == pytest.approx(-0.9486833, rel=1e-6)
    assert sh.spearman([1, 1], [1, 2]) is None
