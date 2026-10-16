"""National Wealth Engine routes. Independent of AGR: imports only georgist.*, paths, api.common.

Honesty rules (draft economic rules v0.4, sections 2, 4.3, 5, 13):
- zone_id must be a real data zone code. 'unknown' or anything malformed is a 422,
  never computed.
- No database means HTTP 503 with a reason. No zeros are invented.
- Totals are per value tier; attribution and policy columns are reported
  separately and never added.
- PUBLIC endpoints only: placeholders/mocks are absent (not merely flagged),
  internal-level or blocked figures are withheld, and only allowlisted columns
  are served. Developers see placeholders/diagnostics on api/internal_routes.py.
"""

from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.common import _scotland_bounds_check
from georgist import db
from georgist import dz_lookup
from georgist.aggregator import MixedPriceYearError, aggregator
from georgist.attribution import attributions_for
from georgist.attribution import SHOWN_STATUSES, AttributionMissing
from georgist.publication_rules import PublicationRuleError, check_site_rows, check_zone_row
from georgist.surface_settings import depreciation_settings
from georgist.display_views import (
    DEFAULT_VIEW, NOT_APPLICABLE, VIEW_ORDER, ZERO_DWELLING_NULL_COLUMNS, ZERO_DWELLINGS, spine_from_flags,
    surface_views,
)
from georgist.wealth_schema import PUBLIC_SURFACE_COLUMNS, QUALITY_FLAG_TAGS, publicly_served, quality_flags_sql

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wealth"])

# Data zone code ranges (NRS): 2011 zones S01006506–S01013481 (6,976);
# 2022 zones S01013482–S01020873 (7,392). Data Zones owns the spine; this is input
# validation only. Vintage is the INTEGER 2011 or 2022 in requests and responses.
DZ_CODE_RE = re.compile(r"^S01\d{6}$")
VINTAGE_QUERY_DESCRIPTION = "Integer 2011 or 2022 (text labels like 'DZ2011' are rejected)"


def parse_vintage(raw: str | None, *, required: bool = False) -> int | None:
    """Query vintage -> 2011 | 2022. Anything else (incl. 'DZ2011') is a loud 422, never mapped."""
    if raw is None and not required:
        return None
    text = (raw or "").strip()
    if text not in ("2011", "2022"):
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_vintage", "vintage": raw,
                    "message": "vintage must be the integer 2011 or 2022; text labels like 'DZ2011' "
                    "are not accepted (Data Zones vintage standard)."},
        )
    return int(text)

DISCLAIMER = "Experimental research estimate. Not an official valuation or tax bill."


def _mixed_years(exc: MixedPriceYearError) -> HTTPException:
    logger.error("Wealth totals refused: %s", exc)
    return HTTPException(
        status_code=500,
        detail={"error": "mixed_price_years", "tier": exc.tier, "price_years": exc.price_years,
                "message": "Rents priced in different years cannot be added; no total returned. "
                "This is a data error to fix upstream, not a figure."},
    )


def _publication_rule(exc: PublicationRuleError) -> HTTPException:
    logger.error("Publication rule violated: %s", exc)
    return HTTPException(
        status_code=500,
        detail={"error": "publication_rule_violation", "where": exc.where, "message": exc.message,
                "rule": "Modelled or proxy values and rents are zone-level only; site-level figures only "
                "from sources public at site level (docs/wealth_api.md). A data error to fix upstream."},
    )


def _attribution_missing(exc: AttributionMissing) -> HTTPException:
    logger.error("Attribution missing: %s", exc)
    return HTTPException(
        status_code=503,
        detail={"error": "attribution_missing", "datasets": exc.datasets,
                "message": "These figures need a licence attribution that is missing from the dataset "
                "manifest; nothing is served without it."},
    )


def _attributions_or_503(layer: str, views_shown) -> list:
    try:
        return attributions_for(layer, views_shown)
    except AttributionMissing as exc:
        raise _attribution_missing(exc) from exc


def _unavailable(exc: db.DatabaseUnavailable) -> HTTPException:
    logger.warning("Wealth DB unavailable: %s", exc)
    return HTTPException(
        status_code=503,
        detail={
            "error": "wealth_database_unavailable",
            "reason": exc.reason,
            "detail": exc.detail,
            "message": "No Wealth figures returned: the database is unavailable. Nothing was estimated.",
        },
    )


