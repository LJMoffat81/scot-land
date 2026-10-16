"""NatureScot SSSI and protected-area designations from local PostGIS.

Sources are NatureScot OGL-3.0 open downloads / WFS. Raw geometry stays under
data/external/naturescot/ (gitignored). BBox endpoints return 503 when tables
are missing or empty — never invent designations.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import os
import threading
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any

import psycopg2
import yaml
from psycopg2 import extras
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"

SSSI_TABLE = "naturescot_sssi"
DESIGNATIONS_TABLE = "naturescot_designations"
MAX_FEATURES = 80
# z6–z9 responses stay within 500 KB. Every zoom stays within 1 MB.
BUDGET_Z6_TO_Z9 = 500 * 1024
BUDGET_ANY_ZOOM = 1024 * 1024
COORD_DECIMALS = 5
# Repeat views at z6, z7, and z8 skip PostGIS. The first view fills the slot.
_LOW_ZOOM_CACHE_MIN = 6
_LOW_ZOOM_CACHE_MAX = 8
_LOW_ZOOM_CACHE_LIMIT = 64
_low_zoom_cache: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
_low_zoom_cache_lock = threading.Lock()

DESIGNATION_TYPES = ("spa", "sac", "nnr")

ATTRIBUTION = (
    "Contains NatureScot information licensed under the Open Government "
    "Licence v3.0. Protected-area boundaries are indicative — confirm legal "
    "status with NatureScot / ScotLIS as appropriate."
)


class LayerUnavailable(Exception):
    """Raised when NatureScot tables are not loaded or PostGIS is unreachable."""


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


@lru_cache(maxsize=1)
def _sources() -> dict[str, Any]:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def sssi_source_meta() -> dict[str, Any]:
    cfg = (_sources().get("naturescot_sssi") or {})
    return {
        "source": cfg.get("name") or "NatureScot Sites of Special Scientific Interest",
        "licence": cfg.get("licence") or "OGL-3.0",
        "attribution": cfg.get("attribution") or ATTRIBUTION,
        "source_url": cfg.get("source_url")
        or "https://opendata.nature.scot/maps/sites-of-special-scientific-interest",
        "download_url": cfg.get("download_url")
        or "https://gis-downloads.nature.scot/SSSI_SCOTLAND_GEOJSON_4326.zip",
        "vintage": cfg.get("vintage") or "see local ingest stamp",
        "gaps": cfg.get("gaps")
        or [
            "Indicative NatureScot boundaries — not a title plan",
            "Status and extent can change after the download vintage",
        ],
    }


def designations_source_meta() -> dict[str, Any]:
    cfg = (_sources().get("naturescot_designations") or {})
    return {
        "source": cfg.get("name")
        or "NatureScot designations (SPA, SAC, NNR)",
        "licence": cfg.get("licence") or "OGL-3.0",
        "attribution": cfg.get("attribution") or ATTRIBUTION,
        "source_url": cfg.get("source_url")
        or "https://opendata.nature.scot/",
        "designation_types": list(cfg.get("designation_types") or DESIGNATION_TYPES),
        "downloads": cfg.get("downloads")
        or {
            "spa": "https://gis-downloads.nature.scot/SPA_SCOTLAND_GEOJSON_4326.zip",
            "sac": "https://gis-downloads.nature.scot/SAC_SCOTLAND_GEOJSON_4326.zip",
            "nnr": "https://gis-downloads.nature.scot/NNR_SCOTLAND_GEOJSON_4326.zip",
        },
        "vintage": cfg.get("vintage") or "see local ingest stamp",
        "gaps": cfg.get("gaps")
        or [
            "Indicative NatureScot boundaries — not a title plan",
            "SSSI is a separate layer; this overlay is SPA / SAC / NNR",
            "Status and extent can change after the download vintage",
        ],
    }


def _table_loaded(table: str) -> bool:
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("NatureScot PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (f"public.{table}",),
            )
            exists = bool(cur.fetchone()[0])
            if not exists:
                return False
            cur.execute(f"SELECT 1 FROM {table} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("NatureScot load check failed (%s): %s", table, exc)
        return False
    finally:
        conn.close()


def sssi_is_loaded() -> bool:
    return _table_loaded(SSSI_TABLE)


def designations_is_loaded() -> bool:
    return _table_loaded(DESIGNATIONS_TABLE)


def require_sssi_loaded() -> None:
    if not sssi_is_loaded():
        raise LayerUnavailable(
            "SSSI designations are not available: naturescot_sssi is missing "
            "or empty. Ingest NatureScot SSSI "
            "(python -m etl.ingest_naturescot --layer sssi) before publishing."
        )


def zoom_for_view(
    south: float,
    west: float,
    north: float,
    east: float,
    zoom: float | None = None,
) -> float:
    """Use the caller zoom, or estimate it from the bbox span."""
    if zoom is not None:
        try:
            parsed = float(zoom)
        except (TypeError, ValueError):
            parsed = float("nan")
        if math.isfinite(parsed):
            return max(0.0, min(22.0, parsed))
    span = max(abs(float(north) - float(south)), abs(float(east) - float(west)), 1e-9)
    return max(0.0, min(22.0, math.log2(360.0 / span)))


def simplify_tolerance_m(zoom: float) -> float:
    """About two screen pixels in metres at 57°N for this Web Mercator zoom."""
    metres_per_pixel = (156543.03392804097 * math.cos(math.radians(57.0))) / (
        2.0 ** zoom
    )
    return max(metres_per_pixel * 2.0, 1.0)


# Python size-cap steps, coarsest last. Same metre function as the SQL simplify.
_CAP_TOLERANCE_ZOOMS = (18, 16, 14, 12, 10, 8, 6)
_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
_TO_WGS = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


def _low_zoom_cache_key(
    layer: str,
    south: float,
    west: float,
    north: float,
    east: float,
    cap: int,
    view_zoom: float,
) -> tuple | None:
    """Cache slot for a settled z6, z7, or z8 view. None outside that range."""
    if view_zoom < _LOW_ZOOM_CACHE_MIN or view_zoom >= _LOW_ZOOM_CACHE_MAX + 1:
        return None
    return (
        layer,
        round(view_zoom, 1),
        round(float(south), 2),
        round(float(west), 2),
        round(float(north), 2),
        round(float(east), 2),
        int(cap),
    )


def clear_low_zoom_cache() -> None:
    """Drop cached z6–z8 SSSI and designation responses."""
    with _low_zoom_cache_lock:
        _low_zoom_cache.clear()


def _cached_low_zoom(key: tuple | None, build) -> dict[str, Any]:
    if key is not None:
        with _low_zoom_cache_lock:
            hit = _low_zoom_cache.get(key)
            if hit is not None:
                _low_zoom_cache.move_to_end(key)
                return copy.deepcopy(hit)
    payload = build()
    if key is None:
        return payload
    with _low_zoom_cache_lock:
        _low_zoom_cache[key] = payload
        _low_zoom_cache.move_to_end(key)
        while len(_low_zoom_cache) > _LOW_ZOOM_CACHE_LIMIT:
            _low_zoom_cache.popitem(last=False)
    return copy.deepcopy(payload)


def payload_byte_budget(zoom: float) -> int:
    """500 KB at z6–z9 (and coarser). 1 MB at finer zooms."""
    if zoom <= 9.0:
        return BUDGET_Z6_TO_Z9
    return BUDGET_ANY_ZOOM


def dumps_feature_collection(payload: dict[str, Any]) -> bytes:
    """Compact JSON, matching the protected-site response body."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _round_coords(node: Any, digits: int = COORD_DECIMALS) -> Any:
    if isinstance(node, (list, tuple)):
        if (
            len(node) >= 2
            and isinstance(node[0], (int, float))
            and not isinstance(node[0], bool)
            and isinstance(node[1], (int, float))
            and not isinstance(node[1], bool)
        ):
            return [round(float(node[0]), digits), round(float(node[1]), digits)]
        return [_round_coords(item, digits) for item in node]
    return node


