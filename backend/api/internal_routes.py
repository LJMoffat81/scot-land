"""INTERNAL developer endpoints: placeholders, mocks and diagnostics. Never public.

Mounted under /internal only when ENABLE_INTERNAL_ENDPOINTS is truthy (1/true/yes/on);
the default is off, so in a normal deployment these routes do not exist (404).

When mounted, every route requires auth via INTERNAL_API_TOKEN (Bearer or X-API-Key).
Missing secret → 403 locked (never fall open). Missing/wrong token → 401.

Rules v0.4 section 2: placeholders and diagnostics are absent from the public API
and map; developers can still see them here.

Tax scenario tools also live here: publication_status=blocked until yield calibration
(land yield deferred to shared surface.yaml; Valuation owns r−g). Never mount them on
public routes.
"""

from __future__ import annotations

import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from api.common import _scotland_bounds_check
from api.internal_auth import require_internal_auth
from api.wealth_routes import (
    VINTAGE_QUERY_DESCRIPTION,
    _attribution_missing,
    _mixed_years,
    _unavailable,
    parse_vintage,
    resolve_zone,
)
from georgist import db
from georgist.aggregator import MixedPriceYearError, aggregator
from georgist.attribution import AttributionMissing
from georgist.surface_settings import YIELD_SOURCE
from georgist.tax_scenarios import (
    DEFAULT_DZ_VINTAGE,
    INTERNAL_WARNING,
    PUBLICATION_STATUS,
    TaxScenarioError,
    aggregate_by_council,
    parse_capture_rate,
    zone_illustration,
    zone_row_from_db,
)
from georgist.wealth_schema import yield_provenance

ENV_FLAG = "ENABLE_INTERNAL_ENDPOINTS"
HEADERS = {"X-Wealth-Internal": "true", "Cache-Control": "no-store"}
WARNING = "INTERNAL ONLY. Contains placeholder/mock figures and diagnostics. Do not publish."
DZ_CODE_RE = re.compile(r"^S01\d{6}$")

router = APIRouter(
    tags=["internal"],
    dependencies=[Depends(require_internal_auth)],
)  # full /internal/... paths below (no prefix: keeps route audits literal)


def internal_enabled() -> bool:
    return os.getenv(ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def _plain(v):
    return float(v) if hasattr(v, "is_finite") else v


@router.get("/internal/georgist/wealth")
def internal_wealth(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    zone_id: str = Query(...),
    vintage: str | None = Query(default=None, description=VINTAGE_QUERY_DESCRIPTION),
) -> JSONResponse:
    """Same as /georgist/wealth but lists placeholders and withheld rows WITH numbers, plus diagnostics.

    Totals are computed by the same function, so they match the public endpoint.
    """
    code, vin, vin_source = resolve_zone(zone_id, parse_vintage(vintage))
    _scotland_bounds_check(lat, lng)
    try:
        wealth = aggregator.get_total_wealth(code, vin, lat, lng, internal=True)
    except db.DatabaseUnavailable as exc:
        raise _unavailable(exc) from exc
    except MixedPriceYearError as exc:
        raise _mixed_years(exc) from exc
    except AttributionMissing as exc:
        raise _attribution_missing(exc) from exc
    body = {"internal": True, "warning": WARNING, "lat": lat, "lng": lng,
            "zone": {"code": code, "vintage": vin, "vintage_source": vin_source}, "wealth": wealth}
    return JSONResponse(body, headers=HEADERS)


@router.get("/internal/georgist/surface-rent/{zone_id}")
def internal_surface_row(
    zone_id: str, vintage: str | None = Query(default=None, description=VINTAGE_QUERY_DESCRIPTION),
) -> JSONResponse:
    """Every stored column of the latest surface_rent_dz row for a zone (diagnostics included)."""
    code, vin, _ = resolve_zone(zone_id, parse_vintage(vintage))
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT * FROM surface_rent_dz WHERE code = %s AND vintage = %s "
                "ORDER BY valuation_date DESC LIMIT 1",
                (code, vin),
            )
            row = cur.fetchone()
    except db.DatabaseUnavailable as exc:
        raise _unavailable(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "surface_row_not_found", "zone": code, "vintage": vin})
    return JSONResponse({"internal": True, "warning": WARNING,
                         "yield": yield_provenance(row),  # config-fallback yields tagged "placeholder"
                         "row": {k: _plain(v) if not hasattr(v, "isoformat") else v.isoformat() for k, v in row.items()}},
                        headers=HEADERS)