def resolve_zone(zone_id: str, vintage: int | None) -> tuple[str, int, str]:
    """Validate a data zone code and return (code, vintage, vintage_source). Raises 422."""
    code = (zone_id or "").strip().upper()
    if not DZ_CODE_RE.match(code):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_zone_id",
                "zone_id": zone_id,
                "message": "zone_id must be a Scottish data zone code like S01012345. "
                "Look the zone up first; 'unknown' is not computed.",
            },
        )
    inferred = dz_lookup.vintage_for_code(code)
    if inferred is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "zone_id_out_of_range", "zone_id": zone_id,
                    "message": "Not in the 2011 or 2022 data zone code ranges."},
        )
    if vintage is not None and vintage != inferred:
        raise HTTPException(
            status_code=422,
            detail={"error": "vintage_mismatch", "zone_id": code, "vintage": vintage,
                    "message": f"{code} is a {inferred} code."},
        )
    return code, inferred, "explicit" if vintage is not None else "inferred_from_code"


@router.get("/layers/context/data-zones/at")
def data_zone_at(
    lat: float = Query(..., ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    lng: float | None = Query(default=None, ge=-180, le=180, description="Alias of lon (old frontend)"),
) -> dict:
    """Data zone(s) containing a WGS84 point: real (code, vintage) for each loaded vintage.

    200 with a null zone when no zone contains the point (e.g. at sea); 503 when
    no boundary source is available. Never returns 'unknown'.
    """
    if lon is None:
        lon = lng
    if lon is None:
        raise HTTPException(status_code=422, detail={"error": "missing_lon", "message": "Provide lon (or lng)."})
    _scotland_bounds_check(lat, lon)
    try:
        found = dz_lookup.lookup(lat, lon)
    except dz_lookup.BoundariesUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "dz_boundaries_unavailable", "reasons": exc.reasons,
                    "message": "No data zone boundary source is available; no zone returned."},
        ) from exc
    # A miss is an empty result (null zone), including points at sea. Boundaries
    # that failed to load stay 503 above. Invalid lat/lng stay 422 from Query.
    # Context metrics (HPI/SIMD/density) stay on platform /layers/open/dz-context —
    # wealth_routes must not import layers/agr (see test_wealth_router_does_not_import_agr).
    return {"lat": lat, "lon": lon, **found.to_dict()}


@router.get("/georgist/wealth")
def get_georgist_wealth(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    zone_id: str = Query(..., description="Data zone code (2011 or 2022 zones), e.g. S01008677"),
    vintage: str | None = Query(
        default=None, description="Optional; must match the code's vintage. " + VINTAGE_QUERY_DESCRIPTION
    ),
) -> dict:
    """Wealth at a location: surface (by data zone) + extractive/eco (by point).

    Per-tier totals only. Placeholders are absent; withheld figures carry a reason, not a number.
    """
    code, vin, vin_source = resolve_zone(zone_id, parse_vintage(vintage))
    _scotland_bounds_check(lat, lng)
    try:
        wealth = aggregator.get_total_wealth(code, vin, lat, lng)
    except db.DatabaseUnavailable as exc:
        raise _unavailable(exc) from exc
    except MixedPriceYearError as exc:
        raise _mixed_years(exc) from exc
    except AttributionMissing as exc:
        raise _attribution_missing(exc) from exc
    except PublicationRuleError as exc:
        raise _publication_rule(exc) from exc
    return {
        "lat": lat,
        "lng": lng,
        "zone_id": code,
        "zone": {"code": code, "vintage": vin, "vintage_source": vin_source},
        "wealth": wealth,
    }


_SURFACE_LAYER_SQL = (
    "SELECT DISTINCT ON (s.code) "
    + ", ".join(f"s.{c}" if c != "valuation_date" else "s.valuation_date::text AS valuation_date"
                for c in PUBLIC_SURFACE_COLUMNS)
    + ", (s.fill_method = 'model_filled') AS model_filled,"
    " ('res_land_settlement_area_rough' = ANY(s.proxy_tags)) AS res_land_rough, " + quality_flags_sql("s") + ","
    " d.residential_land_ha AS d_residential_land_ha, d.settlement_area_ha AS d_settlement_area_ha,"
    " d.share_res_uprn_in_parcels AS d_share_res_uprn_in_parcels, d.mask_too_big_parcel AS d_mask_too_big_parcel,"
    " dc.vintage AS dc_vintage, dc.count_year AS dc_count_year, dc.dwellings_total AS dc_total_dwellings,"
    " dc.vacant_share AS dc_vacant_share, dc.second_home_share AS dc_second_home_share,"
    " pc.vintage AS pc_vintage, pc.pop_year AS pc_count_year, pc.population AS pc_population,"
    " zs.flags AS zs_flags, (zs.code IS NOT NULL) AS zs_present"
    " FROM surface_rent_dz s"
    " LEFT JOIN dz_denominators d ON d.code = s.code AND d.vintage = s.vintage"
    # Counts: same vintage AND count_year = price_year (money year). Never another year/vintage.
    # Dwellings: datazones.dwellings_by_year.dwellings_total; population: datazones.zone_spine at pop_year.
    " LEFT JOIN datazones.dwellings_by_year dc ON dc.code = s.code AND dc.vintage = s.vintage"
    " AND dc.count_year = s.price_year"
    " LEFT JOIN datazones.zone_spine pc ON pc.code = s.code AND pc.vintage = s.vintage"
    " AND pc.pop_year = s.price_year"
    # Zone flags (no year), ';'-separated zone_spine.flags: zero_dwellings overrides any rent (rules v0.7).
    " LEFT JOIN datazones.zone_spine zs ON zs.code = s.code AND zs.vintage = s.vintage"
    " WHERE s.vintage = %s ORDER BY s.code, s.valuation_date DESC"
)
_DENOM_KEYS = ("residential_land_ha", "settlement_area_ha", "share_res_uprn_in_parcels", "mask_too_big_parcel")


