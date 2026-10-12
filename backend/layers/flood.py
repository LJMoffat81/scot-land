"""SEPA Flood Maps overlay (OGL-3.0).

Present-day medium-likelihood river and coastal flood extents (200-year).
Map paint prefers raster tiles via ``/layers/context/flood/tiles/...``.
BBox GeoJSON prefers local PostGIS ingest; falls back to a capped live
MapServer query when the table is empty. Never invents extents.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
import psycopg2
from psycopg2 import extras

logger = logging.getLogger(__name__)

TABLE = "sepa_flood"
TIMEOUT = 10.0
MAX_FEATURES = 80
OUT_SR = 4326
IN_SR = 4326

MAPSERVER = "https://map.sepa.org.uk/server/rest/services/Open/Flood_Maps/MapServer"
# Medium likelihood (200-year): river=1, coastal=7 — matches context tile layers.
LIVE_LAYER_IDS = (1, 7)
LAYER_SOURCE = {1: "River", 7: "Coastal", 4: "Surface Water"}

DOWNLOAD_URL = "https://www2.sepa.org.uk/flooddata/"
MAPSERVER_URL = MAPSERVER
ATTRIBUTION_PDF = (
    "https://www.sepa.org.uk/media/5zidnja5/sepa_flood_maps_data_attribution_statements.pdf"
)
LICENCE = "OGL-3.0"
ATTRIBUTION = (
    "© SEPA 2025; this SEPA product is licensed under the Open Government Licence v3.0. "
    "Flood Maps v3.0 — medium-likelihood river and coastal extents (present day). "
    "Indicative hazard extents, not a flood insurance quote or title."
)
TILE_ENDPOINT = "/layers/context/flood/tiles/{z}/{x}/{y}"
BBOX_ENDPOINT = "/layers/open/flood"
MINZOOM = 8


def _db_config() -> dict[str, Any]:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        return {"dsn": url}
    return {
        "dbname": os.getenv("WEALTH_DB_NAME", "scotland_wealth"),
        "user": os.getenv("WEALTH_DB_USER", "wealth_user"),
        "password": os.getenv("WEALTH_DB_PASSWORD", ""),
        "host": os.getenv("WEALTH_DB_HOST", "localhost"),
        "port": os.getenv("WEALTH_DB_PORT", "5432"),
    }


def _connect():
    cfg = _db_config()
    if "dsn" in cfg:
        return psycopg2.connect(cfg["dsn"])
    return psycopg2.connect(**cfg)


def is_loaded() -> bool:
    """True when PostGIS has at least one SEPA flood row."""
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("SEPA flood PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (f"public.{TABLE}",),
            )
            if not cur.fetchone()[0]:
                return False
            cur.execute(f"SELECT 1 FROM {TABLE} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("SEPA flood load check failed: %s", exc)
        return False
    finally:
        conn.close()


def catalog_layer() -> dict[str, Any]:
    return {
        "id": "flood",
        "group": "spatial",
        "status": "live",
        "label": "SEPA flood extent",
        "description": (
            "Medium-likelihood (200-year) river and coastal flood extents, "
            "SEPA Flood Maps v3.0 present-day. Raster tiles for the map; "
            "bbox GeoJSON from PostGIS when ingested, else a capped live query."
        ),
        "endpoint": BBOX_ENDPOINT,
        "tile_endpoint": TILE_ENDPOINT,
        "licence": LICENCE,
        "minzoom": MINZOOM,
        "source_url": DOWNLOAD_URL,
        "mapserver_url": MAPSERVER_URL,
        "attribution_url": ATTRIBUTION_PDF,
        "gaps": [
            "Surface-water and climate-change scenarios are on the MapServer but "
            "not in the default public toggle (medium river + coastal only).",
            "Extents are indicative hazard maps — not a property-level flood quote.",
        ],
    }


def _feature_props(attrs: dict[str, Any], layer_id: int) -> dict[str, Any]:
    source = attrs.get("SOURCE") or LAYER_SOURCE.get(layer_id) or "Unknown"
    return {
        "object_id": attrs.get("OBJECTID"),
        "layer_id": layer_id,
        "source": source,
        "probability": attrs.get("PROB") or "M",
        "scenario": attrs.get("SCENARIO") or "Present Day",
        "map_type": attrs.get("MAP_TYPE"),
        "reference": attrs.get("REFERENCE"),
        "version": attrs.get("VERSION"),
        "layer": "flood",
        "source_label": ATTRIBUTION,
        "licence": LICENCE,
    }


def _query_postgis(
    south: float,
    west: float,
    north: float,
    east: float,
    *,
    max_features: int,
) -> dict[str, Any] | None:
    if not is_loaded():
        return None
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("SEPA flood PostGIS connect failed: %s", exc)
        return None
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT object_id, layer_id, source, probability, scenario,
                       map_type, reference, version,
                       ST_AsGeoJSON(geom)::json AS geometry
                FROM {TABLE}
                WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                  AND ST_Intersects(
                        geom,
                        ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                  )
                ORDER BY ST_Area(geom) DESC
                LIMIT %s
                """,
                (west, south, east, north, west, south, east, north, max_features),
            )
            rows = cur.fetchall()
    except Exception as exc:
        logger.info("SEPA flood PostGIS query failed: %s", exc)
        return None
    finally:
        conn.close()

    features = []
    for row in rows:
        props = {
            "object_id": row["object_id"],
            "layer_id": row["layer_id"],
            "source": row["source"],
            "probability": row["probability"],
            "scenario": row["scenario"],
            "map_type": row["map_type"],
            "reference": row["reference"],
            "version": row["version"],
            "layer": "flood",
            "source_label": ATTRIBUTION,
            "licence": LICENCE,
            "geometry_source": "postgis",
        }
        features.append(
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": props,
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "backend": "postgis",
            "count": len(features),
            "max_features": max_features,
            "licence": LICENCE,
            "source": ATTRIBUTION,
            "source_url": DOWNLOAD_URL,
            "tile_endpoint": TILE_ENDPOINT,
            "note": (
                "PostGIS ingest of SEPA Flood Maps v3.0 (medium river + coastal). "
                "Prefer raster tiles at zoom for performance."
            ),
        },
    }


