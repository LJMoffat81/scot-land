"""A note beside the live parcel rent.

The note records gaps the land engine has already named. It does not
replace the public pound, split a garden off the parcel, or add hope.
"""

from __future__ import annotations


def beside_live_rent(
    assessment,
    council,
    *,
    capability_code: str | None = None,
    vacant: bool = False,
) -> dict:
    """Return the live rent plus any gap that still needs a signed number."""
    gaps: list[dict] = []
    code = (capability_code or "").strip()
    if getattr(council, "rural", False) and code == "888":
        gaps.append(
            {
                "id": "town_on_productive_rate",
                "detail": (
                    "Land capability marks this parcel urban. The published "
                    "rent is still the council productive rate. A town-land "
                    "rate needs a signed number."
                ),
                "proposed_rent_gbp": None,
            }
        )
    if vacant:
        gaps.append(
            {
                "id": "vacant_land",
                "detail": (
                    "A vacant urban site still has a land rent. The signed "
                    "rule excludes hope value, so this note does not add a pound."
                ),
                "proposed_rent_gbp": None,
            }
        )
    return {
        "public_rent_gbp": assessment.roll_annual_rent_parcel_gbp,
        "land_area_sqm": assessment.parcel_area_sqm,
        "intensity_per_sqm_gbp": assessment.roll_annual_rent_per_sqm_gbp,
        "schedule": assessment.method,
        "lower_land_split_applied": False,
        "hope_added": False,
        "building_kept": True,
        "gaps": gaps,
    }
