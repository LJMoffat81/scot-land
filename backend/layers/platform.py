"""Open land platform layer catalog, place context, and official links.

The product brief is docs/PLATFORM.md. This module exposes what can be
shown from open sources and makes remaining registers visible as gaps.
"""

from __future__ import annotations

from typing import Any

import httpx

from layers.common_good import catalog_layer as common_good_catalog_layer
from layers.common_good import place_common_good
from layers.council_metrics import METRIC_DEFS
from layers.public_land import query_point as public_land_at_point
from layers.registers import registers_for_council
from layers.vdl import query_point as vdl_at_point
from spatial.parcels import lookup_parcel, lookup_parcel_geojson
from spatial.polygons import lookup_council_boundary

# The live function, so a test double can be told apart from it.
_LIVE_PARCEL_LOOKUP = lookup_parcel

_NO_OUTLINE_NOTE = (
    "We found no Land Register boundary at this point. Its title may still be in "
    "the older Sasine register, or the land may not be registered at all. We estimate "
    "it by area and land type, and show no boundaries, titles or owners."
)

SCOTLIS_PUBLIC = "https://scotlis.ros.gov.uk/"
SCOTLIS_ABOUT = "https://www.ros.gov.uk/scotlis"
PUBLIC_LAND_MAP = "https://www.arcgis.com/apps/dashboards/a10668ccd4784209bf22e3adcef6b897"
VDL_REGISTER = (
    "https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/"
)
SPATIAL_HUB_VDL = "https://data.spatialhub.scot/dataset/vacant_and_derelict_land-is"
SPATIAL_HUB_CAT = "https://data.spatialhub.scot/dataset/community_asset_transfer_register-is"
SPATIAL_HUB_ASSETS = "https://data.spatialhub.scot/dataset/council_asset_register-is"
SPATIAL_HUB_LA_OWN = "https://data.spatialhub.scot/dataset/land_ownership-is"
CROWN_ESTATE_HUB = "https://crown-estate-scotland-spatial-hub-coregis.hub.arcgis.com/"


def scotlis_links(lat: float, lng: float, postcode: str | None = None) -> dict[str, Any]:
    """Official title-sheet path. ScotLIS has no public coordinate deep-link API."""
    return {
        "label": "Official title on ScotLIS",
        "public_home": SCOTLIS_PUBLIC,
        "about": SCOTLIS_ABOUT,
        "note": (
            "ScotLIS is Registers of Scotland’s official land information service. "
            "Use it for title sheets, owners on the Land Register, and paid extracts. "
            "This platform does not replace ScotLIS."
        ),
        "search_hint": postcode or f"{lat:.5f}, {lng:.5f}",
    }


