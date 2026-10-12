"""Scottish Public and Crown Estate land overlay.

Source: Scottish Government 2024 FeatureServer behind the official
public-land dashboard. Five bodies only (Forestry and Land Scotland,
NatureScot, Scottish Crown Estate, Scottish Water, Crofting Agricultural
Holdings). Indicative holdings — not a title plan, not local-authority land.
"""

from __future__ import annotations

from typing import Any

import httpx

FEATURE_URL = (
    "https://services-eu1.arcgis.com/4QkhM5AS8YOlkb6T/arcgis/rest/services/"
    "PublicLand_2024_Update/FeatureServer/8/query"
)
TIMEOUT = 12.0
MAX_FEATURES = 80
OUT_FIELDS = "Organisation,Area_Ha,SiteName,OBJECTID"

BODIES = (
    "Forestry and Land Scotland",
    "NatureScot",
    "Scottish Crown Estate",
    "Scottish Water",
    "Crofting Agricultural Holdings",
)

DASHBOARD_URL = (
    "https://www.arcgis.com/apps/dashboards/a10668ccd4784209bf22e3adcef6b897"
)
NEWS_URL = "https://www.gov.scot/news/interactive-map/"

ATTRIBUTION = (
    "Scottish Public and Crown Estate Land 2024. "
    "Scottish Government; landholding bodies listed on the official map. "
    "Non-exhaustive — five bodies only, not a legal title."
)


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT)


def _simplify_offset(south: float, west: float, north: float, east: float) -> float:
    span = max(abs(north - south), abs(east - west))
    return max(span / 500.0, 0.00015)


def _holding(attrs: dict[str, Any]) -> dict[str, Any]:
    return {
        "organisation": attrs.get("Organisation"),
        "site_name": attrs.get("SiteName"),
        "area_ha": attrs.get("Area_Ha"),
        "object_id": attrs.get("OBJECTID"),
    }


def query_point(lat: float, lng: float) -> dict[str, Any]:
    """Holdings whose polygon contains the clicked point."""
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": OUT_FIELDS,
        "returnGeometry": "false",
        "outSR": 4326,
        "resultRecordCount": 5,
        "orderByFields": "Area_Ha DESC",
        "f": "json",
    }
    try:
        with _client() as client:
            response = client.get(FEATURE_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "ok": False,
            "error": str(exc),
            "holdings": [],
            "source": ATTRIBUTION,
            "map_url": DASHBOARD_URL,
        }

    features = payload.get("features") or []
    holdings = [_holding(feat.get("attributes") or {}) for feat in features]
    return {
        "ok": True,
        "intersects": bool(holdings),
        "holdings": holdings,
        "bodies": list(BODIES),
        "source": ATTRIBUTION,
        "map_url": DASHBOARD_URL,
        "about_url": NEWS_URL,
        "note": (
            "Five national bodies only, and not exhaustive even for those. "
            "Not local-authority land. Not a legal title — confirm on ScotLIS."
        ),
    }


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport public / Crown polygons as GeoJSON (WGS84)."""
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
        "orderByFields": "Area_Ha DESC",
        "maxAllowableOffset": _simplify_offset(south, west, north, east),
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
            "meta": {"ok": False, "error": str(exc), "layer": "public_land"},
        }

    if payload.get("type") != "FeatureCollection":
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": "Unexpected public-land response",
                "layer": "public_land",
            },
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
                    "organisation": props.get("Organisation"),
                    "site_name": props.get("SiteName"),
                    "area_ha": props.get("Area_Ha"),
                    "layer": "public_land",
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": cleaned,
        "meta": {
            "ok": True,
            "layer": "public_land",
            "count": len(cleaned),
            "capped": len(features) >= cap,
            "source": ATTRIBUTION,
            "map_url": DASHBOARD_URL,
            "bodies": list(BODIES),
            "licence": "public SG dashboard overlay — not a title",
        },
    }
