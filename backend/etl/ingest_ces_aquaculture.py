"""Ingest Crown Estate Scotland aquaculture seabed leases into PostGIS.

OGL v3 via the CES Spatial Hub FeatureServer only. Does not touch
data/external. No £ rent figures.

  python -m etl.ingest_ces_aquaculture
  python -m etl.ingest_ces_aquaculture --replace

Attribution (required by CES):
  Contains information from the Crown Estate Scotland licensed under the
  Open Government Licence v3.0.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import psycopg2
import yaml
from psycopg2.extras import execute_batch

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
SCHEMA_FILE = (
    REPO_ROOT / "backend" / "db" / "schema" / "021_ces_aquaculture_leases.sql"
)
TABLE = "ces_aquaculture_leases"

DEFAULT_FEATURE_SERVER = (
    "https://services3.arcgis.com/nGV4jiurzcahJ9LV/arcgis/rest/services/"
    "Aquaculture_Crown_Estate_Scotland/FeatureServer/0"
)
OGL_LICENCE_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)
CES_ATTRIBUTION = (
    "Contains information from the Crown Estate Scotland licensed under the "
    "Open Government Licence v3.0."
)
HUB_URL = "https://crown-estate-scotland-spatial-hub-coregis.hub.arcgis.com/"


def _db_connect():
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        dbname=os.getenv("WEALTH_DB_NAME", "scotland_wealth"),
        user=os.getenv("WEALTH_DB_USER", "wealth_user"),
        password=os.getenv("WEALTH_DB_PASSWORD", ""),
        host=os.getenv("WEALTH_DB_HOST", "localhost"),
        port=os.getenv("WEALTH_DB_PORT", "5432"),
    )


def _cfg() -> dict[str, Any]:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        return (yaml.safe_load(handle) or {}).get("ces_aquaculture") or {}


def _ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
    conn.commit()


def _fetch_features(base_url: str) -> list[dict[str, Any]]:
    base = base_url.rstrip("/")
    features: list[dict[str, Any]] = []
    offset = 0
    page_size = 500
    with httpx.Client(timeout=60.0) as client:
        while True:
            response = client.get(
                f"{base}/query",
                params={
                    "where": "1=1",
                    "outFields": "*",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "f": "geojson",
                    "resultOffset": offset,
                    "resultRecordCount": page_size,
                },
            )
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("features") or []
            if not batch:
                break
            features.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
    return features


def _rows_from_features(
    features: list[dict[str, Any]], cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    today = date.today().isoformat()
    licence = cfg.get("licence") or "OGL-3.0"
    licence_url = cfg.get("licence_url") or OGL_LICENCE_URL
    attribution = cfg.get("attribution") or CES_ATTRIBUTION
    source_url = cfg.get("source_url") or HUB_URL
    rows: list[dict[str, Any]] = []
    for feat in features:
        props = feat.get("properties") or {}
        geom = feat.get("geometry")
        if not geom:
            continue
        object_id = props.get("OBJECTID")
        site_id = props.get("Site_ID")
        key = str(site_id if site_id is not None else object_id or "").strip()
        if not key:
            continue
        # Published CES lease polygon → market. proxy/shadow reserved.
        rows.append(
            {
                "id": f"ces-aqua:{key}",
                "site_id": str(site_id) if site_id is not None else None,
                "lease_description": (props.get("Lease_Description") or "").strip()
                or None,
                "property_classification": (
                    (props.get("Property_Classification") or "").strip() or None
                ),
                "value_tier": "market",
                "publication_status": "ok",
                "unpublished_reason": None,
                "geojson": json.dumps(geom),
                "licence": licence,
                "licence_url": licence_url,
                "attribution": attribution,
                "source_url": source_url,
                "retrieved_at": today,
            }
        )
    return rows


def ingest(*, replace: bool = True) -> dict[str, Any]:
    cfg = _cfg()
    base = cfg.get("feature_server") or DEFAULT_FEATURE_SERVER
    conn = _db_connect()
    try:
        _ensure_table(conn)
        features = _fetch_features(base)
        rows = _rows_from_features(features, cfg)
        with conn.cursor() as cur:
            if replace:
                cur.execute(f"TRUNCATE {TABLE}")
            if rows:
                execute_batch(
                    cur,
                    f"""
                    INSERT INTO {TABLE} (
                      id, site_id, lease_description, property_classification,
                      value_tier, publication_status, unpublished_reason, geom,
                      licence, licence_url, attribution, source_url, retrieved_at
                    ) VALUES (
                      %(id)s, %(site_id)s, %(lease_description)s,
                      %(property_classification)s, %(value_tier)s,
                      %(publication_status)s, %(unpublished_reason)s,
                      ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)),
                      %(licence)s, %(licence_url)s, %(attribution)s,
                      %(source_url)s, %(retrieved_at)s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      lease_description = EXCLUDED.lease_description,
                      property_classification = EXCLUDED.property_classification,
                      value_tier = EXCLUDED.value_tier,
                      publication_status = EXCLUDED.publication_status,
                      unpublished_reason = EXCLUDED.unpublished_reason,
                      geom = EXCLUDED.geom,
                      licence = EXCLUDED.licence,
                      licence_url = EXCLUDED.licence_url,
                      attribution = EXCLUDED.attribution,
                      source_url = EXCLUDED.source_url,
                      retrieved_at = EXCLUDED.retrieved_at
                    """,
                    rows,
                    page_size=100,
                )
        conn.commit()
        by_class: dict[str, int] = {}
        for row in rows:
            key = row.get("property_classification") or "unknown"
            by_class[key] = by_class.get(key, 0) + 1
        return {
            "table": TABLE,
            "total": len(rows),
            "by_classification": by_class,
            "value_tier": "market",
            "adds_to_surface_rent": False,
            "licence": cfg.get("licence") or "OGL-3.0",
            "licence_url": cfg.get("licence_url") or OGL_LICENCE_URL,
            "attribution": cfg.get("attribution") or CES_ATTRIBUTION,
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true", default=True)
    parser.add_argument("--no-replace", action="store_false", dest="replace")
    args = parser.parse_args(argv)
    print(json.dumps(ingest(replace=args.replace), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
