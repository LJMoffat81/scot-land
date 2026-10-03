"""Allowlisted context layers for the valuation map.

These layers can later take a weight. This module does not score them and
does not change a parcel rent. The proxy is not open: only the ids below
are fetched, and only from the hosts named here.

Left out on purpose:
- James Hutton land capability (all rights reserved).
- Ordnance Survey Open Zoomstack roads, rail, and airports. The data is
  Open Government Licence, but the only supply is a multi-gigabyte download
  and there is no public map service.
- Population and jobs by small area. Those are official tables, not a map
  service that can be drawn without a new join.
- Electricity wires, water mains, gas pipes, and broadband. No open national map.
- Spatial Hub renewable-energy polygons. The open cut does not carry
  technology and status. The fuller file is the premium copy. Solar, onshore
  wind, and hydro points come from the DESNZ planning database instead.
"""

from __future__ import annotations

import csv
import io
import math
import ssl
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx
from pyproj import Transformer

from spatial.parcels import TRANSPARENT_PNG, tile_bounds_3857

# Wider than the land envelope so the North Sea and the Scottish zone draw.
_CONTEXT = (54.0, -16.0, 64.5, 4.5)  # south, west, north, east
_MERC_EXTENT = 20037508.342789244

_ALLOWED_HOSTS = frozenset(
    {
        "msmap1.atkinsgeospatial.com",
        "map.sepa.org.uk",
        "maps.gov.scot",
        "services-eu1.arcgis.com",
        "services3.arcgis.com",
        "assets.publishing.service.gov.uk",
    }
)

_NSTA = (
    "Contains information provided by the North Sea Transition Authority "
    "and/or other third parties."
)
_SG = (
    "Contains information from the Scottish Government (Marine Scotland) "
    "licensed under the Open Government Licence v3.0."
)
_UKHO = (
    "Contains information from the United Kingdom Hydrographic Office and "
    "the Scottish Government (Marine Scotland), licensed under the "
    "Open Government Licence v3.0."
)
_CES = (
    "Contains information from Crown Estate Scotland licensed under the "
    "Open Government Licence v3.0."
)
_NSTA_FIELDS = (
    "https://services-eu1.arcgis.com/OZMfUznmLTnWccBc/arcgis/rest/services/"
    "Offshore_hydrocarbon_fields_(WGS84)/FeatureServer/0/query"
)
_NSTA_PLATFORMS = (
    "https://services-eu1.arcgis.com/OZMfUznmLTnWccBc/arcgis/rest/services/"
    "UKCS%20offshore%20infrastructure%20surface%20points%20WGS84/"
    "FeatureServer/1/query"
)
_NSTA_PIPES = (
    "https://services-eu1.arcgis.com/OZMfUznmLTnWccBc/arcgis/rest/services/"
    "UKCS%20offshore%20infrastructure%20pipeline%20linear%20ETRS89/"
    "FeatureServer/1/query"
)
_CES_ROOT = "https://services3.arcgis.com/nGV4jiurzcahJ9LV/ArcGIS/rest/services"
_REPD_URL = (
    "https://assets.publishing.service.gov.uk/media/"
    "6a6cbdc00c36759b5ccaa305/REPD_Publication_Q2_2026.csv"
)

_KEEP = frozenset(
    {
        "fieldname",
        "fieldtype",
        "status",
        "name",
        "inftype",
        "pipename",
        "fluid",
        "description",
        "tenant",
        "agreementtype",
        "projectphase",
        "sitename",
        "technologytype",
        "developmentstatusshort",
    }
)

_http_client: httpx.Client | None = None
_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()
_oid_fields: dict[str, str] = {}
_oid_lock = threading.Lock()
_bng_to_wgs = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
# The marine WMS sends only its leaf. This public Sectigo intermediate
# completes the chain to a root already in the default store.
_EXTRA_CA = (
    Path(__file__).resolve().parent.parent
    / "certs"
    / "sectigo-public-server-auth-ca-dv-r36.pem"
)


@dataclass(frozen=True)
class RasterSpec:
    layer_id: str
    kind: str  # wms | export
    url: str
    layers: str
    min_zoom: int
    max_zoom: int


