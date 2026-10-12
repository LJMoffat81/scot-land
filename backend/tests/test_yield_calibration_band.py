"""Georgist INTERNAL provisional yield (hash b3442d47): band, flags, blocked."""

from __future__ import annotations

import copy

import pytest

from agr.config import load_config as load_agr_config
from agr.yield_config import (
    FALLBACK_RENT_ZONE_COUNT,
    MODEL_FILL_ZONE_COUNT_KEEP_NULL,
    YIELD_BAND_HIGH,
    YIELD_BAND_LOW,
    YIELD_CENTRAL,
    YIELD_RESULT_HASH,
    scale_rent,
    yield_band_from_config,
    yield_signoff_payload,
)
from georgist import surface_rent as sr


@pytest.fixture
def cfg():
    return copy.deepcopy(sr.load_config())


def test_agr_yield_config_matches_signed_off_internal_band():
    cfg = load_agr_config()
    band = yield_band_from_config(cfg)
    assert band.central == pytest.approx(YIELD_CENTRAL)
    assert band.low == pytest.approx(YIELD_BAND_LOW)
    assert band.high == pytest.approx(YIELD_BAND_HIGH)
    assert band.high_clipped_at_cap is True
    assert band.result_hash == YIELD_RESULT_HASH
    assert band.central_from_decomposition == pytest.approx(0.0399)
    assert band.r + band.p - band.g == pytest.approx(band.central)
    assert band.value_basis == "proxy"
    assert band.bed_mapping_sensitive is True
    assert band.publication_status == "blocked"
    assert band.fallback_rent_zone_count == FALLBACK_RENT_ZONE_COUNT
    assert band.model_fill_zone_count_keep_null == MODEL_FILL_ZONE_COUNT_KEEP_NULL
    assert cfg["valuer_roll"]["yield_rate"] == pytest.approx(0.0399)
    assert cfg["valuation"]["yield_rate"] == pytest.approx(0.0399)


def test_surface_yield_aligned_with_agr_and_band_tags(cfg):
    assert cfg["yield"]["land_yield"] == pytest.approx(0.0399)
    lo, hi, clipped = sr.configured_yield_band(cfg["yield"])
    assert lo == pytest.approx(0.0352) and hi == pytest.approx(0.0450) and clipped is True
    meta = sr.yield_calibration_flags(cfg)
    assert meta["result_hash"] == "b3442d47"
    assert meta["publication_status"] == "blocked"
    assert meta["rent_display"] == "band"
    assert meta["value_basis"] == "proxy"
    assert meta["bed_mapping_sensitive"] is True
    assert meta["fallback_rent_zones"]["count"] == 390
    assert meta["model_fill_zones"]["keep_null"] is True
    assert meta["model_fill_zones"]["count"] == 727
    # Documentary r+p−g; r/g must not sit inside yield.*
    assert "r" not in cfg["yield"] and "g" not in cfg["yield"]
    decomp = meta["decomposition"]
    assert decomp["r"] + decomp["p"] - decomp["g"] == pytest.approx(decomp["central"])


def test_config_fallback_flags_fallback_rent_zone_and_bed_mapping(cfg):
    cell = sr.resolve_cell_yield(
        brma_id="SYN-B",
        ur6_class=6,
        cell_y=None,
        prs_n=0,
        price_n=0,
        brma_wide_y=None,
        yield_cfg=cfg["yield"],
    )
    assert cell.source == "config_fallback"
    assert "yield_fallback:config" in cell.tags
    assert sr.FALLBACK_RENT_ZONE_TAG in cell.tags
    assert sr.BED_MAPPING_SENSITIVE_TAG in cell.tags
    assert sr.YIELD_HIGH_CLIPPED_TAG in cell.tags


def test_blend_applies_config_band_when_no_halfwidths(cfg):
    cells = {"A": sr.YieldCell("A", 1, 0.0399, "cell")}
    z = sr.blend_zone_yield({"A": 1.0}, cells, yield_cfg=cfg["yield"])
    assert z.y_low == pytest.approx(0.0352)
    assert z.y_high == pytest.approx(0.0450)
    assert "yield_band_from_config" in z.tags
    assert sr.BED_MAPPING_SENSITIVE_TAG in z.tags
    assert sr.YIELD_HIGH_CLIPPED_TAG in z.tags


def test_scale_rent_band_and_signoff_payload():
    cfg = load_agr_config()
    band = yield_band_from_config(cfg)
    lo, hi = scale_rent(1000.0, band)
    assert lo == pytest.approx(round(1000.0 * 0.0352 / 0.0399, 2))
    assert hi == pytest.approx(round(1000.0 * 0.0450 / 0.0399, 2))
    payload = yield_signoff_payload(band)
    assert payload["rent_display"] == "band"
    assert payload["publication_status"] == "blocked"
    assert payload["result_hash"] == "b3442d47"
    assert payload["model_fill_zones"]["keep_null"] is True


def test_scenario_r_g_matches_new_land_yield(cfg):
    y = cfg["yield"]["land_yield"]
    r, g = sr.scenario_r_g(cfg["scenarios"]["illustrative_r_g"], y)
    assert r == pytest.approx(0.0499) and g == pytest.approx(0.01)


def test_output_row_carries_band_proxy_and_bed_mapping(make_valuation_row):
    row = make_valuation_row()
    assert sr.BED_MAPPING_SENSITIVE_TAG in row["proxy_tags"]
    assert row["value_tier"] == "proxy"
    assert row["uncertainty_low"] is not None and row["uncertainty_high"] is not None
    assert row["uncertainty_low"] < row["uncertainty_high"]
    assert "yield_band_from_config" in row["proxy_tags"] or row["uncertainty_low"] is not None
