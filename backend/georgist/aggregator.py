"""Wealth aggregation over PostGIS: surface (by zone) + extractive/eco (by point).

Rules applied (draft economic rules v0.4, sections 2, 4.3, 5, 13):
- Fails loudly: no DB, missing schema or a query error raises
  `DatabaseUnavailable`. Nothing falls back to zeros.
- Totals are per value_tier (market / proxy / shadow), never one mixed headline.
- Placeholders and mocks (quality='placeholder', e.g. today's mock resource/eco
  harvests) are ABSENT from the public payload: the public SQL filters them out,
  so they never leave the database. Only the internal payload lists them.
- publish_level below public_zone, or publication_status='blocked', is withheld:
  listed with the reason, numbers redacted (rules 2).
- Public payloads read an explicit column allowlist; diagnostics stay internal.
- A tier whose components carry different price years raises MixedPriceYearError
  (rules section 2: price_year is the money year; evidence_year is not used for totals).
- planning_uplift / infra_share are "of which" breakdowns. policy_rent is a
  policy column. None of them is ever added to measured rent.
- A zone with no surface row reports surface as missing, not as £0.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

from georgist import db
from georgist.attribution import SHOWN_STATUSES, AttributionMissing, attributions_for, context_attributions
from georgist.publication_rules import check_site_rows
from georgist.display_views import NOT_APPLICABLE, ZERO_DWELLINGS, spine_from_flags, surface_views, zero_dwellings
from georgist.wealth_schema import (
    ATTRIBUTION_COLUMNS,
    INTERNAL_ONLY_COLUMNS,
    PUBLIC_LEVELS,
    PUBLIC_SURFACE_COLUMNS,
    QUALITY_FLAG_TAGS,
    QUALITY_FLAGS_SQL,
    VALUE_TIERS,
    yield_provenance,
)

logger = logging.getLogger(__name__)

_SURFACE_PUBLIC_SQL = (
    "SELECT " + ", ".join(PUBLIC_SURFACE_COLUMNS)
    + ", (fill_method = 'model_filled') AS model_filled"
    + ", ('res_land_settlement_area_rough' = ANY(proxy_tags)) AS res_land_rough"
    + ", " + QUALITY_FLAGS_SQL
    + " FROM surface_rent_dz WHERE code = %s AND vintage = %s"
    " ORDER BY valuation_date DESC LIMIT 1"
)
_SURFACE_INTERNAL_SQL = (
    "SELECT *, (fill_method = 'model_filled') AS model_filled,"
    " ('res_land_settlement_area_rough' = ANY(proxy_tags)) AS res_land_rough, " + QUALITY_FLAGS_SQL + " FROM surface_rent_dz"
    " WHERE code = %s AND vintage = %s ORDER BY valuation_date DESC LIMIT 1"
)

_POINT_COLUMNS = (
    "name, resource_type, annual_rent_gbp, price_year, evidence_year, commons_class, value_tier, quality,"
    " crosswalk_method, source_id, licence, publish_level, publication_status"
)
_POINT_SQL = (
    "SELECT " + _POINT_COLUMNS + " FROM {table}"
    " WHERE ST_Intersects(geom, ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 27700))"
)
# Public: placeholders never leave the database.
_POINT_PUBLIC_SQL = _POINT_SQL + " AND quality <> 'placeholder'"

_DENOMINATOR_SQL = (
    "SELECT residential_land_ha, residential_land_source, settlement_area_ha, settlement_source,"
    " share_res_uprn_in_parcels, mask_too_big_parcel"
    " FROM dz_denominators WHERE code = %s AND vintage = %s"
)
# Counts join on (code, vintage, count_year = price_year). Never another year or vintage.
_DWELLING_COUNT_SQL = (
    "SELECT vintage, count_year, dwellings_total AS total_dwellings, vacant_share, second_home_share"
    " FROM datazones.dwellings_by_year WHERE code = %s AND vintage = %s AND count_year = %s"
)
# Zone-level Data Zones flags (no year), from the ';'-separated zone_spine.flags string:
# zero_dwellings is the single source (rules v0.7).
_SPINE_FLAGS_SQL = "SELECT flags FROM datazones.zone_spine WHERE code = %s AND vintage = %s"
# GIS access context (dz_access.csv): shown beside the figures, never used in them.
ACCESS_TABLE = "processed.gis_dz_access"
ACCESS_COLUMNS = ("job_access", "log_job_access", "road_km_nearest_luc", "nearest_luc", "distance_method",
                  "job_access_method", "network_component")
_ACCESS_PRESENT_SQL = f"SELECT to_regclass('{ACCESS_TABLE}') IS NOT NULL AS present"
_ACCESS_SQL = (f"SELECT {', '.join(ACCESS_COLUMNS)}, flags FROM {ACCESS_TABLE} WHERE code = %s AND vintage = %s")
_POPULATION_COUNT_SQL = (
    "SELECT vintage, pop_year AS count_year, population FROM datazones.zone_spine"
    " WHERE code = %s AND vintage = %s AND pop_year = %s"
)

WITHHELD_REASONS = ("placeholder", "blocked", "not_publishable")


def _num(v: Any) -> float | None:
    return None if v is None else float(v)


def _component(layer: str, row: Mapping[str, Any], rent_key: str, *, internal: bool = False,
               not_applicable: str | None = None) -> dict[str, Any]:
    quality = row.get("quality")
    publish = row.get("publish_level")
    status = row.get("publication_status") or "ok"
    rent = _num(row.get(rent_key))
    lo, hi = _num(row.get("uncertainty_low")), _num(row.get("uncertainty_high"))
    excluded = None
    if quality == "placeholder":
        excluded = "placeholder"
    elif status == "blocked":
        excluded = "blocked"
    elif publish not in PUBLIC_LEVELS:
        excluded = "not_publishable"
    elif not_applicable:
        excluded = not_applicable  # e.g. zero_dwellings: no figure exists, never 0 (rules v0.7)
        rent = lo = hi = None
    elif rent is None:
        excluded = "no_measured_rent"
    elif row.get("value_tier") not in VALUE_TIERS:
        excluded = "unknown_value_tier"
    if excluded in WITHHELD_REASONS and not internal:
        # Rules 2: withheld figures are listed with the reason, never with the number.
        rent = lo = hi = None
    out = {
        "layer": layer,
        "name": row.get("name") or row.get("code"),
        "commons_class": row.get("commons_class"),
        "measured_rent_gbp": rent,
        "price_year": row.get("price_year"),  # year the money is priced in (rules 2)
        "evidence_year": row.get("evidence_year"),  # raw sales/evidence year
        "value_tier": row.get("value_tier"),
        "quality": quality,
        "uncertainty_low": lo,
        "uncertainty_high": hi,
        "crosswalk_method": row.get("crosswalk_method"),
        "source_id": row.get("source_id"),
        "licence": row.get("licence"),
        "publish_level": publish,
        "publication_status": status,
        "in_totals": excluded is None,
        "excluded_reason": excluded,
        "withheld": excluded in WITHHELD_REASONS,
        "status": _status(excluded, not_applicable),
    }
    if layer == "surface":
        out["model_filled"] = bool(row.get("model_filled"))
    if internal and layer == "surface":
        out["diagnostics"] = {k: _jsonable(row.get(k)) for k in INTERNAL_ONLY_COLUMNS if k in row}
        out["yield"] = yield_provenance(row)  # a config-fallback yield is tagged "placeholder"
    return out


def _status(excluded: str | None, not_applicable: str | None) -> str:
    if excluded is None:
        return "ok"
    if excluded in WITHHELD_REASONS:
        return "withheld"
    if not_applicable and excluded == not_applicable:
        return NOT_APPLICABLE
    return "excluded"


def _jsonable(v: Any) -> Any:
    return float(v) if hasattr(v, "is_finite") else v


class MixedPriceYearError(ValueError):
    """Rules section 2: rents priced in different years are never added. Fails loudly."""

    def __init__(self, tier: str, price_years: list[Any]):
        self.tier = tier
        self.price_years = price_years
        super().__init__(f"refusing to add {tier!r} rents priced in different years: {price_years}")


def summarise(components: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Totals per value tier. Pure function; the only place totals are made.

    Reads only `measured_rent_gbp`. Attribution and policy columns are not
    consulted, so they cannot leak into a total. Every component entering a tier
    total must carry the same `price_year` (the money year, rules section 2);
    a missing or differing price_year raises `MixedPriceYearError` instead of
    returning a partial or blank total.
    """
    tiers: dict[str, dict[str, Any]] = {}
    for c in components:
        if not c.get("in_totals"):
            continue
        tier = c["value_tier"]
        year = c.get("price_year")
        t = tiers.setdefault(
            tier,
            {"total_gbp": 0.0, "low_gbp": 0.0, "high_gbp": 0.0, "band_complete": True, "price_year": year, "count": 0},
        )
        if year is None or year != t["price_year"]:
            raise MixedPriceYearError(tier, sorted({t["price_year"], year}, key=lambda y: (y is None, y)))
        t["total_gbp"] += c["measured_rent_gbp"]
        lo, hi = c.get("uncertainty_low"), c.get("uncertainty_high")
        if lo is None or hi is None:
            t["band_complete"] = False
        else:
            t["low_gbp"] += lo
            t["high_gbp"] += hi
        t["count"] += 1
    return {
        tier: {
            "total_gbp": round(t["total_gbp"], 2),
            "low_gbp": round(t["low_gbp"], 2) if t["band_complete"] else None,
            "high_gbp": round(t["high_gbp"], 2) if t["band_complete"] else None,
            "price_year": t["price_year"],
            "components": t["count"],
            "flags": [] if t["band_complete"] else ["band_incomplete"],
        }
        for tier, t in tiers.items()
    }


