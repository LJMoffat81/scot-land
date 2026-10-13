"""Community Ownership in Scotland — OGL asset points from PostGIS.

Source: Scottish Government Community Ownership in Scotland 2024 Dataset
(Open Government Licence v3.0). Geometry is the postcodes.io centroid of the
published asset postcode — not a title polygon. When the PostGIS table is
missing or empty, callers must return HTTP 503 — never invent holdings.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import psycopg2
import yaml
from psycopg2 import extras

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
TABLE = "community_ownership_assets"
MAX_FEATURES = 200

ASSET_TYPES = (
    "Land only",
    "Building only",
    "Land and Building",
    "Other",
    "Structure on land not owned",
    "Area not applicable",
)

PUBLICATION_URL = (
    "https://www.gov.scot/publications/community-ownership-in-scotland-2024/"
)
DOCUMENTS_URL = (
    "https://www.gov.scot/publications/community-ownership-in-scotland-2024/documents/"
)
LICENCE = "Open Government Licence v3.0"
ATTRIBUTION = (
    "Community Ownership in Scotland 2024. Contains public sector information "
    "licensed under the Open Government Licence v3.0. © Scottish Government. "
    "Points are postcode centroids of published assets — not title polygons "
    "(ONS Postcode Directory via postcodes.io). Contains OS data © Crown "
    "copyright and database right 2026. Contains Royal Mail data © Royal Mail "
    "copyright and database right 2026. Contains National Statistics data "
    "© Crown copyright and database right 2026."
)


class LayerUnavailable(Exception):
    """Raised when community ownership data is not loaded or PostGIS is down."""


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
def source_meta() -> dict[str, Any]:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    row = sources.get("community_ownership") or {}
    return {
        "source": row.get("name")
        or "Community Ownership in Scotland 2024",
        "licence": row.get("licence") or LICENCE,
        "licence_url": (
            "https://www.nationalarchives.gov.uk/doc/"
            "open-government-licence/version/3/"
        ),
        "attribution": row.get("attribution") or ATTRIBUTION,
        "source_url": row.get("source_url") or PUBLICATION_URL,
        "dataset_url": row.get("dataset_url") or DOCUMENTS_URL,
        "vintage": row.get("vintage") or "2024-12",
        "gaps": row.get("gaps")
        or [
            "Points are postcode centroids — not title extents",
            "Some assets have no published area (Sasine)",
            "Confidential assets excluded from the open dataset",
        ],
    }


def is_loaded() -> bool:
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("Community ownership PostGIS unavailable: %s", exc)
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
        logger.info("Community ownership load check failed: %s", exc)
        return False
    finally:
        conn.close()


def require_loaded() -> None:
    if not is_loaded():
        raise LayerUnavailable(
            "Community ownership overlay is not available: "
            f"{TABLE} is missing or empty. Ingest the SG 2024 OGL dataset "
            "(python -m etl.ingest_community_ownership) before publishing."
        )


def _props_from_row(row: dict[str, Any]) -> dict[str, Any]:
    meta = source_meta()
    return {
        "asset_id": row.get("asset_id"),
        "group_name": row.get("group_name"),
        "asset_name": row.get("asset_name"),
        "postcode": row.get("postcode"),
        "local_authority": row.get("local_authority"),
        "la_s_code": row.get("la_s_code"),
        "area_ha": row.get("area_ha"),
        "asset_type": row.get("asset_type"),
        "year_of_ownership": row.get("year_of_ownership"),
        "geometry_source": row.get("geometry_source") or "postcode_centroid",
        "layer": "community_ownership",
        "source": meta["attribution"],
        "licence": meta["licence"],
        "licence_url": (
            "https://www.nationalarchives.gov.uk/doc/"
            "open-government-licence/version/3/"
        ),
    }


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport community-ownership points as GeoJSON (WGS84)."""
    require_loaded()
    cap = max(1, min(int(max_features), MAX_FEATURES))
    meta = source_meta()
    sql = f"""
        SELECT asset_id, group_name, asset_name, postcode, local_authority,
               la_s_code, area_ha, asset_type, year_of_ownership,
               geometry_source,
               ST_AsGeoJSON(geom)::json AS geometry
        FROM {TABLE}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
        LIMIT %s
    """
    try:
        conn = _connect()
    except Exception as exc:
        raise LayerUnavailable(f"PostGIS unavailable: {exc}") from exc
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(sql, (west, south, east, north, cap))
            rows = list(cur.fetchall())
    finally:
        conn.close()

    features = []
    for row in rows:
        geom = row.pop("geometry", None)
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": _props_from_row(dict(row)),
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "layer": "community_ownership",
            "count": len(features),
            "capped": len(features) >= cap,
            "source": meta["attribution"],
            "licence": meta["licence"],
            "licence_url": (
                "https://www.nationalarchives.gov.uk/doc/"
                "open-government-licence/version/3/"
            ),
            "source_url": meta["source_url"],
            "dataset_url": meta["dataset_url"],
            "vintage": meta["vintage"],
            "asset_types": list(ASSET_TYPES),
            "geometry_source_live": "postcode_centroid",
            "gaps": meta["gaps"],
        },
    }


