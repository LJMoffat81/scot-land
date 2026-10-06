"""The OPEN_ESTIMATE rebuild band in data/config/surface.yaml."""

import pytest

from georgist import surface_rent as sr


def test_status_and_label_are_open_estimate(cfg):
    rb = cfg["rebuild"]
    assert rb["status"] == "OPEN_ESTIMATE"
    assert "APPROXIMATION" in rb["label"]
    assert rb["price_base"] and rb["valuation_date"] and len(rb["sources"]) >= 4
    for s in rb["sources"]:
        assert s["url"].startswith("https://") and s["date"]


def test_band_complete_and_ordered(cfg):
    band = sr.rebuild_band(cfg)
    assert set(sr.DWELLING_TYPES) <= set(band) <= set(sr.DWELLING_TYPES) | set(sr.REBUILD_EXTRA_TYPES)
    for t, b in band.items():
        assert b["low"] < b["central"] < b["high"], t
        assert b["high"] / b["low"] >= 1.4, f"{t} band should be wide"


def test_band_reproduces_written_derivation(cfg):
    derived = sr.derive_rebuild_band(cfg["rebuild"])
    published = cfg["rebuild"]["gbp_per_m2"]
    assert derived == {t: {s: int(v) for s, v in published[t].items()} for t in published}


def test_pending_or_missing_is_refused(cfg):
    cfg["rebuild"]["status"] = "PENDING_SOURCE"
    with pytest.raises(sr.PendingSourceError):
        sr.rebuild_band(cfg)
    cfg["rebuild"]["status"] = "OPEN_ESTIMATE"
    cfg["rebuild"]["gbp_per_m2"]["terraced"] = {"low": 1, "central": None, "high": 3}
    with pytest.raises(sr.PendingSourceError):
        sr.rebuild_band(cfg)
    cfg["rebuild"]["gbp_per_m2"]["terraced"] = {"low": 3, "central": 2, "high": 1}
    with pytest.raises(ValueError):
        sr.rebuild_band(cfg)


def test_sources_required(cfg):
    cfg["rebuild"]["sources"] = []
    with pytest.raises(sr.PendingSourceError):
        sr.rebuild_band(cfg)


def test_rates_by_scenario(cfg):
    lo, mid, hi = (sr.rebuild_rates(cfg, s) for s in sr.SCENARIOS)
    assert all(lo[t] < mid[t] < hi[t] for t in sr.DWELLING_TYPES)
    with pytest.raises(ValueError):
        sr.rebuild_rates(cfg, "max")


def test_rebuild_band_needs_factor_for_price_year(cfg):
    assert sr.rebuild_band(cfg, 2025) == sr.rebuild_band(cfg)
    with pytest.raises(sr.PendingSourceError):
        sr.rebuild_band(cfg, 2023)  # never assumed 1.0


def test_price_measure_and_skew_defaults_documented(cfg):
    pr = cfg["price"]
    assert pr["measure"] == "mean" and pr["ceiling_measure"] == "mean" and pr["display_measure"] == "median"
    assert pr["skew_flag"]["mean_median_ratio_min"] == 1.40 and pr["skew_flag"]["small_sales_n_below"] == pr["n_full"]
    assert tuple(cfg["publish_levels"]) == sr.PUBLISH_LEVELS
    assert cfg["rebuild_mix"]["bases"] == list(sr.REBUILD_MIX_BASES)