def platform_catalog() -> dict[str, Any]:
    return {
        "version": 2,
        "brief": "docs/PLATFORM.md",
        "principle": "AGR first — open layers around a residual land-rent engine.",
        "choropleth_metrics": [
            {
                "id": mid,
                **{k: v for k, v in defn.items() if k != "property"},
                "property": defn["property"],
            }
            for mid, defn in METRIC_DEFS.items()
        ],
        "layers": [
            {
                "id": "agr_value",
                "group": "value",
                "status": "live",
                "label": "Annual Ground Rent",
                "description": "Residual site-value AGR on W3W cells and notional plots.",
            },
            {
                "id": "boundaries",
                "group": "spatial",
                "status": "live",
                "label": "ROS INSPIRE parcels",
                "description": (
                    "Registered cadastral extents (geometry only — no owners). "
                    "BBox from PostGIS ingest (503 when unloaded); tiles via live WMS."
                ),
                "minzoom": 14,
                "endpoint": "/layers/parcels",
                "tile_endpoint": "/layers/parcels/tiles/{z}/{x}/{y}",
                "licence": "OGL / INSPIRE (Crown)",
                "source_url": "https://www.ros.gov.uk/open-data",
            },
            {
                "id": "cell_grid",
                "group": "value",
                "status": "live",
                "label": "W3W cell grid",
                "minzoom": 12,
            },
            {
                "id": "vdl",
                "group": "spatial",
                "status": "live",
                "label": "Vacant and derelict land",
                "description": (
                    "SVDLS sites (survey polygons, site-level as published). "
                    "Owner class is a survey field, not legal title."
                ),
                "endpoint": "/layers/open/vdl",
                "licence": "OGL-3.0",
                "minzoom": 8,
                "source_url": VDL_REGISTER,
                "spatial_hub_url": SPATIAL_HUB_VDL,
            },
            {
                "id": "public_crown",
                "group": "ownership",
                "status": "live",
                "label": "Public and Crown Estate land",
                "description": (
                    "SG 2024 map of five national bodies and Crown Estate Scotland. "
                    "Indicative holdings, not a title, not local-authority land."
                ),
                "endpoint": "/layers/open/public-land",
                "minzoom": 6,
                "licence": "OGL-3.0",
                "source_url": PUBLIC_LAND_MAP,
            },
            {
                "id": "la_holdings",
                "group": "ownership",
                "status": "gap",
                "label": "Local-authority land holdings",
                "description": (
                    "Spatial Hub ‘Land Ownership – Scotland’ is not an open public layer "
                    "(PSGA / other restrictions). Shown as a gap, not scraped."
                ),
                "source_url": SPATIAL_HUB_LA_OWN,
            },
            {
                "id": "planning",
                "group": "spatial",
                "status": "linked",
                "label": "Planning applications",
                "description": (
                    "Verified official view pages where confirmed; otherwise national "
                    "ePlanning. No national drawable WMS."
                ),
                "endpoint": "/api/registers.json",
                "source_url": "https://www.eplanning.scot/ePlanningClient/",
            },
            {
                "id": "council_assets",
                "group": "ownership",
                "status": "linked",
                "label": "Council asset / CAT registers",
                "description": "Improvement Service amalgamated registers — Spatial Hub login.",
                "source_url": SPATIAL_HUB_ASSETS,
                "also": SPATIAL_HUB_CAT,
            },
            common_good_catalog_layer(),
            {
                "id": "fife_land_map",
                "group": "ownership",
                "status": "linked",
                "label": "Fife land map",
                "description": "This council’s ArcGIS hub. Not a national layer.",
                "source_url": "https://fife.maps.arcgis.com/home/index.html",
            },
            {
                "id": "sasine_private",
                "group": "ownership",
                "status": "gap",
                "label": "Private owners and Sasine land",
                "description": "Incomplete or paid. Gaps are shown; names are not invented.",
            },
        ],
        "tools": [
            {"id": "scenarios", "status": "live", "label": "LVT / AGR scenario calculators"},
            {"id": "api", "status": "live", "label": "Public assessment and layer API"},
            {"id": "downloads", "status": "partial", "label": "Open layer downloads via API"},
            {"id": "scotlis", "status": "live", "label": "Link through to ScotLIS"},
            {
                "id": "filters",
                "status": "partial",
                "label": "Filter by vacant land and value band",
            },
        ],
        "data_policy": {
            "portal_scraping": False,
            "owners_from_inspire": False,
            "purchase_prices_from_inspire": False,
            "open_layers_only": True,
            "gaps_visible": True,
        },
    }


def _outline_field(status: str) -> dict[str, str]:
    """Status, plus the approved note only when the map answered empty."""
    if status == "no_outline":
        return {"status": status, "note": _NO_OUTLINE_NOTE}
    return {"status": status}


def _probe_outline(lat: float, lng: float) -> str:
    """Repeat GetFeatureInfo. 'inside', 'empty', or 'error'.

    lookup_parcel returns None for an empty answer and for a failed call, and
    caches that None. A failure must not be reported as no_outline.
    """
    from spatial.parcels import _http, _parcel_cfg

    try:
        cfg = _parcel_cfg()
        delta = float(cfg["query_delta_degrees"])
        lat_key = round(float(lat), 6)
        lng_key = round(float(lng), 6)
        bbox = f"{lat_key - delta},{lng_key - delta},{lat_key + delta},{lng_key + delta}"
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetFeatureInfo",
            "QUERY_LAYERS": cfg["wms_layer"],
            "LAYERS": cfg["wms_layer"],
            "INFO_FORMAT": "application/json",
            "I": "50",
            "J": "50",
            "WIDTH": "101",
            "HEIGHT": "101",
            "CRS": "EPSG:4326",
            "BBOX": bbox,
        }
        response = _http().get(cfg["wms_url"], params=params)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError):
        return "error"
    if not isinstance(payload, dict):
        return "error"
    features = payload.get("features") or []
    if not isinstance(features, list):
        return "error"
    for feature in features:
        if isinstance(feature, dict) and feature.get("geometry"):
            return "inside"
    return "empty"


