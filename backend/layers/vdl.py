"""Scottish Vacant and Derelict Land overlay.

Authoritative site list: Scottish Government SVDLS site register.
Spatial overlay: Spatial Hub / Improvement Service republish of SVDLS
polygons (OGL). Site-level as published — survey polygons, not a title plan.
"""

from __future__ import annotations

from typing import Any

import httpx

FEATURE_URL = (
    "https://services2.arcgis.com/Ne8d9gKn5SJ3eAaw/ArcGIS/rest/services/"
    "Scottish_Vacant_and_Derelict_Land_2024/FeatureServer/1/query"
)
TIMEOUT = 8.0
MAX_FEATURES = 80
OUT_FIELDS = (
    "site_name,site_type,site_size,local_auth,la_s_code,"
    "owner_1,site_code,address,period"
)

# Published site_type values from the Spatial Hub / SVDLS FeatureServer.
SITE_TYPES = (
    "Vacant Land",
    "Vacant Land and Buildings",
    "Derelict",
)

ATTRIBUTION = (
    "Scottish Vacant and Derelict Land Survey. "
    "Contains public sector information licensed under the Open Government Licence v3.0. "
    "Contains data from Improvement Service under OGL, supplied by Scotland's local "
    "planning authorities and Loch Lomond & The Trossachs National Park Authority. "
    "© Scottish Government. Survey polygons, not a title."
)
REGISTER_URL = (
    "https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/"
)
SPATIAL_HUB_URL = "https://data.spatialhub.scot/dataset/vacant_and_derelict_land-is"
PUBLICATION_URL = (
    "https://www.gov.scot/publications/scottish-vacant-and-derelict-land-survey-2025/"
)


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT)


def _size_ha(raw: Any) -> float | None:
    """Register site size is published as hectares (sometimes as a string)."""
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _site_props(attrs: dict[str, Any]) -> dict[str, Any]:
    """Map FeatureServer attributes to public site fields as published."""
    return {
        "name": attrs.get("site_name"),
        "site_type": attrs.get("site_type"),
        "size_ha": _size_ha(attrs.get("site_size")),
        "local_authority": attrs.get("local_auth"),
        "owner_class": attrs.get("owner_1"),
        "site_code": attrs.get("site_code"),
        "address": attrs.get("address"),
        "period": attrs.get("period"),
        "layer": "vdl",
        "source": ATTRIBUTION,
    }


def by_council_hectares() -> dict[str, dict[str, Any]]:
    """SVDLS hectares and site counts keyed by local-authority S-code."""
    params = {
        "where": "1=1",
        "groupByFieldsForStatistics": "la_s_code",
        "outStatistics": (
            '[{"statisticType":"count","onStatisticField":"FID",'
            '"outStatisticFieldName":"n"},'
            '{"statisticType":"sum","onStatisticField":"Shape__Area",'
            '"outStatisticFieldName":"sqm"}]'
        ),
        "f": "json",
    }
    try:
        with _client() as client:
            response = client.get(FEATURE_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return {}
    by_code: dict[str, dict[str, Any]] = {}
    for feat in payload.get("features") or []:
        attrs = feat.get("attributes") or {}
        code = attrs.get("la_s_code")
        if not code:
            continue
        ha = float(attrs.get("sqm") or 0) / 10_000.0
        by_code[str(code)] = {
            "vacantHa": round(ha, 2),
            "vacantSites": int(attrs.get("n") or 0),
        }
    return by_code


def query_point(lat: float, lng: float) -> dict[str, Any]:
    """Sites whose polygon contains the clicked point."""
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": OUT_FIELDS,
        "returnGeometry": "false",
        "outSR": 4326,
        "resultRecordCount": 5,
        "f": "json",
    }
    try:
        with _client() as client:
            response = client.get(FEATURE_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "sites": [], "source": ATTRIBUTION}

    features = payload.get("features") or []
    sites = []
    for feat in features:
        attrs = feat.get("attributes") or {}
        props = _site_props(attrs)
        sites.append(
            {
                "name": props["name"],
                "site_type": props["site_type"],
                "size_ha": props["size_ha"],
                "local_authority": props["local_authority"],
                "owner_class": props["owner_class"],
                "site_code": props["site_code"],
                "address": props["address"],
                "period": props["period"],
            }
        )
    return {
        "ok": True,
        "intersects": bool(sites),
        "sites": sites,
        "source": ATTRIBUTION,
        "register_url": REGISTER_URL,
        "spatial_hub_url": SPATIAL_HUB_URL,
        "licence": "OGL-3.0",
        "note": (
            "SVDLS site class and owner class are survey fields, not a legal title. "
            "Confirm ownership on ScotLIS."
        ),
    }


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport VDL polygons as GeoJSON (WGS84), site-level as published."""
    cap = max(1, min(int(max_features), MAX_FEATURES))
    envelope = f"{west},{south},{east},{north}"
    params = {
        "geometry": envelope,
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": 4326,
        "resultRecordCount": cap,
        "f": "geojson",
    }
    try:
        with _client() as client:
            response = client.get(FEATURE_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {"ok": False, "error": str(exc), "layer": "vdl"},
        }

    if payload.get("type") != "FeatureCollection":
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {"ok": False, "error": "Unexpected VDL response", "layer": "vdl"},
        }

    features = payload.get("features") or []
    cleaned = []
    for feat in features[:cap]:
        props = dict(feat.get("properties") or {})
        cleaned.append(
            {
                "type": "Feature",
                "geometry": feat.get("geometry"),
                "properties": _site_props(props),
            }
        )
    return {
        "type": "FeatureCollection",
        "features": cleaned,
        "meta": {
            "ok": True,
            "layer": "vdl",
            "count": len(cleaned),
            "capped": len(features) >= cap,
            "source": ATTRIBUTION,
            "register_url": REGISTER_URL,
            "spatial_hub_url": SPATIAL_HUB_URL,
            "publication_url": PUBLICATION_URL,
            "licence": "OGL-3.0",
            "site_types": list(SITE_TYPES),
            "gaps": [
                "Owner class is a survey field, not legal title",
                "Survey polygons are indicative — confirm extent on ScotLIS",
                "Sites removed or re-coded since the Spatial Hub vintage may differ "
                "from the latest SG site register",
            ],
        },
    }
