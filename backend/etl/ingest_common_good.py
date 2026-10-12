"""Ingest OGL Common Good polygons into PostGIS (common_good_sites).

Sources are declared in data/config/common_good.yaml under spatial_sources
with licence starting OGL. Non-OGL sources (e.g. Fife OS INSPIRE EUL) are
skipped — linked in the catalog only.

Usage:
  export DATABASE_URL=postgresql://...
  # From live Highland FeatureServers (OGL open map data):
  python -m etl.ingest_common_good --from-config
  # Or a local GeoJSON FeatureCollection (tests / offline):
  python -m etl.ingest_common_good --input ../data/fixtures/common_good/sample.geojson

Raw bulk downloads may also sit under data/external/common_good/ (gitignored).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
import psycopg2
import yaml
from psycopg2 import extras

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "data" / "config" / "common_good.yaml"
TABLE = "common_good_sites"
TIMEOUT = 60.0
PAGE = 500


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


def connect():
    cfg = _db_config()
    if "dsn" in cfg:
        return psycopg2.connect(cfg["dsn"])
    return psycopg2.connect(**cfg)


def ensure_table(conn) -> None:
    sql_path = REPO_ROOT / "backend" / "db" / "schema" / "018_common_good_sites.sql"
    with conn.cursor() as cur:
        cur.execute(sql_path.read_text(encoding="utf-8"))
    conn.commit()


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def ogl_spatial_sources(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for source in cfg.get("spatial_sources") or []:
        if not isinstance(source, dict):
            continue
        licence = str(source.get("licence") or "")
        if not licence.upper().startswith("OGL"):
            logger.info(
                "Skipping non-OGL spatial source %s (%s)",
                source.get("id"),
                licence or "no licence",
            )
            continue
        if source.get("ingest") is False:
            continue
        out.append(source)
    return out


def _as_multipolygon(geom: dict[str, Any] | None) -> dict[str, Any] | None:
    if not geom or not geom.get("type"):
        return None
    gtype = geom["type"]
    if gtype == "MultiPolygon":
        return geom
    if gtype == "Polygon":
        return {"type": "MultiPolygon", "coordinates": [geom["coordinates"]]}
    return None


def _feature_row(
    feature: dict[str, Any],
    *,
    source: dict[str, Any],
    default_kind: str,
) -> dict[str, Any] | None:
    props = feature.get("properties") or {}
    geom = _as_multipolygon(feature.get("geometry"))
    if not geom:
        return None
    council_code = str(source.get("council_code") or "")
    source_id = str(source.get("id") or "unknown")
    raw_id = (
        props.get("site_id")
        or props.get("HCCODE")
        or props.get("OBJECTID")
        or props.get("objectid")
        or props.get("id")
    )
    if raw_id is None:
        return None
    site_id = f"{source_id}:{raw_id}"
    area_raw = props.get("area_ha") or props.get("SiteArea") or props.get("area")
    try:
        area_ha = float(area_raw) if area_raw not in (None, "") else None
    except (TypeError, ValueError):
        area_ha = None
    return {
        "site_id": site_id,
        "council_code": council_code,
        "council_name": source.get("council_name"),
        "name": props.get("name") or props.get("Name") or props.get("DESCRIPTIO"),
        "site_kind": props.get("site_kind")
        or props.get("Description")
        or props.get("Function_")
        or default_kind,
        "account": props.get("account") or props.get("Account") or "Common Good",
        "description": props.get("description") or props.get("PLOT_NOTES") or props.get("NOTES"),
        "area_ha": area_ha,
        "source_id": source_id,
        "licence": source.get("licence") or "OGL-3.0",
        "source_url": source.get("catalog_url") or source.get("metadata_url"),
        "geom": json.dumps(geom),
    }


def features_from_geojson(
    path: Path,
    *,
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for feat in payload.get("features") or []:
        row = _feature_row(feat, source=source, default_kind="site")
        if row:
            rows.append(row)
    return rows


def features_from_feature_server(source: dict[str, Any]) -> list[dict[str, Any]]:
    base = (source.get("feature_server") or "").rstrip("/")
    if not base:
        return []
    kind = str(source.get("site_kind") or "site")
    rows: list[dict[str, Any]] = []
    offset = 0
    with httpx.Client(timeout=TIMEOUT) as client:
        while True:
            url = (
                f"{base}/query?where=1%3D1&outFields=*&returnGeometry=true"
                f"&outSR=4326&resultOffset={offset}&resultRecordCount={PAGE}"
                f"&f=geojson"
            )
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("features") or []
            if not batch:
                break
            for feat in batch:
                row = _feature_row(feat, source=source, default_kind=kind)
                if row:
                    rows.append(row)
            if len(batch) < PAGE:
                break
            offset += PAGE
    return rows


def upsert_rows(conn, rows: list[dict[str, Any]], *, replace_sources: set[str]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        for source_id in sorted(replace_sources):
            cur.execute(f"DELETE FROM {TABLE} WHERE source_id = %s", (source_id,))
        extras.execute_batch(
            cur,
            f"""
            INSERT INTO {TABLE} (
                site_id, council_code, council_name, name, site_kind, account,
                description, area_ha, source_id, licence, source_url, geom
            ) VALUES (
                %(site_id)s, %(council_code)s, %(council_name)s, %(name)s,
                %(site_kind)s, %(account)s, %(description)s, %(area_ha)s,
                %(source_id)s, %(licence)s, %(source_url)s,
                ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)
            )
            ON CONFLICT (site_id) DO UPDATE SET
                council_code = EXCLUDED.council_code,
                council_name = EXCLUDED.council_name,
                name = EXCLUDED.name,
                site_kind = EXCLUDED.site_kind,
                account = EXCLUDED.account,
                description = EXCLUDED.description,
                area_ha = EXCLUDED.area_ha,
                source_id = EXCLUDED.source_id,
                licence = EXCLUDED.licence,
                source_url = EXCLUDED.source_url,
                geom = EXCLUDED.geom
            """,
            rows,
            page_size=200,
        )
    conn.commit()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-config",
        action="store_true",
        help="Fetch every OGL spatial_source with a feature_server from common_good.yaml",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Local GeoJSON FeatureCollection (uses first OGL source metadata, or --source-id)",
    )
    parser.add_argument("--source-id", help="Override source id when loading --input")
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="TRUNCATE common_good_sites before load",
    )
    args = parser.parse_args(argv)
    if not args.from_config and not args.input:
        parser.error("Provide --from-config and/or --input")

    cfg = load_config()
    sources = ogl_spatial_sources(cfg)
    if not sources and args.input:
        sources = [
            {
                "id": args.source_id or "fixture",
                "council_code": "S12000017",
                "council_name": "Highland",
                "licence": "OGL-3.0",
                "catalog_url": "https://www.highland.gov.uk/information-performance-statistics/open-map-data",
            }
        ]

    conn = connect()
    try:
        ensure_table(conn)
        if args.truncate:
            with conn.cursor() as cur:
                cur.execute(f"TRUNCATE {TABLE}")
            conn.commit()

        total = 0
        if args.input:
            source = sources[0]
            if args.source_id:
                source = {**source, "id": args.source_id}
            rows = features_from_geojson(args.input, source=source)
            total += upsert_rows(conn, rows, replace_sources={source["id"]})
            logger.info("Loaded %s features from %s", len(rows), args.input)

        if args.from_config:
            for source in ogl_spatial_sources(cfg):
                if not source.get("feature_server"):
                    logger.info("No feature_server for %s — skip fetch", source.get("id"))
                    continue
                logger.info("Fetching %s …", source.get("id"))
                rows = features_from_feature_server(source)
                n = upsert_rows(conn, rows, replace_sources={str(source["id"])})
                total += n
                logger.info("Upserted %s rows for %s", n, source.get("id"))

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
            count = int(cur.fetchone()[0])
        logger.info("Done. common_good_sites rows=%s (batch upserted=%s)", count, total)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
