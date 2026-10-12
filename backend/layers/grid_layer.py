"""Viewport Scot-LAND squares layer — AGR for every snapped cell in a bbox (capped)."""

from __future__ import annotations

import math
from typing import Any

from agr.service import ValuationService
from spatial.grid import (
    METERS_PER_DEGREE_LAT,
    W3W_SQUARE_SIZE_M,
    snap_to_w3w_grid,
)


def _step_degrees(lat: float) -> tuple[float, float]:
    lat_step = W3W_SQUARE_SIZE_M / METERS_PER_DEGREE_LAT
    lng_step = W3W_SQUARE_SIZE_M / (METERS_PER_DEGREE_LAT * max(math.cos(math.radians(lat)), 0.2))
    return lat_step, lng_step


def estimate_cell_count(south: float, west: float, north: float, east: float) -> int:
    mid_lat = (south + north) / 2
    lat_step, lng_step = _step_degrees(mid_lat)
    n_lat = max(1, int(math.ceil((north - south) / lat_step)))
    n_lng = max(1, int(math.ceil((east - west) / lng_step)))
    return n_lat * n_lng


def build_w3w_agr_grid(
    south: float,
    west: float,
    north: float,
    east: float,
    *,
    scenario: str = "full_agr",
    max_cells: int = 500,
    service: ValuationService | None = None,
) -> dict[str, Any]:
    """Return GeoJSON of Scot-LAND squares with AGR properties for a bounding box.

    Scotland has ~billions of 3 m cells; this builds only the viewport (capped).
    """
    if south >= north or west >= east:
        raise ValueError("Invalid bbox: require south < north and west < east")

    # Clamp to Scotland-ish envelope
    south = max(south, 54.5)
    north = min(north, 61.0)
    west = max(west, -8.5)
    east = min(east, -0.5)

    raw_count = estimate_cell_count(south, west, north, east)
    stride = 1
    if raw_count > max_cells:
        stride = int(math.ceil(math.sqrt(raw_count / max_cells)))

    mid_lat = (south + north) / 2
    lat_step, lng_step = _step_degrees(mid_lat)
    lat_step *= stride
    lng_step *= stride

    service = service or ValuationService.default()
    features: list[dict[str, Any]] = []
    seen: set[tuple[float, float]] = set()

    lat = south + lat_step / 2
    while lat < north and len(features) < max_cells:
        lng = west + lng_step / 2
        while lng < east and len(features) < max_cells:
            square = snap_to_w3w_grid(lat, lng)
            key = (round(square.lat, 7), round(square.lng, 7))
            if key in seen:
                lng += lng_step
                continue
            seen.add(key)
            try:
                breakdown = service.assess_square(square, scenario=scenario)
            except Exception:
                lng += lng_step
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": square.geojson_polygon,
                    "properties": {
                        "lat": square.lat,
                        "lng": square.lng,
                        "area_sqm": square.area_sqm,
                        "annual_ground_rent_gbp": breakdown.annual_ground_rent_gbp,
                        "economic_annual_rent_gbp": breakdown.economic_annual_rent_gbp,
                        "plot_agr_gbp": breakdown.roll_annual_rent_notional_plot_gbp,
                        "site_rental_per_sqm_gbp": breakdown.site_rental_per_sqm_gbp,
                        "council_code": breakdown.council_code,
                        "council_name": breakdown.council_name,
                        "method": breakdown.method,
                        "confidence": breakdown.confidence,
                        "scenario": scenario,
                    },
                }
            )
            lng += lng_step
        lat += lat_step

    rents = [f["properties"]["annual_ground_rent_gbp"] for f in features]
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "layer": "w3w_agr_grid",
            "scenario": scenario,
            "bbox": [west, south, east, north],
            "cell_count": len(features),
            "estimated_full_cells": raw_count,
            "stride": stride,
            "max_cells": max_cells,
            "sampled": stride > 1,
            "agr_min_gbp": min(rents) if rents else None,
            "agr_max_gbp": max(rents) if rents else None,
            "note": (
                "Viewport Scot-LAND squares only. Full Scotland at 3 m is "
                "~billions of cells; use stride/sampling when the bbox is large. "
                "Zoom in for denser coverage."
            ),
            "status": "research_estimate",
        },
    }