@dataclass(frozen=True)
class FeatureSpec:
    layer_id: str
    kind: str  # arcgis | repd | wave-tidal
    url: str
    where: str
    attribution: str


RASTER: dict[str, RasterSpec] = {
    "sea-12nm": RasterSpec(
        "sea-12nm",
        "wms",
        "https://msmap1.atkinsgeospatial.com/geoserver/nmp/wms",
        "nmp:New_12_Nautical_Mile_Limit",
        3,
        18,
    ),
    "marine-regions": RasterSpec(
        "marine-regions",
        "wms",
        "https://msmap1.atkinsgeospatial.com/geoserver/nmp/wms",
        "nmp:Scottish_Marine_Regions",
        3,
        18,
    ),
    "scottish-zone": RasterSpec(
        "scottish-zone",
        "wms",
        "https://msmap1.atkinsgeospatial.com/geoserver/nmp/wms",
        "nmp:EEZ",
        3,
        18,
    ),
    "harbours": RasterSpec(
        "harbours",
        "wms",
        "https://msmap1.atkinsgeospatial.com/geoserver/nmp/wms",
        "nmp:port_limits",
        7,
        18,
    ),
    "wind-plan": RasterSpec(
        "wind-plan",
        "wms",
        "https://msmap1.atkinsgeospatial.com/geoserver/nmp/wms",
        "nmp:smp_offshore_wind_energy_plan_options_2020",
        4,
        18,
    ),
    "settlements": RasterSpec(
        "settlements",
        "export",
        "https://maps.gov.scot/server/rest/services/NRS/Census2022/MapServer/export",
        "8",
        6,
        18,
    ),
    "flood": RasterSpec(
        "flood",
        "export",
        "https://map.sepa.org.uk/server/rest/services/Open/Flood_Maps/MapServer/export",
        "1,7",
        8,
        18,
    ),
}

FEATURES: dict[str, FeatureSpec] = {
    "oil-fields": FeatureSpec("oil-fields", "arcgis", _NSTA_FIELDS, "1=1", _NSTA),
    "platforms": FeatureSpec(
        "platforms", "arcgis", _NSTA_PLATFORMS, "CURR_ROW='Y'", _NSTA
    ),
    "pipelines": FeatureSpec(
        "pipelines", "arcgis", _NSTA_PIPES, "CURR_ROW='Y'", _NSTA
    ),
    "wind-leases": FeatureSpec(
        "wind-leases",
        "arcgis",
        f"{_CES_ROOT}/Offshore_Wind_Crown_Estate_Scotland/FeatureServer/0/query",
        "1=1",
        _CES,
    ),
    "wave-tidal": FeatureSpec("wave-tidal", "wave-tidal", _CES_ROOT, "1=1", _CES),
    "renewables": FeatureSpec("renewables", "repd", _REPD_URL, "1=1", ""),
}


def _ssl_context() -> ssl.SSLContext:
    """Check certificates. Add the marine host's missing intermediate."""
    ctx = ssl.create_default_context()
    if _EXTRA_CA.is_file():
        ctx.load_verify_locations(cafile=str(_EXTRA_CA))
    return ctx


def _http() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(
            timeout=httpx.Timeout(40.0, connect=5.0),
            follow_redirects=True,
            verify=_ssl_context(),
            headers={"User-Agent": "scot-land/0.9 (https://scot-land.scot; context layers)"},
        )
    return _http_client


def _host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in _ALLOWED_HOSTS


def tile_intersects_context(z: int, x: int, y: int) -> bool:
    try:
        minx, miny, maxx, maxy = tile_bounds_3857(z, x, y)

        def lon(mx: float) -> float:
            return mx / _MERC_EXTENT * 180.0

        def lat(my: float) -> float:
            t = max(-1.0 + 1e-12, min(1.0 - 1e-12, my / _MERC_EXTENT))
            return math.degrees(math.atan(math.sinh(t * math.pi)))

        west, east = lon(minx), lon(maxx)
        south, north = lat(miny), lat(maxy)
        box_s, box_w, box_n, box_e = _CONTEXT
        return not (east < box_w or west > box_e or north < box_s or south > box_n)
    except (OverflowError, ValueError, ZeroDivisionError):
        return False