class WealthAggregator:
    """Reads Wealth tables. Every DB problem propagates as `DatabaseUnavailable`."""

    def surface_row(self, cur, zone_code: str, vintage: int, *, internal: bool = False) -> dict[str, Any] | None:
        cur.execute(_SURFACE_INTERNAL_SQL if internal else _SURFACE_PUBLIC_SQL, (zone_code, vintage))
        return cur.fetchone()

    def point_rows(self, cur, table: str, lat: float, lng: float, *, internal: bool = False) -> list[dict[str, Any]]:
        if table not in ("resource_wealth", "eco_wealth"):
            raise ValueError(table)
        sql = _POINT_SQL if internal else _POINT_PUBLIC_SQL
        cur.execute(sql.format(table=table), (lng, lat))
        return list(cur.fetchall())

    def get_total_wealth(
        self, zone_code: str, vintage: int, lat: float, lng: float, *, internal: bool = False
    ) -> dict[str, Any]:
        with db.cursor() as cur:
            surface = self.surface_row(cur, zone_code, vintage, internal=internal)
            resource = self.point_rows(cur, "resource_wealth", lat, lng, internal=internal)
            eco = self.point_rows(cur, "eco_wealth", lat, lng, internal=internal)
            cur.execute(_DENOMINATOR_SQL, (zone_code, vintage))
            denominators = cur.fetchone()
            cur.execute(_SPINE_FLAGS_SQL, (zone_code, vintage))
            spine_row = cur.fetchone()
            spine = spine_from_flags(spine_row["flags"], present=True) if spine_row else None
            cur.execute(_ACCESS_PRESENT_SQL)
            access: Mapping[str, Any] | None | bool = False  # False = table not loaded
            if cur.fetchone()["present"]:
                cur.execute(_ACCESS_SQL, (zone_code, vintage))
                access = cur.fetchone()
            dwelling_count = population_count = None
            if surface is not None and surface.get("price_year") is not None:
                cur.execute(_DWELLING_COUNT_SQL, (zone_code, vintage, surface["price_year"]))
                dwelling_count = cur.fetchone()
                cur.execute(_POPULATION_COUNT_SQL, (zone_code, vintage, surface["price_year"]))
                population_count = cur.fetchone()
        return build_payload(surface, resource, eco, internal=internal, denominators=denominators,
                             dwelling_count=dwelling_count, population_count=population_count, spine=spine,
                             access=access)


