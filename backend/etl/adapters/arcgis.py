"""ArcGIS FeatureServer GeoJSON paging adapter (outSR 4326)."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import httpx

from etl.build_scotland_extent import redact


def fetch_arcgis(
    url: str,
    *,
    where: str = "1=1",
    out_fields: str = "*",
    page_size: int = 1000,
    max_mb: float = 300,
    max_s: float = 600,
    token: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[dict[str, Any], bytes, str]:
    """Fetch a FeatureCollection via ArcGIS paging.

    Follows ``exceededTransferLimit`` with ``resultOffset`` / page_size.
    Returns ``(collection, raw_body_for_sha, redacted_url)``.
    Raises ``RuntimeError`` with ``budget exceeded: mb|s`` on breach
    (``run_layer`` wraps into ``IngestError`` with the layer id).
    """
    owns_client = client is None
    http = client or httpx.Client(
        timeout=httpx.Timeout(max(60.0, float(max_s)), connect=30.0),
        follow_redirects=True,
    )
    features: list[dict[str, Any]] = []
    chunks: list[bytes] = []
    offset = 0
    started = time.monotonic()
    bytes_total = 0
    logged_url = ""

    try:
        while True:
            elapsed = time.monotonic() - started
            if elapsed > float(max_s):
                raise RuntimeError("budget exceeded: s")
            params: dict[str, str] = {
                "where": where,
                "outFields": out_fields,
                "f": "geojson",
                "outSR": "4326",
                "resultRecordCount": str(page_size),
                "resultOffset": str(offset),
            }
            if token:
                params["token"] = token
            logged_url = redact(f"{url}?{urlencode(params)}")
            response = http.get(url, params=params)
            response.raise_for_status()
            body = response.content
            bytes_total += len(body)
            chunks.append(body)
            if bytes_total > float(max_mb) * 1024 * 1024:
                raise RuntimeError("budget exceeded: mb")
            payload = response.json()
            batch = payload.get("features") or []
            features.extend(batch)
            props = payload.get("properties") or {}
            exceeded = bool(payload.get("exceededTransferLimit")) or bool(
                isinstance(props, dict) and props.get("exceededTransferLimit")
            )
            if not batch or (not exceeded and len(batch) < page_size):
                break
            offset += len(batch)
    finally:
        if owns_client:
            http.close()

    collection: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": features,
    }
    raw = b"".join(chunks) if chunks else b"{}"
    return collection, raw, logged_url