def fetch_context_tile(layer_id: str, z: int, x: int, y: int) -> bytes:
    """XYZ PNG for one allowlisted raster layer. Never raises."""
    spec = RASTER.get(layer_id)
    try:
        if spec is None or not _host_allowed(spec.url):
            return TRANSPARENT_PNG
        if z < spec.min_zoom or z > spec.max_zoom:
            return TRANSPARENT_PNG
        n = 2**z
        if x < 0 or y < 0 or x >= n or y >= n:
            return TRANSPARENT_PNG
        if not tile_intersects_context(z, x, y):
            return TRANSPARENT_PNG
        minx, miny, maxx, maxy = tile_bounds_3857(z, x, y)
        if spec.kind == "wms":
            params = {
                "SERVICE": "WMS",
                "VERSION": "1.1.1",
                "REQUEST": "GetMap",
                "LAYERS": spec.layers,
                "STYLES": "",
                "SRS": "EPSG:3857",
                "BBOX": f"{minx},{miny},{maxx},{maxy}",
                "WIDTH": "256",
                "HEIGHT": "256",
                "FORMAT": "image/png",
                "TRANSPARENT": "true",
            }
            response = _http().get(spec.url, params=params)
        else:
            params = {
                "bbox": f"{minx},{miny},{maxx},{maxy}",
                "bboxSR": "3857",
                "imageSR": "3857",
                "size": "256,256",
                "format": "png32",
                "transparent": "true",
                "layers": f"show:{spec.layers}",
                "f": "image",
            }
            response = _http().get(spec.url, params=params)
        if response.status_code != 200:
            return TRANSPARENT_PNG
        content = response.content
        if not content.startswith(b"\x89PNG"):
            return TRANSPARENT_PNG
        return content
    except Exception:
        return TRANSPARENT_PNG


def _empty(layer_id: str, ok: bool, note: str = "") -> dict:
    meta = {"layer": layer_id, "ok": ok, "count": 0}
    if note:
        meta["note"] = note
    return {"type": "FeatureCollection", "features": [], "meta": meta}


def _slim(props: dict, extra: dict | None = None) -> dict:
    out: dict = {}
    for key, value in (props or {}).items():
        if value in (None, ""):
            continue
        norm = "".join(ch for ch in str(key).lower() if ch.isalnum())
        if norm in _KEEP or norm.startswith("capacity"):
            out[str(key)] = value
    if extra:
        out.update(extra)
    return out


def _layer_root(query_url: str) -> str:
    root = query_url.split("?", 1)[0]
    if root.endswith("/query"):
        root = root[: -len("/query")]
    return root


def _object_id_field(query_url: str) -> str | None:
    """The service's own id field. Crown Estate wind uses OBJECTID_1."""
    root = _layer_root(query_url)
    with _oid_lock:
        cached = _oid_fields.get(root)
    if cached:
        return cached
    if not _host_allowed(root):
        return None
    try:
        response = _http().get(root, params={"f": "json"})
        if response.status_code != 200:
            return None
        name = response.json().get("objectIdField")
    except Exception:
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    field = name.strip()
    with _oid_lock:
        _oid_fields[root] = field
    return field


def _has_more(payload: dict, batch: list) -> bool:
    props = payload.get("properties") or {}
    exceeded = False
    if isinstance(props, dict) and props.get("exceededTransferLimit"):
        exceeded = True
    if payload.get("exceededTransferLimit"):
        exceeded = True
    return exceeded or len(batch) >= 1000


