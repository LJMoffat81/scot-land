"""Open land platform layer catalog, place context, and official links.

The product brief is docs/PLATFORM.md. This module exposes what can be
shown from open sources and makes remaining registers visible as gaps.
"""

from __future__ import annotations

from typing import Any

import httpx

from layers.common_good import catalog_layer as common_good_catalog_layer
from layers.common_good import place_common_good
from layers.community_ownership import catalog_layer as community_ownership_catalog_layer
from layers.community_ownership import query_point as community_ownership_at_point
from layers.council_metrics import METRIC_DEFS
from layers.crofting import catalog_common_grazings, catalog_crofting_register
from layers.crofting import place_crofting
from layers.dz_context import catalog_layers as dz_context_catalog_layers
from layers.flood import catalog_layer as flood_catalog_layer
from layers.hla import SPATIAL_HUB_URL as SPATIAL_HUB_HLA
from layers.hla import query_point as hla_at_point
from layers.ldp import catalog_layer as ldp_catalog_layer
from layers.registers import registers_for_council
from layers.scotwind import OGL_LICENCE_URL as SCOTWIND_LICENCE_URL
from layers.scotwind import source_meta as scotwind_source_meta
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
SPATIAL_HUB_LDP = "https://data.spatialhub.scot/dataset/local_development_plans-is"
SPATIAL_HUB_CAT = "https://data.spatialhub.scot/dataset/community_asset_transfer_register-is"
SPATIAL_HUB_ASSETS = "https://data.spatialhub.scot/dataset/council_asset_register-is"
SPATIAL_HUB_LA_OWN = "https://data.spatialhub.scot/dataset/land_ownership-is"
OGL_V3_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)
HYDRO_SOURCE = (
    "https://www.data.gov.uk/dataset/5750f8e5-d51b-4e75-a8d6-403a0d1ded81/hydropower_sites"
)
SEPA_ENV_DATA = "https://www.sepa.org.uk/environment/environmental-data/"
SEPA_CAR_MAPSERVER = (
    "https://map.sepa.org.uk/server/rest/services/Open/SEPA_Reference/MapServer"
)
CROWN_ESTATE_HUB = "https://crown-estate-scotland-spatial-hub-coregis.hub.arcgis.com/"
NATURESCOT_OPEN_DATA = "https://opendata.nature.scot/"
NATURESCOT_SSSI = (
    "https://opendata.nature.scot/maps/sites-of-special-scientific-interest"
)
COMMUNITY_OWNERSHIP_PUB = (
    "https://www.gov.scot/publications/community-ownership-in-scotland-2024/"
)
NFI_CATALOGUE = (
    "https://www.data.gov.uk/dataset/c50cddf4-cdf0-42fb-8ac1-eae0cb6ef5ad/"
    "national-forest-inventory-scotland-2025"
)
NATIVE_WOODLAND_CATALOGUE = (
    "https://www.data.gov.uk/dataset/da3f8548-a130-4a0d-8ddd-45019adcf1f3/"
    "native-woodland-survey-of-scotland-nwss"
)
REPD_PUBLICATION = (
    "https://www.gov.uk/government/publications/"
    "renewable-energy-planning-database-quarterly-extract"
)


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
                "description": "Residual site-value AGR on Scot-LAND squares and notional plots.",
            },
            {
                "id": "boundaries",
                "group": "spatial",
                "status": "live",
                "label": "ROS INSPIRE parcels",
                "description": (
                    "Registered cadastral extents (geometry only — no owners). "
                    "BBox from PostGIS ingest (503 when unloaded; empty viewport "
                    "is honest 200 when loaded, including fixture-scoped CI). "
                    "Tiles via live WMS."
                ),
                "minzoom": 14,
                "endpoint": "/layers/parcels",
                "tile_endpoint": "/layers/parcels/tiles/{z}/{x}/{y}",
                "licence": "OGL-3.0",
                "licence_url": OGL_V3_URL,
                "source_url": "https://www.ros.gov.uk/open-data",
                "gaps": [
                    "Sasine titles without Land Register polygons",
                    "Private owner names are not in the open INSPIRE product",
                    "Index polygons are registered extents, not a title sheet",
                ],
            },
            {
                "id": "cell_grid",
                "group": "value",
                "status": "live",
                "label": "Scot-LAND squares",
                "minzoom": 12,
            },
            {
                "id": "data_zones",
                "group": "spatial",
                "status": "live",
                "label": "Data Zone boundaries",
                "description": (
                    "2011 Data Zone outlines from PostGIS dz_boundaries when loaded "
                    "(Georgist/Valuation), else SG StatisticalUnits viewport query. "
                    "Hover/click: code, name, council, population and dwellings. "
                    "No AGR £ or Surface Rent on the map."
                ),
                "endpoint": "/layers/open/data-zones",
                "licence": "Open Government Licence v3.0",
                "licence_url": (
                    "https://www.nationalarchives.gov.uk/doc/"
                    "open-government-licence/version/3/"
                ),
                "minzoom": 10,
                "source_url": (
                    "https://www.spatialdata.gov.scot/geonetwork/srv/eng/catalog.search"
                    "#/metadata/7d564e13-a967-495a-ae2f-048ffdfa4b03"
                ),
            },
            {
                "id": "settlements",
                "group": "spatial",
                "status": "live",
                "label": "NRS Settlements",
                "description": (
                    "Census 2022 settlements (places of 500 people or more). "
                    "PostGIS bbox (503 when unloaded). Ledger frame for surface site rent "
                    "(row 1 zone/settlement grain) — not a LayersPanel toggle, not a title."
                ),
                "endpoint": "/layers/open/settlements",
                "licence": "OGL-3.0",
                "licence_url": (
                    "https://www.nationalarchives.gov.uk/doc/"
                    "open-government-licence/version/3/"
                ),
                "minzoom": 6,
                "source_url": (
                    "https://maps.gov.scot/server/rest/services/NRS/Census2022/MapServer"
                ),
                "ledger_role": "ledger-frame",
                "ledger_row": "1",
                "ui_surface": "ledger",
            },
            {
                "id": "localities",
                "group": "spatial",
                "status": "live",
                "label": "NRS Localities",
                "description": (
                    "Census 2022 localities (built-up localities). "
                    "PostGIS bbox (503 when unloaded). Ledger frame for surface site rent "
                    "(row 1) — not a LayersPanel toggle, not ownership."
                ),
                "endpoint": "/layers/open/localities",
                "licence": "OGL-3.0",
                "licence_url": (
                    "https://www.nationalarchives.gov.uk/doc/"
                    "open-government-licence/version/3/"
                ),
                "minzoom": 7,
                "source_url": (
                    "https://maps.gov.scot/server/rest/services/NRS/Census2022/MapServer"
                ),
                "ledger_role": "ledger-frame",
                "ledger_row": "1",
                "ui_surface": "ledger",
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
                "licence_url": (
                    "https://www.nationalarchives.gov.uk/doc/"
                    "open-government-licence/version/3/"
                ),
                "minzoom": 8,
                "source_url": VDL_REGISTER,
                "spatial_hub_url": SPATIAL_HUB_VDL,
            },
            flood_catalog_layer(),
            ldp_catalog_layer(),
            {
                "id": "hla",
                "group": "spatial",
                "status": "live",
                "label": "Housing land audit",
                "description": (
                    "Spatial Hub Housing Land Supply (Housing Land Audit sites). "
                    "PostGIS ingest of the OGL open product (503 when unloaded). "
                    "Natural capital ledger row 1a (planning uplift, nested) — "
                    "not a LayersPanel toggle. Audit polygons, not a title. "
                    "No public AGR £."
                ),
                "endpoint": "/layers/open/hla",
                "licence": "OGL-3.0",
                "minzoom": 8,
                "source_url": SPATIAL_HUB_HLA,
                "spatial_hub_url": SPATIAL_HUB_HLA,
                "ledger_role": "ledger-row",
                "ledger_row": "1a",
                "ui_surface": "ledger",
            },
            *dz_context_catalog_layers(),
            {
                "id": "public_crown",
                "group": "ownership",
                "status": "gap",
                "label": "Public and Crown Estate land",
                "description": (
                    "SG 2024 dashboard of five national bodies — dashboard only, "
                    "no verified open licence. Hidden from the public map until an "
                    "OGL-licensed source is confirmed. Not a title, not local-authority land."
                ),
                "licence": "unverified/not open",
                "source_url": PUBLIC_LAND_MAP,
            },
            community_ownership_catalog_layer(),
            {
                "id": "hydro_sites",
                "group": "spatial",
                "status": "live",
                "label": "Hydropower sites (SEPA CAR)",
                "description": (
                    "SEPA OGL hydropower sites — CAR-licensed water abstractions for "
                    "hydropower (PostGIS). Natural-capital extractive inventory "
                    "(value_tier=proxy). No £ rent; separate from surface rent."
                ),
                "endpoint": "/layers/open/hydro",
                "licence": "OGL-3.0",
                "licence_url": OGL_V3_URL,
                "minzoom": 6,
                "source_url": HYDRO_SOURCE,
                "commons_class": "extractive",
                "value_tier": "proxy",
                "publication_status": "ok",
            },
            {
                "id": "sepa_car",
                "group": "spatial",
                "status": "live",
                "label": "SEPA CAR licences",
                "description": (
                    "SEPA Controlled Activities Regulations — Simple (MapServer 194) "
                    "and Registration (195) ingested from Open/SEPA_Reference into "
                    "PostGIS (`python -m etl.ingest_sepa_car`). OGL confirmed on SEPA "
                    "Environmental data. API serves PostGIS only (never proxies "
                    "MapServer). value_tier=market; no £ rent; not surface rent."
                ),
                "endpoint": "/layers/open/sepa-car",
                "licence": "OGL-3.0",
                "licence_url": OGL_V3_URL,
                "minzoom": 6,
                "source_url": SEPA_ENV_DATA,
                "mapserver_url": SEPA_CAR_MAPSERVER,
                "commons_class": "extractive",
                "value_tier": "market",
                "publication_status": "ok",
                "adds_to_surface_rent": False,
            },

            {
                "id": "sssi",
                "group": "spatial",
                "status": "live",
                "label": "Sites of Special Scientific Interest",
                "description": (
                    "NatureScot SSSI boundaries (OGL-3.0). Indicative designations "
                    "from PostGIS ingest — not a title plan. Natural capital Constraint "
                    "(£0, no rent row); changes best use only. 503 when unloaded."
                ),
                "endpoint": "/layers/open/sssi",
                "licence": "OGL-3.0",
                "licence_url": OGL_V3_URL,
                "minzoom": 7,
                "source_url": NATURESCOT_SSSI,
                "ledger_role": "constraint",
                "ledger_row": None,
                "ui_surface": "ledger",
            },
            {
                "id": "naturescot_designations",
                "group": "spatial",
                "status": "live",
                "label": "NatureScot designations",
                "description": (
                    "NatureScot SPA, SAC and NNR boundaries (OGL-3.0). "
                    "SSSI is a separate layer. Constraint (£0, no rent row). "
                    "Indicative — 503 when unloaded."
                ),
                "endpoint": "/layers/open/naturescot-designations",
                "licence": "OGL-3.0",
                "licence_url": OGL_V3_URL,
                "minzoom": 7,
                "source_url": NATURESCOT_OPEN_DATA,
                "ledger_role": "constraint",
                "ledger_row": None,
                "ui_surface": "ledger",
            },

            {
                "id": "nfi",
                "group": "spatial",
                "status": "live",
                "label": "National Forest Inventory",
                "description": (
                    "NFI woodland Scotland (≥ 0.5 ha). PostGIS ingest of the open "
                    "Forestry Commission / NatureScot product. Natural capital ledger "
                    "row 1 (surface site rent land-use) — not a LayersPanel toggle, "
                    "not a rent and not a title. 503 when unloaded."
                ),
                "endpoint": "/layers/open/nfi",
                "licence": "Open Government Licence v3.0",
                "licence_url": OGL_V3_URL,
                "minzoom": 7,
                "source_url": NFI_CATALOGUE,
                "ledger_role": "ledger-row",
                "ledger_row": "1",
                "ui_surface": "ledger",
            },
            {
                "id": "native_woodland",
                "group": "spatial",
                "status": "live",
                "label": "Native Woodland Survey",
                "description": (
                    "Native Woodland Survey of Scotland polygons and habitat "
                    "attributes. PostGIS ingest of the open Scottish Forestry / "
                    "NatureScot product. Natural capital ledger row 1 (surface site "
                    "rent land-use) — not a LayersPanel toggle, not a rent or title. "
                    "503 when unloaded."
                ),
                "endpoint": "/layers/open/native-woodland",
                "licence": "Open Government Licence v3.0",
                "licence_url": OGL_V3_URL,
                "minzoom": 8,
                "source_url": NATIVE_WOODLAND_CATALOGUE,
                "ledger_role": "ledger-row",
                "ledger_row": "1",
                "ui_surface": "ledger",
            },
            {
                "id": "repd",
                "group": "spatial",
                "status": "live",
                "label": "Renewable energy planning (REPD)",
                "description": (
                    "DESNZ Renewable Energy Planning Database — Scotland planning-site "
                    "points from the OGL quarterly extract (PostGIS). Natural capital "
                    "ledger row 3 (onshore wind + hydro resource) — not a LayersPanel "
                    "toggle. Not lease polygons, not a rent, not a title. 503 when unloaded."
                ),
                "endpoint": "/layers/open/repd",
                "licence": "OGL-3.0",
                "licence_url": OGL_V3_URL,
                "minzoom": 6,
                "source_url": REPD_PUBLICATION,
                "commons_class": "extractive",
                "value_tier": "proxy",
                "publication_status": "ok",
                "ledger_role": "ledger-row",
                "ledger_row": "3",
                "ui_surface": "ledger",
            },
            {
                "id": "crown_estate_leases",
                "group": "ownership",
                "status": "live",
                "label": "Crown Estate Scotland offshore leases",
                "description": (
                    "CES Spatial Hub offshore lease polygons (offshore wind, wave, "
                    "tidal, CCS) under OGL — PostGIS ingest. Offshore only — not "
                    "onshore estate, not aquaculture (separate layer). Natural capital "
                    "ledger row 4 (seabed & foreshore) — not a LayersPanel toggle, "
                    "not a title sheet, no £ rent. 503 when unloaded."
                ),
                "endpoint": "/layers/open/crown-estate-leases",
                "licence": "OGL-3.0",
                "licence_url": OGL_V3_URL,
                "minzoom": 5,
                "source_url": CROWN_ESTATE_HUB,
                "commons_class": "extractive",
                "value_tier": "market",
                "publication_status": "ok",
                "ledger_role": "ledger-row",
                "ledger_row": "4",
                "ui_surface": "ledger",
            },
            {
                "id": "lca",
                "group": "spatial",
                "status": "live",
                "label": "Land capability for agriculture",
                "description": (
                    "James Hutton Institute LCA 1:250,000 — soil and climate "
                    "capability classes. Ledger constraint (£0) — changes best "
                    "permitted use only; not a rent or title. BBox from PostGIS "
                    "ingest (503 when unloaded)."
                ),
                "endpoint": "/layers/open/lca",
                "licence": "James Hutton Institute Open Data Licence",
                "licence_note": (
                    "Not OGL-3.0. Public-sector information in the product is "
                    "under OGL v2.0 per the Hutton attribution clause."
                ),
                "attribution": (
                    "Land Capability for Agriculture 1:250,000 copyright and "
                    "database right The James Hutton Institute. Used with the "
                    "permission of The James Hutton Institute. All rights "
                    "reserved. Any public sector information contained in "
                    "these data is licensed under the Open Government Licence "
                    "v.2.0."
                ),
                "share_alike": (
                    "Redistribution and derived data must be on equivalent "
                    "Hutton Open Data Licence terms; retain attribution and "
                    "pass that obligation through any sublicence."
                ),
                "licence_url": (
                    "https://www.hutton.ac.uk/wp-content/uploads/2024/05/"
                    "The-James-Hutton-Institute-Open-Data-Licence-download.pdf"
                ),
                "minzoom": 7,
                "source_url": (
                    "https://www.hutton.ac.uk/sites/default/files/files/soils/"
                    "downloads/Hutton_LCA250K_OpenData.zip"
                ),
                "ledger_role": "constraint",
                "ledger_row": None,
                "ui_surface": "ledger",
            },
            {
                "id": "scotwind_intog",
                "group": "ownership",
                "status": "live",
                "label": "ScotWind / INTOG seabed options",
                "description": (
                    "Crown Estate Scotland ScotWind and INTOG option/award polygons "
                    "(PostGIS ingest). Evidence tag market. Polygons only — option-fee £ "
                    "are HOLD (press release; see data/config/scotwind_option_fees.yaml), "
                    "not layer attributes. Natural capital ledger row 4 (seabed & foreshore) "
                    "— not a LayersPanel toggle. Separate from surface rent (la-calc) — "
                    "this overlay never adds value. No £ rent."
                ),
                "endpoint": "/layers/open/scotwind-intog",
                "minzoom": 5,
                "licence": scotwind_source_meta()["licence"],
                "licence_url": SCOTWIND_LICENCE_URL,
                "source_url": scotwind_source_meta()["source_url"],
                "attribution": scotwind_source_meta()["attribution"],
                "evidence_tag": scotwind_source_meta()["evidence_tag"],
                "publication_status": scotwind_source_meta()["publication_status"],
                "commons_class": "extractive",
                "value_tier": "market",
                "ledger_role": "ledger-row",
                "ledger_row": "4",
                "ui_surface": "ledger",
            },
            {
                "id": "repd_onshore_wind",
                "group": "natural_capital",
                "status": "live",
                "label": "REPD onshore wind",
                "description": (
                    "DESNZ Renewable Energy Planning Database — Scotland onshore "
                    "wind sites with installed capacity (MW) and development status. "
                    "Natural capital ledger row 3 (onshore wind resource) — not a "
                    "LayersPanel toggle. Natural-capital evidence only: no £ rent, "
                    "never added to Surface Rent or AGR. Planning-site points, not leases."
                ),
                "endpoint": "/layers/open/repd-onshore-wind",
                "minzoom": 6,
                "licence": "OGL-3.0",
                "licence_url": (
                    "https://www.nationalarchives.gov.uk/doc/"
                    "open-government-licence/version/3/"
                ),
                "source_url": (
                    "https://www.gov.uk/government/publications/"
                    "renewable-energy-planning-database-quarterly-extract"
                ),
                "commons_class": "extractive",
                "value_tier": "market",
                "publication_status": "ok",
                "adds_to_surface_rent": False,
                "ledger_role": "ledger-row",
                "ledger_row": "3",
                "ui_surface": "ledger",
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
            catalog_crofting_register(),
            catalog_common_grazings(),
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


def _resolve_council(
    lat: float,
    lng: float,
    *,
    council_code: str | None,
    council_name: str | None,
) -> tuple[str | None, str | None]:
    """Prefer caller-supplied codes; otherwise open council polygons."""
    if council_code and council_name:
        return council_code, council_name
    try:
        match = lookup_council_boundary(lat, lng)
    except FileNotFoundError:
        return council_code, council_name
    if match is None:
        return council_code, council_name
    return (
        council_code or match.hpi_code,
        council_name or match.name,
    )


def _data_zone_at(lat: float, lng: float) -> dict[str, Any]:
    """Data Zone at a point. Never invents a code; unavailable stays explicit."""
    from georgist import dz_lookup

    try:
        found = dz_lookup.lookup(lat, lng)
    except dz_lookup.BoundariesUnavailable as exc:
        return {
            "status": "unavailable",
            "code": None,
            "name": None,
            "vintage": None,
            "zones": [],
            "reasons": list(exc.reasons),
            "note": "Data zone boundaries are not loaded for this server.",
        }
    if not found.zones:
        return {
            "status": "miss",
            "code": None,
            "name": None,
            "vintage": None,
            "zones": [],
            "vintages_checked": found.vintages_loaded,
            "source": found.source,
            "note": "No Scottish data zone contains this point (e.g. at sea).",
        }
    payload = found.to_dict()
    return {
        "status": "ok",
        "code": payload.get("code"),
        "name": payload.get("name"),
        "vintage": payload.get("vintage"),
        "zones": payload.get("zones") or [],
        "dz2011": payload.get("dz2011"),
        "dz2022": payload.get("dz2022"),
        "source": payload.get("source"),
        "vintages_loaded": payload.get("vintages_loaded") or [],
    }


def _layer_row(
    *,
    layer_id: str,
    label: str,
    status: str,
    intersects: bool | None,
    note: str | None = None,
    source_url: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": layer_id,
        "label": label,
        "status": status,
        "intersects": intersects,
    }
    if note:
        row["note"] = note
    if source_url:
        row["source_url"] = source_url
    if detail:
        row["detail"] = detail
    return row


def _layers_at_point(card: dict[str, Any]) -> list[dict[str, Any]]:
    """Which catalog layers meet this spot — live hit/miss, linked, or gap."""
    layers: list[dict[str, Any]] = []
    parcel = card.get("parcel") or {}
    outline = card.get("land_register_outline") or {}
    if parcel.get("found"):
        layers.append(
            _layer_row(
                layer_id="boundaries",
                label="ROS INSPIRE parcels",
                status="live",
                intersects=True,
                note=parcel.get("note"),
                source_url="https://www.ros.gov.uk/open-data",
                detail={
                    "label": parcel.get("label"),
                    "inspire_id": parcel.get("inspire_id"),
                    "area_sqm": parcel.get("area_sqm"),
                },
            )
        )
    elif outline.get("status") == "unknown":
        layers.append(
            _layer_row(
                layer_id="boundaries",
                label="ROS INSPIRE parcels",
                status="live",
                intersects=None,
                note="Parcel lookup did not complete for this point.",
                source_url="https://www.ros.gov.uk/open-data",
            )
        )
    else:
        layers.append(
            _layer_row(
                layer_id="boundaries",
                label="ROS INSPIRE parcels",
                status="live",
                intersects=False,
                note=(outline.get("note") if outline else None)
                or "No Land Register outline at this point.",
                source_url="https://www.ros.gov.uk/open-data",
            )
        )

    vdl = card.get("vdl") or {}
    vdl_ok = vdl.get("ok")
    layers.append(
        _layer_row(
            layer_id="vdl",
            label="Vacant and derelict land",
            status="live",
            intersects=bool(vdl.get("intersects")) if vdl_ok else None,
            note=None if vdl_ok else (vdl.get("error") or "SVDLS overlay unavailable."),
            source_url=VDL_REGISTER,
            detail={"sites": vdl.get("sites") or []} if vdl_ok else None,
        )
    )

    public = card.get("public_or_crown") or {}
    layers.append(
        _layer_row(
            layer_id="public_crown",
            label="Public and Crown Estate land",
            status="gap",
            intersects=None,
            note=public.get("note")
            or (
                "SG 2024 dashboard only — licence unverified/not open. "
                "Not drawn on the public map until an OGL source is confirmed."
            ),
            source_url=PUBLIC_LAND_MAP,
        )
    )

    common_good = card.get("common_good") or {}
    layers.append(
        _layer_row(
            layer_id="common_good",
            label="Common Good",
            status=str(common_good.get("status") or "gap"),
            intersects=None,
            note=common_good.get("national_gap")
            or common_good.get("reason")
            or "No national open Common Good map layer.",
            source_url=(common_good.get("register") or {}).get("url"),
        )
    )

    la = card.get("local_authority_holding") or {}
    layers.append(
        _layer_row(
            layer_id="la_holdings",
            label="Local-authority land holdings",
            status="gap",
            intersects=None,
            note=la.get("reason")
            or "National LA ownership layer is not openly licensed for this portal.",
            source_url=SPATIAL_HUB_LA_OWN,
        )
    )

    sasine = card.get("private_or_sasine") or {}
    layers.append(
        _layer_row(
            layer_id="sasine_private",
            label="Private owners and Sasine land",
            status="gap",
            intersects=None,
            note=sasine.get("note")
            or "Private names and Sasine extents stay on ScotLIS / paid products.",
            source_url=SCOTLIS_PUBLIC,
        )
    )
    return layers


def _place_links(card: dict[str, Any]) -> list[dict[str, str]]:
    """Official / open links for the place card (never modelled rent)."""
    links: list[dict[str, str]] = []
    scotlis = card.get("scotlis") or {}
    if scotlis.get("public_home"):
        links.append(
            {
                "id": "scotlis",
                "label": scotlis.get("label") or "Official title on ScotLIS",
                "url": scotlis["public_home"],
            }
        )
    public = card.get("public_or_crown") or {}
    if public.get("map_url"):
        links.append(
            {
                "id": "public_land_map",
                "label": "Scottish public and Crown Estate land map",
                "url": public["map_url"],
            }
        )
    registers = card.get("registers") or {}
    planning = registers.get("planning") or {}
    if planning.get("url"):
        links.append(
            {
                "id": "planning",
                "label": planning.get("label") or "Planning applications",
                "url": planning["url"],
            }
        )
    common_good = card.get("common_good") or {}
    register = common_good.get("register") or {}
    if register.get("url"):
        links.append(
            {
                "id": "common_good_register",
                "label": register.get("label") or "Common Good register",
                "url": register["url"],
            }
        )
    spatial = common_good.get("spatial") or {}
    if spatial.get("metadata_url"):
        links.append(
            {
                "id": "common_good_spatial",
                "label": spatial.get("label") or "Common Good spatial metadata",
                "url": spatial["metadata_url"],
            }
        )
    links.append(
        {
            "id": "vdl_register",
            "label": "SVDLS site register",
            "url": VDL_REGISTER,
        }
    )
    links.append(
        {
            "id": "methodology",
            "label": "Sources and method",
            "url": "/methodology",
        }
    )
    return links


def place_context(
    lat: float,
    lng: float,
    *,
    postcode: str | None = None,
    parcel: dict[str, Any] | None = None,
    council_code: str | None = None,
    council_name: str | None = None,
) -> dict[str, Any]:
    """Who-holds / what-status card for one place, with honest gaps.

    Public place-card contract (no modelled AGR £). Shells may render this
    payload as-is. Contract version: place_card_v1.
    """
    council_code, council_name = _resolve_council(
        lat, lng, council_code=council_code, council_name=council_name
    )
    parcel_feature = parcel if parcel is not None else lookup_parcel_geojson(lat, lng)
    parcel_props = (parcel_feature or {}).get("properties") or {}

    vdl = vdl_at_point(lat, lng)
    hla = hla_at_point(lat, lng)
    community = community_ownership_at_point(lat, lng)
    vacant = bool(vdl.get("intersects"))
    housing_land = bool(hla.get("intersects"))
    community_holding = bool(community.get("intersects"))

    ownership_flags: list[str] = []
    if vacant:
        ownership_flags.append("vacant_or_derelict_survey")
    if housing_land:
        ownership_flags.append("housing_land_audit")
    if community_holding:
        ownership_flags.append("community_ownership")
    if parcel_feature:
        ownership_flags.append("registered_cadastre")
    else:
        ownership_flags.append("no_inspire_parcel")

    card: dict[str, Any] = {
        "contract": "place_card_v1",
        "lat": lat,
        "lng": lng,
        "postcode": postcode,
        "council_code": council_code,
        "council_name": council_name,
        "data_zone": _data_zone_at(lat, lng),
        "vacant_or_derelict": vacant,
        "vdl": vdl,
        "housing_land_audit": housing_land,
        "hla": hla,
        "parcel": {
            "found": parcel_feature is not None,
            "label": parcel_props.get("label"),
            "inspire_id": parcel_props.get("inspire_id") or parcel_props.get("national_reference"),
            "area_sqm": parcel_props.get("area_sqm"),
            "note": "INSPIRE parcel is an indicative registered extent, not a title sheet.",
        },
        "public_or_crown": {
            "status": "gap",
            "on_this_point": None,
            "holdings": [],
            "note": (
                "SG 2024 public/Crown land dashboard has no verified open licence. "
                "Hidden from the public map until an OGL-licensed source is confirmed. "
                "Not a legal title — confirm on ScotLIS."
            ),
            "map_url": PUBLIC_LAND_MAP,
            "crown_hub": CROWN_ESTATE_HUB,
            "licence": "unverified/not open",
        },
        "local_authority_holding": {
            "status": "gap",
            "on_this_point": None,
            "reason": "National LA ownership layer is not openly licensed for this portal.",
        },
        "common_good": place_common_good(council_code),
        "crofting": place_crofting(council_code),
        "community_ownership": {
            "status": "live" if community.get("ok") else "unavailable",
            "on_this_point": community_holding if community.get("ok") else None,
            "assets": community.get("assets") or [],
            "note": community.get("note")
            or (
                "SG Community Ownership in Scotland 2024 (OGL). "
                "Postcode centroids — not a title. Confirm on ScotLIS."
            ),
            "source_url": COMMUNITY_OWNERSHIP_PUB,
            "licence": community.get("licence"),
            "source": community.get("source"),
        },
        "private_or_sasine": {
            "status": "gap",
            "note": "Private names and Sasine extents stay on ScotLIS / paid products.",
        },
        "registers": registers_for_council(council_code),
        "flags": ownership_flags,
        "scotlis": scotlis_links(lat, lng, postcode),
        "filters": {
            "vacant": vacant,
            # public/Crown map licence unverified — do not classify from that overlay
            "public_private": "unknown",
            "value_band": None,
        },
    }
    outline = _land_register_outline(lat, lng)
    if outline is not None:
        card["land_register_outline"] = outline
    card["layers"] = _layers_at_point(card)
    card["links"] = _place_links(card)
    return card