def access_context(access: Mapping[str, Any] | None | bool) -> dict[str, Any]:
    """GIS dz_access context for one zone. Values and flags passed through as GIS wrote them."""
    if access is False:
        return {"status": "not_loaded", "flags": [], "attributions": []}
    if access is None:
        return {"status": "zone_missing", "flags": [], "attributions": []}
    try:
        credits = context_attributions("access")
    except AttributionMissing as exc:
        logger.error("Access context withheld: %s", exc)
        return {"status": "attribution_missing", "flags": [], "attributions": []}
    out: dict[str, Any] = {"status": "ok"}
    out.update({c: _num(access.get(c)) if c in ("job_access", "log_job_access", "road_km_nearest_luc")
                else access.get(c) for c in ACCESS_COLUMNS})
    out["flags"] = [f for f in str(access.get("flags") or "").split(";") if f]
    out["source_year"] = credits[0].get("source_year")
    out["attributions"] = credits
    out["note"] = "Context for Valuation's gradient check; never used in rents or totals."
    return out


def build_payload(
    surface: Mapping[str, Any] | None,
    resource: Iterable[Mapping[str, Any]],
    eco: Iterable[Mapping[str, Any]],
    *,
    internal: bool = False,
    denominators: Mapping[str, Any] | None = None,
    dwelling_count: Mapping[str, Any] | None = None,
    population_count: Mapping[str, Any] | None = None,
    spine: Mapping[str, Any] | None = None,
    access: Mapping[str, Any] | None | bool = False,
) -> dict[str, Any]:
    """Public by default: placeholders dropped, withheld figures redacted, allowlisted fields only.

    `internal=True` (dev endpoints only) lists placeholders and withheld rows with
    their numbers and Valuation's diagnostics. Totals are identical in both modes.
    """
    resource, eco = list(resource), list(eco)
    if not internal:
        # Point rows are site geometry: only measured figures from site-public sources (loud otherwise).
        check_site_rows("/georgist/wealth", resource + eco)
    components: list[dict[str, Any]] = []
    flags: list[str] = []
    surface_shown = False
    attribution: dict[str, Any] = {"note": "of which; already inside surface measured rent; never added"}
    policy: dict[str, Any] = {"note": "policy/scenario column; not measured rent; never added"}
    if surface is None:
        flags.append("surface_not_found")
    elif surface.get("quality") == "placeholder" and not internal:
        flags.append("surface_not_measured")  # no figure exists yet; nothing is shown
    else:
        zero = zero_dwellings(spine)  # Data Zones' zone_spine flag overrides any row or price
        comp = _component("surface", surface, "measured_rent", internal=internal,
                          not_applicable=ZERO_DWELLINGS if zero else None)
        shown = internal or not comp["withheld"]
        # Valuation quality tags passed through (e.g. plot_bands_borrowed); never acted on here.
        qflags = [t for t in (surface.get("quality_flags") or surface.get("proxy_tags") or [])
                  if t in QUALITY_FLAG_TAGS] if shown else []
        comp["quality_flags"] = sorted(set(qflags))
        components.append(comp)
        flags += [f for f in comp["quality_flags"] if f not in flags]
        surface_shown = shown
        has_figure = shown and not zero
        for col in ATTRIBUTION_COLUMNS:
            attribution[col] = _num(surface.get(col)) if has_figure else None
        attribution["planning_uplift_flag"] = surface.get("planning_uplift_flag")
        policy["policy_rent"] = _num(surface.get("policy_rent")) if has_figure else None
        if zero and comp["excluded_reason"] == ZERO_DWELLINGS:
            flags.append(ZERO_DWELLINGS)
        policy["policy_despec_factor"] = _num(surface.get("policy_despec_factor"))
        if comp["withheld"]:
            flags.append(f"surface_withheld_{comp['excluded_reason']}")
        if comp.get("model_filled"):
            flags.append("model_filled")
        if surface.get("absent_from_ros_price_file"):
            flags.append("absent_from_ros_price_file")
        if surface.get("negative_residual"):
            flags.append("negative_residual")
    for layer, rows in (("extractive", resource), ("eco", eco)):
        for r in rows:
            if r.get("quality") == "placeholder" and not internal:
                continue  # belt and braces: the public SQL already filters these
            components.append(_component(layer, r, "annual_rent_gbp", internal=internal))
    if internal and any(c["excluded_reason"] == "placeholder" for c in components):
        flags.append("placeholders_listed_internal_only")
    if internal and any(c.get("yield", {}).get("status") == "placeholder" for c in components):
        flags.append("yield_placeholder_internal_only")
    display = surface_views(
        None if "surface_not_measured" in flags else surface, denominators, shown=surface_shown,
        dwelling_count=dwelling_count, population_count=population_count, spine=spine,
    )
    flags += [f for f in display["flags"] if f not in flags]
    surface_comp = any(c["layer"] == "surface" and c["excluded_reason"] != ZERO_DWELLINGS for c in components)
    shown_views = [v for v, d in display["views"].items() if d["status"] in SHOWN_STATUSES]
    return {
        "components": components,
        "totals_by_tier": summarise(components),
        "attribution": attribution,
        "policy": policy,
        "display": display,
        "context": {"access": access_context(access)},
        "flags": flags,
        # Licence + attribution for every dataset behind the figures shown (e.g. EPC rollup).
        "attributions": attributions_for("surface_rent", shown_views) if surface_comp else [],
        "status": "experimental_research_estimate",
        "disclaimer": "Experimental research estimate. Not an official valuation or tax bill.",
    }


aggregator = WealthAggregator()
