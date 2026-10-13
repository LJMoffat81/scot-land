"""RoS INSPIRE cadastral parcels from local PostGIS ingest.

Map tiles still proxy the live ROS WMS (see spatial.parcels). This module
serves bbox GeoJSON from a local Index Polygons load. When the table is
missing or empty, callers must return HTTP 503 — never placeholder parcels.

A fixture-scoped CI load (synthetic polygons only) still serves 200 for
viewports with no rows; meta.fixture_scoped and gaps stay honest.

Shapes only — no titles, owners or prices. Attribution is OGL v3 (Laurie
ruling Oct 2026); never the 2017 OS INSPIRE end-user licence.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import psycopg2
import yaml
from psycopg2 import extras

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
TABLE = "inspire_parcels"
META_TABLE = "inspire_parcels_meta"
MAX_FEATURES = 200

OGL_V3_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)
OGL_V3_LICENCE_PHRASE = "Licensed under the Open Government Licence v3.0"
# Exact map / layer-guide credit (harvest year filled at runtime).
ROS_OS_ATTRIBUTION_TEMPLATE = (
    "© Crown copyright. Reproduced with the permission of Registers of Scotland. "
    "Contains OS data © Crown copyright and database right {year}."
)


class LayerUnavailable(Exception):
    """Raised when cadastral data is not loaded or PostGIS is unreachable."""


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


def harvest_year_from_vintage(vintage: str | None, fallback: int | None = None) -> int:
    """Parse harvest year from a vintage stamp (YYYY or YYYY-MM-DD)."""
    if vintage:
        match = re.search(r"(20\d{2})", str(vintage))
        if match:
            return int(match.group(1))
    if fallback is not None:
        return int(fallback)
    return date.today().year


def format_ros_os_attribution(year: int) -> str:
    """Confirmed RoS/OS map credit — shapes only; no titles, owners or prices."""
    return ROS_OS_ATTRIBUTION_TEMPLATE.format(year=int(year))


@lru_cache(maxsize=1)
def parcel_source_meta() -> dict[str, Any]:
    """Licence / attribution / vintage from the committed source registry."""
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    parcels = sources.get("parcels") or {}
    configured_year = parcels.get("harvest_year")
    year = harvest_year_from_vintage(
        str(parcels.get("vintage") or ""),
        fallback=int(configured_year) if configured_year is not None else None,
    )
    attribution = (parcels.get("attribution") or "").strip()
    if not attribution or "{year}" in attribution:
        attribution = format_ros_os_attribution(year)
    else:
        # Keep registry text when it already embeds the harvest year.
        attribution = " ".join(attribution.split())
    return {
        "source": parcels.get("name") or "ROS INSPIRE cadastral parcels",
        "licence": parcels.get("licence") or "OGL-3.0",
        "licence_url": parcels.get("licence_url") or OGL_V3_URL,
        "licence_phrase": parcels.get("licence_phrase") or OGL_V3_LICENCE_PHRASE,
        "attribution": attribution,
        "harvest_year": year,
        "source_url": parcels.get("source_url") or "https://www.ros.gov.uk/open-data",
        "vintage": parcels.get("vintage") or "see live WMS / local ingest stamp",
        "product": parcels.get("product") or "INSPIRE Index Polygons (CP.CadastralParcel)",
        "publication_status": parcels.get("publication_status") or "ok",
        "gaps": list(
            parcels.get("gaps")
            or [
                "Sasine titles without Land Register polygons",
                "Private owner names are not in the open INSPIRE product",
                "Index polygons are registered extents, not a title sheet",
            ]
        ),
    }


def _load_meta_rows(conn) -> dict[str, str]:
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (f"public.{META_TABLE}",),
            )
            if not cur.fetchone()[0]:
                return {}
            cur.execute(f"SELECT key, value FROM {META_TABLE}")
            return {str(k): str(v) for k, v in cur.fetchall()}
    except Exception as exc:
        logger.info("Cadastral meta read failed: %s", exc)
        return {}


def load_scope(conn=None) -> str:
    """Return production | fixture | unknown from inspire_parcels_meta."""
    owns = conn is None
    if owns:
        try:
            conn = _connect()
        except Exception:
            return "unknown"
    try:
        rows = _load_meta_rows(conn)
        scope = (rows.get("load_scope") or "unknown").strip().lower()
        if scope in ("production", "fixture"):
            return scope
        return "unknown"
    finally:
        if owns and conn is not None:
            conn.close()


def is_loaded() -> bool:
    """True when PostGIS has at least one inspire parcel row."""
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("Cadastral PostGIS unavailable: %s", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (f"public.{TABLE}",),
            )
            exists = bool(cur.fetchone()[0])
            if not exists:
                return False
            cur.execute(f"SELECT 1 FROM {TABLE} LIMIT 1")
            return cur.fetchone() is not None
    except Exception as exc:
        logger.info("Cadastral load check failed: %s", exc)
        return False
    finally:
        conn.close()


def require_loaded() -> None:
    if not is_loaded():
        raise LayerUnavailable(
            "Cadastral parcels are not available: inspire_parcels is missing "
            "or empty. Ingest RoS INSPIRE Index Polygons "
            "(python -m etl.ingest_inspire_parcels) before publishing this layer."
        )


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport cadastral polygons as GeoJSON (WGS84). 503 path via require_loaded.

    Empty viewports return an empty FeatureCollection (200) when the table is
    loaded — including fixture-scoped CI loads that only cover a small bbox.
    """
    require_loaded()
    cap = max(1, min(int(max_features), MAX_FEATURES))
    meta = dict(parcel_source_meta())
    sql = f"""
        SELECT
            inspire_id,
            national_reference,
            label,
            area_sqm,
            county,
            ST_AsGeoJSON(geom)::json AS geometry
        FROM {TABLE}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY area_sqm DESC NULLS LAST
        LIMIT %s
    """
    try:
        conn = _connect()
    except Exception as exc:
        raise LayerUnavailable(f"Cadastral PostGIS unavailable: {exc}") from exc
    try:
        scope = load_scope(conn)
        db_meta = _load_meta_rows(conn)
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(sql, (west, south, east, north, west, south, east, north, cap))
            rows = cur.fetchall()
    except LayerUnavailable:
        raise
    except Exception as exc:
        raise LayerUnavailable(f"Cadastral query failed: {exc}") from exc
    finally:
        conn.close()

    fixture_scoped = scope == "fixture"
    year = harvest_year_from_vintage(
        db_meta.get("harvest_year") or db_meta.get("vintage") or meta.get("vintage"),
        fallback=meta.get("harvest_year"),
    )
    meta["harvest_year"] = year
    meta["attribution"] = format_ros_os_attribution(year)
    meta["licence_url"] = meta.get("licence_url") or OGL_V3_URL
    meta["licence_phrase"] = meta.get("licence_phrase") or OGL_V3_LICENCE_PHRASE
    raw_counts = db_meta.get("county_counts")
    if raw_counts:
        try:
            parsed = json.loads(raw_counts)
            if isinstance(parsed, dict):
                meta["county_counts"] = {
                    str(k): int(v) for k, v in parsed.items()
                }
        except (TypeError, ValueError, json.JSONDecodeError):
            meta["county_counts_raw"] = raw_counts
    if db_meta.get("tagged"):
        meta["tagged"] = db_meta["tagged"]
    if db_meta.get("crs_source"):
        meta["crs_source"] = db_meta["crs_source"]
    if db_meta.get("publication_status"):
        meta["publication_status"] = db_meta["publication_status"]
    if fixture_scoped:
        # Fixture loads must not look like a national RoS extract.
        meta["licence"] = db_meta.get("licence") or "synthetic-test-only"
        meta["source_url"] = db_meta.get("source_url") or meta["source_url"]
        meta["vintage"] = db_meta.get("vintage") or meta["vintage"]
        gaps = list(meta.get("gaps") or [])
        gaps.append(
            "PostGIS load is fixture-scoped (synthetic CI polygons only) — "
            "not a national RoS INSPIRE extract"
        )
        meta["gaps"] = gaps

    features = []
    for row in rows:
        geom = row.get("geometry")
        if not geom:
            continue
        # Shapes only — never expose titles, owners or prices on public features.
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "inspire_id": row.get("inspire_id"),
                    "national_reference": row.get("national_reference"),
                    "label": row.get("label") or row.get("national_reference"),
                    "area_sqm": row.get("area_sqm"),
                    "county": row.get("county"),
                    "layer": "cadastral",
                    "source": meta["source"],
                    "licence": meta["licence"],
                    "fixture": fixture_scoped,
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "layer": "cadastral",
            "count": len(features),
            "capped": len(features) >= cap,
            "load_scope": scope,
            "fixture_scoped": fixture_scoped,
            **meta,
        },
    }
