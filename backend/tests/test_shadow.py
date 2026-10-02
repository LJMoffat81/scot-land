from types import SimpleNamespace

from agr.shadow import beside_live_rent


def _assessment(**kwargs):
    base = dict(
        roll_annual_rent_parcel_gbp=8000.67,
        parcel_area_sqm=759.57,
        roll_annual_rent_per_sqm_gbp=10.53315,
        method="residual_drc",
        notional_plot_sqm=280,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_glasgow_anchor_is_not_cut_to_the_notional_plot():
    note = beside_live_rent(
        _assessment(),
        SimpleNamespace(rural=False, code="S12000049"),
    )
    assert note["public_rent_gbp"] == 8000.67
    assert note["land_area_sqm"] == 759.57
    assert note["land_area_sqm"] > note.get("notional_plot_sqm", 280)
    assert note["lower_land_split_applied"] is False
    assert note["hope_added"] is False
    assert note["building_kept"] is True
    assert note["gaps"] == []


def test_town_on_a_productive_council_keeps_the_published_rent():
    note = beside_live_rent(
        _assessment(
            roll_annual_rent_parcel_gbp=8.28,
            parcel_area_sqm=1897.42,
            roll_annual_rent_per_sqm_gbp=0.004364,
            method="productive_land_use",
        ),
        SimpleNamespace(rural=True, code="S12000017"),
        capability_code="888",
    )
    assert note["public_rent_gbp"] == 8.28
    assert note["gaps"][0]["id"] == "town_on_productive_rate"
    assert note["gaps"][0]["proposed_rent_gbp"] is None


def test_vacant_land_is_recorded_without_a_new_pound():
    note = beside_live_rent(
        _assessment(),
        SimpleNamespace(rural=False, code="S12000049"),
        vacant=True,
    )
    assert note["public_rent_gbp"] == 8000.67
    assert note["hope_added"] is False
    assert note["gaps"][0]["id"] == "vacant_land"
    assert note["gaps"][0]["proposed_rent_gbp"] is None