def query_point(lat: float, lng: float, *, radius_m: float = 75.0) -> dict[str, Any]:
    """Assets near a click (postcode centroid within radius_m)."""
    if not is_loaded():
        return {
            "ok": False,
            "error": f"{TABLE} missing or empty",
            "intersects": False,
            "assets": [],
            "source": ATTRIBUTION,
            "licence": LICENCE,
            "licence_url": (
                "https://www.nationalarchives.gov.uk/doc/"
                "open-government-licence/version/3/"
            ),
        }
    sql = f"""
        SELECT asset_id, group_name, asset_name, postcode, local_authority,
               la_s_code, area_ha, asset_type, year_of_ownership,
               geometry_source,
               ST_Distance(
                   geom::geography,
                   ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
               ) AS dist_m
        FROM {TABLE}
        WHERE ST_DWithin(
            geom::geography,
            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
            %s
        )
        ORDER BY dist_m
        LIMIT 5
    """
    conn = None
    try:
        conn = _connect()
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(sql, (lng, lat, lng, lat, float(radius_m)))
            rows = list(cur.fetchall())
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "intersects": False,
            "assets": [],
            "source": ATTRIBUTION,
            "licence": LICENCE,
            "licence_url": (
                "https://www.nationalarchives.gov.uk/doc/"
                "open-government-licence/version/3/"
            ),
        }
    finally:
        if conn is not None:
            conn.close()

    assets = []
    for row in rows:
        props = _props_from_row(dict(row))
        props["distance_m"] = round(float(row.get("dist_m") or 0), 1)
        assets.append(props)
    return {
        "ok": True,
        "intersects": bool(assets),
        "assets": assets,
        "source": ATTRIBUTION,
        "licence": LICENCE,
        "licence_url": (
            "https://www.nationalarchives.gov.uk/doc/"
            "open-government-licence/version/3/"
        ),
        "source_url": PUBLICATION_URL,
        "note": (
            "Community ownership points are postcode centroids from the SG 2024 "
            "OGL dataset — not a legal title. Confirm on ScotLIS."
        ),
    }


def catalog_layer() -> dict[str, Any]:
    meta = source_meta()
    return {
        "id": "community_ownership",
        "group": "ownership",
        "status": "live",
        "label": "Community ownership",
        "description": (
            "Scottish Government Community Ownership in Scotland 2024 assets "
            "(OGL). Postcode-centroid points loaded in PostGIS — not title "
            "polygons. Ownership-context (who/outline) — not a LayersPanel "
            "toggle, not a rent row. 503 when the table is unloaded."
        ),
        "endpoint": "/layers/open/community-ownership",
        "licence": meta["licence"],
        "licence_url": (
            "https://www.nationalarchives.gov.uk/doc/"
            "open-government-licence/version/3/"
        ),
        "minzoom": 6,
        "source_url": meta["source_url"],
        "gaps": meta["gaps"],
        "ledger_role": "ownership-context",
        "ledger_row": None,
        "ui_surface": "ledger",
        "geometry": "points_only",
    }
