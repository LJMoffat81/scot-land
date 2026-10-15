"""AGR routes under the publication geometry rule.

Public router: shapes, metadata, place/address/postcode search, context tiles, and
the council multi-metric choropleth (council grain; scrubbed of modelled AGR £).
Place £ live on `/internal/agr/place` (Wealth Engine, DZ2022 + address_uprn only,
publication_status=blocked). Plot residual diagnostics and (opt-in) national
fiscal / councils-agr live on `internal_router` under /internal/agr/...
(auth; mounted only when ENABLE_INTERNAL_ENDPOINTS is on).

Council/Scotland aggregate £ routes stay behind ENABLE_INTERNAL_AGR_AGGREGATE_GBP
(off by default) and assert_no_aggregate_gbp on the place path.

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
from typing import Any, Mapping

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from agr.batch import assess_points, batch_meta
from agr.config import load_config
from agr.engine import breakdown_to_dict
from agr.export_stamp import with_stamp
from agr.fiscal import fiscal_summary, place_fiscal
from agr.layers import engine_stamp
from agr.overrides import merge_config_overrides
from agr.publication import (
    UNPUBLISHED_REASON,
    blocked_wealth_place,
    internal_yield_from_surface,
)
from agr.report import API_VERSION, build_assessment_report, render_report_markdown
from agr.response_labels import AGR_INTERNAL_ROUTER_NOTE, stamp_experimental
from agr.scenarios import resolve_active_scenario
from agr.service import ValuationService
from georgist import db
from georgist import dz_lookup
from georgist.aggregator import MixedPriceYearError, aggregator
from georgist.attribution import AttributionMissing
from georgist.surface_dz2022 import estimate_label_for_fill
from georgist.tax_scenarios import (
    TaxScenarioError,
    UPRN_DZ2022_CROSSWALK,
    assert_no_aggregate_gbp,
)
from layers.council_metrics import build_council_metrics_geojson, scrub_public_agr_properties
from layers.councils_layer import build_councils_agr_geojson
from layers.grid_layer import build_w3w_agr_grid
from layers.platform import platform_catalog
from spatial.address import NominatimUnavailable, search_door, search_place
from spatial.context_tiles import (
    fetch_context_geojson,
    fetch_context_tile,
    fetch_seabed_async,
    fetch_urban_rural_class_async,
)
from spatial.grid import METERS_PER_DEGREE_LAT, snap_to_w3w_grid
from spatial.parcels import TRANSPARENT_PNG, lookup_parcel_geojson
from spatial.urban_rural import NotLand
from spatial.w3w import (
    W3WNotConfiguredError,
    is_configured as w3w_is_configured,
    normalise_words,
    try_coordinates_to_words,
    words_to_coordinates,
)
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
from api.wealth_routes import (
    _attribution_missing,
    _mixed_years,
    _unavailable,
    parse_vintage,
    resolve_zone,
)

# Opt-in only: council / Scotland residual £ aggregates behind login.
# Default off — Valuation HOLD: no aggregate GBP until the rules doc lands.
_AGGREGATE_GBP_ENV = "ENABLE_INTERNAL_AGR_AGGREGATE_GBP"
_REQUIRED_PLACE_VINTAGE = 2022
_REQUIRED_CROSSWALK = UPRN_DZ2022_CROSSWALK

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
        "INTERNAL ONLY. Place pages use Wealth Engine figures at Data Zone 2022 "
        f"({_REQUIRED_CROSSWALK}); publication_status=blocked. Yield central/band "
        "from surface.yaml (Georgist v3 metadata when present). Council/Scotland "
        f"aggregate £ require {_AGGREGATE_GBP_ENV}=1 (off by default). Experimental; "
        "each rent figure carries a market, proxy or shadow tag."
    ),
}


def _aggregate_gbp_enabled() -> bool:
    return os.getenv(_AGGREGATE_GBP_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _refuse_aggregate_gbp(route: str) -> None:
    """Council/Scotland £ aggregates stay off unless explicitly opted in."""
    if _aggregate_gbp_enabled():
        return
    raise HTTPException(
        status_code=403,
        detail={
            "error": "aggregate_gbp_disabled",
            "route": route,
            "publication_status": "blocked",
            "unpublished_reason": UNPUBLISHED_REASON,
            "setting": _AGGREGATE_GBP_ENV,
            "message": (
                f"Council/Scotland aggregate £ on {route} are disabled by default. "
                f"Set {_AGGREGATE_GBP_ENV}=1 to opt in (internal only). "
                "Place £ stay at Data Zone grain on /internal/agr/place."
            ),
        },
    )


def agr_health_extras() -> dict:
    """AGR fields that /health reported before the split (only when AGR loads)."""
    config = load_config()
    signoff = config.get("economist_signoff", {})
    return stamp_experimental(
        {
            "version": API_VERSION,
            "w3w_configured": w3w_is_configured(),
            "economist_signoff_status": signoff.get("status", "unknown"),
            "sales_pipeline": "comps_crosscheck",
            "data_policy": "no_portal_scraping",
            "public_rents": False,
            "agr_place_pages": "internal_wealth_engine_dz2022_blocked_until_yield_calibration",
            "agr_internal_routes_note": AGR_INTERNAL_ROUTER_NOTE,
            "agr_aggregate_gbp_enabled": _aggregate_gbp_enabled(),
            "assessment_reports": "internal",  # /internal/agr/assessment/report
            "publication_geometry": "public_shapes_no_rents_wealth_engine_internal",
            "stamp": engine_stamp(config),
        }
    )


def _with_internal_block(payload: dict) -> dict:
    body = stamp_experimental(payload)
    body["internal"] = True
    body.update(INTERNAL_PUBLICATION)
    return stamp_experimental(body)


def _estimate_label_from_surface(row: Mapping[str, Any] | None) -> str | None:
    if not row:
        return None
    raw = row.get("estimate_label")
    if raw:
        return str(raw)
    tags = row.get("proxy_tags") or ()
    if isinstance(tags, str):
        tags = [t for t in tags.split(";") if t]
    for tag in tags:
        text = str(tag)
        if text.startswith("estimate_label="):
            return text.split("=", 1)[1]
    return estimate_label_for_fill(row.get("fill_method"))


def _require_dz2022_address_uprn(surface: Mapping[str, Any] | None, *, code: str, vintage: int) -> None:
    """Place path: DZ2022 + address_uprn only (#71)."""
    if int(vintage) != _REQUIRED_PLACE_VINTAGE:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "vintage_required",
                "code": code,
                "vintage": vintage,
                "required_vintage": _REQUIRED_PLACE_VINTAGE,
                "message": (
                    f"/internal/agr/place requires vintage {_REQUIRED_PLACE_VINTAGE} "
                    f"(address_uprn crosswalk). Got {vintage}."
                ),
            },
        )
    if surface is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "surface_row_not_found",
                "code": code,
                "vintage": vintage,
                "crosswalk_method": _REQUIRED_CROSSWALK,
                "message": (
                    f"No internal surface_rent_dz row for {code} vintage {vintage} "
                    f"with {_REQUIRED_CROSSWALK}."
                ),
            },
        )
    method = str(surface.get("crosswalk_method") or "none")
    if method != _REQUIRED_CROSSWALK:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "crosswalk_method_required",
                "code": code,
                "vintage": vintage,
                "crosswalk_method": method,
                "required_crosswalk_method": _REQUIRED_CROSSWALK,
                "message": (
                    f"/internal/agr/place requires crosswalk_method={_REQUIRED_CROSSWALK} "
                    f"(#71 DZ2022 path). Got {method!r}."
                ),
            },
        )


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
    return stamp_experimental(
        config.get("economist_signoff", {"status": "unknown"})
    )


