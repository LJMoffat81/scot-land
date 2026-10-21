"""Fetch adapters for the ARCH-1 layer ingest pipeline."""

from __future__ import annotations

from etl.adapters.arcgis import fetch_arcgis
from etl.adapters.geojson_file import fetch_geojson_file

__all__ = ["fetch_arcgis", "fetch_geojson_file"]
