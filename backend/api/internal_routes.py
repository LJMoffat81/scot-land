"""INTERNAL developer endpoints: placeholders, mocks and diagnostics. Never public.

Mounted under /internal only when ENABLE_INTERNAL_ENDPOINTS is truthy (1/true/yes/on);
the default is off, so in a normal deployment these routes do not exist (404).
There is no authentication beyond the flag: never enable it on a public host.

Rules v0.4 section 2: placeholders and diagnostics are absent from the public API
and map; developers can still see them here.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.common import _scotland_bounds_check
from api.wealth_routes import VINTAGE_QUERY_DESCRIPTION, _attribution_missing, _mixed_years, _unavailable, parse_vintage, resolve_zone
from georgist import db
from georgist.aggregator import MixedPriceYearError, aggregator
from georgist.attribution import AttributionMissing

ENV_FLAG = "ENABLE_INTERNAL_ENDPOINTS"
HEADERS = {"X-Wealth-Internal": "true", "Cache-Control": "no-store"}
WARNING = "INTERNAL ONLY. Contains placeholder/mock figures and diagnostics. Do not publish."

router = APIRouter(tags=["internal"])  # full /internal/... paths below (no prefix: keeps route audits literal)


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
                         "row": {k: _plain(v) if not hasattr(v, "isoformat") else v.isoformat() for k, v in row.items()}},
                        headers=HEADERS)


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