@router.get("/internal/georgist/surface-rent-rollup")
def internal_surface_rent_rollup(
    level: str | None = Query(
        default=None,
        description="Optional filter: intermediate_zone | council | scotland",
    ),
) -> JSONResponse:
    """INTERNAL SG roll-up (DZ2022 → IZ → Council → Scotland). Never public; £ figures unpublished."""
    from georgist.surface_rollup import GEO_LEVELS

    allowed = ("intermediate_zone", "council", "scotland")
    if level is not None and level not in allowed:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_rollup_level",
                "level": level,
                "allowed": list(allowed),
                "hierarchy": list(GEO_LEVELS),
            },
        )
    try:
        with db.cursor() as cur:
            if level is None:
                cur.execute(
                    "SELECT * FROM surface_rent_rollup WHERE publish_level = 'internal' "
                    "ORDER BY geo_level, code, valuation_date DESC"
                )
            else:
                cur.execute(
                    "SELECT * FROM surface_rent_rollup WHERE publish_level = 'internal' "
                    "AND geo_level = %s ORDER BY code, valuation_date DESC",
                    (level,),
                )
            rows = cur.fetchall()
    except db.DatabaseUnavailable as exc:
        raise _unavailable(exc) from exc
    if not rows:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "surface_rent_rollup_not_built",
                "level": level,
                "message": "No internal DZ2022 SG roll-up rows yet.",
            },
        )
    data = [
        {k: _plain(v) if not hasattr(v, "isoformat") else v.isoformat() for k, v in r.items()}
        for r in rows
    ]
    return JSONResponse(
        {
            "internal": True,
            "warning": WARNING,
            "hierarchy": list(GEO_LEVELS),
            "level": level,
            "count": len(data),
            "rows": data,
            "note": "INTERNAL / UNPUBLISHED. DZ2022 → IZ → Council → Scotland. Not official valuations.",
        },
        headers=HEADERS,
    )


def _mock_layer(module_name: str) -> JSONResponse:
    """The mock resource/eco harvest, clearly tagged. Never writes files on GET."""
    if module_name == "resource":
        from georgist.resource_harvester import OUTPUT_FILE, build_resource_features as build
    else:
        from georgist.eco_harvester import OUTPUT_FILE, build_eco_features as build
    data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8")) if OUTPUT_FILE.exists() else build()
    for feat in data.get("features", []):
        props = feat.setdefault("properties", {})
        props.setdefault("quality", "placeholder")
        props["in_totals"] = False
    data.setdefault("meta", {}).update({
        "internal": True,
        "quality": "placeholder",
        "in_totals": False,
        "warning": "MOCK features with unsourced rent factors. Not harvested data. " + WARNING,
    })
    return JSONResponse(data, headers={**HEADERS, "X-Wealth-Quality": "placeholder"})


@router.get("/internal/layers/georgist/resource-rent")
def internal_resource_mock() -> JSONResponse:
    return _mock_layer("resource")


@router.get("/internal/layers/georgist/eco-rent")
def internal_eco_mock() -> JSONResponse:
    return _mock_layer("eco")


# Latest surface_rent_dz row per zone, joined to council codes on the Data Zones spine.
# One Data Zone vintage throughout; la_code/la_name from the spine (e.g. S01010117 → Glasgow City).
_TAX_SCENARIO_SQL = (
    "SELECT DISTINCT ON (s.code) "
    "s.code, s.vintage, s.measured_rent, s.price_year, s.quality, s.publish_level, s.publication_status, "
    "s.value_tier, s.uncertainty_low, s.uncertainty_high, "
    "zs.la_code, zs.la_name, zs.flags "
    "FROM surface_rent_dz s "
    "JOIN datazones.zone_spine zs ON zs.code = s.code AND zs.vintage = s.vintage "
    "WHERE s.vintage = %s "
    "ORDER BY s.code, s.valuation_date DESC"
)


