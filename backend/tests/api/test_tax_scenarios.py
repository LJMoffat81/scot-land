"""Tax scenario tools: Surface Rent × capture rate; research estimates only; no invented totals."""

from __future__ import annotations

import pytest

from georgist.tax_scenarios import (
    CAPTURE_NOTE,
    DISCLAIMER,
    LENS,
    TaxScenarioError,
    ZoneRentRow,
    aggregate_by_council,
    illustrated_collection,
    parse_capture_rate,
    zone_illustration,
    zone_row_from_db,
)


def _row(
    code: str = "S01008677",
    la_code: str = "S12000036",
    la_name: str = "City of Edinburgh",
    rent: float = 100_000.0,
    price_year: int = 2025,
    **extra,
) -> ZoneRentRow:
    return ZoneRentRow(
        code=code,
        vintage=2011,
        la_code=la_code,
        la_name=la_name,
        measured_rent=rent,
        price_year=price_year,
        **extra,
    )


def test_parse_capture_rate_bounds():
    assert parse_capture_rate(0) == 0.0
    assert parse_capture_rate("0.5") == 0.5
    assert parse_capture_rate(1) == 1.0
    with pytest.raises(TaxScenarioError) as exc:
        parse_capture_rate(1.01)
    assert exc.value.code == "invalid_capture_rate"
    with pytest.raises(TaxScenarioError):
        parse_capture_rate("nope")


def test_illustrated_collection_is_product():
    assert illustrated_collection(100_000.0, 0.25) == 25_000.0
    assert illustrated_collection(80_000.0, 0.0) == 0.0


def test_aggregate_by_council_sums_and_labels():
    rows = [
        _row("S01008677", rent=100_000.0),
        _row("S01008678", rent=50_000.0),
        _row("S01009000", la_code="S12000049", la_name="Glasgow City", rent=200_000.0),
    ]
    out = aggregate_by_council(rows, capture_rate=0.5)
    assert out["lens"] == LENS
    assert out["disclaimer"] == DISCLAIMER
    assert out["capture_note"] == CAPTURE_NOTE
    assert out["status"] == "experimental_research_estimate"
    assert out["national"]["zone_count"] == 3
    assert out["national"]["measured_rent_total_gbp"] == 350_000.0
    assert out["national"]["illustrated_collection_gbp"] == 175_000.0
    assert out["national"]["disclaimer"] == DISCLAIMER
    by_name = {c["la_name"]: c for c in out["by_council"]}
    assert by_name["City of Edinburgh"]["illustrated_collection_gbp"] == 75_000.0
    assert by_name["Glasgow City"]["measured_rent_total_gbp"] == 200_000.0
    assert "Sandilands" in out["note"] or "national rent pool" in out["note"]
    assert "AGR" in out["lens_note"]


def test_aggregate_refuses_mixed_price_years():
    rows = [_row(price_year=2025), _row("S01008678", price_year=2024)]
    with pytest.raises(TaxScenarioError) as exc:
        aggregate_by_council(rows, capture_rate=1.0)
    assert exc.value.code == "mixed_price_years"
    assert 2024 in exc.value.extra["price_years"] and 2025 in exc.value.extra["price_years"]


def test_aggregate_la_filter():
    rows = [
        _row(rent=10_000.0),
        _row("S01009000", la_code="S12000049", la_name="Glasgow City", rent=99_000.0),
    ]
    out = aggregate_by_council(rows, capture_rate=1.0, la_code="S12000036")
    assert out["national"]["zone_count"] == 1
    assert out["national"]["measured_rent_total_gbp"] == 10_000.0
    assert [c["la_code"] for c in out["by_council"]] == ["S12000036"]


def test_zone_row_from_db_filters_unpublishable_and_zero_dwellings():
    base = {
        "code": "S01008677",
        "vintage": 2011,
        "measured_rent": 12_000.0,
        "price_year": 2025,
        "quality": "derived",
        "publish_level": "public_zone",
        "publication_status": "ok",
        "la_code": "S12000036",
        "la_name": "City of Edinburgh",
        "flags": "",
    }
    assert zone_row_from_db(base) is not None
    assert zone_row_from_db({**base, "quality": "placeholder"}) is None
    assert zone_row_from_db({**base, "publish_level": "internal"}) is None
    assert zone_row_from_db({**base, "publication_status": "blocked"}) is None
    assert zone_row_from_db({**base, "measured_rent": None}) is None
    assert zone_row_from_db({**base, "flags": "zero_dwellings"}) is None
    assert zone_row_from_db({**base, "flags": "no_census2022_household_residents;zero_dwellings"}) is None


def test_zone_illustration_share_and_labels():
    z = _row(rent=25_000.0)
    out = zone_illustration(z, capture_rate=0.2, council_measured_total=100_000.0, council_zone_count=4)
    assert out["zone"]["illustrated_collection_gbp"] == 5_000.0
    assert out["zone"]["share_of_council_measured_rent"] == 0.25
    assert out["council"]["illustrated_collection_gbp"] == 20_000.0
    assert out["disclaimer"] == DISCLAIMER
    assert out["zone"]["disclaimer"] == DISCLAIMER
    assert out["lens"] == LENS


def test_tax_scenario_routes_registered():
    from api.main import app, registered_routes

    paths = {p for _, p in registered_routes(app)}
    assert "/georgist/tax-scenario" in paths
    assert "/georgist/tax-scenario/zone" in paths


def test_tax_scenario_publication_rules_are_zone_modelled():
    from georgist.publication_rules import rule_for

    for path in ("/georgist/tax-scenario", "/georgist/tax-scenario/zone"):
        rule = rule_for(path)
        assert rule.geometry_level == "zone"
        assert rule.value_basis == "modelled"


def test_tax_scenario_is_503_without_db(client):
    r = client.get("/georgist/tax-scenario", params={"vintage": "2011", "capture_rate": 0.5})
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error"] == "wealth_database_unavailable"
    assert detail["reason"] == "not_configured"


def test_tax_scenario_zone_is_503_without_db(client):
    r = client.get(
        "/georgist/tax-scenario/zone",
        params={"zone_id": "S01008677", "capture_rate": 1.0},
    )
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "wealth_database_unavailable"


def test_tax_scenario_rejects_bad_capture_rate_and_la(client):
    bad_rate = client.get("/georgist/tax-scenario", params={"capture_rate": 2})
    assert bad_rate.status_code == 422
    assert bad_rate.json()["detail"]["error"] == "invalid_capture_rate"
    bad_la = client.get("/georgist/tax-scenario", params={"la_code": "S01008677"})
    assert bad_la.status_code == 422
    assert bad_la.json()["detail"]["error"] == "invalid_la_code"


def test_tax_scenario_zone_rejects_unknown_zone(client):
    r = client.get("/georgist/tax-scenario/zone", params={"zone_id": "unknown"})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "invalid_zone_id"
