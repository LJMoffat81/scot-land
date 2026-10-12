"""Totals: per value tier, placeholders absent publicly, breakdown/policy never added, no silent zeros."""

from georgist.aggregator import build_payload, summarise

SURFACE = {
    "code": "S01008677", "vintage": 2011, "price_year": 2023,
    "measured_rent": 100_000.0, "uncertainty_low": 60_000.0, "uncertainty_high": 150_000.0,
    "planning_uplift": 9_999_999.0, "infra_share": 40_000.0, "planning_uplift_flag": None,
    "policy_rent": 70_000.0, "policy_despec_factor": 0.70,
    "commons_class": "surface_residential", "value_tier": "proxy", "quality": "derived",
    "crosswalk_method": "none", "source_id": "ros_dz2011", "licence": "OGL-3.0",
    "publish_level": "public_zone", "negative_residual": False, "absent_from_ros_price_file": False,
}
MOCK_OIL = {"name": "North Sea Field A", "annual_rent_gbp": 750_000.0, "price_year": 2025,
            "commons_class": "extractive", "value_tier": "proxy", "quality": "placeholder",
            "publish_level": "internal"}
LEASE = {"name": "Lease X", "annual_rent_gbp": 20_000.0, "price_year": 2023,
         "commons_class": "extractive", "value_tier": "market", "quality": "live",
         "publish_level": "public_site", "source_id": "business_rates"}
PEAT = {"name": "Peat Y", "annual_rent_gbp": 5_000.0, "price_year": 2023,
        "commons_class": "eco", "value_tier": "shadow", "quality": "modelled",
        "publish_level": "public_zone"}


def test_component_carries_price_and_evidence_year():
    c = build_payload({**SURFACE, "evidence_year": 2021}, [], [])["components"][0]
    assert c["price_year"] == 2023 and c["evidence_year"] == 2021
    assert "sales_price_year" not in c and "price_base_year" not in c


def test_totals_are_per_tier_and_never_mixed():
    p = build_payload(SURFACE, [LEASE], [])
    t = p["totals_by_tier"]
    assert set(t) == {"proxy", "market"}
    assert t["proxy"]["total_gbp"] == 100_000.0
    assert t["market"]["total_gbp"] == 20_000.0
    for banned in ("total_annual_rent", "total_gbp", "surface_rent"):
        assert banned not in p
    # Shadow-priced eco rows are modelled: zone-level only, so totalled internally, never on a site publicly.
    t = build_payload(SURFACE, [LEASE], [PEAT], internal=True)["totals_by_tier"]
    assert set(t) == {"proxy", "market", "shadow"} and t["shadow"]["total_gbp"] == 5_000.0


def test_placeholders_absent_from_public_payload():
    """Rules v0.4 section 2: not flagged, absent."""
    import json

    p = build_payload(SURFACE, [MOCK_OIL], [])
    assert [c["layer"] for c in p["components"]] == ["surface"]
    assert "North Sea Field A" not in json.dumps(p) and "750000" not in json.dumps(p)
    assert p["totals_by_tier"]["proxy"]["total_gbp"] == 100_000.0
    assert not any("placeholder" in f for f in p["flags"])


def test_placeholders_listed_internally_but_never_totalled():
    p = build_payload(SURFACE, [MOCK_OIL], [], internal=True)
    oil = [c for c in p["components"] if c["name"] == "North Sea Field A"][0]
    assert oil["in_totals"] is False and oil["excluded_reason"] == "placeholder"
    assert oil["measured_rent_gbp"] == 750_000.0  # visible to developers only
    assert p["totals_by_tier"] == build_payload(SURFACE, [MOCK_OIL], [])["totals_by_tier"]
    assert "placeholders_listed_internal_only" in p["flags"]


def test_placeholder_surface_absent_publicly():
    p = build_payload({**SURFACE, "quality": "placeholder"}, [], [])
    assert p["components"] == [] and "surface_not_measured" in p["flags"]
    assert p["policy"].get("policy_rent") is None and p["attribution"].get("infra_share") is None


def test_public_component_has_no_diagnostics():
    row = {**SURFACE, "raw_residual": -5_000.0, "typical_sale_gbp": 180_000.0, "drc_low_gbp": 1.0}
    p = build_payload(row, [], [])
    assert "diagnostics" not in p["components"][0]
    assert "raw_residual" not in str(p) and "typical_sale" not in str(p)
    internal = build_payload(row, [], [], internal=True)
    assert internal["components"][0]["diagnostics"]["raw_residual"] == -5_000.0