def _public_config_view(config: dict) -> dict:
    """Sign-off and methodology labels only — no £ pool / yield money figures."""
    integrity = config.get("integrity") or {}
    _placeholder_yield = "5" + "%"
    caveats = [
        c
        for c in (integrity.get("caveats") or [])
        if isinstance(c, str)
        and _placeholder_yield not in c
        and "5 per cent" not in c.lower()
    ]
    return stamp_experimental(
        {
            "economist_signoff": config.get("economist_signoff", {"status": "unknown"}),
            "integrity": {
                "estimate_kind": integrity.get("estimate_kind"),
                "estimate_label": integrity.get("estimate_label"),
                "caveats": caveats,
            },
            "note": (
                "Monetary parameters and national rent-pool figures are not served on "
                "public /config before yield calibration. Place pages: Wealth Engine "
                "at /internal/agr/place (Data Zone 2022; blocked). Experimental; rents "
                "will carry market / proxy / shadow tags."
            ),
        }
    )


@router.get("/config")
def get_config() -> dict:
    """Public config mirror without rent / money figures."""
    return _public_config_view(load_config())


@router.get("/boundaries/councils")
def get_council_boundaries() -> JSONResponse:
    return _load_geojson(COUNCILS_GEOJSON)


@router.get("/boundaries/glasgow-ward-18")
def get_glasgow_ward_18_boundary() -> JSONResponse:
    return _load_geojson(WARD_18_GEOJSON)


