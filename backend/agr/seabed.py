"""Published Crown Estate Scotland seabed rents for one lease outline.

The bill is the lease polygon, not the 12-mile sea, a marine region, or the
Scottish zone. A note is a published rent rule, or a statement that the
yearly rent is not in the open file. Nothing here is a computed yearly
total, and nothing here is added to the land charge.

Aquaculture tariffs are the Crown Estate Scotland rents-and-charges page.
The open lease does not record equipment length, species inside a shellfish
outline, harvest, or consented biomass, so those tariffs stay rules.
ScotWind's generating rent and the one-off option fees are not in the open
lease attributes, and they are not applied. The Shetland, Orkney, and Outer
Hebrides shellfish discount ended on 1 January 2026 and is not applied.
"""

from __future__ import annotations

import re

_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &'./-]{0,79}$")

# Visitor copy. Kept here so a test can pin the rule and reject a yearly total.
_FINFISH = (
    "Crown Estate Scotland charges salmon at 1% of notional turnover, and "
    "marine trout at half of that. The open lease does not record the harvest "
    "or the species, so this map does not state a yearly total. The lowest "
    "published salmon minimum is £1,500 a year, and it depends on consented "
    "biomass, which is not on the lease."
)
_SHELLFISH = (
    "The published rent is a tariff per metre of deployed equipment: mussels "
    "£0.205 a metre, at least £200 a year; oysters £0.265 a metre, at least "
    "£175 a year; scallops £0.055 a metre, at least £175 a year. This outline "
    "does not name the species, so the map does not pick a tariff."
)
_SEAWEED_FARM = (
    "The published rent is £0.055 per metre of deployed equipment, and at "
    "least £135 a year. The open lease does not record the length, so £135 "
    "is the published floor, not this site's rent."
)
_SEAWEED_HARVEST = (
    "The farm tariff is for farm leases and is not applied to this outline."
)
_EQUIPMENT = "No separate rent is published for this class."
_UNKNOWN = "This class has no published rent rule on the map."
_UNPUBLISHED = "Signed seabed agreement. The yearly rent is not in the open file."


def _label(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return ""
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    if _LABEL.match(text) is None:
        return ""
    return text


def _attr(attrs: dict, name: str) -> str:
    if not isinstance(attrs, dict):
        return ""
    if name in attrs:
        return _label(attrs.get(name))
    folded = {str(key).lower(): item for key, item in attrs.items()}
    return _label(folded.get(name.lower()))


def _headed(title: str, name: str, body: str) -> str:
    head = f"{title} {name}." if name else f"{title}."
    return f"{head} {body}"


def aquaculture_lease(attrs: dict) -> dict | None:
    """One aquaculture lease. The note is the published rule, not a site total."""
    classification = _attr(attrs, "Property_Classification")
    if not classification:
        return None
    name = _attr(attrs, "Lease_Description")
    if classification == "Finfish Farm":
        title, body = "Finfish farm", _FINFISH
    elif classification == "Shellfish Fm":
        title, body = "Shellfish farm", _SHELLFISH
    elif classification == "Seaweed Farming":
        title, body = "Seaweed farm", _SEAWEED_FARM
    elif classification == "Seaweed Harvesting":
        title, body = "Seaweed harvesting", _SEAWEED_HARVEST
    elif classification == "Aqua Equipment":
        title, body = "Aquaculture equipment", _EQUIPMENT
    else:
        title, body = f"Seabed lease {classification}", _UNKNOWN
    record = {
        "estate": "aquaculture",
        "classification": classification,
        "note": _headed(title, name, body),
    }
    if name:
        record["name"] = name
    return record


def agreement_lease(attrs: dict, estate: str, title: str) -> dict | None:
    """A signed wind, wave, or tidal agreement whose yearly rent is unpublished."""
    name = _attr(attrs, "Property_Description") or _attr(attrs, "Lease_Description")
    agreement = _attr(attrs, "Lease_Type_Description")
    phase = _attr(attrs, "Project_Phase")
    if not name and not agreement and not phase:
        return None
    if name:
        head = f"{title}, {name}."
    else:
        head = f"{title}."
    detail = ", ".join(part for part in (agreement, phase) if part)
    if detail:
        head = f"{head} {detail}."
    record = {"estate": estate, "note": f"{head} {_UNPUBLISHED}"}
    if name:
        record["name"] = name
    if agreement:
        record["agreement"] = agreement
    if phase:
        record["phase"] = phase
    return record


def _rows(payload: dict, take) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    found: list[dict] = []
    for feature in payload.get("features") or []:
        if not isinstance(feature, dict):
            continue
        attrs = feature.get("attributes")
        if not isinstance(attrs, dict):
            continue
        row = take(attrs)
        if row is None:
            continue
        found.append(row)
        if len(found) == 4:
            break
    return found


def seabed_record(payloads: dict | None) -> dict:
    """Leases at one point. Empty when no published outline covers it.

    Numeric rent fields on the source feature are dropped. The note is the
    only sentence the card shows.
    """
    body = payloads or {}
    leases: list[dict] = []
    leases.extend(_rows(body.get("aquaculture") or {}, aquaculture_lease))
    leases.extend(
        _rows(
            body.get("wind") or {},
            lambda attrs: agreement_lease(attrs, "wind", "Offshore wind"),
        )
    )
    leases.extend(
        _rows(
            body.get("wave") or {},
            lambda attrs: agreement_lease(attrs, "wave", "Wave lease"),
        )
    )
    leases.extend(
        _rows(
            body.get("tidal") or {},
            lambda attrs: agreement_lease(attrs, "tidal", "Tidal lease"),
        )
    )
    return {"leases": leases}
