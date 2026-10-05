"""Data-zone residual: shrinkage, no 15% floor, diminishing parcel rent."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from agr.areas import CouncilArea, lookup_council
from agr.config import load_config
from agr.engine import calculate_square_agr
from agr.fiscal import basket_total_gbp
from agr.service import ValuationService
from agr.valuation import assess_for_agr_roll
from agr.zone_prices import (
    PINNED_SOURCE_SHA256,
    RESOURCE_ID,
    parse_sales_table,
    refresh_price_table,
    resolve_zone_market_value,
)
from spatial.grid import snap_to_w3w_grid

ROOT = Path(__file__).resolve().parents[2]
PRICES = ROOT / "data" / "processed" / "dz2011_prices.csv"


def setup_function():
    load_config.cache_clear()


def _weak() -> CouncilArea:
    return CouncilArea(
        code="S12000099",
        name="Weak market",
        average_price_gbp=50000,
        annual_change_pct=None,
        rural=False,
        distance_km=1.0,
        lookup_method="boundary",
    )


def test_glasgow_dwelling_rent_and_diminishing_parcel():
    glasgow = lookup_council(55.8642, -4.2518)
    assert glasgow.rural is False
    config = load_config()
    area = 760.0
    assessment = assess_for_agr_roll(glasgow, config, parcel_area_sqm=area)

    assert assessment.method == "residual_drc"
    assert assessment.site_capital_market_gbp == pytest.approx(
        assessment.market_value_gbp - assessment.drc_improvements_gbp,
        abs=0.05,
    )
    assert assessment.roll_annual_rent_notional_plot_gbp == round(
        assessment.site_capital_economic_gbp * assessment.yield_rate,
        2,
    )
    eta = float(config["valuer_roll"]["area_elasticity"])
    cap = float(config["valuer_roll"]["max_area_ratio"])
    ratio = min(area / assessment.notional_plot_sqm, cap)
    assert ratio < cap
    expected = round(assessment.roll_annual_rent_notional_plot_gbp * (ratio ** eta), 2)
    assert assessment.roll_annual_rent_parcel_gbp == expected
    linear = round(assessment.roll_annual_rent_per_sqm_gbp * area, 2)
    assert assessment.roll_annual_rent_parcel_gbp != linear
    text = " ".join(assessment.notes)
    assert "The ceiling binds" not in text
    assert "bound, not an estimate" in text
    assert "Research estimate, not an official valuation or a tax bill." in text
    assert "0.70" in text or "0.70 ×" in text or "Effective rate" in text
    assert assessment.mv_council_gbp == pytest.approx(glasgow.average_price_gbp, abs=0.01)


def test_weak_market_publishes_zero_and_keeps_the_old_floor_as_sensitivity():
    assessment = assess_for_agr_roll(_weak(), parcel_area_sqm=400)
    assert assessment.market_value_gbp < assessment.drc_improvements_gbp
    assert assessment.site_capital_market_gbp == 0
    assert assessment.roll_annual_rent_notional_plot_gbp == 0
    assert assessment.roll_annual_rent_parcel_gbp == 0
    sensitivity = assessment.site_capital_clamped_sensitivity_gbp
    assert sensitivity == pytest.approx(50000 * 0.15, abs=0.02)
    assert sensitivity != assessment.site_capital_market_gbp
    assert sensitivity != assessment.roll_annual_rent_notional_plot_gbp
    assert "The residual is at or below the margin." in assessment.notes
    assert "Research estimate, not an official valuation or a tax bill." in assessment.notes


def test_large_parcel_area_ratio_cap_binds():
    glasgow = lookup_council(55.8642, -4.2518)
    config = load_config()
    area = 100_000.0  # 10 ha
    assessment = assess_for_agr_roll(glasgow, config, parcel_area_sqm=area)
    cap = float(config["valuer_roll"]["max_area_ratio"])
    eta = float(config["valuer_roll"]["area_elasticity"])
    raw_ratio = area / assessment.notional_plot_sqm
    assert raw_ratio > cap
    expected = round(assessment.roll_annual_rent_notional_plot_gbp * (cap ** eta), 2)
    assert assessment.roll_annual_rent_parcel_gbp == expected
    assert any("area-ratio cap binds" in note for note in assessment.notes)
    linear = assessment.roll_annual_rent_per_sqm_gbp * area
    assert assessment.roll_annual_rent_parcel_gbp != pytest.approx(linear, rel=0.05)


def test_rural_large_parcel_stays_linear_category_rent():
    rural = lookup_council(57.08, -3.65)
    assessment = assess_for_agr_roll(rural, parcel_area_sqm=100_000)
    assert assessment.method == "productive_land_use"
    assert assessment.roll_annual_rent_notional_plot_gbp == 43.64
    assert assessment.roll_annual_rent_parcel_gbp == pytest.approx(43.64 * 10, abs=0.05)
    assert assessment.roll_annual_rent_parcel_gbp > 400
    text = " ".join(assessment.notes)
    assert "median" not in text.lower()
    assert "area-ratio cap binds" not in text
    assert "not applied" in text
    assert "Uniform category rent" in text


def test_suppressed_data_zone_uses_the_parent_and_not_zero():
    evidence = resolve_zone_market_value(
        "S01006520",
        council_median_gbp=134923,
        shrinkage_k=8,
        path=PRICES,
    )
    assert evidence.market_value_gbp == 308000
    assert evidence.market_value_gbp != 0
    # A blend that treated the blank price as zero would be (3×0 + 8×308000) / 11.
    assert evidence.market_value_gbp != pytest.approx((8 * 308000) / 11, abs=1)
    assert evidence.mv_council_gbp == 134923
    assert "suppressed, parent median used" in evidence.notes
    assert evidence.zone_median_gbp is None


def test_thin_zone_shrinks_between_the_zone_and_its_parent():
    evidence = resolve_zone_market_value(
        "S01006507",
        council_median_gbp=134923,
        shrinkage_k=8,
        path=PRICES,
    )
    zone = 145000
    parent = 138550
    assert evidence.zone_median_gbp == zone
    assert evidence.parent_median_gbp == parent
    assert evidence.sales_count == 7
    assert min(zone, parent) < evidence.market_value_gbp < max(zone, parent)
    assert evidence.market_value_gbp == pytest.approx((7 * zone + 8 * parent) / 15, abs=0.01)
    assert evidence.mv_council_gbp == 134923
    assert evidence.market_value_gbp != evidence.mv_council_gbp


def test_missing_sales_count_does_not_shrink_as_zero(tmp_path):
    path = tmp_path / "thin.csv"
    path.write_text(
        "dz2011,iz2011,dz_n2023,dz_med2023,iz_n2023,iz_med2023,ca_n2023,ca_med2023\n"
        "S01000001,S02000001,,180000,20,100000,100,90000\n",
        encoding="utf-8",
    )
    evidence = resolve_zone_market_value(
        "S01000001",
        council_median_gbp=50000,
        shrinkage_k=8,
        path=path,
    )
    assert evidence.market_value_gbp == 100000
    assert evidence.zone_median_gbp == 180000
    assert "Sales count missing, parent median used." in evidence.notes
    assert "suppressed, parent median used" not in evidence.notes


def test_open_table_parser_ignores_the_mean_and_keeps_a_blank_median():
    rows = list(
        csv.DictReader(
            [
                "GeographyCode,GeographyName,GeographyType,DateCode,Measurement,Units,Value,Sales",
                "S01006520,Suppressed,2011 Data Zones,2023,Median,GBP,,3",
                "S01006520,Suppressed,2011 Data Zones,2023,Count,Count,3,3",
                "S01006520,Suppressed,2011 Data Zones,2023,Mean,GBP,999999,3",
                "S02001238,Parent,2011 Intermediate Zones,2023,Median,GBP,308000,90",
                "S01006507,Thin,2011 Data Zones,2023,Median,GBP,145000,7",
                "S01006507,Thin,2011 Data Zones,2023,Count,Count,7,7",
                "S01006507,Thin,2011 Data Zones,2023,Mean,GBP,10,7",
                "S12000033,Aberdeen,Council Areas,2022,Median,GBP,1,10",
            ]
        )
    )
    parsed = parse_sales_table(rows)
    assert parsed["year"] == 2023
    assert parsed["data_zone"]["S01006520"]["median"] is None
    assert parsed["data_zone"]["S01006520"]["n"] == 3
    assert parsed["data_zone"]["S01006507"]["median"] == 145000
    assert parsed["intermediate_zone"]["S02001238"]["median"] == 308000
    assert "S12000033" not in parsed["council_area"]


def test_scenario_multipliers_are_unchanged_and_applied_after_valuation(monkeypatch):
    monkeypatch.setattr("agr.engine.lookup_parcel", lambda lat, lng: None)
    config = load_config()
    square = snap_to_w3w_grid(55.9533, -3.1883)
    full = calculate_square_agr(square, scenario="full_agr", config=config)
    income = calculate_square_agr(square, scenario="replace_income_tax", config=config)
    basket_case = calculate_square_agr(square, scenario="replace_full_basket", config=config)

    pool = float(config["macro"]["estimated_scotland_annual_rent_gbp"])
    income_target = float(config["macro"]["scotland_income_tax_replacement_gbp"])
    basket = basket_total_gbp(config)
    assert income.roll_annual_rent_notional_plot_gbp == full.roll_annual_rent_notional_plot_gbp
    assert income.roll_annual_rent_parcel_gbp == full.roll_annual_rent_parcel_gbp
    assert income.annual_ground_rent_gbp == pytest.approx(
        full.economic_annual_rent_gbp * (income_target / pool),
        abs=0.02,
    )
    assert basket_case.annual_ground_rent_gbp == pytest.approx(
        full.economic_annual_rent_gbp * (basket / pool),
        abs=0.02,
    )
    text = " ".join(full.assessment["notes"])
    assert "11.5/90" not in text
    assert "17.1/90" not in text
    source = Path(assess_for_agr_roll.__code__.co_filename).read_text(encoding="utf-8")
    assert "11.5/90" not in source
    assert "17.1/90" not in source


def test_missing_price_file_or_failed_download_uses_the_council_median(tmp_path):
    missing = tmp_path / "absent.csv"
    evidence = resolve_zone_market_value(
        "S01006507",
        council_median_gbp=134923,
        path=missing,
    )
    assert evidence.market_value_gbp == 134923
    assert evidence.mv_council_gbp == 134923
    assert evidence.zone_median_gbp is None
    assert "No data-zone price was fabricated." in " ".join(evidence.notes)
    assert "145000" not in " ".join(evidence.notes)

    def boom():
        raise OSError("download failed")

    changed = {"result": {"resources": [{"id": RESOURCE_ID, "hash": "deadbeef"}]}}
    assert refresh_price_table(lambda: changed, boom, missing) == "kept"
    assert not missing.exists()
    assert refresh_price_table(boom, boom, missing) == "kept"

    kept = tmp_path / "already.csv"
    kept.write_text("keep\n", encoding="utf-8")
    assert refresh_price_table(boom, boom, kept) == "kept"
    assert kept.read_text(encoding="utf-8") == "keep\n"

    calls: list[str] = []
    current = {
        "result": {"resources": [{"id": RESOURCE_ID, "hash": PINNED_SOURCE_SHA256}]}
    }
    assert refresh_price_table(lambda: current, lambda: calls.append("downloaded"), missing) == "current"
    assert calls == []


def test_engine_publishes_the_shrunk_zone_price(monkeypatch):
    monkeypatch.setattr("agr.engine.zone_code_at", lambda lat, lng: "S01006507")
    monkeypatch.setattr("agr.engine.lookup_parcel", lambda lat, lng: None)
    square = snap_to_w3w_grid(57.14905677326626, -2.0970043500611677)
    breakdown = calculate_square_agr(square, scenario="full_agr")
    assert breakdown.method == "residual_drc"
    assert breakdown.market_value_gbp == pytest.approx(141560, abs=0.01)
    assert breakdown.average_price_gbp != breakdown.market_value_gbp
    assert breakdown.assessment["mv_council_gbp"] == breakdown.average_price_gbp
    assert "suppressed, parent median used" not in " ".join(breakdown.assessment["notes"])


def test_council_layer_does_not_take_the_sample_points_zone(monkeypatch):
    monkeypatch.setattr("agr.engine.zone_code_at", lambda lat, lng: "S01006507")
    breakdown = ValuationService(config=load_config()).assess_council_layer(
        "S12000033",
        57.15,
        -2.1,
        "full_agr",
    )
    assert breakdown.market_value_gbp == breakdown.average_price_gbp
    assert breakdown.market_value_gbp != pytest.approx(141560)
