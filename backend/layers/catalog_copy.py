"""Visitor-facing catalogue copy for /data, /developers and /api/catalog.json.

``description`` is plain English. Technical ingest detail lives in
``developer_note`` (shown on /developers/api only).
"""

from __future__ import annotations

import re
from typing import Any

# Forbidden jargon in visitor-facing description (site-watch PR B item 6).
_JARGON = re.compile(
    r"PostGIS|LayersPanel|MapServer|value_tier|python\s+-m|\bbbox\b|"
    r"503\s+when\s+unloaded|fixture|\bCI\b|£0",
    re.IGNORECASE,
)

# Plain-English “what it shows” by catalogue id.
PLAIN_DESCRIPTIONS: dict[str, str] = {
    "boundaries": (
        "Shapes of registered land parcels from Registers of Scotland. "
        "Outlines only — not titles, owners or prices."
    ),
    "data_zones": (
        "Small-area Data Zone boundaries (2022). Hover or click for the zone "
        "code, name, council, population and dwellings. Not a rent figure."
    ),
    "settlements": (
        "Places of 500 people or more from the Census 2022 settlements map. "
        "Helps name a place on the card — not ownership."
    ),
    "localities": (
        "Built-up localities from the Census 2022 localities map. "
        "Helps name a place on the card — not ownership."
    ),
    "vdl": (
        "Sites on the Scottish Vacant and Derelict Land Survey. "
        "Survey fields, not a legal title."
    ),
    "hla": (
        "Housing land audit / housing land supply sites. "
        "Planned housing land, not a title."
    ),
    "ldp_allocations": (
        "Local development plan allocation shapes where an open licence allows. "
        "Coverage is incomplete (Edinburgh is missing). Planning extents, not a title."
    ),
    "ldp": (
        "Local development plan allocation shapes where an open licence allows. "
        "Coverage is incomplete (Edinburgh is missing). Planning extents, not a title."
    ),
    "public_crown": (
        "Public and Crown land where an open national map is confirmed. "
        "Currently held back until the licence is clear."
    ),
    "community_ownership": (
        "Community-owned assets from the Scottish Government 2024 list "
        "(postcode points). Ownership context, not a title."
    ),
    "common_good": (
        "Links to council Common Good registers. No national open map yet."
    ),
    "crofting_register": (
        "Crofting Commission Register of Crofts — open lists only. "
        "No national open boundary map here; map extents stay on RoS."
    ),
    "common_grazings": (
        "Crofting Commission list of common grazings — open lists only. "
        "No national open boundary map here."
    ),
    "hydro_sites": (
        "Hydropower sites licensed by SEPA. Inventory of water use for power — "
        "not a rent figure and not surface land rent."
    ),
    "sepa_car": (
        "SEPA Controlled Activities Regulations licences for water use. "
        "Inventory only — not a rent figure."
    ),
    "sssi": (
        "Sites of Special Scientific Interest. A limit on how land can be used — "
        "not a rent and not a title."
    ),
    "naturescot_designations": (
        "NatureScot SPA, SAC and NNR areas. A limit on how land can be used — "
        "not a rent. SSSI is a separate source."
    ),
    "nfi": (
        "National Forest Inventory woodland of half a hectare or more. "
        "Land-use context for surface rent — not a title."
    ),
    "native_woodland": (
        "Native woodland areas from the open Scottish Forestry product. "
        "Land-use context — not a title."
    ),
    "repd": (
        "Renewable Energy Planning Database onshore wind and related sites. "
        "Planning evidence for resource rent — not lease shapes or a title."
    ),
    "repd_onshore_wind": (
        "Onshore wind sites from the Renewable Energy Planning Database. "
        "Planning evidence — not lease shapes or a title."
    ),
    "crown_estate_leases": (
        "Crown Estate Scotland seabed and foreshore leases (cables, moorings, "
        "offshore energy). Inventory for seabed rent — not a title sheet."
    ),
    "lca": (
        "Land Capability for Agriculture soil and climate classes "
        "(James Hutton Institute). A limit on best use — not a rent or title."
    ),
    "scotwind_intog": (
        "ScotWind and INTOG offshore wind option areas from Crown Estate Scotland. "
        "Option shapes only — separate from surface land rent."
    ),
    "flood": (
        "Medium-likelihood river and coastal flood extents from SEPA Flood Maps. "
        "A limit on how land can be used — not a property-level quote."
    ),
    "sepa_flood": (
        "Medium-likelihood river and coastal flood extents from SEPA Flood Maps. "
        "A limit on how land can be used — not a property-level quote."
    ),
    "carbon_peatland": (
        "Peat and carbon soils used for nature accounting. "
        "Unpriced carbon sits outside market rents."
    ),
    "ces_aquaculture": (
        "Aquaculture seabed leases from Crown Estate Scotland. "
        "Licence rent evidence — not a title."
    ),
    "nsta_oil_gas": (
        "UK oil and gas fields shown for comparison only. "
        "Outside Scotland’s land totals."
    ),
    "house_prices": (
        "House price context at Data Zone grain from open Registers of Scotland "
        "and UK HPI inputs. Not a modelled rent."
    ),
    "simd": (
        "Scottish Index of Multiple Deprivation context at Data Zone grain. "
        "Open statistics — not a rent."
    ),
    "population_density": (
        "Population density at Data Zone grain from open statistics. "
        "Context only — not a rent."
    ),
    "dz_context": (
        "Data Zone house prices, SIMD and population density together. "
        "Open statistics for the surface-rent frame — not a modelled rent."
    ),
}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def visitor_description(layer: dict[str, Any]) -> str:
    """Plain-English description for public catalogue surfaces."""
    layer_id = _as_text(layer.get("id"))
    if layer_id in PLAIN_DESCRIPTIONS:
        return PLAIN_DESCRIPTIONS[layer_id]
    raw = _as_text(layer.get("description"))
    if not raw:
        return _as_text(layer.get("label")) or "Open land source."
    # Fallback: strip known jargon tokens for any unlisted layer.
    cleaned = _JARGON.sub("", raw)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ;,.-")
    return cleaned or _as_text(layer.get("label")) or "Open land source."


def apply_visitor_catalog_copy(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a catalogue payload with plain ``description`` + ``developer_note``."""
    layers_in = payload.get("layers") or []
    layers_out: list[dict[str, Any]] = []
    for layer in layers_in:
        if not isinstance(layer, dict):
            continue
        row = dict(layer)
        original = _as_text(row.get("description"))
        plain = visitor_description(row)
        row["description"] = plain
        # Keep technical detail for /developers/api only.
        if original and original != plain:
            row["developer_note"] = original
        elif row.get("developer_note"):
            row["developer_note"] = _as_text(row.get("developer_note"))
        # Never leave banned tokens in the visitor field.
        if _JARGON.search(row["description"] or ""):
            row["description"] = re.sub(
                _JARGON, "", row["description"] or ""
            )
            row["description"] = re.sub(r"\s{2,}", " ", row["description"]).strip(
                " ;,.-"
            ) or plain
        layers_out.append(row)
    out = dict(payload)
    out["layers"] = layers_out
    return out
