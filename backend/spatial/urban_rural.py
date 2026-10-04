"""Per-point Scottish Government Urban Rural Classification 2022.

Source: https://maps.gov.scot/ATOM/shapefiles/SG_UrbanRural_2022.zip
Open Government Licence v3.0. Copyright Scottish Government, contains
Ordnance Survey data © Crown copyright and database right 2022.

The lookup keeps classes 1-4 (urban). A point on land outside those polygons
is countryside. A point outside the Scottish council boundary is not land.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.prepared import prep

PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "processed"
    / "sg_urban_rural_2022_urban_20m.geojson"
)


class NotLand(Exception):
    """The point is outside the Scottish land boundary."""

    def __init__(self, lat: float, lng: float):
        self.lat = lat
        self.lng = lng
        super().__init__("not_land")


@lru_cache(maxsize=1)
def _urban_polygons():
    payload = json.loads(PATH.read_text(encoding="utf-8"))
    prepared = []
    for feature in payload["features"]:
        prepared.append(prep(shape(feature["geometry"])))
    return prepared


@lru_cache(maxsize=1)
def _to_bng():
    return Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)


@lru_cache(maxsize=4096)
def is_urban_point(lat: float, lng: float) -> bool:
    """True when the point falls inside any class 1-4 polygon."""
    x, y = _to_bng().transform(lng, lat)
    point = Point(x, y)
    return any(polygon.contains(point) for polygon in _urban_polygons())


def is_rural_point(lat: float, lng: float) -> bool:
    return not is_urban_point(round(lat, 6), round(lng, 6))
