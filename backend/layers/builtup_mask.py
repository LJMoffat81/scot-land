"""UX10-2 / SRC-B-SETTLEMENTS built-up display layer from local PostGIS.

Display only: never changes any figure. Both MaskKinds read the live
``run_layer`` table for registry entry ``settlements-2022`` (official NRS
Settlements 2022). Old tables ``map_builtup_mask`` and ``dz2022_masked`` stay
in the DB unread. Served as zoom-simplified viewport GeoJSON for MapLibre
vector layers (same contract as Data Zones / NRS places — not national raw
GeoJSON).

Attribution (visitor): Built-up areas: NRS Settlements 2022. Copyright National Records of Scotland, contains Ordnance Survey data © Crown copyright and database right 2026 (OGL v3)
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from psycopg2 import extras

from etl.run_layer import _table
from georgist.db import DatabaseUnavailable, connect
from layers.registry.loader import registry

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"

MaskKind = Literal["builtup_mask", "dz2022_masked"]

SETTLEMENTS_LAYER_ID = "settlements-2022"

# MVT layer names stay unchanged for the frontend contract (S2).
MVT_LAYER_NAMES: dict[MaskKind, str] = {
    "builtup_mask": "map_builtup_mask",
    "dz2022_masked": "dz2022_masked",
}
MAX_FEATURES = 400
EXPECTED_DZ2022_MASKED = 7392

BUILTUP_CREDIT = "Built-up areas: NRS Settlements 2022. Copyright National Records of Scotland, contains Ordnance Survey data © Crown copyright and database right 2026 (OGL v3)"
BUILTUP_METHOD_NOTE = "These are National Records of Scotland's official 2022 settlement boundaries, for places of 500 or more people. Smaller villages and hamlets are not shown. We only trim them to the coastline. They only decide which parts of the map are coloured. They are not used in any land value."
VISITOR_ATTRIBUTION = BUILTUP_CREDIT


class LayerUnavailable(Exception):
    """Raised when built-up mask tables are not loaded or PostGIS is unreachable."""


def _live_table() -> str:
    """Resolve the live settlements-2022 table via registry + run_layer._table."""
    lid = SETTLEMENTS_LAYER_ID
    entries = registry()
    if lid not in entries:
        raise LayerUnavailable(
            f"Built-up mask registry entry {lid!r} is missing."
        )
    return _table("layers", lid)


def _live_regclass() -> str:
    return 'layers."settlements-2022"'


@lru_cache(maxsize=1)
def _source_block() -> dict[str, Any]:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    return dict(sources.get("map_builtup_mask") or {})


def source_meta(kind: MaskKind = "builtup_mask") -> dict[str, Any]:
    block = _source_block()
    layers = block.get("layers") or {}
    layer = layers.get(kind) or layers.get("builtup_mask") or {}
    return {
        "source": layer.get("name")
        or block.get("name")
        or "Built-up areas (NRS Settlements 2022)",
        "licence": block.get("licence") or "OGL-3.0",
        "attribution": block.get("attribution") or BUILTUP_CREDIT,
        "source_url": block.get("source_url")
        or "https://www.nrscotland.gov.uk/statistics-and-data/geography",
        "vintage": block.get("vintage") or "Census 2022",
        "product": layer.get("product") or kind,
        "gaps": list(block.get("gaps") or []),
        "display_only": True,
    }


def is_loaded(kind: MaskKind = "builtup_mask") -> bool:
    del kind  # both kinds share the settlements-2022 table
    try:
        conn = connect()
    except DatabaseUnavailable as exc:
        logger.info("built-up mask PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (_live_regclass(),),
            )
            if not cur.fetchone()[0]:
                return False
            table = _live_table()
            cur.execute(f"SELECT 1 FROM {table} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("built-up mask load check failed: %s", exc)
        return False
    finally:
        conn.close()


def require_loaded(kind: MaskKind) -> None:
    if not is_loaded(kind):
        raise LayerUnavailable(
            f"Built-up mask {kind} is not available: "
            f'{_live_regclass()} is missing or empty. '
            "Ingest with python -m etl.run_layer settlements-2022 before "
            "publishing this layer."
        )


def count_rows(kind: MaskKind) -> int:
    require_loaded(kind)
    table = _live_table()
    try:
        conn = connect()
    except DatabaseUnavailable as exc:
        raise LayerUnavailable(f"Built-up mask PostGIS unavailable: {exc}") from exc
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def query_bbox(
    kind: MaskKind,
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport settlement polygons as GeoJSON (WGS84) for MapLibre vector layers."""
    require_loaded(kind)
    table = _live_table()
    cap = max(1, min(int(max_features), MAX_FEATURES))
    meta = source_meta(kind)
    sql = f"""
        SELECT
            COALESCE(props ->> 'code', feature_id) AS code,
            props ->> 'name' AS name,
            CASE
                WHEN props ->> 'popcount' ~ '^-?[0-9]+$'
                THEN (props ->> 'popcount')::integer
                ELSE NULL
            END AS popcount,
            ST_AsGeoJSON(
                ST_SimplifyPreserveTopology(ST_Transform(geom, 4326), 0.00005), 6
            )::json AS geometry
        FROM {table}
        WHERE geom && ST_Transform(
                ST_MakeEnvelope(%s, %s, %s, %s, 4326), 27700
              )
          AND ST_Intersects(
                geom,
                ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), 27700)
              )
        ORDER BY code
        LIMIT %s
    """
    try:
        conn = connect()
    except DatabaseUnavailable as exc:
        raise LayerUnavailable(f"Built-up mask PostGIS unavailable: {exc}") from exc
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (west, south, east, north, west, south, east, north, cap),
            )
            rows = cur.fetchall()
    except Exception as exc:
        raise LayerUnavailable(f"Built-up mask query failed: {exc}") from exc
    finally:
        conn.close()

    features = []
    for row in rows:
        geom = row.get("geometry")
        if not geom:
            continue
        props: dict[str, Any] = {
            "layer": kind,
            "source": meta["source"],
            "licence": meta["licence"],
            "display_only": True,
            "code": row.get("code"),
            "name": row.get("name"),
            "popcount": row.get("popcount"),
        }
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": props,
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "layer": kind,
            "count": len(features),
            "capped": len(features) >= cap,
            **meta,
        },
    }


