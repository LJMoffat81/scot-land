"""Per-residential-hectare confidence (team rule 2026-10-06) and display-only residential area.

SYNTHETIC rows and denominators; the figures are test inputs, not estimates.
"""

import pytest

from georgist.aggregator import build_payload
from georgist.display_views import RES_AREA_LOW_CONFIDENCE, surface_views

SURFACE = {"code": "S01008677", "vintage": 2011, "price_year": 2025, "measured_rent": 100_000.0,
           "uncertainty_low": 50_000.0, "uncertainty_high": 150_000.0, "value_tier": "proxy",
           "quality": "derived", "publish_level": "public_zone", "publication_status": "ok"}
DWELLINGS = {"vintage": 2011, "count_year": 2025, "total_dwellings": 500}


@pytest.mark.parametrize("denoms, confidence, reasons", [
    ({"residential_land_ha": 10.0, "share_res_uprn_in_parcels": 0.8, "mask_too_big_parcel": False}, "normal", []),
    ({"residential_land_ha": 10.0, "share_res_uprn_in_parcels": 0.49}, "low", ["share_res_uprn_in_parcels_lt_0.5"]),
    ({"residential_land_ha": 10.0, "share_res_uprn_in_parcels": 0.5}, "normal", []),  # < 0.5 only
    ({"residential_land_ha": 10.0, "mask_too_big_parcel": True}, "low", ["mask_too_big_parcel"]),
    ({"residential_land_ha": 10.0, "share_res_uprn_in_parcels": 0.2, "mask_too_big_parcel": True}, "low",
     ["share_res_uprn_in_parcels_lt_0.5", "mask_too_big_parcel"]),
    ({"settlement_area_ha": 40.0}, "low", ["settlement_mask_not_residential_land"]),
])
def test_confidence(denoms, confidence, reasons):
    out = surface_views(SURFACE, denoms, shown=True, dwelling_count=DWELLINGS)
    rh = out["views"]["per_residential_hectare"]
    assert rh["confidence"] == confidence and rh.get("confidence_reasons", []) == reasons
    if confidence == "low":
        assert out["default"] == "per_dwelling" and RES_AREA_LOW_CONFIDENCE in out["flags"]
        assert rh["value"] is not None  # still shown, just not the preferred view
    else:
        assert out["default"] == "per_residential_hectare" and RES_AREA_LOW_CONFIDENCE not in out["flags"]


def test_low_confidence_keeps_hectare_default_when_no_per_home_figure():
    out = surface_views(SURFACE, {"residential_land_ha": 10.0, "mask_too_big_parcel": True}, shown=True)
    assert out["views"]["per_dwelling"]["status"] == "denominator_pending"
    assert out["default"] == "per_residential_hectare" and out["views"]["per_residential_hectare"]["confidence"] == "low"


def test_pending_area_has_no_confidence():
    out = surface_views(SURFACE, {}, shown=True, dwelling_count=DWELLINGS)
    assert out["views"]["per_residential_hectare"]["confidence"] is None


@pytest.mark.parametrize("denoms", [
    None, {}, {"residential_land_ha": 0.5}, {"residential_land_ha": 5_000.0},
    {"settlement_area_ha": 12.0}, {"residential_land_ha": 3.0, "mask_too_big_parcel": True},
])
def test_residential_area_never_changes_surface_money_totals(denoms):
    base = build_payload(SURFACE, [], [], dwelling_count=DWELLINGS)
    p = build_payload(SURFACE, [], [], denominators=denoms, dwelling_count=DWELLINGS)
    assert p["totals_by_tier"] == base["totals_by_tier"]
    assert [c["measured_rent_gbp"] for c in p["components"]] == [c["measured_rent_gbp"] for c in base["components"]]
    assert p["display"]["views"]["per_dwelling"] == base["display"]["views"]["per_dwelling"]


def test_plot_bands_borrowed_passes_through_as_quality_flag():
    row = {**SURFACE, "quality_flags": ["plot_bands_borrowed"]}
    p = build_payload(row, [], [])
    comp = next(c for c in p["components"] if c["layer"] == "surface")
    assert comp["quality_flags"] == ["plot_bands_borrowed"] and "plot_bands_borrowed" in p["flags"]
    assert comp["measured_rent_gbp"] == SURFACE["measured_rent"]  # reported, never re-valued
    assert build_payload(SURFACE, [], [])["components"][0]["quality_flags"] == []
    # Only allowlisted tags pass; other internal tags never leak.
    leak = build_payload({**SURFACE, "proxy_tags": ["epc_mix_marginal_approx", "plot_bands_borrowed"]}, [], [])
    assert leak["components"][0]["quality_flags"] == ["plot_bands_borrowed"]
    assert "epc_mix_marginal_approx" not in leak["flags"]