def _cap_tolerances_m() -> tuple[float, ...]:
    """Size-cap fallback steps in metres, matching ``simplify_tolerance_m``."""
    return (0.0, *(simplify_tolerance_m(zoom) for zoom in _CAP_TOLERANCE_ZOOMS))


def _as_rounded_geojson(geom) -> dict[str, Any] | None:
    if geom is None or geom.is_empty:
        return None
    mapped = mapping(geom)
    if "coordinates" in mapped:
        mapped["coordinates"] = _round_coords(mapped["coordinates"])
    return mapped


def _project(transformer: Transformer, geom):
    return shapely_transform(transformer.transform, geom)


def _geometry_under(geom: dict[str, Any] | None, tolerance_m: float) -> dict[str, Any] | None:
    """Simplify one WGS84 geometry. ``tolerance_m`` is metres in EPSG:27700."""
    if not geom:
        return None
    if tolerance_m <= 0:
        rounded = dict(geom)
        if "coordinates" in rounded:
            rounded["coordinates"] = _round_coords(rounded["coordinates"])
        return rounded
    try:
        parsed = shape(geom)
        if parsed.is_empty:
            return None
        projected = _project(_TO_BNG, parsed)
        simple = projected.simplify(tolerance_m, preserve_topology=True)
        if simple.is_empty:
            return None
        return _as_rounded_geojson(_project(_TO_WGS, simple))
    except Exception:
        rounded = dict(geom)
        if "coordinates" in rounded:
            rounded["coordinates"] = _round_coords(rounded["coordinates"])
        return rounded


