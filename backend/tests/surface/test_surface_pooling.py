"""Methods PR-1: surface price pooling (R3.1–R3.5, R4.7). Exact money/counts only."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from georgist import surface_illustrative as si
from georgist import surface_rent as sr

REPO = Path(__file__).resolve().parents[3]
DZ_PRICES = REPO / "data" / "processed" / "dz2011_prices.csv"
ZONE_SPINE = REPO / "data" / "processed" / "datazones" / "zone_spine.csv"
EXTRACT = si.METHODS_PR1_EXTRACT
EXTRACT_META = si.METHODS_PR1_EXTRACT_META
LOCAL_PCT_RUN = si.METHODS_LOCAL_PCT_RUN


def _pence(x: float) -> int:
    return int(round(float(x) * 100))


def _assert_extract_pinned():
    assert EXTRACT.is_file(), f"missing RoS sales_n extract {EXTRACT}"
    assert EXTRACT_META.is_file(), f"missing extract pin {EXTRACT_META}"
    meta = json.loads(EXTRACT_META.read_text(encoding="utf-8"))
    digest = hashlib.sha256(EXTRACT.read_bytes()).hexdigest()
    assert digest == meta["extract_sha256"]
    assert meta["source_sha256_match"] is True
    assert meta["licence"] == "OGL-3.0"
    assert set(meta["columns"]) == {"code", "year", "sales_n", "suppressed"}
    # No £ columns in the extract
    header = EXTRACT.read_text(encoding="utf-8").splitlines()[0].lower()
    assert "gbp" not in header and "price" not in header and "median" not in header and "mean" not in header


# --- (a) 3-year pool exact pence + pooled_3y ---------------------------------


def test_pool_prices_3y_exact_pence_and_pooled_3y_tag():
    # sales 6/4/5, means 200000/210000/190000, factors 1.10/1.05/1.00
    obs = [
        sr.YearPrice(2021, 6, 200_000, 195_000),
        sr.YearPrice(2022, 4, 210_000, 205_000),
        sr.YearPrice(2023, 5, 190_000, 185_000),
    ]
    idx = {2021: 1.10, 2022: 1.05, 2023: 1.00}
    p = sr.pool_prices(
        obs, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=2023,
    )
    # (6*200000*1.10 + 4*210000*1.05 + 5*190000*1.00) / 15 = 3152000/15
    assert p.sales_n == 15
    assert _pence(p.price_gbp) == _pence(3_152_000 / 15)
    assert "pooled_3y" in p.tags
    assert p.evidence_oldest_year == 2021
    assert "evidence_oldest_year:2021" in p.tags


# --- (b) widen to 5y; oldest year tag ---------------------------------------


def test_pool_prices_widens_to_5y_with_oldest_year():
    y = 2023
    obs = [
        sr.YearPrice(y - 4, 6, 150_000, 140_000),
        sr.YearPrice(y - 2, None, None, None),
        sr.YearPrice(y - 1, None, None, None),
        sr.YearPrice(y, None, None, None),
    ]
    idx = {y - 4: 1.20, y - 3: 1.10, y - 2: 1.05, y - 1: 1.02, y: 1.00}
    p = sr.pool_prices(
        obs, latest_year=y, measure="mean", pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=y,
    )
    assert "pooled_5y" in p.tags
    assert p.evidence_oldest_year == y - 4
    assert "evidence_oldest_year:%d" % (y - 4) in p.tags
    assert p.sales_n == 6
    assert _pence(p.price_gbp) == _pence(150_000 * 1.20)
    assert "evidence_oldest_year_dominant" in p.tags


# --- (c) all years suppressed → suppressed_all_years ------------------------


def test_pool_prices_all_suppressed_then_model_fill_path():
    obs = [
        sr.YearPrice(2019, None, None, None),
        sr.YearPrice(2021, None, None, None),
        sr.YearPrice(2022, 3, None, None),
        sr.YearPrice(2023, None, None, None),
    ]
    idx = {y: 1.0 for y in range(2019, 2024)}
    p = sr.pool_prices(
        obs, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=2023,
    )
    assert p.price_gbp is None and p.sales_n == 0
    assert p.tags == ("suppressed_all_years",)
    assert p.evidence_oldest_year is None
    lv = sr.resolve_land_value(
        dwellings=400, observed=None, sales_n=p.sales_n, model_gbp=40_000,
        n_min=5, n_full=15, shrinkage_k=8,
    )
    assert lv.fill_method == "model_filled"
    assert _pence(lv.land_value) == _pence(40_000)


# --- (d) pooling several years with no index → error ------------------------


def test_pool_prices_several_years_without_index_raises():
    obs = [
        sr.YearPrice(2021, 6, 200_000, 190_000),
        sr.YearPrice(2023, 5, 190_000, 180_000),
    ]
    with pytest.raises(ValueError, match="index_factor"):
        sr.pool_prices(obs, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5)


# --- (e) dominant NOT at exactly 50%; IS at 50%+1 ---------------------------


def test_evidence_oldest_year_dominant_strictly_over_half():
    idx = {2021: 1.0, 2022: 1.0, 2023: 1.0}
    half = [
        sr.YearPrice(2021, 5, 100_000, 95_000),
        sr.YearPrice(2023, 5, 110_000, 105_000),
    ]
    p_half = sr.pool_prices(
        half, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=2023,
    )
    assert p_half.sales_n == 10 and p_half.evidence_oldest_year == 2021
    assert "evidence_oldest_year_dominant" not in p_half.tags

    plus = [
        sr.YearPrice(2021, 6, 100_000, 95_000),
        sr.YearPrice(2023, 5, 110_000, 105_000),
    ]
    p_plus = sr.pool_prices(
        plus, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=2023,
    )
    assert p_plus.sales_n == 11
    assert "evidence_oldest_year_dominant" in p_plus.tags


# --- (f) every observed pooled zone carries pooling tags --------------------


def test_observed_zone_output_carries_pooling_tags():
    cfg = sr.load_config()["price"]
    obs = [
        sr.YearPrice(2021, 6, 200_000, 195_000),
        sr.YearPrice(2022, 4, 210_000, 205_000),
        sr.YearPrice(2023, 5, 190_000, 185_000),
    ]
    idx = {2021: 1.10, 2022: 1.05, 2023: 1.00}
    pooled = si.pool_zone_price(
        obs, latest_year=2023, price_cfg=cfg, index_factor=idx, index_to_year=2023,
    )
    assert pooled.price_gbp is not None
    row = {
        "sales_n": pooled.sales_n,
        "proxy_tags": list(pooled.tags),
        "evidence_oldest_year": pooled.evidence_oldest_year,
    }
    assert "pooled_3y" in row["proxy_tags"] or "pooled_5y" in row["proxy_tags"]
    assert row["evidence_oldest_year"] is not None
    assert any(t.startswith("evidence_oldest_year:") for t in row["proxy_tags"])
    lv = sr.resolve_land_value(
        dwellings=400,
        observed=sr.residual_land_value(200_000, 100_000),
        sales_n=row["sales_n"],
        model_gbp=50_000,
        n_min=int(cfg["n_min"]),
        n_full=int(cfg["n_full"]),
        shrinkage_k=float(cfg["shrinkage_k"]),
    )
    assert lv.fill_method == "observed_pooled"
    assert row["sales_n"] == 15


def test_suppressed_years_contribute_nothing_to_counts():
    obs = [
        sr.YearPrice(2021, 10, 100_000, 95_000),
        sr.YearPrice(2022, 4, None, None),
        sr.YearPrice(2023, None, None, None),
    ]
    idx = {2021: 1.0, 2022: 1.0, 2023: 1.0}
    p = sr.pool_prices(
        obs, latest_year=2023, measure="mean", pool_years=3, pool_years_max=5, n_min=5,
        index_factor=idx, index_to_year=2023,
    )
    assert p.sales_n == 10
    assert p.evidence_oldest_year == 2021
    assert _pence(p.price_gbp) == _pence(100_000)


# --- Valuation acceptance (computed from pinned RoS extract — can fail) -----


def test_ros_sales_n_extract_is_hash_pinned_ogl_no_prices():
    _assert_extract_pinned()


def test_valuation_empty_zone_pooling_from_ros_extract():
    """Of empty-with-dwellings zones, 3y then 5y gains are computed from the extract."""
    _assert_extract_pinned()
    assert ZONE_SPINE.is_file()
    cov = si.empty_zone_pooling_coverage_from_ros_extract(EXTRACT, ZONE_SPINE)
    # These assert computed results — wrong extract / logic fails the build.
    assert cov["empty_with_dwellings"] == 727
    assert cov["gained_pooled_3y"] == 557
    assert cov["gained_pooled_5y"] == 41
    assert cov["gained_observed"] == 598
    assert cov["gained_pooled_3y"] + cov["gained_pooled_5y"] == cov["gained_observed"]
    assert cov["remaining_model_fill"] == 129
    assert cov["remaining_model_fill"] < 135
    assert cov["null_dz_fill_target_n_old"] == 727
    assert cov["null_dz_fill_target_n_new"] == cov["remaining_model_fill"]
    # Zone lists must match counts (ordering tests assert full lists via length + set size)
    assert len(cov["gained_pooled_3y_codes"]) == cov["gained_pooled_3y"]
    assert len(cov["gained_pooled_5y_codes"]) == cov["gained_pooled_5y"]
    assert len(cov["remaining_model_fill_codes"]) == cov["remaining_model_fill"]
    assert len(set(cov["gained_pooled_5y_codes"])) == 41


def test_valuation_3y_matches_committed_dz_prices_cross_check():
    """3y gain from extract must match the committed dz2011_prices 3y path."""
    _assert_extract_pinned()
    from_extract = si.empty_zone_pooling_coverage_from_ros_extract(EXTRACT, ZONE_SPINE)
    from_prices = si.empty_zone_pooling_coverage_from_dz_prices(DZ_PRICES, ZONE_SPINE)
    assert from_extract["gained_pooled_3y"] == from_prices["gained_pooled_3y"]
    assert from_extract["empty_with_dwellings"] == from_prices["empty_with_dwellings"]


def test_scotland_total_pct_move_under_2_local_only():
    """£ / % residual move: local ignored run output only; skipped in CI.

    Reason: full residual before/after needs local RoS means + HPI + EPC rebuild;
    committed artifacts hold counts/% report only (no *_gbp keys).
    """
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        pytest.skip(
            "Scotland total £/% move needs local ignored run output "
            f"({LOCAL_PCT_RUN}); not available in CI (no residual £ in repo)"
        )
    if not LOCAL_PCT_RUN.is_file():
        pytest.skip(
            f"local run output missing: {LOCAL_PCT_RUN} "
            "(write pct_change_common_zones from illustrative before/after)"
        )
    payload = json.loads(LOCAL_PCT_RUN.read_text(encoding="utf-8"))
    pct = float(payload["pct_change_common_zones"])
    assert payload["common_zones_n"] == 6246
    assert pct < 2.0


def test_committed_methods_report_has_no_gbp_keys():
    report = REPO / "data/processed/methods_code_1/pr1/report.json"
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "_gbp" not in text
    assert "£" not in text
    payload = json.loads(text)
    assert payload.get("publish_level") == "internal"
    cov = payload["coverage"]
    assert cov["gained_pooled_3y"] == 557
    assert cov["gained_pooled_5y"] == 41
    assert cov["remaining_model_fill"] == 129
