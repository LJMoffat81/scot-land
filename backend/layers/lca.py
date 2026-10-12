"""Land Capability for Agriculture (James Hutton 1:250k) from local PostGIS.

Source download is openly licensed under the James Hutton Institute Open Data
Licence (not pure OGL). Public-sector information in the product is under
OGL v2.0 per the Hutton attribution clause. Raw geometry stays in
``data/external/lca/`` (gitignored); this module serves bbox GeoJSON and
returns LayerUnavailable when the table is missing or empty (HTTP 503).
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
TABLE = "lca_agriculture"
MAX_FEATURES = 200


class LayerUnavailable(Exception):
    """Raised when LCA data is not loaded or PostGIS is unreachable."""


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
def lca_source_meta() -> dict[str, Any]:
    """Licence / attribution / vintage from the committed source registry."""
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    lca = sources.get("lca") or {}
    return {
        "source": lca.get("name")
        or "Land Capability for Agriculture 1:250,000 (James Hutton Institute)",
        "licence": lca.get("licence") or "James Hutton Institute Open Data Licence",
        "licence_note": lca.get("licence_note")
        or (
            "Not OGL-3.0. Public-sector information in the product is under "
            "OGL v2.0 per the Hutton attribution clause."
        ),
        "attribution": lca.get("attribution")
        or (
            "Land Capability for Agriculture 1:250,000 copyright and database "
            "right The James Hutton Institute. Used with the permission of "
            "The James Hutton Institute. All rights reserved. Any public "
            "sector information contained in these data is licensed under "
            "the Open Government Licence v.2.0."
        ),
        "share_alike": lca.get("share_alike")
        or (
            "Redistribution and derived data must be on equivalent Hutton "
            "Open Data Licence terms; retain attribution and pass that "
            "obligation through any sublicence."
        ),
        "source_url": lca.get("source_url")
        or (
            "https://www.hutton.ac.uk/sites/default/files/files/soils/downloads/"
            "Hutton_LCA250K_OpenData.zip"
        ),
        "catalogue_url": lca.get("catalogue_url")
        or (
            "https://spatialdata.gov.scot/geonetwork/srv/api/records/"
            "24c6df5a-6b04-43f8-839f-0d45cc2802e3"
        ),
        "licence_url": lca.get("licence_url")
        or (
            "https://www.hutton.ac.uk/wp-content/uploads/2024/05/"
            "The-James-Hutton-Institute-Open-Data-Licence-download.pdf"
        ),
        "vintage": lca.get("vintage") or "1:250k national open release",
        "product": lca.get("product") or "LCA_250K",
        "gaps": lca.get("gaps")
        or [
            "1:250,000 national scale — not a field-boundary survey",
            "1:50,000 partial-cover product is a separate download",
        ],
    }


def is_loaded() -> bool:
    """True when PostGIS has at least one LCA polygon."""
    try:
        conn = _connect()
    except Exception as exc:
        logger.info("LCA PostGIS unavailable: %s", exc)
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
        logger.info("LCA load check failed: %s", exc)
        return False
    finally:
        conn.close()


def require_loaded() -> None:
    if not is_loaded():
        raise LayerUnavailable(
            "Land Capability for Agriculture is not available: "
            f"{TABLE} is missing or empty. Ingest the Hutton LCA 1:250k open "
            "download (python -m etl.ingest_lca) before publishing this layer."
        )


def query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_features: int = MAX_FEATURES,
) -> dict[str, Any]:
    """Viewport LCA polygons as GeoJSON (WGS84). 503 path via require_loaded."""
    require_loaded()
    cap = max(1, min(int(max_features), MAX_FEATURES))
    meta = lca_source_meta()
    sql = f"""
        SELECT
            id,
            lccode,
            class_label,
            prime,
            scale,
            hectares,
            sqmid,
            ST_AsGeoJSON(geom)::json AS geometry
        FROM {TABLE}
        WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
        ORDER BY hectares DESC NULLS LAST
        LIMIT %s
    """
    try:
        conn = _connect()
    except Exception as exc:
        raise LayerUnavailable(f"LCA PostGIS unavailable: {exc}") from exc
    try:
        with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
            cur.execute(
                sql, (west, south, east, north, west, south, east, north, cap)
            )
            rows = cur.fetchall()
    except Exception as exc:
        raise LayerUnavailable(f"LCA query failed: {exc}") from exc
    finally:
        conn.close()

    features = []
    for row in rows:
        geom = row.get("geometry")
        if not geom:
            continue
        lccode = row.get("lccode")
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "id": row.get("id"),
                    "lccode": lccode,
                    "class_label": row.get("class_label"),
                    "prime": row.get("prime"),
                    "scale": row.get("scale"),
                    "hectares": row.get("hectares"),
                    "sqmid": row.get("sqmid"),
                    "layer": "lca",
                    "source": meta["source"],
                    "licence": meta["licence"],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "ok": True,
            "layer": "lca",
            "count": len(features),
            "capped": len(features) >= cap,
            **meta,
        },
    }