def _with_features(payload: dict[str, Any], features: list[dict[str, Any]]) -> dict[str, Any]:
    meta = dict(payload.get("meta") or {})
    meta["count"] = len(features)
    return {**payload, "features": features, "meta": meta}


def cap_feature_collection(payload: dict[str, Any], budget: int) -> dict[str, Any]:
    """Simplify until the compact JSON fits `budget`. Never emit a bounding box.

    When every simplification is still over the budget, return no features and
    set ``meta.hidden_below_zoom``. The map asks the visitor to zoom in.
    """
    original = [row for row in (payload.get("features") or []) if isinstance(row, dict)]
    if not original:
        return payload
    for tolerance in _cap_tolerances_m():
        features: list[dict[str, Any]] = []
        for feature in original:
            geom = _geometry_under(feature.get("geometry"), tolerance)
            if not geom:
                continue
            features.append({**feature, "geometry": geom})
        if not features:
            continue
        candidate = _with_features(payload, features)
        if len(dumps_feature_collection(candidate)) <= budget:
            return candidate
    hidden = _with_features(payload, [])
    meta = dict(hidden.get("meta") or {})
    meta["hidden_below_zoom"] = True
    meta["count"] = 0
    return {**hidden, "meta": meta}


def _protected_geom_sql() -> str:
    """Simplify in British National Grid metres, then return WGS84 GeoJSON."""
    return f"""
            ST_AsGeoJSON(
                ST_Transform(
                    ST_SimplifyPreserveTopology(
                        ST_MakeValid(ST_Transform(geom, 27700)),
                        %s
                    ),
                    4326
                ),
                {COORD_DECIMALS}
            )::json AS geometry"""


def require_designations_loaded() -> None:
    if not designations_is_loaded():
        raise LayerUnavailable(
            "NatureScot designations are not available: naturescot_designations "
            "is missing or empty. Ingest SPA/SAC/NNR "
            "(python -m etl.ingest_naturescot --layer designations) before publishing."
        )


def query_sssi_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
    zoom: float | None = None,
) -> dict[str, Any]:
    """Viewport SSSI polygons as GeoJSON (WGS84), simplified for the zoom.

    z6, z7, and z8 keep the finished body in memory. A repeat of that view
    does not run PostGIS again.
    """
    require_sssi_loaded()
    cap = max(1, min(int(max_features), MAX_FEATURES))
    view_zoom = zoom_for_view(south, west, north, east, zoom)
    cache_key = _low_zoom_cache_key("sssi", south, west, north, east, cap, view_zoom)
    return _cached_low_zoom(
        cache_key,
        lambda: _query_sssi_uncached(south, west, north, east, cap, view_zoom),
    )


