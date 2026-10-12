"""Public / Common Good ownership tags the owner; it must not zero land value."""

from __future__ import annotations

import pytest

from agr.scenarios import charge_after_policy
from layers.ownership_value import (
    RULE_ID,
    owner_tags_from_place_fields,
    ownership_value_block,
    rent_unchanged_with_owners,
    scenario_ownership_relief_gbp,
)
from layers.platform import place_context


def test_public_owner_does_not_zero_rent():
    rent = 12_345.67
    out = rent_unchanged_with_owners(
        rent,
        [{"owner_class": "public_or_crown", "label": "NatureScot"}],
    )
    assert out["valuation_affected"] is False
    assert out["rent_gbp"] == rent
    assert out["public_or_community_owner"] is True
    assert out["rule"] == RULE_ID


def test_common_good_tag_without_on_point_hit():
    tags = owner_tags_from_place_fields(
        common_good={
            "status": "linked",
            "on_this_point": None,
            "register": {
                "url": "https://example.invalid/common-good",
                "label": "Example Common Good register",
            },
        }
    )
    assert len(tags) == 1
    assert tags[0]["owner_class"] == "common_good"
    assert tags[0]["on_this_point"] is None
    valued = rent_unchanged_with_owners(999.0, tags)
    assert valued["rent_gbp"] == 999.0
    assert valued["valuation_affected"] is False


def test_place_context_exposes_ownership_value_contract(monkeypatch):
    # Public/Crown overlay stays a gap on main (unverified licence) — do not
    # reintroduce public_land_at_point. Ownership tags still surface via
    # Common Good linked registers without zeroing rent.
    monkeypatch.setattr(
        "layers.platform.vdl_at_point",
        lambda lat, lng: {"ok": True, "intersects": False, "sites": []},
    )
    monkeypatch.setattr(
        "layers.platform.hla_at_point",
        lambda lat, lng: {"ok": True, "intersects": False, "sites": []},
    )
    monkeypatch.setattr(
        "layers.platform.lookup_parcel_geojson",
        lambda lat, lng: None,
    )
    monkeypatch.setattr(
        "layers.platform._land_register_outline",
        lambda lat, lng: None,
    )
    monkeypatch.setattr(
        "layers.platform.place_common_good",
        lambda code: {
            "status": "linked",
            "on_this_point": None,
            "register": {
                "url": "https://example.invalid/cg",
                "label": "Linked Common Good register",
            },
            "spatial": None,
            "reason": "test",
            "national_gap": "No single open national Common Good spatial layer.",
        },
    )

    card = place_context(56.0, -3.5, council_code="S12000036")
    block = card["ownership_value"]
    assert block["valuation_affected"] is False
    assert block["rent_gbp"] is None
    assert card["public_or_crown"]["status"] == "gap"
    assert card["public_or_crown"]["on_this_point"] is None
    classes = {row["owner_class"] for row in block["owners"]}
    assert "public_or_crown" not in classes
    assert "common_good" in classes
    assert ownership_value_block(card)["rule"] == RULE_ID


def test_ownership_value_tags_public_when_on_point_present():
    """If a licensed public overlay later sets on_this_point, tag — do not zero."""
    block = ownership_value_block(
        {
            "public_or_crown": {
                "status": "live",
                "on_this_point": True,
                "holdings": [
                    {
                        "organisation": "Forestry and Land Scotland",
                        "site_name": "Test forest",
                    }
                ],
            },
            "common_good": {"status": "gap"},
            "local_authority_holding": {"status": "gap"},
        }
    )
    assert block["valuation_affected"] is False
    assert block["rent_gbp"] is None
    assert block["public_or_community_owner"] is True
    assert {row["owner_class"] for row in block["owners"]} == {"public_or_crown"}


def test_scenario_ownership_relief_only_reduces_charge_not_rent():
    rent = 1000.0
    owners = [{"owner_class": "common_good", "label": "Common Good"}]
    # Valuation path: rent stays
    assert rent_unchanged_with_owners(rent, owners)["rent_gbp"] == rent
    # Scenario path: optional ownership_reliefs reduce the charge only
    assert scenario_ownership_relief_gbp(rent, owners, {}) == 0.0
    assert scenario_ownership_relief_gbp(rent, owners, {"common_good": 1.0}) == 1000.0
    charge = charge_after_policy(
        rent,
        {
            "tau": 1.0,
            "reliefs": [],
            "ownership_reliefs": {"common_good": 1.0},
            "phasing": [{"year": 1, "share": 1.0}],
        },
        owners=owners,
    )
    assert charge == 0.0
    # Without ownership_reliefs, full_agr still charges the full rent
    assert (
        charge_after_policy(
            rent,
            {
                "tau": 1.0,
                "reliefs": [],
                "ownership_reliefs": {},
                "phasing": [{"year": 1, "share": 1.0}],
            },
            owners=owners,
        )
        == rent
    )


def test_scenario_ownership_relief_rejects_bad_share():
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        scenario_ownership_relief_gbp(
            100.0,
            [{"owner_class": "public_or_crown"}],
            {"public_or_crown": 1.5},
        )
