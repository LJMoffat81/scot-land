"""Open land platform HTTP routes."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from agr.export_stamp import current_stamp, stamp_comment, with_stamp
from layers.open_stats import (
    catalog_json,
    public_land_json,
    roll_json,
    vdl_councils_json,
    vdl_json,
)
from layers.platform import place_context, platform_catalog
from layers.registers import registers_payload
from layers.public_land import query_bbox as public_land_bbox
from layers.vdl import query_bbox as vdl_bbox

router = APIRouter()


def _scotland_bounds_check(lat: float, lng: float) -> None:
    if lat < 54.5 or lat > 61.0 or lng < -8.5 or lng > -0.5:
        raise HTTPException(status_code=400, detail="Coordinates appear to be outside Scotland.")


@router.get("/layers/open/vdl")
def layer_open_vdl(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """Vacant and derelict land polygons in the viewport (OGL survey overlay)."""
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    return JSONResponse(vdl_bbox(south, west, north, east, max_features=max_features))


@router.get("/layers/open/public-land")
def layer_open_public_land(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """Public and Crown Estate holdings in the viewport (SG 2024 overlay)."""
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    return JSONResponse(
        public_land_bbox(south, west, north, east, max_features=max_features)
    )


@router.get("/platform/place")
def platform_place(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    postcode: str | None = Query(default=None),
) -> dict:
    """Ownership / vacant / gap card for one point."""
    _scotland_bounds_check(lat, lng)
    return place_context(lat, lng, postcode=postcode)


@router.get("/platform/gaps")
def platform_gaps() -> dict:
    """Visible register gaps — first-class product, not hidden."""
    catalog = platform_catalog()
    return {
        "brief": catalog["brief"],
        "gaps": [layer for layer in catalog["layers"] if layer["status"] in ("gap", "linked")],
        "live": [layer for layer in catalog["layers"] if layer["status"] == "live"],
        "policy": catalog["data_policy"],
    }


@router.get("/api/catalog.json")
def api_catalog() -> dict:
    return with_stamp(catalog_json())


@router.get("/api/public-land.json")
def api_public_land() -> dict:
    return with_stamp(public_land_json())


@router.get("/api/vdl.json")
def api_vdl() -> dict:
    return with_stamp(vdl_json())


@router.get("/api/vdl-councils.json")
def api_vdl_councils(
    scenario: str = Query(default="full_agr"),
) -> dict:
    return with_stamp(vdl_councils_json(scenario))


@router.get("/api/roll.json")
def api_roll(scenario: str = Query(default="full_agr")) -> dict:
    return with_stamp(roll_json(scenario))


@router.get("/api/roll.csv")
def api_roll_csv(scenario: str = Query(default="full_agr")) -> PlainTextResponse:
    payload = roll_json(scenario)
    rows = payload.get("councils") or []
    comment = stamp_comment(current_stamp())
    cache = {"Cache-Control": "public, max-age=300"}
    if not rows:
        return PlainTextResponse(
            comment + "\n", media_type="text/csv", headers=cache
        )
    fields = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return PlainTextResponse(
        comment + "\n" + buf.getvalue(), media_type="text/csv", headers=cache
    )


@router.get("/api/place.json")
def api_place(
    pc: str | None = Query(default=None),
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
) -> dict:
    """Place card: vacant / public / parcel / gaps. AGR stays on /square."""
    result: dict = {}
    if pc:
        import httpx

        from api.main import _load_postcode_api_url

        normalised = pc.replace(" ", "").upper()
        api_url = _load_postcode_api_url()
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{api_url}/{normalised}")
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Postcode lookup failed: {exc}") from exc
        if response.status_code != 200:
            raise HTTPException(status_code=404, detail="Postcode not found.")
        result = (response.json() or {}).get("result") or {}
        lat = float(result["latitude"])
        lng = float(result["longitude"])
        pc = result.get("postcode") or pc
    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="Provide pc= or lat= and lng=.")
    _scotland_bounds_check(lat, lng)
    council_code = None
    council_name = None
    if pc:
        codes = result.get("codes") if pc else None
        if isinstance(codes, dict):
            council_code = codes.get("admin_district")
        council_name = result.get("admin_district")

    from agr.service import ValuationService

    breakdown = ValuationService.default().assess_point(lat, lng)
    if not council_code:
        council_code = breakdown.council_code
        council_name = breakdown.council_name
    card = place_context(
        lat,
        lng,
        postcode=pc,
        council_code=council_code,
        council_name=council_name,
    )
    card["postcode"] = pc
    card["agr"] = {
        "council_code": breakdown.council_code,
        "council_name": breakdown.council_name,
        "plot_gbp": breakdown.roll_annual_rent_notional_plot_gbp,
        "per_sqm_gbp": round(float(breakdown.site_rental_per_sqm_gbp), 4),
        "method": breakdown.method,
        "disclaimer": "Research estimate, not a rates bill.",
    }
    return with_stamp(card)


@router.get("/api/registers.json")
def api_registers() -> dict:
    return with_stamp(registers_payload())


@router.get("/downloads")
def open_downloads() -> dict:
    """Index of freely licensed layers and official sources."""
    return with_stamp({
        "note": (
            "Only openly licensed material is offered here. "
            "Spatial Hub login layers are listed as sources, not mirrored."
        ),
        "items": [
            {
                "id": "vdl_register",
                "label": "SVDLS site register",
                "licence": "OGL-3.0",
                "url": "https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/",
            },
            {
                "id": "vdl_overlay",
                "label": "VDL map overlay (this API)",
                "licence": "OGL-3.0",
                "endpoint": "/layers/open/vdl",
            },
            {
                "id": "public_land_overlay",
                "label": "Public / Crown land overlay (this API)",
                "licence": "SG 2024 dashboard overlay — not a title",
                "endpoint": "/layers/open/public-land",
                "note": "Viewport query of the official map. Five bodies only.",
            },
            {
                "id": "council_agr",
                "label": "Council AGR metrics GeoJSON",
                "licence": "research estimate + OGL inputs",
                "endpoint": "/layers/councils",
            },
            {
                "id": "inspire_parcels",
                "label": "ROS INSPIRE cadastral parcels",
                "licence": "ROS INSPIRE / Crown",
                "url": "https://www.ros.gov.uk/open-data",
            },
            {
                "id": "public_crown_map",
                "label": "Scottish public and Crown Estate land map",
                "licence": "official SG map — link, not a copy",
                "url": "https://www.arcgis.com/apps/dashboards/a10668ccd4784209bf22e3adcef6b897",
            },
            {
                "id": "scotlis",
                "label": "ScotLIS official titles",
                "licence": "ROS service",
                "url": "https://scotlis.ros.gov.uk/",
            },
        ],
    })
