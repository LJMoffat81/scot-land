"""E5 expected figures: every after-E12a row, and the 32 council home plots."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agr.config import load_config
from agr.engine import calculate_square_agr
from agr.fiscal import fiscal_summary
from agr.service import ValuationService
from api.main import app
from spatial.grid import snap_to_w3w_grid
from spatial.parcels import CadastralParcel
from spatial.urban_rural import NotLand

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXPECTED = FIXTURES / "expected-figures-E5-after-E12a.csv"
COUNCILS = FIXTURES / "council_layer_expected-after-E12a.csv"
EDGES = FIXTURES / "edge_pairs.csv"

# Snapshot cells for QA's 10 postcodes and 4 fixed points. Class is stable across the snap.
POINTS = {
    "fixed:aberdeenshire": (57.35, -2.4),
    "fixed:cairngorms": (57.08, -3.65),
    "fixed:glasgow": (55.8642, -4.2518),
    "fixed:wick": (58.439, -3.093),
    "pc:AB10 1AQ": (57.14905677326626, -2.0970043500611677),
    "pc:DG1 2BD": (55.06705892921308, -3.6103301114618684),
    "pc:EH1 1YZ": (55.950323392022995, -3.193038826692529),
    "pc:G1 1BL": (55.858318361480414, -4.243151736384563),
    "pc:G2 1DY": (55.86058210564139, -4.250746750193743),
    "pc:HS1 2BG": (58.20805785123967, -6.389336463646755),
    "pc:IV1 1JJ": (57.477245777937476, -4.225000535734551),
    "pc:KW1 4AA": (58.445373697448794, -3.0941375618402254),
    "pc:TD14 5AA": (55.871819978440534, -2.092316292411329),
    "pc:ZE1 0LL": (60.15512037369745, -1.1433820350575834),
}

PORTOBELLO_SEA = (55.9535, -3.100)

FISCAL_FIELDS = {
    "national_rent_pool_gbp": lambda summary: summary["collection"]["national_rent_pool_gbp"],
    "collection_annual_gbp": lambda summary: summary["collection"]["annual_gbp"],
    "surplus_gbp": lambda summary: summary["surplus_gbp"],
    "dividend_per_person_gbp": lambda summary: summary["dividend"]["per_person_gbp"],
}


def setup_function():
    load_config.cache_clear()


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _close(expected: str, actual) -> bool:
    if expected == "":
        return actual is None
    if expected in {"residual_drc", "productive_land_use"}:
        return actual == expected
    number = float(expected)
    if actual is None:
        return False
    decimals = len(expected.split(".")[1]) if "." in expected else 0
    return round(float(actual), decimals) == round(number, decimals)


def _parcel(area: float | None) -> CadastralParcel | None:
    if area is None:
        return None
    return CadastralParcel(
        inspire_id="test",
        label="test",
        national_reference="",
        area_sqm=area,
        county=None,
        geometry=None,
    )


def test_expected_figure_rows_match_to_the_penny(monkeypatch):
    grouped: dict[str, dict[str, str]] = {}
    fiscal_rows = []
    sum_row = None
    for row in _rows(EXPECTED):
        if row["point"] == "scotland" and row["field"].startswith("fiscal_summary:"):
            fiscal_rows.append(row)
            continue
        if row["point"] == "scotland":
            sum_row = row
            continue
        grouped.setdefault(row["point"], {})[row["field"]] = row["new"]

    assert set(grouped) == set(POINTS)
    holder: dict[str, CadastralParcel | None] = {"parcel": None}
    monkeypatch.setattr("agr.engine.lookup_parcel", lambda lat, lng: holder["parcel"])

    for point, fields in grouped.items():
        lat, lng = POINTS[point]
        area_text = fields.get("parcel_area_sqm", "")
        holder["parcel"] = _parcel(float(area_text) if area_text else None)
        breakdown = calculate_square_agr(snap_to_w3w_grid(lat, lng))
        assessment = breakdown.assessment
        actual = {
            "annual_ground_rent_gbp": breakdown.annual_ground_rent_gbp,
            "roll_annual_rent_notional_plot_gbp": breakdown.roll_annual_rent_notional_plot_gbp,
            "roll_annual_rent_per_sqm_gbp": assessment["roll_annual_rent_per_sqm_gbp"],
            "roll_annual_rent_parcel_gbp": breakdown.roll_annual_rent_parcel_gbp,
            "market_value_gbp": breakdown.market_value_gbp,
            "parcel_area_sqm": breakdown.parcel_area_sqm,
            "method": breakdown.method,
        }
        for field, expected in fields.items():
            assert _close(expected, actual[field]), f"{point} {field}: {actual[field]!r} != {expected!r}"

    config = load_config()
    for row in fiscal_rows:
        _prefix, scenario, field = row["field"].split(":")
        summary = fiscal_summary(scenario, config)
        assert _close(row["new"], FISCAL_FIELDS[field](summary)), row["field"]
        assert row["old"] == row["new"]

    assert sum_row is not None
    plots = [
        ValuationService(config=config)
        .assess_council_layer(row["layer_feature_code"], 57.0, -4.0, "full_agr")
        .roll_annual_rent_notional_plot_gbp
        for row in _rows(COUNCILS)
    ]
    assert len(plots) == 32
    assert _close(sum_row["new"], round(sum(plots), 2))


def test_council_layer_home_plots_within_one_pound(monkeypatch):
    monkeypatch.setattr("agr.engine.lookup_parcel", lambda lat, lng: None)
    service = ValuationService(config=load_config())
    rows = _rows(COUNCILS)
    assert len(rows) == 32
    for row in rows:
        breakdown = service.assess_council_layer(
            row["layer_feature_code"],
            float(row["layer_point_lat"]),
            float(row["layer_point_lon"]),
            "full_agr",
        )
        expected = float(row["expected_home_plot_gbp_yr"])
        got = breakdown.roll_annual_rent_notional_plot_gbp
        assert breakdown.method == "residual_drc"
        assert abs(got - expected) <= 1.0, f"{row['layer_feature_name']}: {got} != {expected}"


def test_edge_pairs_keep_their_class(monkeypatch):
    monkeypatch.setattr("agr.engine.lookup_parcel", lambda lat, lng: None)
    council_plot = {
        row["layer_feature_code"]: float(row["expected_home_plot_gbp_yr"]) for row in _rows(COUNCILS)
    }
    for row in _rows(EDGES):
        breakdown = calculate_square_agr(
            snap_to_w3w_grid(float(row["codepoint_lat"]), float(row["codepoint_lon"]))
        )
        assert breakdown.method == row["method"], row["postcode"]
        if row["method"] == "productive_land_use":
            assert breakdown.roll_annual_rent_notional_plot_gbp == 43.64
            assert breakdown.basis == "countryside"
        else:
            assert breakdown.basis == "town"
            assert abs(breakdown.roll_annual_rent_notional_plot_gbp - council_plot[row["council_code"]]) <= 0.01


def test_portobello_sea_point_is_not_land():
    lat, lng = PORTOBELLO_SEA
    with pytest.raises(NotLand):
        calculate_square_agr(snap_to_w3w_grid(lat, lng))
    client = TestClient(app)
    response = client.get("/square", params={"lat": lat, "lng": lng, "scenario": "full_agr"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reason"] == "not_land"
    assert body["agr"] is None


def test_countryside_rate_is_unchanged():
    breakdown = calculate_square_agr(snap_to_w3w_grid(57.08, -3.65))
    assert breakdown.method == "productive_land_use"
    assert breakdown.roll_annual_rent_notional_plot_gbp == 43.64
    aberdeenshire = calculate_square_agr(snap_to_w3w_grid(57.35, -2.4))
    assert aberdeenshire.method == "productive_land_use"
    assert aberdeenshire.roll_annual_rent_notional_plot_gbp == 43.64
