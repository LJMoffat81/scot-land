"""Valuation date on the stamp. Figures stay where they are."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from agr.config import load_config
from agr.layers import engine_stamp
from api.main import app

SOURCE = "Scottish non-domestic revaluation 2026 tone date"
UNKNOWN_KEYS = (
    "valuer_roll.yield_rate",
    "valuer_roll.rebuild.house_gbp_per_m2",
    "valuer_roll.rebuild.flat_gbp_per_m2",
    "valuer_roll.depreciation.average_stock_remaining_factor",
    "despeculation.farmland_market_to_productive",
    "despeculation.urban_speculation_discount",
)


def _assert_valuation_date(stamp: dict, config: dict) -> None:
    valuation = stamp["valuation"]
    assert valuation["valuation_date"] == "2025-04-01"
    assert valuation["rebased_to_valuation_date"] is False
    as_of = valuation["inputs_as_of"]
    assert isinstance(as_of, dict) and as_of
    land = config["land_use_values_gbp_per_ha_2009"]
    expected = {key: "unknown" for key in UNKNOWN_KEYS}
    expected.update({f"land_use_values_gbp_per_ha_2009.{name}": "2009" for name in land})
    assert as_of == expected
    assert config["_meta"]["valuation.valuation_date"]["source"] == SOURCE


def test_stamp_carries_the_valuation_date_and_input_dates():
    config = load_config()
    _assert_valuation_date(engine_stamp(config), config)


def test_square_and_postcode_carry_the_valuation_date(monkeypatch):
    monkeypatch.delenv("W3W_API_KEY", raising=False)
    monkeypatch.setattr("api.main.lookup_parcel_geojson", lambda lat, lng: None)

    class _Response:
        status_code = 200

        def json(self):
            return {
                "result": {
                    "postcode": "G1 1BL",
                    "latitude": 55.8642,
                    "longitude": -4.2518,
                    "parish": None,
                    "admin_district": "Glasgow City",
                    "country": "Scotland",
                }
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, *args, **kwargs):
            if str(url).rstrip("/").endswith("G11BL"):
                return _Response()
            raise httpx.HTTPError("offline in test")

    monkeypatch.setattr("api.main.httpx.Client", _Client)
    client = TestClient(app)
    config = load_config()

    square = client.get("/square", params={"lat": 55.8642, "lng": -4.2518, "scenario": "full_agr"})
    assert square.status_code == 200, square.text
    _assert_valuation_date(square.json()["agr"]["stamp"], config)

    postcode = client.get("/postcode/G1 1BL", params={"scenario": "full_agr"})
    assert postcode.status_code == 200, postcode.text
    _assert_valuation_date(postcode.json()["agr"]["stamp"], config)