def _tax_scenario_error(exc: TaxScenarioError) -> HTTPException:
    status = 500 if exc.code == "mixed_price_years" else 422
    detail = {"error": exc.code, "message": exc.message, **exc.extra}
    return HTTPException(status_code=status, detail=detail)


def _load_tax_scenario_zones(vintage: int) -> list:
    """Zone rows usable as scenario *inputs* (publishable measured_rent). Output stays blocked."""
    try:
        with db.cursor() as cur:
            cur.execute(_TAX_SCENARIO_SQL, (vintage,))
            rows = cur.fetchall()
    except db.DatabaseUnavailable as exc:
        raise _unavailable(exc) from exc
    zones = []
    for r in rows:
        code = str(r.get("code") or "")
        if not DZ_CODE_RE.match(code):
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "invalid_zone_in_tax_scenario_source",
                    "code": code,
                    "message": "Tax scenario source row is not a Data Zone code; refusing the payload.",
                },
            )
        z = zone_row_from_db(r)
        if z is not None:
            zones.append(z)
    if not zones:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "tax_scenario_not_built",
                "vintage": vintage,
                "message": (
                    "No publishable Surface Rent rows joined to Data Zone councils for this vintage. "
                    "Nothing was estimated."
                ),
            },
        )
    return zones


@router.get("/internal/georgist/tax-scenario")
def internal_tax_scenario(
    vintage: str = Query(
        default=str(DEFAULT_DZ_VINTAGE),
        description="One Data Zone version throughout (default 2011). " + VINTAGE_QUERY_DESCRIPTION,
    ),
    scenario_id: str = Query(
        default="S2",
        description="Approved defaults (v0.1) scenario: S1 (per-council revenue swap), S2 (50%), S3 (85%)",
    ),
    capture_rate: float = Query(
        default=1.0,
        description="Optional override for fixed-rate scenarios; ignored for S1 solved rates",
    ),
    la_code: str | None = Query(
        default=None,
        description="Optional council area code (S12…); filter by_council and national to that LA",
    ),
    phase_in_year: int | None = Query(
        default=None,
        ge=1,
        description="Optional phase-in policy year (1-indexed); default = fully phased in",
    ),
    council_share: float | None = Query(
        default=None,
        description="Optional revenue-share override (with dividend_share); must sum to 1",
    ),
    dividend_share: float | None = Query(
        default=None,
        description="Optional revenue-share override (with council_share); must sum to 1",
    ),
) -> JSONResponse:
    """INTERNAL: Surface Rent scenarios. publication_status=blocked. No public £."""
    vin = parse_vintage(vintage, required=True)
    try:
        rate = parse_capture_rate(capture_rate)
    except TaxScenarioError as exc:
        raise _tax_scenario_error(exc) from exc
    if la_code is not None:
        code = la_code.strip().upper()
        if not re.fullmatch(r"S12\d{6}", code):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_la_code",
                    "la_code": la_code,
                    "message": "la_code must be a Scottish council area code like S12000036.",
                },
            )
        la_code = code
    share_override = None
    if council_share is not None or dividend_share is not None:
        if council_share is None or dividend_share is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_revenue_share",
                    "message": "council_share and dividend_share must both be supplied and sum to 1.",
                },
            )
        share_override = {"council_share": council_share, "dividend_share": dividend_share}
    zones = _load_tax_scenario_zones(vin)
    try:
        payload = aggregate_by_council(
            zones,
            capture_rate=rate,
            la_code=la_code,
            scenario_id=scenario_id,
            phase_in_year=phase_in_year,
            revenue_sharing=share_override,
        )
    except TaxScenarioError as exc:
        raise _tax_scenario_error(exc) from exc
    payload["ok"] = True
    payload["source"] = "surface_rent_dz + datazones.zone_spine"
    payload["vintage"] = vin
    if la_code:
        payload["la_code"] = la_code
    assert payload.get("publication_status") == PUBLICATION_STATUS
    assert payload.get("money_grain") == "data_zone"
    yp = payload.get("yield_placeholder") or {}
    assert yp.get("status") == "placeholder"
    assert yp.get("owner") == "Valuation"
    assert yp.get("source") == YIELD_SOURCE
    assert isinstance(yp.get("land_yield"), (int, float)) and yp["land_yield"] > 0
    assert abs(float(yp["land_yield"]) - 0.05) > 1e-12  # no 0.05 left in yield config
    assert payload.get("policy_config", {}).get("status") == "approved_defaults"
    assert payload.get("policy_config", {}).get("separate_from_measured_land_values") is True
    return JSONResponse(payload, headers={**HEADERS, "X-Wealth-Publication-Status": PUBLICATION_STATUS})


