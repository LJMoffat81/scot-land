"""Ingest OGL Local Development Plan allocation polygons into PostGIS.

Raw Spatial Hub ZIPs and authority downloads stay under data/external/ldp/
(gitignored). This script never commits geometry — it loads a local GeoJSON
or pulls a configured OGL FeatureServer into ``ldp_allocations``.

Usage:
  export DATABASE_URL=postgresql://...
  # Local GeoJSON (WGS84 FeatureCollection):
  python -m etl.ingest_ldp_allocations \\
    --input ../data/external/ldp/allocations.geojson \\
    --authority "Highland"

  # Configured OGL FeatureServer seed (Highland Council under OGL-3.0):
  python -m etl.ingest_ldp_allocations --from-config
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import psycopg2
import yaml
from psycopg2 import extras

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
TABLE = "ldp_allocations"
DEFAULT_INPUT = REPO_ROOT / "data" / "external" / "ldp" / "allocations.geojson"
TIMEOUT = 60.0


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
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                site_id TEXT PRIMARY KEY,
                authority TEXT NOT NULL,
                allocation TEXT,
                code TEXT,
                plan_source TEXT,
                hectares DOUBLE PRECISION,
                licence TEXT NOT NULL DEFAULT 'OGL-3.0',
                source_url TEXT,
                geom GEOMETRY(MultiPolygon, 4326) NOT NULL
            );
            """
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_geom ON {TABLE} USING GIST (geom);"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_authority ON {TABLE} (authority);"
        )
    conn.commit()


def _props(feature: dict[str, Any]) -> dict[str, Any]:
    return feature.get("properties") or {}


def _site_id(props: dict[str, Any], authority: str, index: int) -> str:
    for key in ("site_id", "code", "Id", "OBJECTID", "OBJECTID_12"):
        val = props.get(key)
        if val is not None and str(val).strip():
            return f"{authority}:{val}"
    return f"{authority}:row-{index}"


def _hectares(props: dict[str, Any], geom_json: dict[str, Any] | None) -> float | None:
    for key in ("hectares", "ha", "site_size", "Shape__Area"):
        raw = props.get(key)
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if key == "Shape__Area":
            # ArcGIS Shape__Area on Highland layer is in CRS units (m² for BNG-derived).
            return val / 10_000.0
        return val
    return None


def features_from_geojson(
    collection: dict[str, Any],
    *,
    authority: str,
    licence: str,
    source_url: str,
) -> list[dict[str, Any]]:
    if collection.get("type") != "FeatureCollection":
        raise ValueError("input must be a GeoJSON FeatureCollection")
    out = []
    for i, feat in enumerate(collection.get("features") or []):
        geom = feat.get("geometry")
        if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        props = _props(feat)
        out.append(
            {
                "site_id": _site_id(props, authority, i),
                "authority": authority,
                "allocation": props.get("allocation") or props.get("ALLOCATION") or props.get("type"),
                "code": props.get("code") or props.get("CODE"),
                "plan_source": props.get("source") or props.get("plan_source") or authority,
                "hectares": _hectares(props, geom),
                "licence": licence,
                "source_url": source_url,
                "geometry": geom,
            }
        )
    return out


def fetch_featureserver(
    query_url: str,
    *,
    authority: str,
    licence: str,
    source_url: str,
    max_records: int = 2000,
) -> list[dict[str, Any]]:
    """Pull an OGL ArcGIS FeatureServer layer as GeoJSON (outSR=4326)."""
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
        "resultRecordCount": str(max_records),
    }
    with httpx.Client(timeout=TIMEOUT) as client:
        response = client.get(query_url, params=params)
        response.raise_for_status()
        payload = response.json()
    return features_from_geojson(
        payload, authority=authority, licence=licence, source_url=source_url,
    )