def test_attribution_and_policy_never_added():
    p = build_payload(SURFACE, [], [])
    assert p["totals_by_tier"]["proxy"]["total_gbp"] == 100_000.0
    assert p["attribution"]["planning_uplift"] == 9_999_999.0
    assert p["attribution"]["infra_share"] == 40_000.0
    assert p["policy"]["policy_rent"] == 70_000.0
    surface = p["components"][0]
    assert surface["measured_rent_gbp"] == 100_000.0
    assert "planning_uplift" not in surface and "policy_rent" not in surface


def test_missing_surface_is_flagged_not_zero():
    p = build_payload(None, [], [])
    assert "surface_not_found" in p["flags"]
    assert p["totals_by_tier"] == {}  # nothing measured => no total, not £0


def test_null_rent_is_excluded_not_zero():
    p = build_payload({**SURFACE, "measured_rent": None}, [], [])
    assert p["components"][0]["excluded_reason"] == "no_measured_rent"
    assert p["totals_by_tier"] == {}


def test_mixed_price_years_refused_loudly():
    """Rules section 2: price_year is the money year; rents in different years are never added."""
    import pytest

    from georgist.aggregator import MixedPriceYearError

    rows = [
        {"in_totals": True, "value_tier": "proxy", "measured_rent_gbp": 1.0, "price_year": 2023,
         "uncertainty_low": 1, "uncertainty_high": 1},
        {"in_totals": True, "value_tier": "proxy", "measured_rent_gbp": 2.0, "price_year": 2025,
         "uncertainty_low": 2, "uncertainty_high": 2},
    ]
    with pytest.raises(MixedPriceYearError) as exc:
        summarise(rows)
    assert exc.value.tier == "proxy" and exc.value.price_years == [2023, 2025]
    with pytest.raises(MixedPriceYearError):  # a missing money year is refused too
        summarise([{**rows[0], "price_year": None}])
    # Different tiers in different years are fine: tiers are never added together.
    t = summarise([rows[0], {**rows[1], "value_tier": "market"}])
    assert t["proxy"]["price_year"] == 2023 and t["market"]["price_year"] == 2025


def test_evidence_year_never_drives_totals():
    a = {"in_totals": True, "value_tier": "proxy", "measured_rent_gbp": 1.0, "price_year": 2025,
         "evidence_year": 2023, "uncertainty_low": 1, "uncertainty_high": 1}
    b = {**a, "evidence_year": 2021}
    assert summarise([a, b])["proxy"]["total_gbp"] == 2.0


def test_payload_with_mixed_years_raises():
    import pytest

    from georgist.aggregator import MixedPriceYearError

    with pytest.raises(MixedPriceYearError):
        build_payload(SURFACE, [{**LEASE, "price_year": 2025}], [{**LEASE, "name": "Rates Y"}])


def test_incomplete_band_is_flagged():
    t = summarise([
        {"in_totals": True, "value_tier": "market", "measured_rent_gbp": 5.0, "price_year": 2023,
         "uncertainty_low": None, "uncertainty_high": None},
    ])
    assert t["market"]["total_gbp"] == 5.0
    assert t["market"]["low_gbp"] is None
    assert "band_incomplete" in t["market"]["flags"]


def test_negative_residual_and_absent_zone_flags_surface():
    p = build_payload({**SURFACE, "negative_residual": True, "absent_from_ros_price_file": True}, [], [])
    assert {"negative_residual", "absent_from_ros_price_file"} <= set(p["flags"])


def test_internal_and_blocked_surface_withheld():
    for over, reason in (({"publish_level": "internal"}, "not_publishable"),
                         ({"publication_status": "blocked"}, "blocked")):
        p = build_payload({**SURFACE, **over}, [], [])
        c = p["components"][0]
        assert c["excluded_reason"] == reason and c["withheld"] is True
        assert c["measured_rent_gbp"] is None and c["uncertainty_low"] is None
        assert p["attribution"]["infra_share"] is None and p["policy"]["policy_rent"] is None
        assert p["totals_by_tier"] == {}
        assert f"surface_withheld_{reason}" in p["flags"]


def test_blocked_keeps_publish_level():
    c = build_payload({**SURFACE, "publication_status": "blocked"}, [], [])["components"][0]
    assert c["publish_level"] == "public_zone" and c["publication_status"] == "blocked"