@router.get("/internal/georgist/tax-scenario/zone")
def internal_tax_scenario_zone(
    zone_id: str = Query(..., description="Data zone code (2011 or 2022), e.g. S01008677"),
    vintage: str | None = Query(
        default=None, description="Optional; must match the code's vintage. " + VINTAGE_QUERY_DESCRIPTION
    ),
    scenario_id: str = Query(
        default="S2",
        description="Approved defaults (v0.1) scenario: S1 / S2 / S3",
    ),
    capture_rate: float = Query(
        default=1.0,
        description="Optional override for fixed-rate scenarios; ignored for S1 solved rates",
    ),
    phase_in_year: int | None = Query(
        default=None,
        ge=1,
        description="Optional phase-in policy year (1-indexed); default = fully phased in",
    ),
    council_share: float | None = Query(
        default=None,
        description="Optional revenue-share override (with dividend_share); must sum to 1",
    ),
    dividend_share: float | None = Query(
        default=None,
        description="Optional revenue-share override (with council_share); must sum to 1",
    ),
) -> JSONResponse:
    """INTERNAL: who-pays illustration for one Data Zone. publication_status=blocked. No public £."""
    code, vin, vin_source = resolve_zone(zone_id, parse_vintage(vintage))
    try:
        rate = parse_capture_rate(capture_rate)
    except TaxScenarioError as exc:
        raise _tax_scenario_error(exc) from exc
    share_override = None
    if council_share is not None or dividend_share is not None:
        if council_share is None or dividend_share is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_revenue_share",
                    "message": "council_share and dividend_share must both be supplied and sum to 1.",
                },
            )
        share_override = {"council_share": council_share, "dividend_share": dividend_share}
    zones = _load_tax_scenario_zones(vin)
    match = next((z for z in zones if z.code == code), None)
    if match is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "zone_surface_rent_unavailable",
                "zone_id": code,
                "vintage": vin,
                "message": (
                    "No publishable Surface Rent for this data zone (withheld, zero dwellings, "
                    "or not built). Nothing was estimated."
                ),
            },
        )
    council_rows = [z for z in zones if z.la_code == match.la_code]
    try:
        # Mixed-year guard on council membership (counts only; £ stays on the zone).
        aggregate_by_council(
            council_rows,
            capture_rate=rate,
            scenario_id=scenario_id,
            phase_in_year=phase_in_year,
            revenue_sharing=share_override,
        )
        payload = zone_illustration(
            match,
            capture_rate=rate,
            council_zone_count=len(council_rows),
            scenario_id=scenario_id,
            council_rows=council_rows,
            phase_in_year=phase_in_year,
            revenue_sharing=share_override,
        )
    except TaxScenarioError as exc:
        raise _tax_scenario_error(exc) from exc
    payload["ok"] = True
    payload["source"] = "surface_rent_dz + datazones.zone_spine"
    payload["vintage"] = vin
    payload["zone_id"] = code
    payload["zone_meta"] = {"code": code, "vintage": vin, "vintage_source": vin_source}
    assert payload.get("publication_status") == PUBLICATION_STATUS
    assert payload.get("money_grain") == "data_zone"
    assert payload.get("yield_placeholder", {}).get("status") == "placeholder"
    assert INTERNAL_WARNING in (payload.get("warning") or "")
    zone = payload.get("zone") or {}
    assert isinstance(zone.get("measured_rent_gbp"), dict)
    assert set(zone["measured_rent_gbp"]) >= {"low", "central", "high"}
    assert zone.get("value_tier") in {"market", "proxy", "shadow"}
    assert zone.get("tag") == zone.get("value_tier")
    return JSONResponse(payload, headers={**HEADERS, "X-Wealth-Publication-Status": PUBLICATION_STATUS})
