from __future__ import annotations

import json
from pathlib import Path

from agr.engine import calculate_square_agr
from spatial.grid import snap_to_w3w_grid
from spatial.polygons import lookup_council_boundary, lookup_glasgow_ward_18

REPO_ROOT = Path(__file__).resolve().parents[2]
WARD_PATH = REPO_ROOT / "data" / "processed" / "glasgow_ward_18.geojson"


def _sample_points_in_ward(count: int = 12) -> list[tuple[float, float]]:
    from shapely.geometry import shape

    with WARD_PATH.open(encoding="utf-8") as handle:
        feature = json.load(handle)["features"][0]

    geom = shape(feature["geometry"])
    minx, miny, maxx, maxy = geom.bounds
    points: list[tuple[float, float]] = []

    steps = int(count**0.5) + 2
    lat_step = (maxy - miny) / steps
    lng_step = (maxx - minx) / steps

    for i in range(steps):
        for j in range(steps):
            lng = minx + (j + 0.5) * lng_step
            lat = miny + (i + 0.5) * lat_step
            from shapely.geometry import Point

            if geom.contains(Point(lng, lat)):
                points.append((lat, lng))
            if len(points) >= count:
                return points

    centroid = geom.centroid
    return [(centroid.y, centroid.x)]


def run_validation(sample_count: int = 12) -> dict:
    ward_feature = json.loads(WARD_PATH.read_text(encoding="utf-8"))["features"][0]
    ward_props = ward_feature["properties"]
    samples = _sample_points_in_ward(sample_count)

    results: list[dict] = []
    for lat, lng in samples:
        square = snap_to_w3w_grid(lat, lng)
        breakdown = calculate_square_agr(square)
        ward = lookup_glasgow_ward_18(square.lat, square.lng)
        council = lookup_council_boundary(square.lat, square.lng)

        results.append(
            {
                "lat": square.lat,
                "lng": square.lng,
                "in_ward": ward is not None,
                "council_code": council.hpi_code if council else None,
                "annual_ground_rent_gbp": breakdown.annual_ground_rent_gbp,
                "confidence": breakdown.confidence,
            }
        )

    agr_values = [item["annual_ground_rent_gbp"] for item in results]
    in_ward = sum(1 for item in results if item["in_ward"])
    glasgow = sum(1 for item in results if item["council_code"] == "S12000049")

    return {
        "ward": ward_props,
        "samples_tested": len(results),
        "samples_in_ward": in_ward,
        "samples_in_glasgow": glasgow,
        "agr_min_gbp": min(agr_values),
        "agr_max_gbp": max(agr_values),
        "agr_mean_gbp": round(sum(agr_values) / len(agr_values), 2),
        "all_in_ward": in_ward == len(results),
        "all_in_glasgow": glasgow == len(results),
        "samples": results,
        "status": "pass" if in_ward == len(results) and glasgow == len(results) else "review",
    }