def _query_sssi_uncached(
    south: float,
    west: float,
    north: float,
    east: float,
    cap: int,
    view_zoom: float,
) -> dict[str, Any]:
    tolerance = simplify_tolerance_m(view_zoom)
    meta = sssi_source_meta()
    sql = f"""
        SELECT
            pa_code,
            name,
            status,
            site_type,
            site_ha,
            european_code,
            {_protected_geom_sql()}
        FROM {SSSI_TABLE}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY site_ha DESC NULLS LAST
        LIMIT %s
    """
    try:
        conn = _connect()
    except Exception as exc:
        raise LayerUnavailable(f"NatureScot PostGIS unavailable: {exc}") from exc
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (tolerance, west, south, east, north, west, south, east, north, cap),
            )
            rows = cur.fetchall()
    except Exception as exc:
        raise LayerUnavailable(f"SSSI query failed: {exc}") from exc
    finally:
        conn.close()

    features = []
    for row in rows:
        geom = row.get("geometry")
        if not geom:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "pa_code": row.get("pa_code"),
                    "name": row.get("name"),
                    "status": row.get("status"),
                    "site_type": row.get("site_type"),
                    "site_ha": row.get("site_ha"),
                    "european_code": row.get("european_code"),
                    "designation_type": "sssi",
                    "layer": "sssi",
                    "source": meta["source"],
                    "licence": meta["licence"],
                },
            }
        )
    payload = {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "layer": "sssi",
            "count": len(features),
            "capped": len(features) >= cap,
            **meta,
        },
    }
    return cap_feature_collection(payload, payload_byte_budget(view_zoom))


def query_designations_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
    zoom: float | None = None,
) -> dict[str, Any]:
    """Viewport SPA / SAC / NNR polygons as GeoJSON (WGS84), simplified for the zoom.

    z6, z7, and z8 keep the finished body in memory. A repeat of that view
    does not run PostGIS again.
    """
    require_designations_loaded()
    cap = max(1, min(int(max_features), MAX_FEATURES))
    view_zoom = zoom_for_view(south, west, north, east, zoom)
    cache_key = _low_zoom_cache_key(
        "naturescot_designations", south, west, north, east, cap, view_zoom
    )
    return _cached_low_zoom(
        cache_key,
        lambda: _query_designations_uncached(
            south, west, north, east, cap, view_zoom
        ),
    )


def _query_designations_uncached(
    south: float,
    west: float,
    north: float,
    east: float,
    cap: int,
    view_zoom: float,
) -> dict[str, Any]:
    tolerance = simplify_tolerance_m(view_zoom)
    meta = designations_source_meta()
    sql = f"""
        SELECT
            site_key,
            designation_type,
            pa_code,
            name,
            status,
            site_type,
            site_ha,
            european_code,
            {_protected_geom_sql()}
        FROM {DESIGNATIONS_TABLE}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY site_ha DESC NULLS LAST
        LIMIT %s
    """
    try:
        conn = _connect()
    except Exception as exc:
        raise LayerUnavailable(f"NatureScot PostGIS unavailable: {exc}") from exc
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (tolerance, west, south, east, north, west, south, east, north, cap),
            )
            rows = cur.fetchall()
    except Exception as exc:
        raise LayerUnavailable(f"NatureScot designations query failed: {exc}") from exc
    finally:
        conn.close()

    features = []
    for row in rows:
        geom = row.get("geometry")
        if not geom:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "site_key": row.get("site_key"),
                    "designation_type": row.get("designation_type"),
                    "pa_code": row.get("pa_code"),
                    "name": row.get("name"),
                    "status": row.get("status"),
                    "site_type": row.get("site_type"),
                    "site_ha": row.get("site_ha"),
                    "european_code": row.get("european_code"),
                    "layer": "naturescot_designations",
                    "source": meta["source"],
                    "licence": meta["licence"],
                },
            }
        )
    payload = {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "layer": "naturescot_designations",
            "count": len(features),
            "capped": len(features) >= cap,
            **meta,
        },
    }
    return cap_feature_collection(payload, payload_byte_budget(view_zoom))