@router.get("/layers/catalog")
def get_layer_catalog() -> dict:
    """Open land platform layer list (brief + live/gap status). No rents."""
    return stamp_experimental(platform_catalog())


@router.get("/layers/councils")
def layer_councils_metrics(
    scenario: str = Query(default="full_agr"),
) -> JSONResponse:
    """Council FeatureCollection with open context metrics only (no modelled money figures)."""
    try:
        geo = build_council_metrics_geojson(scenario)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # Copy so the cached layer is not given a stamp it did not have.
    return JSONResponse(with_stamp(scrub_public_agr_properties(geo)))


@internal_router.get("/internal/agr/place")
def internal_agr_place(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    zone_id: str | None = Query(
        default=None,
        description="Optional data zone code; inferred from lat/lng when omitted",
    ),
    vintage: str | None = Query(
        default="2022",
        description="Must be 2022 (DZ2022 + address_uprn path from #71)",
    ),
) -> JSONResponse:
    """INTERNAL place page: Wealth Engine at Data Zone 2022. Blocked.

    Requires vintage=2022 and surface crosswalk_method=address_uprn.
    Yield central/band are read from surface.yaml (same path as #9).
    Every £ figure is a low/central/high range. No council/Scotland aggregates.
    """
    _scotland_bounds_check(lat, lng)
    vin = parse_vintage(vintage, required=True)
    if vin != _REQUIRED_PLACE_VINTAGE:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "vintage_required",
                "vintage": vin,
                "required_vintage": _REQUIRED_PLACE_VINTAGE,
                "message": (
                    f"/internal/agr/place requires vintage {_REQUIRED_PLACE_VINTAGE} "
                    f"with crosswalk_method={_REQUIRED_CROSSWALK}."
                ),
            },
        )
    if zone_id:
        code, resolved_vin, vin_source = resolve_zone(zone_id, vin)
    else:
        try:
            found = dz_lookup.lookup(lat, lng)
        except db.DatabaseUnavailable as exc:
            raise _unavailable(exc) from exc
        except dz_lookup.BoundariesUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={"error": "dz_boundaries_unavailable", "reasons": exc.reasons},
            ) from exc
        hit = found.to_dict()
        if not hit.get("code"):
            raise HTTPException(
                status_code=404,
                detail={"error": "no_data_zone_at_point", "lat": lat, "lng": lng},
            )
        code = hit["code"]
        resolved_vin = int(hit["vintage"])
        if vin != resolved_vin:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "vintage_mismatch",
                    "code": code,
                    "vintage": resolved_vin,
                    "required_vintage": _REQUIRED_PLACE_VINTAGE,
                },
            )
        vin_source = "point_lookup"
    if resolved_vin != _REQUIRED_PLACE_VINTAGE:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "vintage_required",
                "code": code,
                "vintage": resolved_vin,
                "required_vintage": _REQUIRED_PLACE_VINTAGE,
            },
        )

    try:
        with db.cursor() as cur:
            surface = aggregator.surface_row(
                cur, code, resolved_vin, internal=True
            )
    except db.DatabaseUnavailable as exc:
        raise _unavailable(exc) from exc

    _require_dz2022_address_uprn(surface, code=code, vintage=resolved_vin)

    try:
        wealth = aggregator.get_total_wealth(
            code, resolved_vin, lat, lng, internal=True
        )
    except db.DatabaseUnavailable as exc:
        raise _unavailable(exc) from exc
    except MixedPriceYearError as exc:
        raise _mixed_years(exc) from exc
    except AttributionMissing as exc:
        raise _attribution_missing(exc) from exc

    ycfg = internal_yield_from_surface()
    estimate_label = _estimate_label_from_surface(surface)
    value_tier = None
    if surface is not None and surface.get("value_tier") in {"market", "proxy", "shadow"}:
        value_tier = str(surface["value_tier"])

    zone_meta: dict[str, Any] = {
        "code": code,
        "vintage": resolved_vin,
        "vintage_source": vin_source,
        "crosswalk_method": _REQUIRED_CROSSWALK,
    }
    if estimate_label is not None:
        zone_meta["estimate_label"] = estimate_label
    if value_tier is not None:
        zone_meta["value_tier"] = value_tier

    # Per-zone labels also on each place/surface row in wealth.
    if isinstance(wealth, dict):
        for comp in wealth.get("components") or []:
            if isinstance(comp, dict) and comp.get("layer") == "surface":
                if estimate_label is not None:
                    comp["estimate_label"] = estimate_label
                if value_tier is not None:
                    comp["value_tier"] = value_tier

    body = blocked_wealth_place(
        lat=lat,
        lng=lng,
        zone=zone_meta,
        wealth=wealth,
        yield_cfg=ycfg,
        estimate_label=estimate_label,
        value_tier=value_tier,
    )
    body["warning"] = INTERNAL_PUBLICATION["note"]
    try:
        assert_no_aggregate_gbp(body)
    except TaxScenarioError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": exc.code,
                "message": exc.message,
                **exc.extra,
            },
        ) from exc
    return JSONResponse(body, headers=INTERNAL_HEADERS)