def query_mvt(kind: MaskKind, z: int, x: int, y: int) -> bytes:
    """Mapbox Vector Tile for one XYZ tile (Web Mercator). Empty bytes if none."""
    require_loaded(kind)
    table = _live_table()
    mvt_name = MVT_LAYER_NAMES[kind]
    sql = f"""
        WITH bounds AS (
            SELECT ST_TileEnvelope(%s, %s, %s) AS geom
        )
        SELECT COALESCE(ST_AsMVT(tile, %s, 4096, 'geom'), ''::bytea)
        FROM (
            SELECT
                COALESCE(d.props ->> 'code', d.feature_id) AS code,
                d.props ->> 'name' AS name,
                CASE
                    WHEN d.props ->> 'popcount' ~ '^-?[0-9]+$'
                    THEN (d.props ->> 'popcount')::integer
                    ELSE NULL
                END AS popcount,
                ST_AsMVTGeom(
                    ST_Transform(d.geom, 3857),
                    bounds.geom,
                    4096,
                    64,
                    true
                ) AS geom
            FROM {table} d, bounds
            WHERE ST_Transform(d.geom, 3857) && bounds.geom
        ) AS tile
    """
    params = (z, x, y, mvt_name)
    try:
        conn = connect()
    except DatabaseUnavailable as exc:
        raise LayerUnavailable(f"Built-up mask PostGIS unavailable: {exc}") from exc
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            payload = row[0] if row else b""
            if payload is None:
                return b""
            if isinstance(payload, memoryview):
                return payload.tobytes()
            if isinstance(payload, bytes):
                return payload
            return bytes(payload)
    except Exception as exc:
        raise LayerUnavailable(f"Built-up mask MVT query failed: {exc}") from exc
    finally:
        conn.close()