def _query_live_layer(
    client: httpx.Client,
    layer_id: int,
    south: float,
    west: float,
    north: float,
    east: float,
    *,
    max_features: int,
) -> list[dict[str, Any]]:
    params = {
        "geometry": f"{west},{south},{east},{north}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": str(IN_SR),
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "OBJECTID,MAP_TYPE,SOURCE,PROB,SCENARIO,REFERENCE,VERSION",
        "returnGeometry": "true",
        "outSR": str(OUT_SR),
        "resultRecordCount": str(max_features),
        "f": "geojson",
    }
    response = client.get(f"{MAPSERVER}/{layer_id}/query", params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("SEPA flood response was not a JSON object")
    out: list[dict[str, Any]] = []
    for feat in payload.get("features") or []:
        if not isinstance(feat, dict) or not feat.get("geometry"):
            continue
        props = _feature_props(feat.get("properties") or {}, layer_id)
        props["geometry_source"] = "sepa_mapserver"
        out.append(
            {
                "type": "Feature",
                "geometry": feat["geometry"],
                "properties": props,
            }
        )
    return out


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    *,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Flood polygons in the viewport. PostGIS first; live MapServer fallback."""
    limit = max(1, min(int(max_features), MAX_FEATURES))
    if south >= north or west >= east:
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": "invalid bbox",
                "licence": LICENCE,
                "source": ATTRIBUTION,
            },
        }

    postgis = _query_postgis(south, west, north, east, max_features=limit)
    if postgis is not None:
        return postgis

    features: list[dict[str, Any]] = []
    per_layer = max(1, limit // len(LIVE_LAYER_IDS))
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            for layer_id in LIVE_LAYER_IDS:
                if len(features) >= limit:
                    break
                room = min(per_layer, limit - len(features))
                features.extend(
                    _query_live_layer(
                        client,
                        layer_id,
                        south,
                        west,
                        north,
                        east,
                        max_features=room,
                    )
                )
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": str(exc),
                "licence": LICENCE,
                "source": ATTRIBUTION,
                "source_url": DOWNLOAD_URL,
                "tile_endpoint": TILE_ENDPOINT,
            },
        }

    return {
        "type": "FeatureCollection",
        "features": features[:limit],
        "meta": {
            "ok": True,
            "backend": "sepa_mapserver",
            "count": len(features[:limit]),
            "max_features": limit,
            "licence": LICENCE,
            "source": ATTRIBUTION,
            "source_url": DOWNLOAD_URL,
            "tile_endpoint": TILE_ENDPOINT,
            "note": (
                "Live SEPA MapServer query (capped). Ingest to PostGIS for "
                "stable bbox; map paint should use raster tiles."
            ),
        },
    }
