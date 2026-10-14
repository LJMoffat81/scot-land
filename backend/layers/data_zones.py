"""Data Zone boundary overlay — PostGIS first, ArcGIS fallback.

Viewport GeoJSON for the map (simplified by bbox). Boundaries + useful
per-zone rollups from ``datazones.zone_spine`` (population, dwellings,
council). **No AGR £ / Surface Rent** on this layer.

PostGIS ``dz_boundaries`` is the Georgist/Valuation source of truth when
loaded via ``etl.load_processed``. The ArcGIS MapServer path is a live
fallback for display when the DB is empty or unavailable — never invents
geometry.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from georgist import db

logger = logging.getLogger(__name__)

# Layer 10 = DataZoneBdry2022 on ScotGov/StatisticalUnits (display fallback).
# Layer 2 remains available when vintage=2011 is requested explicitly.
FEATURE_URL_BY_VINTAGE = {
    2022: (
        "https://maps.gov.scot/server/rest/services/ScotGov/"
        "StatisticalUnits/MapServer/10/query"
    ),
    2011: (
        "https://maps.gov.scot/server/rest/services/ScotGov/"
        "StatisticalUnits/MapServer/2/query"
    ),
}
FEATURE_URL = FEATURE_URL_BY_VINTAGE[2022]
TIMEOUT = 12.0
MAX_FEATURES = 120
# 2022 fields are dzcode/dzname; 2011 fields are datazone/name.
OUT_FIELDS_BY_VINTAGE = {
    2022: "dzcode,dzname",
    2011: "datazone,name",
}
OUT_FIELDS = OUT_FIELDS_BY_VINTAGE[2022]
DEFAULT_VINTAGE = 2022

# Official geometry metadata (SG Data Zone boundaries 2022 by default).
SOURCE_PAGE = (
    "https://www.spatialdata.gov.scot/geonetwork/srv/eng/catalog.search"
    "#/metadata/7d564e13-a967-495a-ae2f-048ffdfa4b03"
)
OGL_V3_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)
LICENCE = "Open Government Licence v3.0"
ATTRIBUTION = (
    "Scottish Government Data Zone boundaries 2022. "
    "Contains Ordnance Survey data © Crown copyright and database right. "
    "Licensed under the Open Government Licence v3.0. "
    "Outlines and open rollups only — not a rent."
)

# PostGIS simplify tolerance (metres, EPSG:27700) from bbox span.
_PG_BBOX = """
SELECT
  b.code,
  b.vintage,
  COALESCE(b.name, s.name) AS name,
  s.la_code,
  s.la_name,
  s.population,
  s.pop_year,
  s.dwellings,
  s.dw_year,
  s.households,
  s.hh_year,
  ST_AsGeoJSON(
    ST_Transform(
      ST_SimplifyPreserveTopology(b.geom, %s),
      4326
    ),
    5
  ) AS geometry
FROM dz_boundaries b
LEFT JOIN datazones.zone_spine s
  ON s.code = b.code AND s.vintage = b.vintage
WHERE b.vintage = %s
  AND ST_Intersects(
    b.geom,
    ST_Transform(
      ST_MakeEnvelope(%s, %s, %s, %s, 4326),
      27700
    )
  )
