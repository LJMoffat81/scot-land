"""Ingest Crown Estate Scotland OGL lease polygons into PostGIS.

Fetches lease themes from the CES Spatial Hub FeatureServers (OGL v3).
Does not touch data/external.

  python -m etl.ingest_crown_estate_leases
  python -m etl.ingest_crown_estate_leases --replace
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
from shapely.geometry import MultiPolygon, shape
from shapely.geometry.base import BaseGeometry

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
TABLE = "crown_estate_leases"

# Offshore lease agreement themes only (OGL). Aquaculture / onshore / trails omitted.
DEFAULT_THEMES: list[dict[str, str]] = [
    {
        "id": "offshore_wind",
        "label": "Offshore Wind",
        "url": (
            "https://services3.arcgis.com/nGV4jiurzcahJ9LV/arcgis/rest/services/"
            "Offshore_Wind_Crown_Estate_Scotland/FeatureServer/0"
        ),
    },
    {
        "id": "wave",
        "label": "Wave",
        "url": (
            "https://services3.arcgis.com/nGV4jiurzcahJ9LV/arcgis/rest/services/"
            "Wave_Crown_Estate_Scotland/FeatureServer/0"
        ),
    },
    {
        "id": "tidal",
        "label": "Tidal",
        "url": (
            "https://services3.arcgis.com/nGV4jiurzcahJ9LV/arcgis/rest/services/"
            "Tidal_Crown_Estate_Scotland/FeatureServer/0"
        ),
    },
    {
        "id": "ccs",
        "label": "Carbon Capture Storage",
        "url": (
            "https://services3.arcgis.com/nGV4jiurzcahJ9LV/arcgis/rest/services/"
            "CCS_Crown_Estate_Scotland/FeatureServer/0"
        ),
    },
]


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


def _themes() -> list[dict[str, str]]:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    configured = (sources.get("crown_estate_leases") or {}).get("themes")
    if isinstance(configured, list) and configured:
        return [
            {
                "id": str(item["id"]),
                "label": str(item.get("label") or item["id"]),
                "url": str(item["url"]),
            }
            for item in configured
            if item.get("id") and item.get("url")
        ]
    return DEFAULT_THEMES


def _ensure_table(conn) -> None:
    sql_path = REPO_ROOT / "backend" / "db" / "schema" / "011_open_energy_leases.sql"
    with conn.cursor() as cur:
        cur.execute(sql_path.read_text(encoding="utf-8"))
    conn.commit()


def _as_multipolygon(geom: BaseGeometry) -> MultiPolygon | None:
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "MultiPolygon":
        return geom  # type: ignore[return-value]
    if geom.geom_type == "Polygon":
        return MultiPolygon([geom])
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            return None
        parts = []
        for g in polys:
            if g.geom_type == "Polygon":
                parts.append(g)
            else:
                parts.extend(list(g.geoms))
        return MultiPolygon(parts) if parts else None
    return None


def _fetch_theme(theme: dict[str, str]) -> list[dict[str, Any]]:
    base = theme["url"].rstrip("/")
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 200
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        while True:
            params = {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "geojson",
            }
            response = client.get(f"{base}/query", params=params)
            response.raise_for_status()
            payload = response.json()
            features = payload.get("features") or []
            if not features:
                break
            for feat in features:
                props = feat.get("properties") or {}
                geom_raw = feat.get("geometry")
                if not geom_raw:
                    continue
                try:
                    geom = _as_multipolygon(shape(geom_raw))
                except Exception:
                    continue
                if geom is None:
                    continue
                object_id = (
                    props.get("OBJECTID")
                    or props.get("OBJECTID_1")
                    or props.get("FID")
                    or props.get("GlobalID")
                    or len(rows)
                )
                capacity_raw = props.get("Capacity_MW") or props.get("CapacityMW")
                try:
                    capacity_mw = float(capacity_raw) if capacity_raw is not None else None
                except (TypeError, ValueError):
                    capacity_mw = None
                rows.append(
                    {
                        "id": f"{theme['id']}:{object_id}",
                        "lease_theme": theme["id"],
                        "description": props.get("Property_Description")
                        or props.get("Description")
                        or props.get("NAME"),
                        "tenant_name": props.get("Tenant_Name") or props.get("Tenant"),
                        "agreement_type": props.get("Lease_Type_Description")
                        or props.get("Agreement_Type")
                        or props.get("AgreementType"),
                        "property_classification": props.get("Property_Classification")
                        or props.get("Classification"),
                        "project_phase": props.get("Project_Phase")
                        or props.get("ProjectPhase"),
                        "capacity_mw": capacity_mw,
                        "geom_geojson": json.dumps(geom.__geo_interface__),
                    }
                )
            if len(features) < page_size:
                break
            offset += page_size
            if offset > 20_000:
                break
    return rows


def ingest(*, replace: bool = True) -> dict[str, Any]:
    retrieved = date.today()
    themes = _themes()
    all_rows: list[dict[str, Any]] = []
    per_theme: dict[str, int] = {}
    for theme in themes:
        theme_rows = _fetch_theme(theme)
        per_theme[theme["id"]] = len(theme_rows)
        all_rows.extend(theme_rows)

    conn = _db_connect()
    try:
        _ensure_table(conn)
        with conn.cursor() as cur:
            if replace:
                cur.execute(f"TRUNCATE {TABLE}")
            execute_batch(
                cur,
                f"""
                INSERT INTO {TABLE} (
                  id, lease_theme, description, tenant_name, agreement_type,
                  property_classification, project_phase, capacity_mw,
                  geom, retrieved_at
                ) VALUES (
                  %(id)s, %(lease_theme)s, %(description)s, %(tenant_name)s,
                  %(agreement_type)s, %(property_classification)s, %(project_phase)s,
                  %(capacity_mw)s,
                  ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geom_geojson)s), 4326)),
                  %(retrieved_at)s
                )
                ON CONFLICT (id) DO UPDATE SET
                  lease_theme = EXCLUDED.lease_theme,
                  description = EXCLUDED.description,
                  tenant_name = EXCLUDED.tenant_name,
                  agreement_type = EXCLUDED.agreement_type,
                  property_classification = EXCLUDED.property_classification,
                  project_phase = EXCLUDED.project_phase,
                  capacity_mw = EXCLUDED.capacity_mw,
                  geom = EXCLUDED.geom,
                  retrieved_at = EXCLUDED.retrieved_at
                """,
                [{**row, "retrieved_at": retrieved} for row in all_rows],
                page_size=200,
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "table": TABLE,
        "rows": len(all_rows),
        "themes": per_theme,
        "retrieved_at": retrieved.isoformat(),
        "licence": "OGL-3.0",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replace",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="TRUNCATE before load (default: true)",
    )
    args = parser.parse_args()
    print(ingest(replace=args.replace))


if __name__ == "__main__":
    main()
