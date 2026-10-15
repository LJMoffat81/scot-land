"""RoS INSPIRE cadastral parcel routes (PR #4).

Always mounted with the Wealth core so cadastral layers work even when the
legacy AGR router is skipped for missing publication declarations.
Plain shapes only — no value or rent attached (publication geometry rule).

Public access is gated by PARCELS_PUBLIC=true (default off) via a router
dependency — do not change main.py for this flag.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from api.common import _scotland_bounds_check
from api.parcels_public import require_parcels_public
from layers.cadastral import LayerUnavailable, query_bbox as parcels_bbox
from spatial.parcels import TRANSPARENT_PNG, fetch_parcel_tile_png, lookup_parcel_geojson

router = APIRouter(
    tags=["cadastral"],
    dependencies=[Depends(require_parcels_public)],
)


def _parcel_tile_response(z: int, x: int, y: int) -> Response:
    """Always 200 + PNG so MapLibre / Next rewrites never surface tile 500s."""
    try:
        if z < 0 or z > 22 or x < 0 or y < 0:
            png = TRANSPARENT_PNG
        else:
            png = fetch_parcel_tile_png(z, x, y)
    except Exception:
        png = TRANSPARENT_PNG
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Layer-Source": "ROS-INSPIRE-CP.CadastralParcel",
        },
    )


@router.get("/layers/parcels")
def layer_parcels_bbox(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=200, ge=1, le=200),
) -> JSONResponse:
    """RoS INSPIRE Index Polygons in the viewport (PostGIS ingest).

    Returns 503 when inspire_parcels is missing or empty — never placeholder
    geometry. When loaded, an empty viewport returns 200 with features=[]
    (including fixture-scoped CI loads). Live WMS tiles remain on
    /layers/parcels/tiles for map display.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    if south >= north or west >= east:
        raise HTTPException(
            status_code=400,
            detail="Invalid bbox: require south < north and west < east",
        )
    try:
        return JSONResponse(
            parcels_bbox(south, west, north, east, max_features=max_features)
        )
    except LayerUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/layers/parcels/tiles/{z}/{x}/{y}.png")
def layer_parcel_tiles_png(z: int, x: int, y: int) -> Response:
    """ROS INSPIRE cadastral parcels as XYZ PNG (with .png suffix)."""
    return _parcel_tile_response(z, x, y)


@router.get("/layers/parcels/tiles/{z}/{x}/{y}")
def layer_parcel_tiles(z: int, x: int, y: int) -> Response:
    """ROS INSPIRE cadastral parcels as XYZ PNG (extensionless, preferred)."""
    return _parcel_tile_response(z, x, y)


@router.get("/layers/parcels/at")
def layer_parcel_at(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
) -> JSONResponse:
    """Cadastral parcel polygon under a point (GeoJSON FeatureCollection)."""
    _scotland_bounds_check(lat, lng)
    feature = lookup_parcel_geojson(lat, lng)
    if feature is None:
        return JSONResponse(
            {
                "type": "FeatureCollection",
                "features": [],
                "meta": {"source": "ROS INSPIRE", "found": False},
            }
        )
    return JSONResponse(
        {
            "type": "FeatureCollection",
            "features": [feature],
            "meta": {
                "source": "ROS INSPIRE CP.CadastralParcel",
                "found": True,
                "label": feature["properties"].get("label"),
            },
        }
    )
