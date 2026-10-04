"""Policy scenarios sit after valuation. full_agr keeps today's charge."""

import copy

import pytest
from fastapi.testclient import TestClient

from agr.config import load_config
from agr.engine import calculate_square_agr
from agr.layers import engine_stamp
from agr.scenarios import charge_after_policy, load_policy, resolve_active_scenario
from agr.service import ValuationService
from api.main import app
from spatial.grid import snap_to_w3w_grid


def _placeholders() -> list[str]:
    scenarios = load_policy()["scenarios"]
    return sorted(
        name
        for name, spec in scenarios.items()
        if isinstance(spec, dict) and spec.get("status") == "placeholder"
    )


def test_full_agr_is_the_whole_rent_in_year_one():
    spec = load_policy()["scenarios"]["full_agr"]
    assert spec["tau"] == 1.0
    assert spec["reliefs"] == []
    assert spec["phasing"] == [{"year": 1, "share": 1.0}]
    assert spec.get("status") != "placeholder"


def test_placeholders_have_every_value_null():
    names = _placeholders()
    assert names == ["deferral", "phasing", "reliefs"]
    for name in names:
        spec = load_policy()["scenarios"][name]
        assert spec["tau"] is None
        assert spec["reliefs"] is None
        assert spec["phasing"] is None


def test_full_agr_and_existing_scenarios_keep_todays_charges():
    square = snap_to_w3w_grid(55.8642, -4.2518)
    service = ValuationService()
    for scenario in ("full_agr", "replace_income_tax", "revenue_neutral", "replace_full_basket"):
        direct = calculate_square_agr(square, scenario=scenario)
        via = service.assess_square(square, scenario=scenario)
        assert via.annual_ground_rent_gbp == direct.annual_ground_rent_gbp
        assert via.economic_annual_rent_gbp == direct.economic_annual_rent_gbp
        assert via.roll_annual_rent_parcel_gbp == direct.roll_annual_rent_parcel_gbp
        assert via.roll_annual_rent_notional_plot_gbp == direct.roll_annual_rent_notional_plot_gbp
    assert service.assess_square(square).annual_ground_rent_gbp == service.assess_square(
        square
    ).economic_annual_rent_gbp


def test_placeholder_scenario_is_http_400():
    client = TestClient(app)
    for name in _placeholders():
        response = client.get(
            "/square",
            params={"lat": 55.8642, "lng": -4.2518, "scenario": name},
        )
        assert response.status_code == 400, response.text
        assert response.json()["detail"] == "scenario not set"
        assert "scenario not set" in response.text


def test_unknown_scenario_is_not_the_placeholder_error():
    with pytest.raises(ValueError, match="Unknown scenario"):
        resolve_active_scenario("abolish_all_tax")


def test_tau_changes_only_the_policy_hash():
    config = load_config()
    original = engine_stamp(config)
    changed_policy = copy.deepcopy(load_policy())
    changed_policy["scenarios"]["full_agr"]["tau"] = 0.5
    changed = engine_stamp(config, policy=changed_policy)
    assert changed["policy"]["inputs_hash"] != original["policy"]["inputs_hash"]
    assert changed["valuation"]["inputs_hash"] == original["valuation"]["inputs_hash"]
    assert set(changed["policy"]) == {"version", "inputs_hash"}
    assert set(changed) == set(original)


def test_tau_scales_the_charge_and_leaves_the_valuation_rent(monkeypatch):
    policy = copy.deepcopy(load_policy())
    policy["scenarios"]["full_agr"]["tau"] = 0.5

    def _spec(scenario_id: str):
        if scenario_id == "full_agr":
            return policy["scenarios"]["full_agr"]
        return None

    monkeypatch.setattr("agr.service.policy_spec", _spec)
    square = snap_to_w3w_grid(55.8642, -4.2518)
    base = calculate_square_agr(square, scenario="full_agr")
    scaled = ValuationService().assess_square(square, scenario="full_agr")
    assert scaled.economic_annual_rent_gbp == base.economic_annual_rent_gbp
    assert scaled.annual_ground_rent_gbp == round(base.economic_annual_rent_gbp * 0.5, 2)
    assert scaled.roll_annual_rent_parcel_gbp == base.roll_annual_rent_parcel_gbp
    assert scaled.scenarios["replace_income_tax"]["annual_charge_gbp"] == base.scenarios[
        "replace_income_tax"
    ]["annual_charge_gbp"]
    assert charge_after_policy(10.0, policy["scenarios"]["full_agr"]) == 5.0


def test_formula_subtracts_reliefs_and_uses_the_year_one_share():
    spec = {
        "tau": 0.5,
        "reliefs": [1.0, 0.25],
        "phasing": [{"year": 2, "share": 0.25}, {"year": 1, "share": 0.5}],
    }
    assert charge_after_policy(10.0, spec) == round(0.5 * 0.5 * (10.0 - 1.25), 2)
