"""Helpers shared by the Wealth, AGR and platform routers. No AGR imports here."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from paths import CONFIG_DIR, PROCESSED_DIR

SOURCES_PATH = CONFIG_DIR / "sources.yaml"
COUNCILS_GEOJSON = PROCESSED_DIR / "scotland_councils.geojson"
WARD_18_GEOJSON = PROCESSED_DIR / "glasgow_ward_18.geojson"


def _load_postcode_api_url() -> str:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        sources = yaml.safe_load(handle)
    return sources["postcodes"]["api_url"]


def _scotland_bounds_check(lat: float, lng: float) -> None:
    if lat < 54.5 or lat > 61.0 or lng < -8.5 or lng > -0.5:
        raise HTTPException(status_code=400, detail="Coordinates appear to be outside Scotland.")


def _load_geojson(path: Path) -> JSONResponse:
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Missing {path.name}. Run the Phase 3 ETL scripts in backend/etl/.",
        )
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