def _layer_views(r: dict) -> dict:
    """Per-zone display values for the three map views (rules v0.5). Pending => None, never computed."""
    denoms = {k: r.pop(f"d_{k}") for k in _DENOM_KEYS}
    dc = {k: r.pop(f"dc_{k}") for k in ("vintage", "count_year", "total_dwellings", "vacant_share", "second_home_share")}
    pc = {k: r.pop(f"pc_{k}") for k in ("vintage", "count_year", "population")}
    spine = spine_from_flags(r.pop("zs_flags"), present=bool(r.pop("zs_present")))
    dwelling_count = dc if dc["count_year"] is not None else None
    out = surface_views(r, denoms, shown=True, dwelling_count=dwelling_count,
                        population_count=pc if pc["count_year"] is not None else None, spine=spine)
    v = out["views"]
    zero = ZERO_DWELLINGS in out["flags"]
    if zero:  # rules v0.7: no residential surface rent; null, never 0
        r.update(dict.fromkeys(ZERO_DWELLING_NULL_COLUMNS))
    return {
        "status": NOT_APPLICABLE if zero else "ok",
        "denominator_flags": out["flags"],
        "rent_per_residential_ha": v["per_residential_hectare"]["value"],
        "rent_per_residential_ha_status": v["per_residential_hectare"]["status"],
        # Display only: low where UPRN-in-parcel coverage < 0.5 or the parcel mask is too big.
        "rent_per_residential_ha_confidence": v["per_residential_hectare"].get("confidence"),
        "preferred_view": out["default"],
        "quality_flags": [t for t in (r.pop("quality_flags", None) or []) if t in QUALITY_FLAG_TAGS],
        "rent_per_dwelling": v["per_dwelling"]["value"],
        "rent_per_dwelling_status": v["per_dwelling"]["status"],
        "rent_per_resident": v["per_resident"]["value"],
        "rent_per_resident_status": v["per_resident"]["status"],
        "second_home_share": v["per_resident"].get("second_home_share"),
        "vacant_share": v["per_resident"].get("vacant_share"),
    }


def _withheld_reason(r) -> str:
    if r["quality"] == "placeholder":
        return "placeholder"
    if r.get("publication_status") == "blocked":
        return "blocked"
    return "not_publishable"


def _plain(v):
    return float(v) if hasattr(v, "is_finite") else v


