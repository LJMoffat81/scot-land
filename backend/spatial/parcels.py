from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx
import yaml
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"

# 1×1 transparent PNG — empty tile when WMS fails or tile is out of range
TRANSPARENT_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)

# Web Mercator half-world extent (EPSG:3857)
_MERC_EXTENT = 20037508.342789244

# Rough Scotland envelope in WGS84 — skip external WMS for distant tiles
_SCOTLAND = (54.5, -9.0, 61.0, -0.5)  # south, west, north, east

_http_client: httpx.Client | None = None


@dataclass(frozen=True)
class CadastralParcel:
    inspire_id: str
    label: str
    national_reference: str
    area_sqm: float
    county: str | None
    geometry: dict | None = None


@lru_cache(maxsize=1)
def _parcel_cfg() -> dict:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle)
    return sources["parcels"]


def _http() -> httpx.Client:
    """Shared client so concurrent tile requests reuse connections."""
    global _http_client
    if _http_client is None:
        timeout_s = float(_parcel_cfg().get("timeout_seconds", 8.0))
        _http_client = httpx.Client(
            timeout=httpx.Timeout(timeout_s, connect=3.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            headers={"User-Agent": "scot-land/0.8 (research; parcel tiles)"},
        )
    return _http_client


def _compute_area_sqm(geometry: dict) -> float:
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    project = lambda x, y, z=None: transformer.transform(x, y)
    projected = transform(project, shape(geometry))
    return round(float(projected.area), 2)


def _parcel_from_feature(feature: dict) -> CadastralParcel | None:
    props = feature.get("properties") or {}
    geometry = feature.get("geometry")
    if not geometry:
        return None
    return CadastralParcel(
        inspire_id=str(props.get("inspireid") or feature.get("id") or ""),
        label=str(props.get("label") or ""),
        national_reference=str(props.get("nationalcadastralreference") or ""),
        area_sqm=_compute_area_sqm(geometry),
        county=props.get("county"),
        geometry=geometry,
    )


@lru_cache(maxsize=512)
def _feature_at(lat_key: float, lng_key: float) -> tuple | None:
    """Cached GetFeatureInfo; keys rounded to ~1 m (6 dp)."""
    lat, lng = lat_key, lng_key
    cfg = _parcel_cfg()
    delta = cfg["query_delta_degrees"]
    bbox = f"{lat - delta},{lng - delta},{lat + delta},{lng + delta}"

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

    try:
        response = _http().get(cfg["wms_url"], params=params)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return None

    features = payload.get("features") or []
    if not features:
        return None
    return (features[0],)


def lookup_parcel(lat: float, lng: float) -> CadastralParcel | None:
    """Query ROS INSPIRE cadastral parcels via free WMS GetFeatureInfo."""
    packed = _feature_at(round(lat, 6), round(lng, 6))
    if not packed:
        return None
    return _parcel_from_feature(packed[0])


def _point_for_label(payload: dict, label: str) -> dict | None:
    """One parcel point, and only when the title label is the one asked for."""
    features = payload.get("features") or []
    if len(features) != 1 or not isinstance(features[0], dict):
        return None
    feature = features[0]
    props = feature.get("properties") or {}
    found = str(props.get("nationalcadastralreference") or props.get("label") or "")
    if found.upper() != label.upper():
        return None
    point = props.get("point_geom") if isinstance(props.get("point_geom"), dict) else {}
    coords = point.get("coordinates") if isinstance(point, dict) else None
    geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else {}
    if not coords and geometry.get("type") == "Point":
        coords = geometry.get("coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        lng, lat = float(coords[0]), float(coords[1])
        return {"lat": round(lat, 6), "lng": round(lng, 6), "label": label}
    if geometry.get("type") in ("Polygon", "MultiPolygon"):
        centre = shape(geometry).centroid
        return {"lat": round(float(centre.y), 6), "lng": round(float(centre.x), 6), "label": label}
    return None


def lookup_parcel_by_title(label: str) -> dict | None:
    """Ask the published parcel service for one title label.

    The view service rejects a feature filter, so this returns nothing rather
    than scanning Scotland. A matching feature is accepted only when its own
    title label is the one requested.
    """
    cfg = _parcel_cfg()
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": cfg["wms_layer"],
        "count": "1",
        "outputFormat": "application/json",
        "CQL_FILTER": f"nationalcadastralreference='{label}'",
    }
    try:
        response = _http().get(cfg["wms_url"], params=params)
        if response.status_code != 200:
            return None
        return _point_for_label(response.json(), label)
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return None


def lookup_parcel_geojson(lat: float, lng: float) -> dict | None:
    """Single-parcel GeoJSON Feature for map highlight."""
    parcel = lookup_parcel(lat, lng)
    if parcel is None or not parcel.geometry:
        return None
    return {
        "type": "Feature",
        "geometry": parcel.geometry,
        "properties": {
            "inspire_id": parcel.inspire_id,
            "label": parcel.label,
            "national_reference": parcel.national_reference,
            "area_sqm": parcel.area_sqm,
            "county": parcel.county,
            "source": "ROS INSPIRE CP.CadastralParcel",
        },
    }


def tile_bounds_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Web Mercator bbox for XYZ tile (minx, miny, maxx, maxy)."""
    n = 2**z
    res = (2 * _MERC_EXTENT) / n
    minx = -_MERC_EXTENT + x * res
    maxx = -_MERC_EXTENT + (x + 1) * res
    maxy = _MERC_EXTENT - y * res
    miny = _MERC_EXTENT - (y + 1) * res
    return minx, miny, maxx, maxy


def tile_intersects_scotland(z: int, x: int, y: int) -> bool:
    """Cheap reject for tiles well outside Scotland (WGS84 envelope)."""
    try:
        minx, miny, maxx, maxy = tile_bounds_3857(z, x, y)

        def lon(mx: float) -> float:
            return mx / _MERC_EXTENT * 180.0

        def lat(my: float) -> float:
            # Clamp to avoid sinh overflow near poles
            t = max(-1.0 + 1e-12, min(1.0 - 1e-12, my / _MERC_EXTENT))
            return math.degrees(math.atan(math.sinh(t * math.pi)))

        west, east = lon(minx), lon(maxx)
        south, north = lat(miny), lat(maxy)
        s, w, n, e = _SCOTLAND
        return not (east < w or west > e or north < s or south > n)
    except (OverflowError, ValueError, ZeroDivisionError):
        return False


def fetch_parcel_tile_png(z: int, x: int, y: int) -> bytes:
    """
    Proxy ROS INSPIRE WMS GetMap as a MapLibre XYZ PNG tile.
    Always returns PNG bytes — never raises (map tiles must not 500).
    """
    try:
        if z < 12 or z > 19:
            return TRANSPARENT_PNG
        n = 2**z
        if x < 0 or y < 0 or x >= n or y >= n:
            return TRANSPARENT_PNG
        if not tile_intersects_scotland(z, x, y):
            return TRANSPARENT_PNG

        cfg = _parcel_cfg()
        minx, miny, maxx, maxy = tile_bounds_3857(z, x, y)
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetMap",
            "LAYERS": cfg["wms_layer"],
            "STYLES": "",
            "SRS": "EPSG:3857",
            "BBOX": f"{minx},{miny},{maxx},{maxy}",
            "WIDTH": "256",
            "HEIGHT": "256",
            "FORMAT": "image/png",
            "TRANSPARENT": "true",
        }
        response = _http().get(cfg["wms_url"], params=params)
        if response.status_code != 200:
            return TRANSPARENT_PNG
        content = response.content
        if not content.startswith(b"\x89PNG"):
            return TRANSPARENT_PNG
        return content
    except Exception:
        return TRANSPARENT_PNG
