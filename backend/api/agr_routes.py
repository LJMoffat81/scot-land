"""AGR routes under the publication geometry rule.

Public router: shapes, metadata, place/address/postcode search, context tiles, and
the council multi-metric choropleth (council grain). Modelled residual AGR £ on
plot grain (W3W grid, cell square, assessment packs, validation) and national
fiscal / councils-agr choropleth live on `internal_router` under /internal/agr/...
(auth; mounted only when ENABLE_INTERNAL_ENDPOINTS is on).

api/main.py mounts the public router optionally (import or declaration failure
skips it; /health.routers reports why).
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import math
import os
import threading
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from agr.engine import breakdown_to_dict
from agr.config import load_config
from agr.export_stamp import with_stamp
from agr.layers import engine_stamp
from agr.fiscal import fiscal_summary, place_fiscal
from agr.overrides import merge_config_overrides
from agr.batch import assess_points, batch_meta
from agr.report import API_VERSION, build_assessment_report, render_report_markdown
from agr.scenarios import resolve_active_scenario
from agr.service import ValuationService
from spatial.grid import METERS_PER_DEGREE_LAT, snap_to_w3w_grid
from spatial.urban_rural import NotLand
from spatial.w3w import (
    W3WNotConfiguredError,
    is_configured as w3w_is_configured,
    normalise_words,
    try_coordinates_to_words,
    words_to_coordinates,
)
from layers.councils_layer import build_councils_agr_geojson
from layers.council_metrics import build_council_metrics_geojson
from layers.grid_layer import build_w3w_agr_grid
from layers.platform import platform_catalog
from spatial.address import search_door, search_place
from spatial.context_tiles import (
    fetch_context_geojson,
    fetch_context_tile,
    fetch_seabed_async,
    fetch_urban_rural_class_async,
)
from spatial.parcels import TRANSPARENT_PNG, lookup_parcel_geojson
from validation.glasgow_ward_18 import run_validation
from validation.ratio_study import ratio_study_points

from api.common import (  # noqa: F401  (re-exported for platform_routes)
    COUNCILS_GEOJSON,
    WARD_18_GEOJSON,
    _load_geojson,
    _load_postcode_api_url,
    _scotland_bounds_check,
)
from api.internal_auth import require_internal_auth

router = APIRouter()
internal_router = APIRouter(
    tags=["internal-agr"],
    dependencies=[Depends(require_internal_auth)],
)

INTERNAL_HEADERS = {"X-Wealth-Internal": "true", "Cache-Control": "no-store"}
INTERNAL_PUBLICATION = {
    "publication_status": "blocked",
    "unpublished_reason": "yield_calibration_pending",
    "note": (
        "INTERNAL ONLY. Modelled residual AGR £ is blocked from the public map "
        "until yield calibration (Data Zone publication rule)."
    ),
}


def agr_health_extras() -> dict:
    """AGR fields that /health reported before the split (only when AGR loads)."""
    config = load_config()
    signoff = config.get("economist_signoff", {})
    return {
        "version": API_VERSION,
        "w3w_configured": w3w_is_configured(),
        "economist_signoff_status": signoff.get("status", "unknown"),
        "sales_pipeline": "comps_crosscheck",
        "data_policy": "no_portal_scraping",
        "assessment_reports": "internal",  # /internal/agr/assessment/report
        "publication_geometry": "public_shapes_modelled_agr_internal",
        "stamp": engine_stamp(config),
    }


def _with_internal_block(payload: dict) -> dict:
    body = dict(payload)
    body["internal"] = True
    body.update(INTERNAL_PUBLICATION)
    return body


def _parse_sensitivity(
    yield_rate: float | None,
    urban_speculation: float | None,
    farmland_factor: float | None,
) -> dict:
    base = load_config()
    try:
        return merge_config_overrides(
            base,
            yield_rate=yield_rate,
            urban_speculation_discount=urban_speculation,
            farmland_market_to_productive=farmland_factor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _square_response(
    lat: float,
    lng: float,
    scenario: str | None = None,
    *,
    words_hint: str | None = None,
    config: dict | None = None,
    include_sales_context: bool = False,
) -> dict:
    _scotland_bounds_check(lat, lng)
    square = snap_to_w3w_grid(lat, lng)
    service = ValuationService(config=config if config is not None else load_config())
    try:
        breakdown = service.assess_square(square, scenario=scenario)
    except NotLand:
        what3words = words_hint
        if what3words is None:
            what3words = try_coordinates_to_words(square.lat, square.lng)
        return {
            "reason": "not_land",
            "square": {
                "lat": square.lat,
                "lng": square.lng,
                "area_sqm": square.area_sqm,
                "grid": "what3words_3m",
                "bounds": {
                    "south": square.south,
                    "west": square.west,
                    "north": square.north,
                    "east": square.east,
                },
                "polygon": square.geojson_polygon,
            },
            "what3words": what3words,
            "w3w_configured": w3w_is_configured(),
            "agr": None,
        }

    # Prefer caller-supplied words; otherwise reverse-geocode snapped cell if key present
    what3words = words_hint
    if what3words is None:
        what3words = try_coordinates_to_words(square.lat, square.lng)

    payload = {
        "square": {
            "lat": square.lat,
            "lng": square.lng,
            "area_sqm": square.area_sqm,
            "grid": "what3words_3m",
            "bounds": {
                "south": square.south,
                "west": square.west,
                "north": square.north,
                "east": square.east,
            },
            "polygon": square.geojson_polygon,
        },
        "what3words": what3words,
        "w3w_configured": w3w_is_configured(),
        "method_family": "valuer_residual_roll",
        "agr": breakdown_to_dict(breakdown),
    }
    if include_sales_context:
        # Default service loads synthetic fixture for research — never claim as ROS
        research = ValuationService.default()
        if config is not None:
            research = ValuationService(config=config, sales=research.sales)
        ctx = research.sales_context(square.lat, square.lng)
        ctx["disclaimer"] = (
            "Sales context may include synthetic fixtures for pipeline tests. "
            "Only production_eligible rows may be treated as real market evidence."
        )
        payload["sales_context"] = ctx

    # Property boundary for the cadastral parcel under this cell (ROS INSPIRE)
    parcel_feature = lookup_parcel_geojson(square.lat, square.lng)
    if parcel_feature is not None:
        payload["parcel"] = parcel_feature

    # Fiscal tool: gross plot liability vs equal dividend vs remote credit
    cfg = config if config is not None else load_config()
    active = resolve_active_scenario(scenario)
    plot_full = breakdown.roll_annual_rent_notional_plot_gbp or 0.0
    cell_full = breakdown.economic_annual_rent_gbp or 0.0
    active_cell = breakdown.annual_ground_rent_gbp or 0.0
    scale = (active_cell / cell_full) if cell_full > 0 else 1.0
    gross_plot = plot_full * scale
    # Prefer parcel-scale gross when cadastral area known
    if breakdown.roll_annual_rent_parcel_gbp is not None:
        gross_plot = breakdown.roll_annual_rent_parcel_gbp * scale
    payload["fiscal"] = place_fiscal(
        gross_plot_gbp=gross_plot,
        council_code=breakdown.council_code,
        scenario=active,
        config=cfg,
    )
    payload["fiscal_summary"] = fiscal_summary(active, cfg)
    payload["agr"]["stamp"] = engine_stamp(cfg)

    return payload


@router.get("/signoff")
def get_signoff() -> dict:
    config = load_config()
    return config.get("economist_signoff", {"status": "unknown"})


@router.get("/config")
def get_config() -> dict:
    return load_config()


@router.get("/boundaries/councils")
def get_council_boundaries() -> JSONResponse:
    return _load_geojson(COUNCILS_GEOJSON)


@router.get("/boundaries/glasgow-ward-18")
def get_glasgow_ward_18_boundary() -> JSONResponse:
    return _load_geojson(WARD_18_GEOJSON)


@router.get("/layers/catalog")
def get_layer_catalog() -> dict:
    """Open land platform layer list (brief + live/gap status)."""
    return platform_catalog()


@router.get("/layers/councils")
def layer_councils_metrics(
    scenario: str = Query(default="full_agr"),
) -> JSONResponse:
    """Full multi-metric council FeatureCollection (AGR, HPI, SIMD, density, …)."""
    try:
        geo = build_council_metrics_geojson(scenario)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # Copy so the cached layer is not given a stamp it did not have.
    return JSONResponse(with_stamp(geo))


@internal_router.get("/internal/agr/fiscal/summary")
def internal_fiscal_summary(
    scenario: str = Query(default="replace_full_basket"),
    dividend: bool = Query(default=True, description="Include equal-share dividend knobs"),
    remote_credit: bool = Query(default=True, description="Include remote/island credits"),
) -> JSONResponse:
    """INTERNAL: national fiscal dashboard (modelled Sandilands pool). Blocked until yield calibration."""
    try:
        active = resolve_active_scenario(scenario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    body = _with_internal_block(
        with_stamp(
            fiscal_summary(
                active,
                dividend_enabled=dividend,
                remote_credit_enabled=remote_credit,
            )
        )
    )
    return JSONResponse(body, headers=INTERNAL_HEADERS)


@internal_router.get("/internal/agr/layers/councils-agr")
def internal_layer_councils_agr(
    scenario: str = Query(default="full_agr"),
) -> JSONResponse:
    """INTERNAL: council AGR choropleth (modelled residual). Blocked until yield calibration."""
    try:
        geo = build_councils_agr_geojson(scenario)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    body = _with_internal_block(dict(geo))
    body["stamp"] = engine_stamp(load_config())
    return JSONResponse(body, headers=INTERNAL_HEADERS)


# About 60 a minute, with a short burst so a zoom still draws. 8,000 km² is
# above a wide desktop at zoom 12. The map asks for 200 cells.
_W3W_PER_MINUTE = 60
_W3W_BURST = 20
_W3W_MAX_CELLS = 400
_W3W_MAX_AREA_KM2 = 8_000.0
_w3w_lock = threading.Lock()
_w3w_buckets: dict[str, tuple[float, float]] = {}


def _w3w_now() -> float:
    return time.monotonic()


def reset_w3w_rate_limit() -> None:
    with _w3w_lock:
        _w3w_buckets.clear()


def _bbox_area_km2(south: float, west: float, north: float, east: float) -> float:
    mid = (south + north) / 2
    height_m = (north - south) * METERS_PER_DEGREE_LAT
    width_m = (east - west) * METERS_PER_DEGREE_LAT * max(math.cos(math.radians(mid)), 0.2)
    return (height_m * width_m) / 1_000_000


def _loopback_or_private(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def _forwarded_visitor(header: str | None) -> str | None:
    if not header:
        return None
    first = header.split(",")[0].strip()
    return first or None


def _w3w_visitor(request: Request) -> str:
    """Whose grid allowance this request uses.

    The forwarded address counts only when the Next proxy proves itself with
    SCOT_PROXY_SECRET, or when no secret is set and the connection is local.
    """
    host = request.client.host if request.client else "unknown"
    visitor = _forwarded_visitor(request.headers.get("x-forwarded-for"))
    secret = os.getenv("SCOT_PROXY_SECRET", "")
    if secret:
        presented = request.headers.get("x-scotland-proxy") or ""
        if visitor and presented == secret:
            return visitor
        return host
    if visitor and _loopback_or_private(host):
        return visitor
    return host


def _w3w_allowed(host: str) -> bool:
    now = _w3w_now()
    rate = _W3W_PER_MINUTE / 60
    with _w3w_lock:
        tokens, updated = _w3w_buckets.get(host, (float(_W3W_BURST), now))
        tokens = min(float(_W3W_BURST), tokens + (now - updated) * rate)
        if tokens < 1:
            _w3w_buckets[host] = (tokens, now)
            return False
        _w3w_buckets[host] = (tokens - 1, now)
        return True


@internal_router.get("/internal/layers/w3w-grid")
def internal_layer_w3w_grid(
    request: Request,
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    scenario: str = Query(default="full_agr"),
    max_cells: int = Query(default=400, ge=10),
) -> JSONResponse:
    """INTERNAL: W3W cells with modelled AGR (plot grain; never public)."""
    if south >= north or west >= east:
        raise HTTPException(
            status_code=400,
            detail="Invalid bbox: require south < north and west < east",
        )
    if max_cells > _W3W_MAX_CELLS:
        raise HTTPException(status_code=400, detail="Ask for fewer cells.")
    if _bbox_area_km2(south, west, north, east) > _W3W_MAX_AREA_KM2:
        raise HTTPException(status_code=400, detail="Ask for a smaller area.")
    if not _w3w_allowed(_w3w_visitor(request)):
        raise HTTPException(status_code=429, detail="The grid is busy. Wait a moment.")
    try:
        geo = build_w3w_agr_grid(
            south, west, north, east, scenario=scenario, max_cells=max_cells
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(_with_internal_block(with_stamp(geo)), headers=INTERNAL_HEADERS)


# Parcel tile / bbox / at routes live on api.cadastral_routes (always mounted).


@router.get("/layers/context/urban-rural/class")
async def layer_urban_rural_class(
    lat: float = Query(...),
    lng: float = Query(...),
) -> JSONResponse:
    """Eight-class urban-rural name. A label, never a rent and never a 500."""
    try:
        body = await fetch_urban_rural_class_async(lat, lng)
    except Exception:
        body = {"name": ""}
    cache = "public, max-age=86400" if body.get("name") else "no-store"
    return JSONResponse(body, headers={"Cache-Control": cache})


# /layers/context/data-zones/at moved to api/wealth_routes.py (PostGIS / local
# boundary lookup returning real (code, vintage)). The old remote ArcGIS version
# is spatial.context_tiles.fetch_data_zone_async (see c6adad0).


@router.get("/layers/context/seabed/at")
async def layer_seabed_at(
    lat: float = Query(...),
    lng: float = Query(...),
) -> JSONResponse:
    """Published Crown Estate Scotland lease at a point.

    The note is a rent rule, or a statement that the yearly rent is not in
    the open file. It is not added to the land charge.
    """
    try:
        body = await fetch_seabed_async(lat, lng)
    except Exception:
        body = {"leases": []}
    cache = "public, max-age=86400" if body.get("leases") else "no-store"
    return JSONResponse(body, headers={"Cache-Control": cache})


@router.get("/layers/context/{layer_id}/tiles/{z}/{x}/{y}")
async def layer_context_tiles(layer_id: str, z: int, x: int, y: int) -> Response:
    """Allowlisted government context layer as an XYZ PNG. Never a 500.

    The fetch runs off the parcel-tile pool. A street search otherwise queues
    this export until the browser has already given up.
    """
    try:
        png = await asyncio.to_thread(fetch_context_tile, layer_id, z, x, y)
    except Exception:
        png = TRANSPARENT_PNG
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Layer-Source": layer_id if layer_id.replace("-", "").isalnum() else "context",
        },
    )


@router.get("/layers/context/{layer_id}")
def layer_context_features(layer_id: str) -> JSONResponse:
    """Allowlisted oil, lease, or renewable features. Empty when unknown."""
    try:
        geo = fetch_context_geojson(layer_id)
    except Exception:
        geo = {
            "type": "FeatureCollection",
            "features": [],
            "meta": {"layer": layer_id, "ok": False, "count": 0},
        }
    return JSONResponse(
        geo,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@internal_router.get("/internal/agr/validation/glasgow-ward-18")
def internal_validate_glasgow_ward_18(
    samples: int = Query(default=12, ge=3, le=30),
) -> JSONResponse:
    if not WARD_18_GEOJSON.exists():
        raise HTTPException(status_code=503, detail="Glasgow Ward 18 boundary not built yet.")
    return JSONResponse(
        _with_internal_block(with_stamp(run_validation(sample_count=samples))),
        headers=INTERNAL_HEADERS,
    )


@internal_router.get("/internal/agr/validation/ratio-study")
def internal_validation_ratio_study(
    samples: int = Query(default=8, ge=3, le=24),
    scenario: str = Query(default="full_agr"),
) -> JSONResponse:
    """INTERNAL: residual vs sales-comp ratios (plot samples)."""
    if not WARD_18_GEOJSON.exists():
        raise HTTPException(status_code=503, detail="Glasgow Ward 18 boundary not built yet.")
    from validation.glasgow_ward_18 import _sample_points_in_ward

    points = _sample_points_in_ward(samples)
    study = ratio_study_points(points, scenario=scenario)
    study["area"] = "glasgow_ward_18"
    study["note"] = (
        "Research structure for professional QA. Synthetic sales make production_ready=false."
    )
    return JSONResponse(_with_internal_block(with_stamp(study)), headers=INTERNAL_HEADERS)


@internal_router.get("/internal/agr/validation/ward18-qa-pack")
def internal_ward18_qa_pack(
    samples: int = Query(default=10, ge=3, le=24),
    scenario: str = Query(default="full_agr"),
) -> JSONResponse:
    """INTERNAL: combined professional QA pack for Glasgow Ward 18."""
    if not WARD_18_GEOJSON.exists():
        raise HTTPException(status_code=503, detail="Glasgow Ward 18 boundary not built yet.")
    from validation.glasgow_ward_18 import _sample_points_in_ward

    spatial = run_validation(sample_count=samples)
    points = _sample_points_in_ward(samples)
    ratios = ratio_study_points(points, scenario=scenario)
    roll_rows = assess_points(points, scenario=scenario, include_sales=True)
    meta = batch_meta(roll_rows, scenario=scenario)
    return JSONResponse(
        _with_internal_block(
            with_stamp({
                "area": "glasgow_ward_18",
                "label": "East Centre — featured validation case study",
                "status": "research_estimate",
                "not_statutory": True,
                "spatial_validation": spatial,
                "ratio_study": ratios,
                "mini_roll": {"meta": meta, "rows": roll_rows},
                "next_steps": [
                    "Ingest ROS/licensed sales to data/licensed/sales.jsonl",
                    "Re-run QA pack until production_ready on ratio_study",
                    "Optional OpenAVMKit pilot on the same points",
                ],
            })
        ),
        headers=INTERNAL_HEADERS,
    )


@internal_router.get("/internal/agr/assessment/report")
def internal_assessment_report(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    scenario: str = Query(default="full_agr"),
    include_sales_context: bool = Query(default=True),
    format: str = Query(default="json", description="json or markdown"),
    yield_rate: float | None = Query(default=None),
    urban_speculation: float | None = Query(default=None),
    farmland_factor: float | None = Query(default=None),
):
    """INTERNAL: downloadable assessment pack (plot grain modelled AGR)."""
    _scotland_bounds_check(lat, lng)
    config = _parse_sensitivity(yield_rate, urban_speculation, farmland_factor)
    try:
        report = build_assessment_report(
            lat,
            lng,
            scenario=scenario,
            config=config,
            include_sales=include_sales_context,
        )
    except NotLand:
        if format.lower() in ("md", "markdown", "text"):
            return PlainTextResponse("No land here\n", media_type="text/markdown; charset=utf-8")
        return JSONResponse(_with_internal_block({"reason": "not_land"}), headers=INTERNAL_HEADERS)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stamp = engine_stamp(config)
    report["stamp"] = stamp
    report["assessment"]["stamp"] = stamp
    report["markdown"] = render_report_markdown(report)
    report = _with_internal_block(report)

    if format.lower() in ("md", "markdown", "text"):
        return PlainTextResponse(
            report["markdown"],
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{report["report_id"]}.md"',
                **INTERNAL_HEADERS,
            },
        )
    return JSONResponse(report, headers=INTERNAL_HEADERS)


@internal_router.get("/internal/agr/square")
def internal_get_square(
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    words: str | None = Query(default=None, description="What3Words address e.g. filled.count.soap"),
    scenario: str | None = Query(
        default="full_agr",
        description="Policy scenario: full_agr, replace_income_tax, revenue_neutral",
    ),
    yield_rate: float | None = Query(
        default=None,
        description="Sensitivity: rentalisation yield (0.02–0.12). Default from config.",
    ),
    urban_speculation: float | None = Query(
        default=None,
        description="Sensitivity: Pickard urban factor (0.3–1.0). Default 0.70.",
    ),
    farmland_factor: float | None = Query(
        default=None,
        description="Sensitivity: Pickard farmland productive factor (0.1–1.0). Default 0.20.",
    ),
    include_sales_context: bool = Query(
        default=False,
        description="Include nearby sales from fixture/licensed store (research).",
    ),
) -> JSONResponse:
    """INTERNAL: W3W cell residual AGR (plot grain). Blocked from public map."""
    words_hint: str | None = None
    if words:
        try:
            coords = words_to_coordinates(words)
            words_hint = normalise_words(words)
            if coords.words:
                words_hint = coords.words
        except W3WNotConfiguredError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        lat = coords.lat
        lng = coords.lng

    if lat is None or lng is None:
        raise HTTPException(
            status_code=400,
            detail="Provide lat and lng, or words (requires W3W_API_KEY).",
        )

    config = _parse_sensitivity(yield_rate, urban_speculation, farmland_factor)
    try:
        payload = _square_response(
            lat,
            lng,
            scenario=scenario,
            words_hint=words_hint,
            config=config,
            include_sales_context=include_sales_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(_with_internal_block(payload), headers=INTERNAL_HEADERS)


@router.get("/sales/status")
def sales_status() -> dict:
    """Pipeline status for professional sales ingest (fixtures vs licensed)."""
    service = ValuationService.default()
    summary = service.sales.summary() if service.sales else {"count": 0}
    return {
        "pipeline": "scaffolded",
        "portal_scraping": False,
        "preferred_authority": "Registers of Scotland",
        "fixture_loaded": bool(service.sales and len(service.sales) > 0),
        "store": summary,
        "docs": [
            "docs/DATA_LICENSING.md",
            "docs/DATA_ACQUISITION.md",
            "docs/PROFESSIONAL_STANDARD.md",
        ],
    }


def _lookup_postcode_result(postcode: str) -> dict:
    normalised = postcode.replace(" ", "").upper()
    if len(normalised) < 5 or len(normalised) > 7:
        raise HTTPException(status_code=400, detail="Invalid postcode format.")

    api_url = _load_postcode_api_url()
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{api_url}/{normalised}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Postcode lookup failed: {exc}") from exc

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Postcode not found.")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Postcode service unavailable.")

    payload = response.json()
    result = payload.get("result")
    if not result:
        raise HTTPException(status_code=404, detail="Postcode not found.")
    return result


@router.get("/postcode/{postcode}")
def get_postcode_location(postcode: str) -> dict:
    """Public postcode → centroid only. Modelled AGR is /internal/agr/postcode/{postcode}."""
    result = _lookup_postcode_result(postcode)
    lat = float(result["latitude"])
    lng = float(result["longitude"])
    try:
        _scotland_bounds_check(lat, lng)
    except HTTPException as exc:
        if exc.status_code == 400:
            raise HTTPException(
                status_code=400,
                detail="Postcode resolves outside Scotland.",
            ) from exc
        raise
    return {
        "postcode": {
            "postcode": result["postcode"],
            "parish": result.get("parish"),
            "admin_district": result.get("admin_district"),
            "country": result.get("country"),
        },
        "lat": lat,
        "lng": lng,
        "agr": None,
        "status": "location_only",
        "note": "Centroid only; modelled residual AGR is internal until yield calibration.",
    }


@internal_router.get("/internal/agr/postcode/{postcode}")
def internal_get_postcode_square(
    postcode: str,
    scenario: str | None = Query(
        default="full_agr",
        description="Policy scenario: full_agr, replace_income_tax, revenue_neutral",
    ),
    yield_rate: float | None = Query(default=None),
    urban_speculation: float | None = Query(default=None),
    farmland_factor: float | None = Query(default=None),
    include_sales_context: bool = Query(default=False),
) -> JSONResponse:
    """INTERNAL: postcode centroid → cell residual AGR (plot grain)."""
    result = _lookup_postcode_result(postcode)
    lat = result["latitude"]
    lng = result["longitude"]

    config = _parse_sensitivity(yield_rate, urban_speculation, farmland_factor)
    try:
        square_payload = _square_response(
            lat,
            lng,
            scenario=scenario,
            config=config,
            include_sales_context=include_sales_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException as exc:
        if exc.status_code == 400:
            raise HTTPException(
                status_code=400,
                detail="Postcode resolves outside Scotland.",
            ) from exc
        raise

    square_payload["postcode"] = {
        "postcode": result["postcode"],
        "parish": result.get("parish"),
        "admin_district": result.get("admin_district"),
        "country": result.get("country"),
    }
    return JSONResponse(_with_internal_block(square_payload), headers=INTERNAL_HEADERS)


@router.get("/place")
def get_place(q: str = Query(description="Postcode, address, place, or title number")) -> dict:
    """Find where to open the map. A title miss is not a rent and not a ScotLIS call."""
    try:
        return search_place(q)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Place search is unavailable.") from exc


@router.get("/address")
def get_address(
    postcode: str = Query(description="Scottish postcode already found"),
    door: str = Query(description="Door number, such as 12, 12A, or 2/1"),
    lat: float | None = Query(default=None, description="Postcode centre latitude"),
    lng: float | None = Query(default=None, description="Postcode centre longitude"),
) -> dict:
    """Point for a door in a postcode. The rent is looked up separately."""
    try:
        return search_door(postcode, door, lat=lat, lng=lng)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Address search is unavailable.") from exc
