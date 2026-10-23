"""Open land platform layer catalog, place context, and official links.

The product brief is docs/PLATFORM.md. This module exposes what can be
shown from open sources and makes remaining registers visible as gaps.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from pyproj import Transformer

from georgist.gbp_live import attach_gbp_live_to_place_card
from layers.common_good import catalog_layer as common_good_catalog_layer
from layers.common_good import place_common_good
from layers.community_ownership import catalog_layer as community_ownership_catalog_layer
from layers.community_ownership import query_point as community_ownership_at_point
from layers.council_metrics import METRIC_DEFS, PUBLIC_CATALOG_METRIC_IDS
from layers.crofting import catalog_common_grazings, catalog_crofting_register
from layers.crofting import place_crofting
from layers.dz_context import catalog_layers as dz_context_catalog_layers
from layers.flood import catalog_layer as flood_catalog_layer
from layers.hla import SPATIAL_HUB_URL as SPATIAL_HUB_HLA
from layers.hla import query_point as hla_at_point
from layers.layer_flags import FLAG_HLS, layer_hls_enabled
from layers.ldp import catalog_layer as ldp_catalog_layer
from layers.flood_dz import is_loaded as flood_dz_loaded
from layers.layers_add_catalog import (
    public_layers_add_entries,
    waiting_for_permission_rows,
)
from layers.registers import registers_for_council
from layers.cadastral import OGL_V3_LICENCE_PHRASE as PARCELS_OGL_PHRASE
from layers.cadastral import OGL_V3_URL as PARCELS_OGL_URL
from layers.cadastral import parcel_source_meta
from layers.iz_names import iz_name
from layers.nrs_places import lookup_at as nrs_place_at
from layers.scotwind import OGL_LICENCE_URL as SCOTWIND_LICENCE_URL
from layers.scotwind import source_meta as scotwind_source_meta
from layers.vdl import query_point as vdl_at_point
from spatial.council_names import official_council_name
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


def _parcels_meta() -> dict[str, Any]:
    """Catalog row for RoS INSPIRE parcels — shapes only; confirmed OGL v3 credit.

    Public map keeps parcels off (PARCELS_PUBLIC default false) — catalog status
    is gap until that flag is on so LAYER-CATALOG-STATUS matches reality.
    """
    meta = parcel_source_meta()
    parcels_on = os.getenv("PARCELS_PUBLIC", "").strip().lower() == "true"
    return {
        "id": "boundaries",
        "group": "spatial",
        "status": "live" if parcels_on else "gap",
        "label": "ROS INSPIRE parcels",
        "description": "Shapes of registered land parcels from Registers of Scotland. Outlines only — not titles, owners or prices.",
        "developer_note": "Registered cadastral extents (geometry only — no owners, titles or prices). BBox from PostGIS ingest (503 when unloaded; empty viewport is honest 200 when loaded, including fixture-scoped CI). Tiles via live WMS. Source CRS EPSG:27700; shapes only on the public map.",
        "minzoom": 14,
        "endpoint": "/layers/parcels",
        "tile_endpoint": "/layers/parcels/tiles/{z}/{x}/{y}",
        "licence": PARCELS_OGL_PHRASE,
        "licence_url": PARCELS_OGL_URL,
        "source_url": meta["source_url"],
        "attribution": meta["attribution"],
        "harvest_year": meta["harvest_year"],
        "publication_status": meta.get("publication_status", "ok"),
        "gaps": meta["gaps"],
    }


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


def _hla_catalog_layer() -> dict[str, Any] | None:
    """Housing land supply — omitted from public catalog when LAYER_HLS_ENABLED is off."""
    enabled = layer_hls_enabled()
    if not enabled:
        return None
    return {
        "id": "hla",
        "group": "spatial",
        "status": "live",
        "label": "Housing land audit",
        "description": (
            "Housing land audit / housing land supply sites. Planning: of which "
            "figure inside the land part — never added again."
        ),
        "developer_note": (
            "Spatial Hub Housing Land Supply (Housing Land Audit sites). PostGIS "
            "ingest of the OGL open product (503 when unloaded). Annual Ground Rent "
            "breakdown row 1a (planning uplift, already included in surface) — not a "
            "LayersPanel toggle. Audit polygons, not a title. No public money figures. "
            "LAYERS-ADD-1a: LAYER_HLS_ENABLED (default OFF; PSGA restriction)."
        ),
        "endpoint": "/layers/open/hla",
        "licence": "OGL-3.0",
        "licence_status": "ogl",
        "flag_name": FLAG_HLS,
        "minzoom": 8,
        "source_url": SPATIAL_HUB_HLA,
        "spatial_hub_url": SPATIAL_HUB_HLA,
        "ledger_role": "ledger-row",
        "ledger_row": "1a",
        "ui_surface": "ledger",
    }


def platform_catalog() -> dict[str, Any]:
    layers: list[dict[str, Any]] = [
            {
                "id": "agr_value",
                "group": "value",
                "status": "blocked",
                "label": "Annual Ground Rent",
                "description": "Annual Ground Rent figures are withheld from the public catalogue until publication is approved.",
                "developer_note": "Residual site-value AGR withheld from the public catalogue until ECONOMIC_RULES approval — no public money figures.",
            },
            _parcels_meta(),

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
                    "Small-area Data Zone boundaries (2022). Hover or click for the zone "
                    "code, name, council, population and dwellings. Not a rent figure; "
                    "no Annual Ground Rent figures on the map."
                ),
                "developer_note": (
                    "Data Zone boundaries 2022 outlines from PostGIS dz_boundaries when "
                    "loaded (Georgist/Valuation), else SG StatisticalUnits viewport query."
                ),
                "endpoint": "/layers/open/data-zones",
                "licence": "Open Government Licence v3.0",
                "licence_url": (
                    "https://www.nationalarchives.gov.uk/doc/"
                    "open-government-licence/version/3/"
                ),
                "attribution": (
                    "Scottish Government Data Zone boundaries 2022 (OGL). "
                    "Outlines only — not a rent."
                ),
                "minzoom": 10,
                "source_url": (
                    "https://www.spatialdata.gov.scot/geonetwork/srv/eng/catalog.search"
                    "#/metadata/7d564e13-a967-495a-ae2f-048ffdfa4b03"
                ),
            },
            {
                "id": "builtup_mask",
                "group": "spatial",
                "status": "live",
                "label": "Built-up display mask",
                "description": "This is our own estimate of built-up land, not an official boundary. We start with National Records of Scotland's 2022 settlement boundaries, add a 50 m area around each OS Open UPRN address point outside them, then cut the result to each 2022 Data Zone. It only decides which parts of the map are coloured. It is not used in any land value.",
                "developer_note": (
                    "UX10-2: PostGIS map_builtup_mask + dz2022_masked. Vector tiles at "
                    "/layers/open/builtup-mask/tiles/{z}/{x}/{y} and "
                    "/layers/open/dz2022-masked/tiles/{z}/{x}/{y}; bbox GeoJSON siblings. "
                    "503 when unloaded. Faint full Data Zone outlines stay clickable. "
                    "No value colouring (UX10-3)."
                ),
                "endpoint": "/layers/open/dz2022-masked",
                "tile_endpoint": "/layers/open/dz2022-masked/tiles/{z}/{x}/{y}",
                "licence": "OGL-3.0",
                "licence_url": (
                    "https://www.nationalarchives.gov.uk/doc/"
                    "open-government-licence/version/3/"
                ),
                "attribution": "Built-up areas: our estimate from NRS Settlements 2022 and OS Open UPRN. Contains NRS and OS data © Crown copyright and database right 2026 (OGL v3)",
                "minzoom": 10,
                "source_url": (
                    "https://maps.gov.scot/server/rest/services/NRS/Census2022/MapServer"
                ),
            },
            {
                "id": "settlements",
                "group": "spatial",
                "status": "live",
                "label": "NRS Settlements",
                "description": "Places of 500 people or more from the Census 2022 settlements map. Helps name a place on the card — not ownership.",
                "developer_note": "Census 2022 settlements (places of 500 people or more). PostGIS bbox (503 when unloaded). Annual Ground Rent breakdown frame for surface site rent (row 1 zone/settlement grain) — not a LayersPanel toggle, not a title.",
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
                "description": "Built-up localities from the Census 2022 localities map. Helps name a place on the card — not ownership.",
                "developer_note": "Census 2022 localities (built-up localities). PostGIS bbox (503 when unloaded). Annual Ground Rent breakdown frame for surface site rent (row 1) — not a LayersPanel toggle, not ownership.",
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
                "description": "Totals from the Scottish Vacant and Derelict Land Survey, grouped by Data Zone. Zones with one or two sites show no area.",
                "developer_note": "Open /layers/open/vdl returns Data Zone totals only. Zones with fewer than 3 sites publish site_count '<3' and no area. Other areas are rounded to 0.5 ha. No site polygon on the public map.",
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
            _hla_catalog_layer(),
            *dz_context_catalog_layers(),
            {
                "id": "public_crown",
                "group": "ownership",
                "status": "gap",
                "label": "Public and Crown Estate land",
                "description": "Public and Crown land where an open national map is confirmed. Currently held back until the licence is clear.",
                "developer_note": "SG 2024 dashboard of five national bodies — dashboard only, no verified open licence. Hidden from the public map until an OGL-licensed source is confirmed. Not a title, not local-authority land.",
                "licence": "unverified/not open",
                "source_url": PUBLIC_LAND_MAP,
            },
            community_ownership_catalog_layer(),
            {
                "id": "hydro_sites",
                "group": "spatial",
                "status": "live",
                "label": "Hydropower sites (SEPA CAR)",
                "description": "Hydropower sites licensed by SEPA. Inventory of water use for power — not a rent figure and not surface land rent.",
                "developer_note": "SEPA OGL hydropower sites — CAR-licensed water abstractions for hydropower (PostGIS). Extractive inventory (value_tier=proxy). No money figures; separate from surface rent.",
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
                    "SEPA Controlled Activities Regulations licences for water use "
                    "(Simple 194 and Registration 195). Inventory only — never proxies "
                    "live map services. No money figures; not surface rent."
                ),
                "developer_note": (
                    "Ingested from Open/SEPA_Reference MapServer layers 194/195 "
                    "(`python -m etl.ingest_sepa_car`). API serves PostGIS only "
                    "(never proxies MapServer). value_tier=market."
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
                    "Sites of Special Scientific Interest. "
                    "Constraint: changes best use, adds no value — not a rent and not a title."
                ),
                "developer_note": (
                    "NatureScot SSSI boundaries (OGL-3.0). Indicative designations "
                    "from PostGIS ingest — not a title plan. 503 when unloaded."
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
                    "NatureScot SPA, SAC and NNR areas. "
                    "Constraint: changes best use, adds no value — not a rent. "
                    "SSSI is a separate source."
                ),
                "developer_note": (
                    "NatureScot SPA, SAC and NNR boundaries (OGL-3.0). "
                    "SSSI is a separate layer. Indicative — 503 when unloaded."
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
                "description": "National Forest Inventory woodland of half a hectare or more. Land-use context for surface rent — not a title.",
                "developer_note": "NFI woodland Scotland (≥ 0.5 ha). PostGIS ingest of the open Forestry Commission / NatureScot product. Annual Ground Rent breakdown row 1 (surface site rent land-use) — not a LayersPanel toggle, not a rent and not a title. 503 when unloaded.",
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
                "description": "Native woodland areas from the open Scottish Forestry product. Land-use context — not a title.",
                "developer_note": "Native Woodland Survey of Scotland polygons and habitat attributes. PostGIS ingest of the open Scottish Forestry / NatureScot product. Annual Ground Rent breakdown row 1 (surface site rent land-use) — not a LayersPanel toggle, not a rent or title. 503 when unloaded.",
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
                "description": "Renewable Energy Planning Database onshore wind and related sites. Planning evidence for resource rent — not lease shapes or a title.",
                "developer_note": "DESNZ Renewable Energy Planning Database — Scotland planning-site points from the OGL quarterly extract (PostGIS). Annual Ground Rent breakdown row 3 (onshore wind + hydro resource) — not a LayersPanel toggle. Not lease polygons, not a rent, not a title. 503 when unloaded.",
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
                "description": "Crown Estate Scotland seabed and foreshore leases (cables, moorings, offshore energy). Inventory for seabed rent — not a title sheet.",
                "developer_note": "CES Spatial Hub offshore lease polygons (offshore wind, wave, tidal, CCS) under OGL — PostGIS ingest. Offshore only — not onshore estate, not aquaculture (separate layer). Annual Ground Rent breakdown row 4 (seabed & foreshore) — not a LayersPanel toggle, not a title sheet, no money figures. 503 when unloaded.",
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
                # Not ingested on public hosts yet — Coming soon until PostGIS load.
                "status": "gap",
                "label": "Land capability for agriculture",
                "description": (
                    "Land Capability for Agriculture soil and climate classes "
                    "(James Hutton Institute). "
                    "Constraint: changes best use, adds no value — not a rent or title."
                ),
                "developer_note": (
                    "James Hutton Institute LCA 1:250,000 — soil and climate "
                    "capability classes. BBox from PostGIS ingest (503 when unloaded)."
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
                    "ScotWind and INTOG offshore wind option areas from Crown Estate "
                    "Scotland. Option shapes only — separate from surface rent. "
                    "Option-fee HOLD — not layer attributes."
                ),
                "developer_note": (
                    "PostGIS ingest. Evidence tag market. Fees config: "
                    "data/config/scotwind_option_fees.yaml. "
                    "Annual Ground Rent breakdown row 4."
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
                "description": "Onshore wind sites from the Renewable Energy Planning Database. Planning evidence — not lease shapes or a title.",
                "developer_note": "DESNZ Renewable Energy Planning Database — Scotland onshore wind sites with installed capacity (MW) and development status. Annual Ground Rent breakdown row 3 (onshore wind resource) — not a LayersPanel toggle. Resource-rent evidence only: no money figures, never added to Surface Rent or AGR. Planning-site points, not leases.",
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
                "id": "ces_aquaculture",
                "group": "natural_capital",
                # Not ingested on public hosts yet — Coming soon until PostGIS load.
                "status": "gap",
                "label": "CES aquaculture seabed leases",
                "description": (
                    "Aquaculture seabed leases from Crown Estate Scotland. Licence rent "
                    "evidence — not a title. No money figures; never added to surface rent "
                    "(Annual Ground Rent breakdown row 5)."
                ),
                "developer_note": (
                    "Spatial Hub aquaculture seabed lease polygons (OGL). "
                    "value_tier=market. SEPA biomass stays GIS HOLD."
                ),
                "endpoint": "/layers/open/ces-aquaculture",
                "licence": "OGL-3.0",
                "licence_url": OGL_V3_URL,
                "minzoom": 5,
                "source_url": CROWN_ESTATE_HUB,
                "attribution": (
                    "Contains information from the Crown Estate Scotland licensed "
                    "under the Open Government Licence v3.0."
                ),
                "value_tier": "market",
                "adds_to_surface_rent": False,
                "publication_status": "ok",
                "ledger_role": "ledger-row",
                "ledger_row": "5",
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
                "id": "carbon_peatland",
                "group": "natural_capital",
                "status": "linked",
                "label": "Carbon & Peatland 2016",
                "description": "Peat and carbon soils used for nature accounting. Unpriced carbon sits outside market rents.",
                "developer_note": "NatureScot / James Hutton Carbon and Peatland Map 2016. Allowed while Scot-LAND is non-commercial; tagged licence=non-commercial. Not painted until the loader lands.",
                "licence": "non-commercial",
                "licence_url": (
                    "https://gis-downloads.nature.scot/CPM2016_SCOTLAND_GPKG_27700.zip"
                ),
                "attribution": (
                    "Contains NatureScot / James Hutton Institute Carbon and "
                    "Peatland Map 2016 information. Non-commercial use only."
                ),
                "source_url": (
                    "https://gis-downloads.nature.scot/CPM2016_SCOTLAND_GPKG_27700.zip"
                ),
                "ledger_role": "ledger-row",
                "ledger_row": "8",
                "ui_surface": "ledger",
            },
            {
                "id": "nsta_oil_gas",
                "group": "natural_capital",
                "status": "linked",
                "label": "NSTA oil and gas",
                "description": "UK oil and gas fields shown for comparison only. Outside Scotland’s land totals.",
                "developer_note": "North Sea Transition Authority licences and fields. Allowed while Scot-LAND is non-commercial; tagged licence=non-commercial. Outside the Scottish totals.",
                "licence": "non-commercial",
                "licence_url": "https://www.nstauthority.co.uk/data-and-insights/",
                "attribution": (
                    "Contains information provided by the North Sea Transition "
                    "Authority and/or other third parties. Non-commercial use only."
                ),
                "source_url": "https://www.nstauthority.co.uk/data-and-insights/",
                "ledger_role": "ledger-row",
                "ledger_row": "9",
                "ui_surface": "ledger",
            },
            {
                "id": "sasine_private",
                "group": "ownership",
                "status": "gap",
                "label": "Private owners and Sasine land",
                "description": "Incomplete or paid. Gaps are shown; names are not invented.",
            },
    ]
    # Drop None slots from gated catalog helpers (LDP/HLS when flags OFF).
    layers = [row for row in layers if row is not None]
    # Omit SEPA flood extent from the public list when its gate is OFF.
    layers = [
        row
        for row in layers
        if not (
            row.get("id") == "flood"
            and row.get("status") != "live"
            and row.get("flag_name") == "LAYER_SEPA_FLOOD_EXTENT_ENABLED"
        )
    ]
    return {
        "version": 2,
        "brief": "docs/PLATFORM.md",
        "principle": (
            "Annual Ground Rent for every place in Scotland; every figure labelled "
            "Market, Modelled, or Estimate; figures not published yet"
        ),
        "choropleth_metrics": [
            {
                "id": mid,
                **{k: v for k, v in defn.items() if k != "property"},
                "property": defn["property"],
            }
            for mid, defn in METRIC_DEFS.items()
            if mid in PUBLIC_CATALOG_METRIC_IDS
        ],
        "layers": layers,
        "flood_dz_loaded": flood_dz_loaded(),
        # LAYERS-ADD-1 public surfaces only (no flagged / prohibited ids).
        "layers_add": public_layers_add_entries(),
        "layers_add_waiting": waiting_for_permission_rows(),
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
    """Prefer caller-supplied codes; otherwise open council polygons.

    Display names are always canonicalised to the official NRS/SG 32 council
    area list (fixes HPI aliases and typos such as "City of Ediburgh").
    """
    code = council_code
    name = council_name
    if not (code and name):
        try:
            match = lookup_council_boundary(lat, lng)
        except FileNotFoundError:
            match = None
        if match is not None:
            code = code or match.hpi_code
            name = name or match.name
    return code, official_council_name(code, name)


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


_FIGURES_PENDING = "figures pending sign-off"
_CONSTRAINT_LABEL = "Constraint: changes best use, adds no value"

# WGS84 → OSGB36 British National Grid (EPSG:27700). always_xy: lon, lat in.
_TO_OSGB36 = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)


def _square_reference(lat: float, lng: float) -> str:
    """Map reference as OSGB36 easting,northing (EPSG:27700); never what3words."""
    easting, northing = _TO_OSGB36.transform(lng, lat)
    return f"{int(round(easting))},{int(round(northing))}"


def _intermediate_zone_for(data_zone: dict[str, Any]) -> dict[str, Any]:
    """Intermediate Zone from zone_spine + official NRS/SG name lookup.

    Never show \"No data\" when the IZ code is known — prefer the official name,
    else the code itself.
    """
    code = data_zone.get("code")
    vintage = data_zone.get("vintage")
    if not code or vintage is None:
        return {"status": "no_data", "code": None, "name": None, "note": "No data"}
    try:
        from georgist import db
    except Exception:
        return {"status": "no_data", "code": None, "name": None, "note": "No data"}
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT iz_code FROM datazones.zone_spine "
                "WHERE code = %s AND vintage = %s LIMIT 1",
                (code, int(vintage)),
            )
            row = cur.fetchone()
    except Exception:
        return {"status": "no_data", "code": None, "name": None, "note": "No data"}
    if not row:
        return {"status": "no_data", "code": None, "name": None, "note": "No data"}
    iz_code = row.get("iz_code") if isinstance(row, dict) else row[0]
    if not iz_code:
        return {"status": "no_data", "code": None, "name": None, "note": "No data"}
    name = iz_name(str(iz_code), int(vintage))
    if name:
        return {
            "status": "ok",
            "code": iz_code,
            "name": name,
            "note": None,
            "licence": "OGL v3.0 — NRS/Scottish Government Intermediate Zones",
        }
    # Code known but official name not in the lookup yet — never "No data".
    return {
        "status": "ok",
        "code": iz_code,
        "name": None,
        "note": "name not loaded yet",
        "licence": "OGL v3.0 — NRS/Scottish Government Intermediate Zones",
    }


def _place_label_from_nrs(
    lat: float,
    lng: float,
    *,
    council_name: str | None,
    postcode: str | None,
) -> str:
    """Title from NRS locality/settlement; fall back to council then postcode."""
    locality = nrs_place_at("localities", lat, lng)
    settlement = nrs_place_at("settlements", lat, lng)
    loc_name = (locality or {}).get("name") if isinstance(locality, dict) else None
    set_name = (settlement or {}).get("name") if isinstance(settlement, dict) else None
    loc_name = str(loc_name).strip() if loc_name else None
    set_name = str(set_name).strip() if set_name else None
    if set_name and loc_name and set_name.lower() != loc_name.lower():
        return f"{set_name}, {loc_name}"
    if loc_name:
        return loc_name
    if set_name:
        return set_name
    if council_name:
        return str(council_name).strip()
    if postcode:
        return str(postcode).strip()
    return "This place"


# Public rent/value group headings (AGENTS.md / RENT_GROUP_NAMES). Never Surface/Resource/Nature.
_RENT_GROUP_LABELS = {
    "surface": "Land",
    "resource": "Natural resource rents",
    "nature": "Services of nature",
}

_PART_GLOSS = {
    "surface": "The yearly rental value of the land under homes, without the buildings.",
    "resource": "Rent from natural resources such as wind, water, minerals and fish farm sites.",
    "nature": "What nature gives us for free, such as peat holding carbon. Estimate only.",
}

# UX-10 / FP1: pre-£ range text until modules publish amounts.
_PART_NOT_YET = "not yet estimated"


def _agr_rows() -> list[dict[str, Any]]:
    """AGR parts: land / resource rents / services of nature — FP1 schema, no £."""
    return [
        {
            "id": "surface",
            "label": _RENT_GROUP_LABELS["surface"],
            "tag": "proxy",
            "amount_label": _FIGURES_PENDING,
            "gloss": _PART_GLOSS["surface"],
            "range": _PART_NOT_YET,
            "unit": None,
            "confidence": None,
            "method": None,
            "class": "proxy",
            "of_which": [
                {"id": "planning_uplift", "label": "of which: planning uplift"},
                {
                    "id": "infrastructure_share",
                    "label": "of which: infrastructure share",
                },
            ],
        },
        {
            "id": "resource",
            "label": _RENT_GROUP_LABELS["resource"],
            "tag": "market",
            "amount_label": _FIGURES_PENDING,
            "gloss": _PART_GLOSS["resource"],
            "range": _PART_NOT_YET,
            "unit": None,
            "confidence": None,
            "method": None,
            "class": "market",
        },
        {
            "id": "nature",
            "label": _RENT_GROUP_LABELS["nature"],
            "tag": "shadow",
            "amount_label": _FIGURES_PENDING,
            "gloss": _PART_GLOSS["nature"],
            "range": _PART_NOT_YET,
            "unit": None,
            "confidence": None,
            "method": None,
            "class": "shadow",
        },
    ]


def _constraints_for(card: dict[str, Any]) -> list[dict[str, Any]]:
    """Constraint rows — never show £ / £0."""
    vacant = bool(card.get("vacant_or_derelict"))
    crofting = card.get("crofting") or {}
    croft_applies = None
    if crofting.get("status") in {"live", "linked"}:
        croft_applies = bool(crofting.get("on_this_point")) if "on_this_point" in crofting else None
    return [
        {
            "id": "vdl",
            "label": "Vacant and derelict land",
            "applies": vacant,
            "banner": _CONSTRAINT_LABEL,
        },
        {
            "id": "designations",
            "label": "Designations (e.g. SSSI)",
            "applies": None,
            "note": "No data",
            "banner": _CONSTRAINT_LABEL,
        },
        {
            "id": "flood",
            "label": "Flood",
            "applies": None,
            "note": "No data",
            "banner": _CONSTRAINT_LABEL,
        },
        {
            "id": "crofting",
            "label": "Crofting / common grazings",
            "applies": croft_applies,
            "note": None if croft_applies is not None else "No data",
            "banner": _CONSTRAINT_LABEL,
        },
    ]


def _holder_for(card: dict[str, Any]) -> dict[str, Any]:
    """Public-records holder only, else private, not shown."""
    community = card.get("community_ownership") or {}
    if community.get("on_this_point"):
        assets = community.get("assets") or []
        name = None
        if assets and isinstance(assets[0], dict):
            name = (assets[0].get("name") or "").strip() or None
        return {
            "status": "public_record",
            "label": name or "Community ownership (public record)",
            "note": community.get("note"),
        }
    public = card.get("public_or_crown") or {}
    if public.get("on_this_point"):
        holdings = public.get("holdings") or []
        org = None
        if holdings and isinstance(holdings[0], dict):
            org = (holdings[0].get("organisation") or "").strip() or None
        return {
            "status": "public_record",
            "label": org or "Public / Crown holding (public record)",
            "note": public.get("note"),
        }
    return {
        "status": "private_not_shown",
        "label": "private, not shown",
        "note": "Owner details from public records only.",
    }


def _layer_row(
    *,
    layer_id: str,
    label: str,
    status: str,
    intersects: bool | None,
    note: str | None = None,
    source_url: str | None = None,
    licence: str | None = None,
    licence_url: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One place-card layer row. Every layer carries a licence credit."""
    row: dict[str, Any] = {
        "id": layer_id,
        "label": label,
        "status": status,
        "intersects": intersects,
        "licence": licence or "Licence not recorded",
    }
    if note:
        row["note"] = note
    if source_url:
        row["source_url"] = source_url
    if licence_url:
        row["licence_url"] = licence_url
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
                licence=PARCELS_OGL_PHRASE,
                licence_url=PARCELS_OGL_URL,
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
                licence=PARCELS_OGL_PHRASE,
                licence_url=PARCELS_OGL_URL,
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
                licence=PARCELS_OGL_PHRASE,
                licence_url=PARCELS_OGL_URL,
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
            licence="OGL-3.0",
            licence_url=OGL_V3_URL,
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
            licence=public.get("licence") or "unverified/not open",
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
            licence=(
                common_good.get("licence")
                or "Linked registers; Highland licence unconfirmed; "
                "Fife OS INSPIRE EUL linked only"
            ),
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
            licence="Not openly licensed for this portal",
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
            licence="Incomplete or paid — gaps shown, names not invented",
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

    data_zone = _data_zone_at(lat, lng)
    # Identify: top-level dz_code mirrors data_zone.code; null/omit on sea miss.
    dz_code = data_zone.get("code") if data_zone.get("status") == "ok" else None
    card: dict[str, Any] = {
        "contract": "place_card_v1",
        "lat": lat,
        "lng": lng,
        "postcode": postcode,
        "council_code": council_code,
        "council_name": council_name,
        "data_zone": data_zone,
        # MAP-CARDS-ADDENDUM-1 A6: identify + build CRS for later BNG→DZ lookup.
        "dz_code": dz_code,
        "source_crs": "EPSG:27700",
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
    card["place_label"] = _place_label_from_nrs(
        lat, lng, council_name=council_name, postcode=postcode
    )
    card["square_reference"] = _square_reference(lat, lng)
    card["intermediate_zone"] = _intermediate_zone_for(card["data_zone"])
    card["agr_rows"] = _agr_rows()
    card["constraints"] = _constraints_for(card)
    card["holder"] = _holder_for(card)
    card["layers"] = _layers_at_point(card)
    card["links"] = _place_links(card)
    # Land outline for the place card — never expose parcel ID on the public card.
    parcel_block = card.get("parcel") or {}
    card["land_outline"] = {
        "status": (outline or {}).get("status") if outline else (
            "inside_outline" if parcel_block.get("found") else "unknown"
        ),
        "label": "Land outline",
        "area_sqm": parcel_block.get("area_sqm"),
        "note": (
            (outline or {}).get("note")
            or parcel_block.get("note")
            or "Registered extent outline only — not a title sheet."
        ),
        # Explicitly omit inspire_id / national_reference from public card field.
    }
    # GBP-LIVE-V1: attach flag (default OFF). Money only when enabled in gbp_live.yaml.
    return attach_gbp_live_to_place_card(card)
