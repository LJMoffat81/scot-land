"""Scottish Vacant and Derelict Land overlay.

Authoritative site list: Scottish Government SVDLS site register.
Spatial overlay: Spatial Hub / Improvement Service republish of SVDLS
polygons (OGL). Upstream features are survey polygons, not a title plan.
The public ``/layers/open/vdl`` body is Data Zone totals only (count and
area): no site code, site name, per-site area, address or site geometry.

Geometry precedence (room decision): Spatial Hub survey > RoS title outline >
point. Upstream sites are tagged with ``geometry_source`` before the roll-up.
The live FeatureServer path is Spatial Hub survey only; see
``layers.svdls_geometry``.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx

from georgist.dz_lookup import (
    BoundariesUnavailable,
    lookup as lookup_data_zone,
    vintage_for_code,
)
from layers.svdls_geometry import (
    GEOMETRY_PRECEDENCE,
    GEOMETRY_SOURCE_LABELS,
    GEOMETRY_SOURCE_SPATIALHUB_SURVEY,
)

FEATURE_URL = (
    "https://services2.arcgis.com/Ne8d9gKn5SJ3eAaw/ArcGIS/rest/services/"
    "Scottish_Vacant_and_Derelict_Land_2024/FeatureServer/1/query"
)
TIMEOUT = 8.0
MAX_FEATURES = 80
# GIS: FeatureServer geometry must be requested in WGS84 for the map.
OUT_SR = 4326
IN_SR = 4326
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

# Live open overlay geometry: Spatial Hub survey (highest public precedence).
# Used only to tag upstream features before they are rolled up. The public
# /layers/open/vdl body never includes site geometry or site identifiers.
LIVE_GEOMETRY_SOURCE = GEOMETRY_SOURCE_SPATIALHUB_SURVEY

# Exact public keys for GET /layers/open/vdl (Data Zone grain only).
OPEN_VDL_TOP_KEYS = frozenset({"type", "features", "meta"})
OPEN_VDL_META_KEYS = frozenset(
    {
        "ok",
        "layer",
        "count",
        "capped",
        "grain",
        "licence",
        "source",
        "register_url",
        "spatial_hub_url",
        "publication_url",
        "site_types",
        "gaps",
        "data_zones",
    }
)
OPEN_VDL_ZONE_KEYS = frozenset({"data_zone", "vintage", "site_count", "area_ha"})
# Fewer than 3 sites: the count is this band and area is omitted.
SMALL_SITE_COUNT = "<3"
# Public source, gaps lead, and map attribution. Zone totals only.
ZONE_TOTALS_TEXT = (
    "Totals from the Scottish Vacant and Derelict Land Survey, grouped by Data Zone. "
    "Zones with one or two sites show no area."
)
_STALE_VDL_PHRASES = (
    "Survey sites, not a title",
    "Owner class is a survey field",
    "Survey polygons are indicative",
)
# Rejected anywhere in the public body — finer than Data Zone.
OPEN_VDL_FORBIDDEN_KEYS = frozenset(
    {
        "site_code",
        "site_name",
        "name",
        "address",
        "uprn",
        "size_ha",
        "site_size",
        "owner_class",
        "owner_1",
        "site_type",
        "local_authority",
        "local_auth",
        "period",
        "geometry",
        "coordinates",
        "geometry_source",
        "geometry_source_label",
    }
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


def zone_for_point(lng: float, lat: float) -> tuple[str, int] | None:
    """Data Zone containing a point, or None when boundaries are unavailable.

    Prefers the 2022 code when both vintages hit. Never invents a code.
    """
    try:
        found = lookup_data_zone(lat, lng)
    except BoundariesUnavailable:
        return None
    zones = [
        zone
        for zone in found.zones
        if vintage_for_code(str(zone.get("code") or "")) == zone.get("vintage")
    ]
    if not zones:
        return None
    primary = next((zone for zone in zones if zone["vintage"] == 2022), zones[0])
    return str(primary["code"]), int(primary["vintage"])


def _ring_centroid(ring: Any) -> tuple[float, float] | None:
    if not isinstance(ring, list) or not ring:
        return None
    points = [
        point
        for point in ring
        if isinstance(point, (list, tuple)) and len(point) >= 2
    ]
    if not points:
        return None
    lng = sum(float(point[0]) for point in points) / len(points)
    lat = sum(float(point[1]) for point in points) / len(points)
    return lng, lat


def _feature_centroid(geom: Any) -> tuple[float, float] | None:
    """Internal only — the centroid is never copied onto the public response."""
    if not isinstance(geom, dict):
        return None
    coords = geom.get("coordinates")
    kind = geom.get("type")
    if kind == "Point":
        return _ring_centroid([coords])
    if kind == "Polygon":
        return _ring_centroid(coords[0] if isinstance(coords, list) and coords else None)
    if kind == "MultiPolygon" and isinstance(coords, list) and coords:
        first = coords[0]
        ring = first[0] if isinstance(first, list) and first else None
        return _ring_centroid(ring)
    return None


def round_area_ha(area: float) -> float:
    """Nearest 0.5 hectare, half up (7.3 → 7.5)."""
    doubled = (Decimal(str(area)) * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(doubled / 2)


def publish_zone_figures(site_count: int, area_ha: float) -> tuple[str | int, float | None]:
    """Small counts hide area. Larger totals are rounded to 0.5 ha."""
    if site_count < 3:
        return SMALL_SITE_COUNT, None
    return site_count, round_area_ha(area_ha)


def _zone_identity(raw: dict[str, Any]) -> tuple[str, int] | None:
    if OPEN_VDL_FORBIDDEN_KEYS.intersection(raw):
        return None
    code = raw.get("data_zone")
    vintage = raw.get("vintage")
    if isinstance(vintage, bool) or not isinstance(vintage, int):
        return None
    if vintage_for_code(str(code) if code is not None else "") != vintage:
        return None
    return str(code), vintage


def _raw_measure(raw: dict[str, Any]) -> tuple[int, float] | None:
    count = raw.get("site_count")
    area = raw.get("area_ha")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return None
    if isinstance(area, bool) or not isinstance(area, (int, float)):
        return None
    return count, float(area)


def _merge_zones(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sum raw counts, then apply the small-count band. Already-banded rows stay banded."""
    raw_acc: dict[tuple[str, int], dict[str, float | int]] = {}
    published: dict[tuple[str, int], dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        ident = _zone_identity(raw)
        if ident is None:
            continue
        measure = _raw_measure(raw)
        if measure is not None:
            count, area = measure
            slot = raw_acc.get(ident)
            if slot is None:
                raw_acc[ident] = {"site_count": count, "area_ha": area}
            else:
                slot["site_count"] = int(slot["site_count"]) + count
                slot["area_ha"] = float(slot["area_ha"]) + area
            continue
        if raw.get("site_count") == SMALL_SITE_COUNT:
            published[ident] = {
                "data_zone": ident[0],
                "vintage": ident[1],
                "site_count": SMALL_SITE_COUNT,
                "area_ha": None,
            }
    out: list[dict[str, Any]] = []
    for ident in sorted(set(raw_acc) | set(published)):
        if ident in raw_acc:
            slot = raw_acc[ident]
            count, area = publish_zone_figures(
                int(slot["site_count"]), float(slot["area_ha"])
            )
            out.append(
                {
                    "data_zone": ident[0],
                    "vintage": ident[1],
                    "site_count": count,
                    "area_ha": area,
                }
            )
        else:
            out.append(published[ident])
    return out


def _public_gaps(raw: Any) -> list[str]:
    kept: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, str) or item == ZONE_TOTALS_TEXT:
                continue
            if any(phrase in item for phrase in _STALE_VDL_PHRASES):
                continue
            kept.append(item)
    return [ZONE_TOTALS_TEXT, *kept]


