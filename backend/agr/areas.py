from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from spatial.polygons import lookup_council_boundary
from spatial.urban_rural import is_rural_point

REPO_ROOT = Path(__file__).resolve().parents[2]
COUNCILS_PATH = REPO_ROOT / "data" / "processed" / "councils.json"


@dataclass(frozen=True)
class CouncilArea:
    code: str
    name: str
    average_price_gbp: int
    annual_change_pct: float | None
    rural: bool
    distance_km: float
    lookup_method: str


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return radius_km * 2 * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def _load_councils() -> list[dict]:
    if not COUNCILS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {COUNCILS_PATH}. Run: cd backend && python -m etl.build_processed"
        )
    with COUNCILS_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload["councils"]


@lru_cache(maxsize=1)
def _councils_by_code() -> dict[str, dict]:
    return {council["code"]: council for council in _load_councils()}


def _from_boundary(lat: float, lng: float, boundary_match) -> CouncilArea | None:
    council = _councils_by_code().get(boundary_match.hpi_code)
    if council is None:
        return None
    return CouncilArea(
        code=council["code"],
        name=council["name"],
        average_price_gbp=council["average_price_gbp"],
        annual_change_pct=council.get("annual_change_pct"),
        rural=is_rural_point(lat, lng),
        distance_km=0.0,
        lookup_method="boundary",
    )


def _from_centroid(lat: float, lng: float) -> CouncilArea:
    councils = _load_councils()
    best: dict | None = None
    best_distance = float("inf")

    for council in councils:
        centroid = council["centroid"]
        distance = _haversine_km(lat, lng, centroid["lat"], centroid["lng"])
        if distance < best_distance:
            best = council
            best_distance = distance

    if best is None:
        raise RuntimeError("No Scottish council areas loaded")

    return CouncilArea(
        code=best["code"],
        name=best["name"],
        average_price_gbp=best["average_price_gbp"],
        annual_change_pct=best.get("annual_change_pct"),
        rural=is_rural_point(lat, lng),
        distance_km=round(best_distance, 2),
        lookup_method="centroid_fallback",
    )


def lookup_council(lat: float, lng: float) -> CouncilArea:
    boundary_match = lookup_council_boundary(lat, lng)
    if boundary_match is not None:
        council = _from_boundary(lat, lng, boundary_match)
        if council is not None:
            return council
    return _from_centroid(lat, lng)