def _land_register_outline(lat: float, lng: float) -> dict[str, str] | None:
    """Point-in-outline status. Absent over sea and outside Scotland.

    Only status, and a note when the lookup answered empty. No id, title,
    owner, price, or geometry.
    """
    if lookup_council_boundary(lat, lng) is None:
        return None
    try:
        found = lookup_parcel(lat, lng)
    except (httpx.HTTPError, TimeoutError):
        return _outline_field("unknown")
    if found is not None:
        return _outline_field("inside_outline")
    # A stand-in that returns None is an empty answer. The live lookup also
    # returns None when the call failed, so that case is checked again.
    if lookup_parcel is not _LIVE_PARCEL_LOOKUP:
        return _outline_field("no_outline")
    probed = _probe_outline(lat, lng)
    if probed == "error":
        return _outline_field("unknown")
    if probed == "inside":
        return _outline_field("inside_outline")
    return _outline_field("no_outline")


def place_context(
    lat: float,
    lng: float,
    *,
    postcode: str | None = None,
    parcel: dict[str, Any] | None = None,
    council_code: str | None = None,
    council_name: str | None = None,
) -> dict[str, Any]:
    """Who-holds / what-status card for one place, with honest gaps."""
    parcel_feature = parcel if parcel is not None else lookup_parcel_geojson(lat, lng)
    parcel_props = (parcel_feature or {}).get("properties") or {}

    vdl = vdl_at_point(lat, lng)
    public = public_land_at_point(lat, lng)
    vacant = bool(vdl.get("intersects"))
    public_holding = bool(public.get("intersects"))

    ownership_flags: list[str] = []
    if vacant:
        ownership_flags.append("vacant_or_derelict_survey")
    if public_holding:
        ownership_flags.append("public_or_crown")
    if parcel_feature:
        ownership_flags.append("registered_cadastre")
    else:
        ownership_flags.append("no_inspire_parcel")

    card: dict[str, Any] = {
        "lat": lat,
        "lng": lng,
        "vacant_or_derelict": vacant,
        "vdl": vdl,
        "parcel": {
            "found": parcel_feature is not None,
            "label": parcel_props.get("label"),
            "inspire_id": parcel_props.get("inspire_id") or parcel_props.get("national_reference"),
            "area_sqm": parcel_props.get("area_sqm"),
            "note": "INSPIRE parcel is an indicative registered extent, not a title sheet.",
        },
        "public_or_crown": {
            "status": "live",
            "on_this_point": public_holding if public.get("ok") else None,
            "holdings": public.get("holdings") or [],
            "note": public.get("note")
            or (
                "Five national bodies only. Not local-authority land. "
                "Not a legal title — confirm on ScotLIS."
            ),
            "map_url": PUBLIC_LAND_MAP,
            "crown_hub": CROWN_ESTATE_HUB,
            "source": public.get("source"),
        },
        "local_authority_holding": {
            "status": "gap",
            "on_this_point": None,
            "reason": "National LA ownership layer is not openly licensed for this portal.",
        },
        "common_good": place_common_good(council_code),
        "private_or_sasine": {
            "status": "gap",
            "note": "Private names and Sasine extents stay on ScotLIS / paid products.",
        },
        "registers": registers_for_council(council_code),
        "council_code": council_code,
        "council_name": council_name,
        "flags": ownership_flags,
        "scotlis": scotlis_links(lat, lng, postcode),
        "filters": {
            "vacant": vacant,
            "public_private": "public" if public_holding else "unknown",
            "value_band": None,
        },
    }
    outline = _land_register_outline(lat, lng)
    if outline is not None:
        card["land_register_outline"] = outline
    return card
