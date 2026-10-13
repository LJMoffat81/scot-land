"""NRS Census 2022 Settlements and Localities (OGL) — PostGIS bbox routes.

Plain place polygons only — no land value or rent attached.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.common import _scotland_bounds_check
from layers.nrs_places import LayerUnavailable, lookup_at, query_bbox

router = APIRouter(tags=["nrs-places"])


def _bbox_response(kind: str, south: float, west: float, north: float, east: float, max_features: int):
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    if south >= north or west >= east:
        raise HTTPException(
            status_code=400,
            detail="Invalid bbox: require south < north and west < east",
        )
    try:
        return JSONResponse(
            query_bbox(kind, south, west, north, east, max_features=max_features)
        )
    except LayerUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/layers/open/settlements")
def layer_open_settlements(
    south: float = Query(...),
    west: float = Query(...),
    north: float = Query(...),
    east: float = Query(...),
    max_features: int = Query(default=200, ge=1, le=200),
) -> JSONResponse:
    """NRS Census 2022 Settlements in the viewport (PostGIS). 503 when unloaded."""
    return _bbox_response("settlements", south, west, north, east, max_features)


@router.get("/layers/open/localities")
def layer_open_localities(
    south: float = Query(...),
    west: float = Query(...),
    north: float = Query(...),
    east: float = Query(...),
    max_features: int = Query(default=200, ge=1, le=200),
) -> JSONResponse:
    """NRS Census 2022 Localities in the viewport (PostGIS). 503 when unloaded."""
    return _bbox_response("localities", south, west, north, east, max_features)


@router.get("/layers/open/settlements/at")
def layer_settlement_at(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
) -> JSONResponse:
    """Settlement containing a point (when PostGIS ingest is loaded)."""
    _scotland_bounds_check(lat, lng)
    hit = lookup_at("settlements", lat, lng)
    return JSONResponse(
        {
            "ok": True,
            "found": hit is not None,
            "settlement": hit,
            "note": (
                None
                if hit is not None
                else "No settlement polygon at this point, or NRS settlements not loaded."
            ),
        }
    )


@router.get("/layers/open/localities/at")
def layer_locality_at(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
) -> JSONResponse:
    """Locality containing a point (when PostGIS ingest is loaded)."""
    _scotland_bounds_check(lat, lng)
    hit = lookup_at("localities", lat, lng)
    return JSONResponse(
        {
            "ok": True,
            "found": hit is not None,
            "locality": hit,
            "note": (
                None
                if hit is not None
                else "No locality polygon at this point, or NRS localities not loaded."
            ),
        }
    )
