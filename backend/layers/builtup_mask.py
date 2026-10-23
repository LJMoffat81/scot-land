"""UX10-2 built-up display mask from local PostGIS.

Display only: never changes any figure. Tables ``map_builtup_mask`` (national
built-up extent parts) and ``dz2022_masked`` (DZ2022 ∩ mask, one row per zone
with addresses). Served as zoom-simplified viewport GeoJSON for MapLibre
vector layers (same contract as Data Zones / NRS places — not national raw
GeoJSON).

Attribution (visitor): Built-up areas: our estimate from NRS Settlements 2022 and OS Open UPRN. Contains NRS and OS data © Crown copyright and database right 2026 (OGL v3)
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from psycopg2 import extras

from georgist.db import DatabaseUnavailable, connect

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"

MaskKind = Literal["builtup_mask", "dz2022_masked"]

TABLES: dict[MaskKind, str] = {
    "builtup_mask": "map_builtup_mask",
    "dz2022_masked": "dz2022_masked",
}
MAX_FEATURES = 400
EXPECTED_DZ2022_MASKED = 7392

BUILTUP_CREDIT = "Built-up areas: our estimate from NRS Settlements 2022 and OS Open UPRN. Contains NRS and OS data © Crown copyright and database right 2026 (OGL v3)"
BUILTUP_METHOD_NOTE = "This is our own estimate of built-up land, not an official boundary. We start with National Records of Scotland's 2022 settlement boundaries, add a 50 m area around each OS Open UPRN address point outside them, then cut the result to each 2022 Data Zone. It only decides which parts of the map are coloured. It is not used in any land value."
VISITOR_ATTRIBUTION = BUILTUP_CREDIT


class LayerUnavailable(Exception):
    """Raised when built-up mask tables are not loaded or PostGIS is unreachable."""


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
        or "Built-up display mask (NRS Settlements 2022 + OS Open UPRN)",
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
    table = TABLES[kind]
    try:
        conn = connect()
    except DatabaseUnavailable as exc:
        logger.info("built-up mask %s PostGIS unavailable: %s", kind, exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{table}",))
            if not cur.fetchone()[0]:
                return False
            cur.execute(f"SELECT 1 FROM {table} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("built-up mask %s load check failed: %s", kind, exc)
        return False
    finally:
        conn.close()


def require_loaded(kind: MaskKind) -> None:
    if not is_loaded(kind):
        table = TABLES[kind]
        raise LayerUnavailable(
            f"Built-up mask {kind} is not available: {table} is missing or empty. "
            "Ingest with python -m etl.ingest_builtup_mask before publishing this layer."
        )


def count_rows(kind: MaskKind) -> int:
    require_loaded(kind)
    table = TABLES[kind]
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
    """Viewport mask polygons as GeoJSON (WGS84) for MapLibre vector layers."""
    require_loaded(kind)
    table = TABLES[kind]
    cap = max(1, min(int(max_features), MAX_FEATURES))
    meta = source_meta(kind)
    if kind == "dz2022_masked":
        sql = f"""
            SELECT
                code,
                ST_AsGeoJSON(
                    ST_SimplifyPreserveTopology(geom, 0.00005), 6
                )::json AS geometry
            FROM {table}
            WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
              AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
            ORDER BY code
            LIMIT %s
        """
    else:
        sql = f"""
            SELECT
                gid,
                ST_AsGeoJSON(
                    ST_SimplifyPreserveTopology(geom, 0.00005), 6
                )::json AS geometry
            FROM {table}
            WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
              AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
            ORDER BY gid
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
        }
        if kind == "dz2022_masked":
            props["code"] = row.get("code")
        else:
            props["gid"] = row.get("gid")
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
    table = TABLES[kind]
    if kind == "dz2022_masked":
        sql = f"""
            WITH bounds AS (
                SELECT ST_TileEnvelope(%s, %s, %s) AS geom
            )
            SELECT COALESCE(ST_AsMVT(tile, %s, 4096, 'geom'), ''::bytea)
            FROM (
                SELECT
                    d.code,
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
        params = (z, x, y, "dz2022_masked")
    else:
        sql = f"""
            WITH bounds AS (
                SELECT ST_TileEnvelope(%s, %s, %s) AS geom
            )
            SELECT COALESCE(ST_AsMVT(tile, %s, 4096, 'geom'), ''::bytea)
            FROM (
                SELECT
                    d.gid,
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
        params = (z, x, y, "map_builtup_mask")
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
