from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.prepared import prep

from spatial.council_names import official_council_name

REPO_ROOT = Path(__file__).resolve().parents[2]
COUNCILS_GEOJSON_PATH = REPO_ROOT / "data" / "processed" / "scotland_councils.geojson"
WARD_18_PATH = REPO_ROOT / "data" / "processed" / "glasgow_ward_18.geojson"


@dataclass(frozen=True)
class BoundaryMatch:
    hpi_code: str
    name: str
    boundary_code: str


@dataclass(frozen=True)
class WardMatch:
    ward_number: int
    ward_name: str
    ward_code: str
    council: str


@lru_cache(maxsize=1)
def _council_index() -> list[tuple[BoundaryMatch, object]]:
    if not COUNCILS_GEOJSON_PATH.exists():
        raise FileNotFoundError(
            f"Missing {COUNCILS_GEOJSON_PATH}. Run: cd backend && python -m etl.build_boundaries"
        )
    with COUNCILS_GEOJSON_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    index: list[tuple[BoundaryMatch, object]] = []
    for feature in payload["features"]:
        props = feature["properties"]
        hpi_code = props["hpi_code"]
        # GeoJSON may still carry UK HPI aliases ("City of Glasgow"); always
        # expose the official NRS/SG council area name on the place card.
        name = official_council_name(hpi_code, props.get("name")) or props["name"]
        match = BoundaryMatch(
            hpi_code=hpi_code,
            name=name,
            boundary_code=props["boundary_code"],
        )
        index.append((match, prep(shape(feature["geometry"]))))
    return index


@lru_cache(maxsize=1)
def _ward_18_geometry():
    if not WARD_18_PATH.exists():
        return None, None
    with WARD_18_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    feature = payload["features"][0]
    props = feature["properties"]
    ward = WardMatch(
        ward_number=props["ward_number"],
        ward_name=props["ward_name"],
        ward_code=props["ward_code"],
        council=props["council"],
    )
    return ward, prep(shape(feature["geometry"]))


def lookup_council_boundary(lat: float, lng: float) -> BoundaryMatch | None:
    point = Point(lng, lat)
    for match, prepared in _council_index():
        if prepared.contains(point):
            return match
    return None


def lookup_glasgow_ward_18(lat: float, lng: float) -> WardMatch | None:
    ward, prepared = _ward_18_geometry()
    if ward is None or prepared is None:
        return None
    if prepared.contains(Point(lng, lat)):
        return ward
    return None