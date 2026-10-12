"""Scottish Vacant and Derelict Land overlay.

Authoritative statistics: Scottish Government SVDLS site register.
Spatial overlay queried from a public FeatureServer republish of Spatial Hub
SVDLS polygons (OGL). Indicative geometry — not a title plan.
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
OUT_FIELDS = "site_name,site_type,site_size,local_auth,la_s_code,owner_1,site_code,address"

ATTRIBUTION = (
    "Scottish Vacant and Derelict Land Survey. "
    "Contains public sector information licensed under the Open Government Licence v3.0. "
    "Spatial Hub / Improvement Service; site register: Scottish Government."
)
REGISTER_URL = (
    "https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/"
)


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT)


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
        sites.append(
            {
                "name": attrs.get("site_name"),
                "site_type": attrs.get("site_type"),
                "size_ha": attrs.get("site_size"),
                "local_authority": attrs.get("local_auth"),
                "owner_class": attrs.get("owner_1"),
                "site_code": attrs.get("site_code"),
                "address": attrs.get("address"),
            }
        )
    return {
        "ok": True,
        "intersects": bool(sites),
        "sites": sites,
        "source": ATTRIBUTION,
        "register_url": REGISTER_URL,
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
    """Viewport VDL polygons as GeoJSON (WGS84)."""
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
                "properties": {
                    "name": props.get("site_name"),
                    "site_type": props.get("site_type"),
                    "size_ha": props.get("site_size"),
                    "local_authority": props.get("local_auth"),
                    "owner_class": props.get("owner_1"),
                    "site_code": props.get("site_code"),
                    "layer": "vdl",
                },
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
            "licence": "OGL-3.0",
        },
    }
