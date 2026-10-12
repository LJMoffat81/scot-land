"""Ownership tags land; it must not rewrite land value.

Room rule (follow-up to Common Good layer):
- Public / Crown / Common Good / LA ownership does **not** zero land value.
- Value the land like any other land and **tag the owner**.
- Tax exemption belongs **only in scenario tools**, never in valuation.

Valuation callers use ``ownership_value_block`` / ``rent_unchanged_with_owners``.
Scenario tools may call ``scenario_ownership_relief_gbp`` when applying policy
reliefs to a charge. Valuation code must never call that helper.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

RULE_ID = "value_like_any_land_tag_owner"
RULE_NOTE = (
    "Public, Crown, local-authority and Common Good ownership does not zero "
    "land value. Value the land like any other land and tag the owner. "
    "Tax exemption belongs only in scenario tools, never in valuation."
)

# Owner classes that must never silently zero measured / residual rent.
PUBLIC_OWNER_CLASSES = frozenset(
    {
        "public_or_crown",
        "common_good",
        "local_authority_holding",
    }
)


def rent_unchanged_with_owners(
    rent_gbp: float | None,
    owners: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return rent unchanged beside owner tags. Never floors public land to zero."""
    tags = [dict(row) for row in (owners or [])]
    publicish = any(
        str(row.get("owner_class") or "") in PUBLIC_OWNER_CLASSES for row in tags
    )
    return {
        "rule": RULE_ID,
        "valuation_affected": False,
        "rent_gbp": None if rent_gbp is None else float(rent_gbp),
        "owners": tags,
        "public_or_community_owner": publicish,
        "note": RULE_NOTE,
    }


def owner_tags_from_place_fields(
    *,
    public_or_crown: Mapping[str, Any] | None = None,
    common_good: Mapping[str, Any] | None = None,
    local_authority_holding: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build owner tags from place-card ownership blocks (no value maths)."""
    tags: list[dict[str, Any]] = []
    public = public_or_crown or {}
    if public.get("on_this_point"):
        holdings = public.get("holdings") or []
        if holdings:
            for holding in holdings:
                org = (holding or {}).get("organisation")
                tags.append(
                    {
                        "owner_class": "public_or_crown",
                        "label": org or "Public or Crown Estate holding",
                        "organisation": org,
                        "site_name": (holding or {}).get("site_name"),
                        "source": "sg_public_land_2024",
                    }
                )
        else:
            tags.append(
                {
                    "owner_class": "public_or_crown",
                    "label": "Public or Crown Estate holding",
                    "source": "sg_public_land_2024",
                }
            )

    la = local_authority_holding or {}
    if la.get("on_this_point"):
        tags.append(
            {
                "owner_class": "local_authority_holding",
                "label": "Local-authority holding",
                "source": "la_ownership",
                "note": la.get("reason"),
            }
        )

    cg = common_good or {}
    # Common Good has no national on-point geometry yet — tag when a council
    # register / spatial metadata link is present so ownership stays visible
    # without inventing an intersection or zeroing rent.
    if cg.get("status") == "linked" and (cg.get("register") or cg.get("spatial")):
        register = cg.get("register") or {}
        spatial = cg.get("spatial") or {}
        tags.append(
            {
                "owner_class": "common_good",
                "label": register.get("label")
                or spatial.get("label")
                or "Common Good (council register linked)",
                "status": "linked",
                "on_this_point": cg.get("on_this_point"),
                "register_url": register.get("url"),
                "metadata_url": spatial.get("metadata_url"),
                "source": "common_good_registers",
                "note": (
                    "Statutory / indicative Common Good link for this council. "
                    "Not an on-point title hit; value is still assessed."
                ),
            }
        )
    return tags


def ownership_value_block(place: Mapping[str, Any]) -> dict[str, Any]:
    """Place-card block: owners tagged; valuation explicitly not rewritten."""
    owners = owner_tags_from_place_fields(
        public_or_crown=place.get("public_or_crown"),
        common_good=place.get("common_good"),
        local_authority_holding=place.get("local_authority_holding"),
    )
    return rent_unchanged_with_owners(None, owners)


def scenario_ownership_relief_gbp(
    rent_gbp: float,
    owners: Iterable[Mapping[str, Any]] | None,
    ownership_reliefs: Mapping[str, Any] | None,
) -> float:
    """Named ownership reliefs for **scenario charges only**.

    ``ownership_reliefs`` maps owner_class → share in [0, 1] of rent to relieve
    (1.0 = full exemption). Missing / empty map → £0 relief (no silent zeroing).
    Valuation must never call this.
    """
    reliefs = ownership_reliefs or {}
    if not reliefs:
        return 0.0
    rent = float(rent_gbp)
    if rent <= 0:
        return 0.0
    share = 0.0
    seen: set[str] = set()
    for row in owners or []:
        owner_class = str(row.get("owner_class") or "")
        if not owner_class or owner_class in seen:
            continue
        if owner_class not in reliefs:
            continue
        seen.add(owner_class)
        raw = reliefs[owner_class]
        try:
            part = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"ownership_reliefs[{owner_class!r}] must be a number in [0, 1]"
            ) from exc
        if part < 0.0 or part > 1.0:
            raise ValueError(
                f"ownership_reliefs[{owner_class!r}] must be a number in [0, 1]"
            )
        share = max(share, part)
    return round(rent * share, 2)