@router.get("/layers/georgist/surface-rent")
def layer_georgist_surface_rent(
    vintage: str = Query(default="2011", description=VINTAGE_QUERY_DESCRIPTION),
) -> JSONResponse:
    """Surface rent by data zone from `surface_rent_dz` (latest valuation per zone).

    Only rows cleared for publication are returned: publish_level public_zone or
    public_site, publication_status ok, not a placeholder. The latest row per zone
    decides, so a newer blocked/internal row is never replaced by an older public
    one. Only allowlisted columns are served (no diagnostics).
    `planning_uplift` and `infra_share` are "of which" columns, not additions.
    """
    vintage = parse_vintage(vintage, required=True)
    try:
        with db.cursor() as cur:
            cur.execute(_SURFACE_LAYER_SQL, (vintage,))
            rows = cur.fetchall()
    except db.DatabaseUnavailable as exc:
        raise _unavailable(exc) from exc
    publishable = [r for r in rows if publicly_served(r)]
    withheld: dict[str, int] = {}
    for r in rows:
        if not publicly_served(r):
            reason = _withheld_reason(r)
            withheld[reason] = withheld.get(reason, 0) + 1
    if not publishable:
        raise HTTPException(
            status_code=503,
            detail={"error": "surface_rent_not_built", "vintage": vintage, "withheld_by_reason": withheld,
                    "message": "surface_rent_dz has no publishable rows for this vintage yet."},
        )
    data = {}
    for r in publishable:
        try:
            check_zone_row("/layers/georgist/surface-rent", r)  # zone-level only: keyed by Data Zone code
        except PublicationRuleError as exc:
            raise _publication_rule(exc) from exc
        row = {k: _plain(v) for k, v in r.items()}
        row.update(_layer_views(row))
        data[r["code"]] = row
    views_status = {
        view: {status: sum(1 for z in data.values() if z[f"rent_{key}_status"] == status)
               for status in {z[f"rent_{key}_status"] for z in data.values()}}
        for view, key in (("per_residential_hectare", "per_residential_ha"), ("per_dwelling", "per_dwelling"),
                          ("per_resident", "per_resident"))
    }
    return JSONResponse({
        "ok": True,
        "source": "surface_rent_dz (residual_drc_surface_v1)",
        "vintage": vintage,
        "count": len(data),
        "withheld": len(rows) - len(publishable),
        "withheld_by_reason": withheld,
        "data": data,
        "views": {"default": DEFAULT_VIEW, "order": list(VIEW_ORDER), "status_counts": views_status,
                  "note": "Default view is rent per hectare of residential land. 'denominator_pending' "
                  "means the denominator is not loaded yet: nothing is computed. Rent per hectare of "
                  "whole-zone area is never served for surface rent."},
        "breakdown_columns": ["planning_uplift", "infra_share"],
        "method_settings": {"depreciation": depreciation_settings()},  # read from surface.yaml
        "attributions": _attributions_or_503(
            "surface_rent", [view for view, counts in views_status.items()
                           if any(counts.get(st) for st in SHOWN_STATUSES)]),
        "zero_dwellings": sorted(c for c, z in data.items() if z["status"] == NOT_APPLICABLE),
        "note": "Rent per zone in GBP/yr priced in price_year (evidence_year = raw sales year). Proxy tier. planning_uplift and "
        "infra_share are breakdowns of measured_rent, never added to it.",
        "disclaimer": DISCLAIMER,
    })


_POINT_LAYER_SQL = (
    "SELECT id, name, resource_type, annual_rent_gbp, price_year, evidence_year, commons_class, value_tier, quality,"
    " crosswalk_method, source_id, licence, publish_level, publication_status,"
    " ST_AsGeoJSON(ST_Transform(geom, 4326), 6) AS geometry"
    " FROM {table}"
    " WHERE quality <> 'placeholder' AND publication_status = 'ok' AND publish_level IN ('public_site', 'public_zone')"
)
# Site-level geometry is public only at public_site; public_zone rows would need
# zone aggregation first, so they are withheld from this point layer.
_POINT_LAYER_SITE_ONLY = " AND publish_level = 'public_site'"


def _point_layer(table: str, layer: str, path: str) -> JSONResponse:
    """Real, publishable extractive/eco features only. Mock harvests never appear here.

    Site geometry: every row must be a measured figure from a site-public source
    (publication_rules); one modelled/proxy row fails the whole layer loudly (500).
    """
    try:
        with db.cursor() as cur:
            cur.execute(_POINT_LAYER_SQL.format(table=table) + _POINT_LAYER_SITE_ONLY)
            rows = cur.fetchall()
    except db.DatabaseUnavailable as exc:
        raise _unavailable(exc) from exc
    try:
        check_site_rows(path, rows)
    except PublicationRuleError as exc:
        raise _publication_rule(exc) from exc
    if not rows:
        raise HTTPException(
            status_code=503,
            detail={"error": f"{layer}_layer_not_built", "layer": layer,
                    "message": f"No real, publishable {layer} rent data yet. Placeholder/mock "
                    "figures are not served (rules v0.4 section 2)."},
        )
    features = []
    for r in rows:
        geometry = r.pop("geometry")
        features.append({"type": "Feature", "geometry": json.loads(geometry) if geometry else None,
                         "properties": {k: _plain(v) for k, v in r.items()}})
    return JSONResponse({"type": "FeatureCollection", "features": features,
                         "meta": {"layer": layer, "count": len(features), "disclaimer": DISCLAIMER}})


@router.get("/layers/georgist/resource-rent")
def layer_georgist_resource_rent() -> JSONResponse:
    """Extractive layer: real publishable rows from `resource_wealth` only (503 until they exist)."""
    return _point_layer("resource_wealth", "extractive", "/layers/georgist/resource-rent")


@router.get("/layers/georgist/eco-rent")
def layer_georgist_eco_rent() -> JSONResponse:
    """Eco layer: real publishable rows from `eco_wealth` only (503 until they exist)."""
    return _point_layer("eco_wealth", "eco", "/layers/georgist/eco-rent")