ORDER BY b.code
LIMIT %s
"""

_PG_HAS_VINTAGE = """
SELECT EXISTS (
  SELECT 1 FROM dz_boundaries WHERE vintage = %s LIMIT 1
)
"""


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT)


def _simplify_offset_deg(south: float, west: float, north: float, east: float) -> float:
    span = max(abs(north - south), abs(east - west))
    return max(span / 400.0, 0.00012)


def _simplify_tolerance_m(south: float, west: float, north: float, east: float) -> float:
    """Rough metres from WGS84 span (Scotland latitudes)."""
    span_deg = max(abs(north - south), abs(east - west))
    # ~111 km per degree latitude; clamp for readability vs payload size.
    return max(min(span_deg * 111_000.0 / 400.0, 250.0), 8.0)


def _feature(
    *,
    code: str,
    name: str | None,
    vintage: int,
    geometry: Any,
    la_code: str | None = None,
    la_name: str | None = None,
    population: int | None = None,
    pop_year: int | None = None,
    dwellings: int | None = None,
    dw_year: int | None = None,
    households: int | None = None,
    hh_year: int | None = None,
) -> dict[str, Any]:
    props: dict[str, Any] = {
        "code": code,
        "name": name,
        "vintage": vintage,
        "layer": "data_zones",
        "source": ATTRIBUTION,
        "licence": LICENCE,
        "licence_url": OGL_V3_URL,
    }
    if la_code:
        props["la_code"] = la_code
    if la_name:
        props["la_name"] = la_name
    if population is not None:
        props["population"] = int(population)
        if pop_year is not None:
            props["pop_year"] = int(pop_year)
    if dwellings is not None:
        props["dwellings"] = int(dwellings)
        if dw_year is not None:
            props["dw_year"] = int(dw_year)
    if households is not None:
        props["households"] = int(households)
        if hh_year is not None:
            props["hh_year"] = int(hh_year)
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": props,
    }


def _meta(
    *,
    ok: bool,
    count: int = 0,
    capped: bool = False,
    source: str,
    vintage: int = DEFAULT_VINTAGE,
    error: str | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "ok": ok,
        "layer": "data_zones",
        "count": count,
        "capped": capped,
        "vintage": vintage,
        "serve": source,
        "source": ATTRIBUTION,
        "source_url": SOURCE_PAGE,
        "licence": LICENCE,
        "licence_url": OGL_V3_URL,
        "note": (
            "Boundaries and open rollups (population, dwellings, council) only. "
            "No Annual Ground Rent or Surface Rent figures."
        ),
    }
    if error:
        meta["error"] = error
    return meta


def query_bbox_postgis(
    south: float,
    west: float,
    north: float,
    east: float,
    *,
    vintage: int = DEFAULT_VINTAGE,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any] | None:
    """BBox from ``dz_boundaries`` + spine rollups, or None if DB unusable/empty."""
    if not db.database_configured():
        return None
    cap = max(1, min(int(max_features), MAX_FEATURES))
    tol = _simplify_tolerance_m(south, west, north, east)
    try:
        with db.cursor() as cur:
            cur.execute(_PG_HAS_VINTAGE, (vintage,))
            row = cur.fetchone()
            has = bool(row["exists"] if isinstance(row, dict) else row[0])
            if not has:
                return None
            cur.execute(
                _PG_BBOX,
                (tol, vintage, west, south, east, north, cap),
            )
            rows = cur.fetchall()
    except db.DatabaseUnavailable as exc:
        logger.info("dz_boundaries bbox unavailable: %s", exc.reason)
        return None

    features = []
    for r in rows:
        geom_raw = r["geometry"]
        if not geom_raw:
            continue
        geometry = json.loads(geom_raw) if isinstance(geom_raw, str) else geom_raw
        features.append(
            _feature(
                code=str(r["code"]).strip(),
                name=(str(r["name"]).strip() if r.get("name") else None),
                vintage=int(r["vintage"]),
                geometry=geometry,
                la_code=r.get("la_code"),
                la_name=r.get("la_name"),
                population=r.get("population"),
                pop_year=r.get("pop_year"),
                dwellings=r.get("dwellings"),
                dw_year=r.get("dw_year"),
                households=r.get("households"),
                hh_year=r.get("hh_year"),
            )
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": _meta(
            ok=True,
            count=len(features),
            capped=len(features) >= cap,
            source="postgis:dz_boundaries",
            vintage=vintage,
        ),
    }


def query_bbox_arcgis(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
    vintage: int = DEFAULT_VINTAGE,
) -> dict[str, Any]:
    """Viewport from SG StatisticalUnits MapServer (display fallback)."""
    vin = 2022 if int(vintage) != 2011 else 2011
    cap = max(1, min(int(max_features), MAX_FEATURES))
    envelope = f"{west},{south},{east},{north}"
    code_field = "dzcode" if vin == 2022 else "datazone"
    name_field = "dzname" if vin == 2022 else "name"
    params = {
        "geometry": envelope,
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": OUT_FIELDS_BY_VINTAGE[vin],
        "returnGeometry": "true",
        "outSR": 4326,
        "resultRecordCount": cap,
        "orderByFields": f"{code_field} ASC",
        "maxAllowableOffset": _simplify_offset_deg(south, west, north, east),
        "f": "geojson",
    }
    try:
        with _client() as client:
            response = client.get(FEATURE_URL_BY_VINTAGE[vin], params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": _meta(
                ok=False,
                source="arcgis:StatisticalUnits",
                vintage=vin,
                error=str(exc),
            ),
        }

    if payload.get("type") != "FeatureCollection":
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": _meta(
                ok=False,
                source="arcgis:StatisticalUnits",
                vintage=vin,
                error="Unexpected data-zone response",
            ),
        }

    features = []
    for feat in (payload.get("features") or [])[:cap]:
        props = dict(feat.get("properties") or {})
        code = str(props.get(code_field) or props.get("datazone") or "").strip()
        name = (
            str(props.get(name_field) or props.get("name") or "").strip() or None
        )
        if not code:
            continue
        features.append(
            _feature(
                code=code,
                name=name,
                vintage=vin,
                geometry=feat.get("geometry"),
            )
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": _meta(
            ok=True,
            count=len(features),
            capped=len(features) >= cap
            or bool(payload.get("exceededTransferLimit")),
            source="arcgis:StatisticalUnits",
            vintage=vin,
        ),
    }


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
    vintage: int = DEFAULT_VINTAGE,
) -> dict[str, Any]:
    """Viewport data-zone polygons as GeoJSON (WGS84). PostGIS preferred."""
    postgis = query_bbox_postgis(
        south,
        west,
        north,
        east,
        vintage=vintage,
        max_features=max_features,
    )
    if postgis is not None:
        return postgis
    return query_bbox_arcgis(
        south, west, north, east, max_features=max_features, vintage=vintage
    )
