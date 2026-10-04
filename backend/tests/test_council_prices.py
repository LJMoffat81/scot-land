"""Town market value is the indexed 2023 council median. Farmland stays farmland."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agr.config import load_config
from agr.layers import DZ_PRICES_SHA256, engine_stamp
from agr.valuation import assess_for_agr_roll
from scripts.build_council_prices import PRICE_BASIS, PRICE_YEAR, indexed_council_prices

ROOT = Path(__file__).resolve().parents[2]
COUNCILS_PATH = ROOT / "data" / "processed" / "councils.json"
DZ_PATH = ROOT / "data" / "processed" / "dz2011_prices.csv"

def _councils() -> list[dict]:
    return json.loads(COUNCILS_PATH.read_text(encoding="utf-8"))["councils"]


def _by_code() -> dict[str, dict]:
    return {council["code"]: council for council in _councils()}


def test_indexed_prices_match_the_engine_references():
    councils = _by_code()
    assert councils["S12000049"]["average_price_gbp"] == 187_858
    assert councils["S12000049"]["name"] == "City of Glasgow"
    assert councils["S12000017"]["average_price_gbp"] == 209_114
    assert councils["S12000036"]["average_price_gbp"] == 285_882
    fresh = indexed_council_prices()
    for council in councils.values():
        assert council["average_price_gbp"] == fresh[council["code"]]
        assert council["price_basis"] == PRICE_BASIS
        assert council["price_year_basis"] == PRICE_YEAR


def test_no_council_is_flagged_wholly_rural():
    councils = _by_code()
    assert all(council["rural"] is False for council in councils.values())
    context = {code for code, council in councils.items() if council.get("rural_context")}
    assert context == {
        "S12000013",
        "S12000017",
        "S12000023",
        "S12000027",
        "S12000035",
    }
    # The £145,000 rule is gone. A low price does not flip the council.
    assert councils["S12000050"]["name"] == "North Lanarkshire"
    assert councils["S12000050"]["average_price_gbp"] < 145_000
    assert councils["S12000050"]["rural"] is False


def _highland(price: int):
    highland = _by_code()["S12000017"]

    class _Council:
        code = highland["code"]
        name = highland["name"]
        average_price_gbp = price
        annual_change_pct = highland["annual_change_pct"]
        rural = True
        distance_km = 0.0
        lookup_method = "boundary"

    return _Council()


def test_farmland_rent_ignores_the_new_town_price():
    config = load_config()
    low = assess_for_agr_roll(_highland(1), config, parcel_area_sqm=1897.42)
    high = assess_for_agr_roll(_highland(999_999), config, parcel_area_sqm=1897.42)
    assert low.method == "productive_land_use"
    assert low.market_value_gbp is None
    assert low.roll_annual_rent_parcel_gbp == high.roll_annual_rent_parcel_gbp == 8.28
    assert "median" not in " ".join(low.notes).lower()


def test_price_file_is_the_pinned_release_and_the_stamp_names_it():
    digest = hashlib.sha256(DZ_PATH.read_bytes()).hexdigest()
    assert digest == DZ_PRICES_SHA256
    price_data = engine_stamp(load_config())["valuation"]["price_data"]
    assert price_data["file_sha256"] == DZ_PRICES_SHA256
    assert price_data["year"] == 2023
    assert price_data["source"].startswith("RoS Residential Properties Sales and Price")
    assert "2025-04-01" in price_data["index"]
    assert engine_stamp(load_config())["valuation"]["valuation_date"] == "2025-04-01"
