"""Fetch adapters for the ARCH-1 / ARCH-2a layer ingest pipeline."""

from __future__ import annotations

from etl.adapters.arcgis import fetch_arcgis
from etl.adapters.geojson_file import fetch_geojson_file
from etl.adapters.postgis_table import fetch_postgis_table

__all__ = ["fetch_arcgis", "fetch_geojson_file", "fetch_postgis_table"]
