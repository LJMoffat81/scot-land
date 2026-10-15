"""FILL-MEASURED-ZERO: measured floored zeros are not filled; post-fill gate + n/a."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from georgist import dz2022_fill as fill
from georgist import rent_table_pooled as rtp
from georgist import surface_costs as sc
from georgist import surface_holdout as sh
from georgist import surface_rent as sr

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dz2022_fill"
RENT = FIXTURES / "rent_2011.csv"


def test_synthetic_price_floored_zero_stays_measured_not_filled():
    """Zone with price evidence but floored zero stays measured, never empty-to-fill."""
    row = {
        "code": "S01019901",
        "measured_rent": 0.0,
        "uncertainty_low": 0.0,
        "uncertainty_high": 120.0,
        "fill_method": "observed_pooled",
        "dwellings": 40,
        "sales_n": 12,
        "flags": "",
        "evidence_window": "pooled_3y",
    }
    assert fill.has_price_evidence(row)
    assert fill._is_measured(row)
    assert fill.is_measured_zero(row)
    assert not fill._is_empty_to_fill(row, fill.ZERO_DWELLING_CODES)
    assert fill.COST_AT_OR_ABOVE_PRICE_TAG == "cost_at_or_above_price"


def test_no_price_zone_is_filled():
    """Zone with no measured/pooled price evidence needs filling."""
    row = {
        "code": "S01019902",
        "measured_rent": None,
        "fill_method": "model_fill_pending",
        "dwellings": 40,
        "sales_n": 0,
        "flags": "",
    }
    assert not fill.has_price_evidence(row)
    assert not fill._is_measured(row)
    assert fill._is_empty_to_fill(row, fill.ZERO_DWELLING_CODES)


def test_rent_zero_alone_is_not_needs_filling_when_measured():
    """Needs-filling never keys off rent==0."""
    empty_looking = {
        "code": "S01019903",
        "measured_rent": 0.0,
        "fill_method": "observed_pooled",
        "dwellings": 10,
        "sales_n": 8,
    }
    assert not fill._is_empty_to_fill(empty_looking, fill.ZERO_DWELLING_CODES)


def test_real_counts_129_filled_and_27_measured_zeros():
    """Inventory shaped like the real run: 129 model-fill + 27 measured zeros + 3 D."""
    rows: list[dict] = []
    # 125 suppressed-after-pooling empties (not the 4 not-in-price codes).
    for i in range(125):
        rows.append(
            {
                "code": f"S0103{i:04d}",
                "measured_rent": None,
                "fill_method": "model_fill_pending",
                "dwellings": 20,
                "sales_n": 0,
                "flags": "",
            }
        )
    for code in sorted(fill.NOT_IN_PRICE_FILE_CODES):
        rows.append(
            {
                "code": code,
                "measured_rent": None,
                "fill_method": "model_fill_pending",
                "dwellings": 20,
                "sales_n": 0,
                "flags": "absent_from_ros_price_file",
            }
        )
    for i in range(27):
        rows.append(
            {
                "code": f"S0104{i:04d}",
                "measured_rent": 0.0,
                "uncertainty_low": 0.0,
                "uncertainty_high": 50.0 + i,
                "fill_method": "observed_pooled",
                "dwellings": 15,
                "sales_n": 10,
                "flags": sr.COST_AT_OR_ABOVE_PRICE_TAG,
                "evidence_window": "2023",
            }
        )
    for code in sorted(fill.ZERO_DWELLING_CODES):
        rows.append(
            {
                "code": code,
                "measured_rent": 0.0,
                "fill_method": "not_applicable",
                "dwellings": 0,
                "sales_n": 0,
                "flags": "zero_dwellings",
            }
        )
    # Positive measured zones must not swell the fill count.
    for i in range(40):
        rows.append(
            {
                "code": f"S0105{i:04d}",
                "measured_rent": 100.0 + i,
                "fill_method": "observed_pooled",
                "dwellings": 25,
                "sales_n": 20,
                "flags": "",
            }
        )

    counts = fill.count_reconciled_sources(rows)
    assert counts["model_fill_n"] == 129
    assert counts["not_in_price_file_n"] == 4
    assert counts["zero_dwellings_n"] == 3
    assert fill.count_measured_zeros(rows) == 27
    facts = fill.reconciled_facts()
    assert facts["model_fill_n"] == 129
    assert facts["measured_zeros_n"] == 27
    fill.assert_reconciled_source_counts(rows)


def test_post_fill_gate_accepts_measured_zero_with_band():
    rows_2011 = [
        {
            "code": "S01019910",
            "measured_rent": 0.0,
            "uncertainty_low": 0.0,
            "uncertainty_high": 80.0,
            "fill_method": "observed_pooled",
            "dwellings": 10,
            "sales_n": 9,
        }
    ]
    rows_2022 = [
        {
            "code": "S01029910",
            "measured_rent": 0.0,
            "uncertainty_low": 0.0,
            "uncertainty_high": 80.0,
            "fill_method": "observed_pooled",
            "estimate_label": fill.ESTIMATE_MEASURED,
            "publication_status": "blocked",
            "value_tier": "proxy",
            "proxy_tags": [fill.PROXY_TAG, fill.COST_AT_OR_ABOVE_PRICE_TAG],
            "dwellings": 10,
            "sales_n": 9,
        }
    ]
    fill.assert_post_fill_gate(rows_2011, rows_2022)
    assert rows_2022[0]["uncertainty_low"] == 0.0
    assert rows_2022[0]["uncertainty_high"] == 80.0
    assert rows_2022[0]["uncertainty_high"] > rows_2022[0]["measured_rent"]


def test_post_fill_gate_fails_zero_without_price_evidence():
    """Negative: inject a zero with no evidence → run FAIL."""
    rows_2011 = [
        {
            "code": "S01019911",
            "measured_rent": 0.0,
            "fill_method": "model_fill_pending",
            "dwellings": 10,
            "sales_n": 0,
        }
    ]
    rows_2022 = [
        {
            "code": "S01029911",
            "measured_rent": 0.0,
            "fill_method": "model_filled",
            "estimate_label": fill.ESTIMATE_FULLY,
            "publication_status": "blocked",
            "value_tier": "proxy",
            "proxy_tags": [fill.PROXY_TAG],
            "dwellings": 10,
            "sales_n": 0,
        }
    ]
    with pytest.raises(fill.FillError, match="without measured price evidence"):
        fill.assert_post_fill_gate(rows_2011, rows_2022)


def test_cost_at_or_above_price_tag_on_residual():
    neg = sr.residual_land_value(80_000, 120_000)
    assert neg.land_value == 0.0
    assert neg.negative_residual is True
    assert "negative_residual" in neg.tags
    assert sr.COST_AT_OR_ABOVE_PRICE_TAG in neg.tags
    eq = sr.residual_land_value(100_000, 100_000)
    assert eq.land_value == 0.0
    assert eq.negative_residual is False  # zero is not negative (unchanged)
    assert sr.COST_AT_OR_ABOVE_PRICE_TAG in eq.tags


def test_measured_zero_uncertainty_band_not_flat(cfg, band):
    """Band is £0 to upper under low rebuild, not collapsed flat £0."""
    mix = [sr.MixComponent("semi_detached", 1.0, 90.0, "1965-1975")]
    rbs = sr.depreciated_rebuild_band(
        mix, band=band, depreciation=cfg["depreciation"], valuation_year=2025, region=1.0
    )
    # Price below central DRC → floored zero; low rebuild may still leave positive high.
    price = rbs["central"].drc_gbp * 0.5
    rb = sr.residual_band(price, rbs)
    assert rb.central.land_value == 0.0
    assert rb.land_value_low == 0.0
    assert rb.land_value_high >= 0.0
    assert sr.COST_AT_OR_ABOVE_PRICE_TAG in rb.tags
    # Upper end is P - DRC(low), floored — must not force high == central when low rebuild helps.
    assert rb.land_value_high == max(0.0, price - rbs["low"].drc_gbp)


def test_measured_zeros_count_toward_check5_share_at_zero(cfg):
    """Check 5 / negative-by-class: measured zeros count toward the zero share cap."""
    c = cfg["land_share_checks"]
    rows = [
        {"ur6_class": 1, "negative_residual": False, "land_value": 50_000, "fill_method": "observed_pooled"}
        for _ in range(8)
    ]
    # Two measured zeros (cost >= price) — must count even when negative_residual is False.
    rows += [
        {
            "ur6_class": 1,
            "negative_residual": False,
            "land_value": 0.0,
            "fill_method": "observed_pooled",
            "proxy_tags": [sr.COST_AT_OR_ABOVE_PRICE_TAG],
        }
        for _ in range(2)
    ]
    out = sh.negative_by_class_check(
        rows,
        high_demand_ur6=c["negative_high_demand_ur6"],
        max_share_high_demand=c["negative_max_share_high_demand"],
    )
    assert out["share_negative_by_ur6"][1] == 0.2


def test_na_string_round_trips_in_cost_table(tmp_path):
    """Literal rebuild_status 'n/a' survives pandas read (keep_default_na=False)."""
    rows = [
        sc._na_row("S01010206", 0),
        {
            "code": "S01013401",
            "dwellings": 100,
            "rebuild_status": "OPEN_ESTIMATE",
            "rebuild_new_gbp": 1000.0,
            "remaining_factor": 0.5,
            "drc_gbp": 500.0,
            "drc_low_gbp": 400.0,
            "drc_high_gbp": 600.0,
        },
    ]
    path = sc.write_cost_table(rows, tmp_path / "costs.csv")
    # Default pandas would turn "n/a" into NaN — prove our reader does not.
    raw = pd.read_csv(path)
    assert pd.isna(raw.loc[0, "rebuild_status"])
    got = sc.read_cost_table(path)
    assert got[0]["rebuild_status"] == "n/a"
    assert got[0]["rebuild_status"] == sc.NA_STATUS
    assert got[0]["drc_gbp"] is None
    assert got[1]["rebuild_status"] == "OPEN_ESTIMATE"
    assert got[1]["drc_gbp"] == 500.0


def test_rent_table_loader_keeps_measured_zero_and_band(tmp_path):
    sha = "a" * 64
    rows = [
        rtp.rent_row_from_resolved(
            code="S01019920",
            land=sr.LandValue(
                0.0, "observed_pooled", (sr.COST_AT_OR_ABOVE_PRICE_TAG, "negative_residual")
            ),
            dwellings=20,
            la_code="S12000049",
            ur6_class=1,
            sales_n=11,
            evidence_window="2023",
            evidence_oldest_year=2023,
            pooling_sha=sha,
            low=0.0,
            high=75.0,
        )
    ]
    path = rtp.write_rent_table(rows, tmp_path / "rent.csv")
    loaded = fill.load_2011_rent_table(path)
    assert len(loaded) == 1
    r = loaded[0]
    assert r["measured_rent"] == 0.0
    assert r["fill_method"] == "observed_pooled"
    assert r["uncertainty_low"] == 0.0
    assert r["uncertainty_high"] == 75.0
    assert fill.is_measured_zero(r)
    assert not fill._is_empty_to_fill(r, fill.ZERO_DWELLING_CODES)


def test_existing_fixture_still_loads():
    rent = fill.load_2011_rent_table(RENT)
    assert len(rent) >= 5
    empties = [r for r in rent if fill._is_empty_to_fill(r, fill.ZERO_DWELLING_CODES)]
    measured = [r for r in rent if fill._is_measured(r)]
    assert empties
    assert measured