def upsert_rows(conn, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = f"""
        INSERT INTO {TABLE} (
            site_id, authority, allocation, code, plan_source, hectares,
            licence, source_url, geom
        ) VALUES (
            %(site_id)s, %(authority)s, %(allocation)s, %(code)s, %(plan_source)s,
            %(hectares)s, %(licence)s, %(source_url)s,
            ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geom_json)s), 4326))
        )
        ON CONFLICT (site_id) DO UPDATE SET
            authority = EXCLUDED.authority,
            allocation = EXCLUDED.allocation,
            code = EXCLUDED.code,
            plan_source = EXCLUDED.plan_source,
            hectares = EXCLUDED.hectares,
            licence = EXCLUDED.licence,
            source_url = EXCLUDED.source_url,
            geom = EXCLUDED.geom
    """
    payload = []
    for row in rows:
        payload.append(
            {
                **{k: row[k] for k in (
                    "site_id", "authority", "allocation", "code", "plan_source",
                    "hectares", "licence", "source_url",
                )},
                "geom_json": json.dumps(row["geometry"]),
            }
        )
    with conn.cursor() as cur:
        extras.execute_batch(cur, sql, payload, page_size=200)
    conn.commit()
    return len(payload)


def write_stamp(path: Path, *, n: int, authority: str) -> None:
    stamp = {
        "ingested_on": date.today().isoformat(),
        "rows": n,
        "authority": authority,
        "table": TABLE,
    }
    path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")


def load_sources() -> dict[str, Any]:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        return (yaml.safe_load(handle) or {}).get("ldp_allocations") or {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None, help="Local GeoJSON FeatureCollection")
    parser.add_argument("--authority", type=str, default="unknown", help="Planning authority label")
    parser.add_argument("--from-config", action="store_true", help="Fetch configured OGL FeatureServers")
    parser.add_argument("--replace-authority", action="store_true",
                        help="Delete existing rows for the authority before insert")
    args = parser.parse_args(argv)

    cfg = load_sources()
    licence = cfg.get("licence") or "OGL-3.0"
    conn = connect()
    ensure_table(conn)

    total = 0
    if args.from_config:
        for seed in cfg.get("ingest_seeds") or []:
            lic = str(seed.get("licence") or "")
            if "OGL" not in lic.upper():
                logger.warning("Skipping non-OGL seed %s", seed.get("id"))
                continue
            authority = seed.get("authority") or seed.get("id") or "unknown"
            query_url = seed.get("feature_server_query") or (
                (seed.get("feature_server") or "").rstrip("/") + "/0/query"
            )
            if not query_url.endswith("/query"):
                query_url = query_url.rstrip("/") + "/query"
            logger.info("Fetching OGL seed %s from %s", seed.get("id"), query_url)
            rows = fetch_featureserver(
                query_url,
                authority=authority,
                licence=seed.get("licence") or licence,
                source_url=seed.get("source_url") or seed.get("feature_server") or "",
            )
            if args.replace_authority:
                with conn.cursor() as cur:
                    cur.execute(f"DELETE FROM {TABLE} WHERE authority = %s", (authority,))
                conn.commit()
            n = upsert_rows(conn, rows)
            total += n
            logger.info("Upserted %s rows for %s", n, authority)
    elif args.input:
        path = args.input
        if not path.exists():
            raise SystemExit(f"input not found: {path}")
        collection = json.loads(path.read_text(encoding="utf-8"))
        rows = features_from_geojson(
            collection,
            authority=args.authority,
            licence=licence,
            source_url=str(path),
        )
        if args.replace_authority:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {TABLE} WHERE authority = %s", (args.authority,))
            conn.commit()
        total = upsert_rows(conn, rows)
        stamp = path.with_suffix(path.suffix + ".ingest.json")
        write_stamp(stamp, n=total, authority=args.authority)
        logger.info("Upserted %s rows from %s", total, path)
    else:
        raise SystemExit("Provide --input PATH or --from-config")

    conn.close()
    logger.info("Done. total_upserted=%s table=%s", total, TABLE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
