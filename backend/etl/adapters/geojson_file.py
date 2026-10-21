"""Load a local GeoJSON FeatureCollection for offline ingest / tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def fetch_geojson_file(path: Path | str) -> tuple[dict[str, Any], bytes, str]:
    """Return ``(collection, raw_bytes, redacted_url)`` for a local file.

    Raises ``RuntimeError`` with an ``INGEST:``-ready message on bad input.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise RuntimeError(f"geojson file missing: {file_path}")
    raw = file_path.read_bytes()
    try:
        collection = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"geojson file not JSON: {file_path}") from exc
    if not isinstance(collection, dict):
        raise RuntimeError(f"geojson file not a FeatureCollection: {file_path}")
    features = collection.get("features")
    if not isinstance(features, list):
        collection = {"type": "FeatureCollection", "features": []}
    return collection, raw, f"file://{file_path.resolve()}"