def _string_list(raw: Any, fallback: tuple[str, ...] | list[str]) -> list[str]:
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return list(raw)
    return list(fallback)


def public_vdl_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Data Zone totals only. Drops site identifiers, per-site area and geometry."""
    meta_in = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    if meta_in.get("ok") is False:
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": str(meta_in.get("error") or "upstream source failed"),
                "layer": "vdl",
            },
        }

    incoming: list[Any] = []
    zones_in = meta_in.get("data_zones")
    if isinstance(zones_in, list):
        incoming.extend(zones_in)
    for feat in payload.get("features") or []:
        if not isinstance(feat, dict) or feat.get("geometry"):
            continue
        props = feat.get("properties")
        if isinstance(props, dict):
            incoming.append(props)
    zones = _merge_zones(incoming)
    gaps = _public_gaps(meta_in.get("gaps"))
    return {
        "type": "FeatureCollection",
        "features": [],
        "meta": {
            "ok": True,
            "layer": "vdl",
            "count": len(zones),
            "capped": bool(meta_in.get("capped")),
            "grain": "data_zone",
            "licence": str(meta_in.get("licence") or "OGL-3.0"),
            "source": ZONE_TOTALS_TEXT,
            "register_url": str(meta_in.get("register_url") or REGISTER_URL),
            "spatial_hub_url": str(meta_in.get("spatial_hub_url") or SPATIAL_HUB_URL),
            "publication_url": str(meta_in.get("publication_url") or PUBLICATION_URL),
            "site_types": _string_list(meta_in.get("site_types"), SITE_TYPES),
            "gaps": gaps,
            "data_zones": zones,
        },
    }


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
        # Live FeatureServer features are Spatial Hub survey polygons.
        "geometry_source": LIVE_GEOMETRY_SOURCE,
        "geometry_source_label": GEOMETRY_SOURCE_LABELS[LIVE_GEOMETRY_SOURCE],
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
        "inSR": IN_SR,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": OUT_FIELDS,
        "returnGeometry": "false",
        "outSR": OUT_SR,
        "resultRecordCount": 5,
        "f": "json",
    }
    try:
        with _client() as client:
            response = client.get(FEATURE_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "sites": [], "source": ZONE_TOTALS_TEXT}

    features = payload.get("features") or []
    return {
        "ok": True,
        "intersects": bool(features),
        # Site rows stay off the public place payload (finer than Data Zone).
        "sites": [],
        "source": ZONE_TOTALS_TEXT,
        "register_url": REGISTER_URL,
        "spatial_hub_url": SPATIAL_HUB_URL,
        "licence": "OGL-3.0",
        "geometry_precedence": list(GEOMETRY_PRECEDENCE),
        "note": (
            "SVDLS site class and owner class are survey fields, not a legal title. "
            "Confirm ownership on ScotLIS. Geometry precedence: Spatial Hub survey, "
            "then RoS title outline, then point."
        ),
    }


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport VDL as Data Zone totals (count and area). No site geometry."""
    cap = max(1, min(int(max_features), MAX_FEATURES))
    envelope = f"{west},{south},{east},{north}"
    params = {
        "geometry": envelope,
        "geometryType": "esriGeometryEnvelope",
        "inSR": IN_SR,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": OUT_SR,
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
    buckets: dict[tuple[str, int], dict[str, Any]] = {}
    unzoned = False
    for feat in features[:cap]:
        props = _site_props(dict(feat.get("properties") or {}))
        centroid = _feature_centroid(feat.get("geometry"))
        zone = zone_for_point(*centroid) if centroid is not None else None
        if zone is None:
            unzoned = True
            continue
        code, vintage = zone
        slot = buckets.setdefault(
            (code, vintage),
            {"site_count": 0, "area_ha": 0.0},
        )
        slot["site_count"] += 1
        if props["size_ha"] is not None:
            slot["area_ha"] += float(props["size_ha"])
    data_zones = [
        {
            "data_zone": code,
            "vintage": vintage,
            "site_count": slot["site_count"],
            "area_ha": round(slot["area_ha"], 2),
        }
        for (code, vintage), slot in sorted(buckets.items())
    ]
    gaps = [
        "Sites removed or re-coded since the Spatial Hub vintage may differ "
        "from the latest SG site register",
        "RoS title-outline geometry stays internal until OS/RoS end-user "
        "terms are cleared for public publication",
        "Published here as Data Zone totals only (count and area)",
    ]
    if unzoned:
        gaps.append(
            "Sites that could not be placed in a Data Zone are omitted"
        )
    return public_vdl_response(
        {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": True,
                "layer": "vdl",
                "capped": len(features) >= cap,
                "source": ATTRIBUTION,
                "register_url": REGISTER_URL,
                "spatial_hub_url": SPATIAL_HUB_URL,
                "publication_url": PUBLICATION_URL,
                "licence": "OGL-3.0",
                "site_types": list(SITE_TYPES),
                "gaps": gaps,
                "data_zones": data_zones,
            },
        }
    )