@internal_router.get("/internal/agr/fiscal/summary")
def internal_fiscal_summary(
    scenario: str = Query(default="replace_full_basket"),
    dividend: bool = Query(default=True, description="Include equal-share dividend knobs"),
    remote_credit: bool = Query(default=True, description="Include remote/island credits"),
) -> JSONResponse:
    """INTERNAL: national fiscal dashboard. Off unless ENABLE_INTERNAL_AGR_AGGREGATE_GBP=1."""
    _refuse_aggregate_gbp("/internal/agr/fiscal/summary")
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
    """INTERNAL: council AGR choropleth. Off unless ENABLE_INTERNAL_AGR_AGGREGATE_GBP=1."""
    _refuse_aggregate_gbp("/internal/agr/layers/councils-agr")
    try:
        geo = build_councils_agr_geojson(scenario)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    body = _with_internal_block(dict(geo))
    body["stamp"] = engine_stamp(load_config())
    return JSONResponse(body, headers=INTERNAL_HEADERS)


@internal_router.get("/internal/agr/layers/councils")
def internal_layer_councils_metrics(
    scenario: str = Query(default="full_agr"),
) -> JSONResponse:
    """INTERNAL: multi-metric council layer with residual £. Off by default."""
    _refuse_aggregate_gbp("/internal/agr/layers/councils")
    try:
        geo = build_council_metrics_geojson(scenario)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    body = _with_internal_block(with_stamp(geo))
    body["geometry_level_note"] = (
        "Council residual diagnostic. Place £ figures are Wealth Engine at Data Zone only."
    )
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
    """INTERNAL: Scot-LAND squares with modelled AGR (plot grain; never public)."""
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
    words: str | None = Query(
        default=None,
        description="Scot-LAND square three-word address e.g. filled.count.soap",
    ),
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
    """INTERNAL: Scot-LAND square residual AGR (plot grain). Blocked from public map."""
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


_PLACE_BUSY = "Place search is busy. Try again in a moment."
_ADDRESS_BUSY = "Address search is busy. Try again in a moment."


@router.get("/place")
def get_place(q: str = Query(description="Postcode, address, place, or title number")) -> dict:
    """Find where to open the map. A title miss is not a rent and not a ScotLIS call."""
    try:
        return search_place(q)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NominatimUnavailable as exc:
        # Nominatim 429 / exhaustion — never surface as 502 after SHARE-FIX.
        raise HTTPException(status_code=503, detail=_PLACE_BUSY) from exc
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=_PLACE_BUSY) from exc


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
    except NominatimUnavailable as exc:
        raise HTTPException(status_code=503, detail=_ADDRESS_BUSY) from exc
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=_ADDRESS_BUSY) from exc