def _arcgis_features(url: str, where: str, extra: dict | None = None) -> list[dict]:
    if not _host_allowed(url):
        return []
    oid = _object_id_field(url)
    features: list[dict] = []
    offset = 0
    while offset <= 20000:
        params = {
            "where": where,
            "outFields": "*",
            "outSR": "4326",
            "f": "geojson",
            "resultRecordCount": "1000",
            "geometryPrecision": "5",
        }
        if oid:
            params["orderByFields"] = oid
            params["resultOffset"] = str(offset)
        response = _http().get(url, params=params)
        if response.status_code != 200:
            raise RuntimeError(f"feature service {response.status_code}")
        payload = response.json()
        batch = payload.get("features") or []
        if payload.get("error") and not batch:
            raise RuntimeError("feature service error")
        for feature in batch:
            geom = feature.get("geometry")
            if not geom:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": _slim(feature.get("properties") or {}, extra),
                }
            )
        if not oid:
            if _has_more(payload, batch):
                raise RuntimeError("feature service page incomplete")
            break
        if not _has_more(payload, batch):
            break
        if not batch:
            break
        offset += len(batch)
    return features


def _repd_features(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    features: list[dict] = []
    for row in reader:
        country = (row.get("Country") or "").strip().lower()
        if country != "scotland":
            continue
        tech = (row.get("Technology Type") or "").strip()
        tech_l = tech.lower()
        if "offshore" in tech_l:
            continue
        if not ("solar" in tech_l or "onshore" in tech_l or "hydro" in tech_l):
            continue
        status = (row.get("Development Status (short)") or "").strip()
        if status.lower() not in {"operational", "under construction"}:
            continue
        try:
            easting = float(row.get("X-coordinate") or "")
            northing = float(row.get("Y-coordinate") or "")
        except ValueError:
            continue
        if easting < 1000 or northing < 1000:
            continue
        lon, lat = _bng_to_wgs.transform(easting, northing)
        if not (-16 <= lon <= 4.5 and 54 <= lat <= 64.5):
            continue
        capacity = (row.get("Installed Capacity (MWelec)") or "").strip()
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                "properties": {
                    "site": (row.get("Site Name") or "").strip(),
                    "technology": tech,
                    "status": status,
                    "capacity_mw": capacity,
                },
            }
        )
    return features


def fetch_context_geojson(layer_id: str) -> dict:
    """GeoJSON for one allowlisted feature layer. Never raises."""
    spec = FEATURES.get(layer_id)
    if spec is None:
        return _empty(layer_id, False, "unknown layer")
    with _cache_lock:
        cached = _cache.get(layer_id)
    if cached is not None:
        return cached
    try:
        if spec.kind == "arcgis":
            features = _arcgis_features(spec.url, spec.where)
        elif spec.kind == "wave-tidal":
            features = []
            for name, kind in (
                ("Wave_Crown_Estate_Scotland", "wave"),
                ("Tidal_Crown_Estate_Scotland", "tidal"),
            ):
                url = f"{spec.url}/{name}/FeatureServer/0/query"
                features.extend(_arcgis_features(url, "1=1", {"kind": kind}))
        elif spec.kind == "repd":
            if not _host_allowed(spec.url):
                return _empty(layer_id, False, "host not allowed")
            response = _http().get(spec.url)
            if response.status_code != 200:
                return _empty(layer_id, False, "renewable database did not load")
            features = _repd_features(response.text)
        else:
            return _empty(layer_id, False, "unknown kind")
        geo = {
            "type": "FeatureCollection",
            "features": features,
            "meta": {"layer": layer_id, "ok": True, "count": len(features)},
        }
    except Exception:
        return _empty(layer_id, False, "layer did not load")
    with _cache_lock:
        _cache[layer_id] = geo
    return geo


def raster_request_url(layer_id: str, z: int, x: int, y: int) -> str | None:
    """Allowlisted GetMap or export URL, for tests. None when the tile is skipped."""
    spec = RASTER.get(layer_id)
    if spec is None or not _host_allowed(spec.url):
        return None
    if z < spec.min_zoom or z > spec.max_zoom or not tile_intersects_context(z, x, y):
        return None
    minx, miny, maxx, maxy = tile_bounds_3857(z, x, y)
    if spec.kind == "wms":
        params = {
            "SERVICE": "WMS",
            "LAYERS": spec.layers,
            "SRS": "EPSG:3857",
            "BBOX": f"{minx},{miny},{maxx},{maxy}",
        }
    else:
        params = {
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "layers": f"show:{spec.layers}",
            "f": "image",
        }
    return f"{spec.url}?{urlencode(params)}"
