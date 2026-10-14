"""Crown Estate Scotland ScotWind / INTOG option polygons (PostGIS).

Natural-capital P1 overlay: observed award/option extents from the CES Spatial
Hub FeatureServers. Separate from surface rent (la-calc) — overlays never add
value or rent to the residual roll.

Polygons only. Option-fee £ are HOLD (press release / FOI) — see
``data/config/scotwind_option_fees.yaml``; never layer attributes.
Evidence tag for the polygons: ``market`` (published CES award extents).
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
TABLE = "ces_scotwind_intog"
MAX_FEATURES = 80

EVIDENCE_TAG = "market"
PUBLICATION_STATUS_OK = "ok"
LICENCE = "OGL-3.0"
# GIS-confirmed catalog credit (CES Spatial Hub open datasets under OGL).
CATALOG_CREDIT = (
    "Contains information from the Crown Estate Scotland licensed under the "
    "Open Government Licence v3.0"
)
OGL_LICENCE_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)


class LayerUnavailable(Exception):
    """Raised when ScotWind/INTOG data is not loaded or PostGIS is unreachable."""


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
    """Licence / attribution / vintage from the committed source registry."""
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    block = sources.get("scotwind_intog") or {}
    return {
        "source": block.get("name")
        or "Crown Estate Scotland ScotWind / INTOG option areas",
        "licence": block.get("licence") or LICENCE,
        "licence_url": block.get("licence_url") or OGL_LICENCE_URL,
        "attribution": block.get("attribution") or CATALOG_CREDIT,
        "source_url": block.get("source_url")
        or (
            "https://crown-estate-scotland-spatial-hub-coregis.hub.arcgis.com/"
            "datasets/coregis::scotwind-offers-crown-estate-scotland/about"
        ),
        "feature_servers": block.get("feature_servers") or {},
        "vintage": block.get("vintage") or "CES Spatial Hub extract",
        "evidence_tag": block.get("evidence_tag") or EVIDENCE_TAG,
        "publication_status": block.get("publication_status") or PUBLICATION_STATUS_OK,
        "fees_config": block.get("fees_config")
        or "data/config/scotwind_option_fees.yaml",
        "gaps": block.get("gaps")
        or [
            "Option-fee figures held in data/config/scotwind_option_fees.yaml (press release) — not on features",
            "Overlay never adds value to surface rent (la-calc)",
        ],
    }


def is_loaded() -> bool:
    """True when PostGIS has at least one ScotWind/INTOG row."""
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("ScotWind/INTOG PostGIS unavailable: %s", exc)
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
        logger.info("ScotWind/INTOG load check failed: %s", exc)
        return False
    finally:
        conn.close()


def require_loaded() -> None:
    if not is_loaded():
        raise LayerUnavailable(
            "ScotWind/INTOG option polygons are not available: "
            f"{TABLE} is missing or empty. Ingest with "
            "python -m etl.ingest_scotwind_intog before publishing this layer."
        )


def _public_props(row: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """Public feature properties — polygons + award descriptors only; no fee £."""
    return {
        "id": row.get("id"),
        "leasing_round": row.get("leasing_round"),
        "award_id": row.get("award_id"),
        "lead_applicant": row.get("lead_applicant"),
        "technology": row.get("technology"),
        "category": row.get("category"),
        "innovation_category": row.get("innovation_category"),
        "capacity_mw": row.get("capacity_mw"),
        "area_km2": row.get("area_km2"),
        "evidence_tag": row.get("evidence_tag") or meta["evidence_tag"],
        "publication_status": row.get("publication_status")
        or meta["publication_status"],
        "layer": "scotwind_intog",
        "source": meta["source"],
        "licence": meta["licence"],
        "licence_url": meta["licence_url"],
        "attribution": meta["attribution"],
        "adds_to_surface_rent": False,
    }


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport ScotWind/INTOG option polygons as GeoJSON (WGS84)."""
    require_loaded()
    cap = max(1, min(int(max_features), MAX_FEATURES))
    meta = source_meta()
    sql = f"""
        SELECT
            id,
            leasing_round,
            award_id,
            lead_applicant,
            technology,
            category,
            innovation_category,
            capacity_mw,
            area_km2,
            evidence_tag,
            publication_status,
            ST_AsGeoJSON(geom)::json AS geometry
        FROM {TABLE}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY area_km2 DESC NULLS LAST
        LIMIT %s
    """
    try:
        conn = _connect()
    except Exception as exc:
        raise LayerUnavailable(f"ScotWind/INTOG PostGIS unavailable: {exc}") from exc
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(sql, (west, south, east, north, west, south, east, north, cap))
            rows = cur.fetchall()
    except Exception as exc:
        raise LayerUnavailable(f"ScotWind/INTOG query failed: {exc}") from exc
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
                "properties": _public_props(row, meta),
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "layer": "scotwind_intog",
            "count": len(features),
            "capped": len(features) >= cap,
            "evidence_tag": meta["evidence_tag"],
            "publication_status": meta["publication_status"],
            "adds_to_surface_rent": False,
            "fees_on_features": False,
            "fees_config": meta["fees_config"],
            "source": meta["source"],
            "licence": meta["licence"],
            "licence_url": meta["licence_url"],
            "attribution": meta["attribution"],
            "source_url": meta["source_url"],
            "vintage": meta["vintage"],
            "gaps": meta["gaps"],
        },
    }
