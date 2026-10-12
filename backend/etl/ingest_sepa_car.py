"""Ingest SEPA CAR licences from OGL MapServer into PostGIS.

Default (one command)::

    python -m etl.ingest_sepa_car

Fetches Open/SEPA_Reference MapServer layers **194** (CAR Simple Licenced
Site) and **195** (CAR Registration) from map.sepa.org.uk, with retry/backoff,
and loads them into ``sepa_car_licences``.

The public API must serve PostGIS only — never proxy MapServer to clients.
Does not write under ``data/external``.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import psycopg2
import yaml
from psycopg2.extras import execute_batch

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
TABLE = "sepa_car_licences"
SCHEMA_SQL = REPO_ROOT / "backend" / "db" / "schema" / "006_hydro_sepa_car.sql"

DEFAULT_MAPSERVER = (
    "https://map.sepa.org.uk/server/rest/services/Open/SEPA_Reference/MapServer"
)
DEFAULT_LAYERS = (
    {"id": 194, "car_layer": "simple", "label": "CAR Simple Licenced Site"},
    {"id": 195, "car_layer": "registration", "label": "CAR Registration"},
)
PAGE_SIZE = 1000
MAX_RETRIES = 5
BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 16.0)
OUT_FIELDS = (
    "authorisation_no,authorisation_holder,authorisation_description,"
    "authorisation_status,authorisation_level,category,regulatory_area,"
    "authorisation_activity,representative_ngr,easting,northing"
)


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


def _config() -> dict[str, Any]:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle) or {}
    return sources.get("sepa_car") or {}


def _ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, Any],
    max_retries: int = MAX_RETRIES,
    backoff: tuple[float, ...] = BACKOFF_SECONDS,
) -> httpx.Response:
    """GET with exponential backoff on timeouts / 429 / 5xx."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.get(url, params=params)
            if response.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError(
                    f"retryable status {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt >= max_retries - 1:
                break
            delay = backoff[min(attempt, len(backoff) - 1)]
            logger.warning(
                "SEPA MapServer request failed (attempt %s/%s): %s; retry in %.1fs",
                attempt + 1,
                max_retries,
                exc,
                delay,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def feature_to_row(feat: dict[str, Any], car_layer: str) -> dict[str, Any] | None:
    """Map one GeoJSON feature to a PostGIS row dict (no network)."""
    props = feat.get("properties") or {}
    auth_no = str(props.get("authorisation_no") or "").strip()
    if not auth_no:
        return None
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates") if geom.get("type") == "Point" else None
    lng = lat = None
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        lng, lat = float(coords[0]), float(coords[1])
        if not (54.4 <= lat <= 61.0 and -9.0 <= lng <= 0.2):
            lng = lat = None
    status = str(props.get("authorisation_status") or "").strip() or None
    publication_status = "ok" if (lng is not None or status) else "blocked"
    return {
        "authorisation_no": auth_no,
        "car_layer": car_layer,
        "authorisation_holder": str(props.get("authorisation_holder") or "").strip()
        or None,
        "authorisation_description": str(
            props.get("authorisation_description") or ""
        ).strip()
        or None,
        "authorisation_level": str(props.get("authorisation_level") or "").strip()
        or None,
        "authorisation_status": status,
        "regulatory_area": str(props.get("regulatory_area") or "").strip() or None,
        "authorisation_activity": str(props.get("authorisation_activity") or "").strip()
        or None,
        "category": str(props.get("category") or "").strip() or None,
        "ngr": str(props.get("representative_ngr") or "").strip() or None,
        "easting": _as_int(props.get("easting")),
        "northing": _as_int(props.get("northing")),
        "value_tier": "market",
        "publication_status": publication_status,
        "lng": lng,
        "lat": lat,
    }


def fetch_layer_features(
    client: httpx.Client,
    mapserver: str,
    layer_id: int,
    *,
    page_size: int = PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Page GeoJSON from a MapServer layer (ingest-time only)."""
    features: list[dict[str, Any]] = []
    offset = 0
    query_url = f"{mapserver.rstrip('/')}/{layer_id}/query"
    while True:
        response = get_with_retry(
            client,
            query_url,
            params={
                "where": "1=1",
                "outFields": OUT_FIELDS,
                "returnGeometry": "true",
                "outSR": 4326,
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "geojson",
            },
        )
        payload = response.json()
        batch = payload.get("features") or []
        if not batch:
            break
        features.extend(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)
        if offset > 500_000:
            break
    return features


def rows_from_features(
    features: list[dict[str, Any]], car_layer: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feat in features:
        row = feature_to_row(feat, car_layer)
        if row:
            rows.append(row)
    return rows


def ingest(*, replace: bool = True) -> dict[str, Any]:
    """Fetch MapServer 194/195 and load PostGIS. One-command default path."""
    cfg = _config()
    mapserver = cfg.get("mapserver_url") or DEFAULT_MAPSERVER
    layers = cfg.get("mapserver_layers") or list(DEFAULT_LAYERS)
    retrieved = date.today()
    rows: list[dict[str, Any]] = []

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        for layer in layers:
            layer_id = int(layer["id"])
            car_layer = str(layer["car_layer"])
            features = fetch_layer_features(client, mapserver, layer_id)
            rows.extend(rows_from_features(features, car_layer))
            logger.info(
                "SEPA CAR layer %s (%s): %s features",
                layer_id,
                car_layer,
                len(features),
            )

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
                  authorisation_no, car_layer, authorisation_holder,
                  authorisation_description, authorisation_level,
                  authorisation_status, regulatory_area, authorisation_activity,
                  category, ngr, easting, northing, value_tier,
                  publication_status, geom, retrieved_at
                ) VALUES (
                  %(authorisation_no)s, %(car_layer)s, %(authorisation_holder)s,
                  %(authorisation_description)s, %(authorisation_level)s,
                  %(authorisation_status)s, %(regulatory_area)s,
                  %(authorisation_activity)s, %(category)s, %(ngr)s,
                  %(easting)s, %(northing)s, %(value_tier)s,
                  %(publication_status)s,
                  CASE
                    WHEN %(lng)s IS NULL THEN NULL
                    ELSE ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)
                  END,
                  %(retrieved_at)s
                )
                ON CONFLICT (authorisation_no, car_layer) DO UPDATE SET
                  authorisation_holder = EXCLUDED.authorisation_holder,
                  authorisation_description = EXCLUDED.authorisation_description,
                  authorisation_level = EXCLUDED.authorisation_level,
                  authorisation_status = EXCLUDED.authorisation_status,
                  regulatory_area = EXCLUDED.regulatory_area,
                  authorisation_activity = EXCLUDED.authorisation_activity,
                  category = EXCLUDED.category,
                  ngr = EXCLUDED.ngr,
                  easting = EXCLUDED.easting,
                  northing = EXCLUDED.northing,
                  value_tier = EXCLUDED.value_tier,
                  publication_status = EXCLUDED.publication_status,
                  geom = EXCLUDED.geom,
                  retrieved_at = EXCLUDED.retrieved_at
                """,
                [{**row, "retrieved_at": retrieved} for row in rows],
                page_size=500,
            )
        conn.commit()
    finally:
        conn.close()

    with_geom = sum(1 for row in rows if row["lng"] is not None)
    return {
        "table": TABLE,
        "rows": len(rows),
        "rows_with_geometry": with_geom,
        "layers": [dict(layer) for layer in layers],
        "retrieved_at": retrieved.isoformat(),
        "licence": "OGL-3.0",
        "value_tier": "market",
        "commons_class": "extractive",
        "publication_status": "ok",
        "command": "python -m etl.ingest_sepa_car",
        "note": (
            "Ingested from SEPA_Reference MapServer 194/195 into PostGIS. "
            "Public API must not proxy MapServer."
        ),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description=(
            "Load SEPA CAR licences from OGL MapServer 194/195 into PostGIS. "
            "One command: python -m etl.ingest_sepa_car"
        )
    )
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
