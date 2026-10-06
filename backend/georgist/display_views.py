"""Display denominators for surface rent (economic rules v0.5, section 7 'Map denominators').

Three views, in this order:
  per_residential_hectare  DEFAULT. Rent / hectares of residential land (GIS).
                           Interim: zone area inside the NRS settlement, flagged rough.
  per_dwelling             Rent / NRS total dwellings (incl. vacant and second homes).
  per_resident             Optional. Rent / residents, always with the second-home share.

Valuation's row (687cf43, rules v0.5) already carries `residential_land_ha`,
`rent_per_res_ha`, `vacant_share` and `second_home_share`; those win. The
`dz_denominators` table (areas, GIS) fills gaps.

Counts (dwellings, population) are Scot-LAND Data Zones' and must match the figure
exactly: same integer vintage AND count_year == price_year (the money year).
  dwellings   datazones.dwellings_by_year.dwellings_total (NOT assessor_dwellings_dec).
              Valuation's own same-year `dwellings` only raise `dwellings_differ_from_valuation_row`.
  population  datazones.zone_spine.population at pop_year (mid-2022 on 2011 zones, mid-2024
              on 2022 zones), so a 2025 money year has no population and per_resident is pending.
A missing count is flagged (`dwellings_count_missing_for_price_year`,
`population_count_missing_for_price_year`) and NEVER filled from another year or vintage.

Never per hectare of whole-zone area. A missing denominator gives
status='denominator_pending' and value=None: nothing is computed or guessed.
Denominators share the figure's (code, vintage) key, so vintages always match.
"""

from __future__ import annotations

from typing import Any, Mapping

VIEW_ORDER = ("per_residential_hectare", "per_dwelling", "per_resident")
DEFAULT_VIEW = "per_residential_hectare"
PENDING = "denominator_pending"
HIGH_SECOND_HOME_SHARE = 0.10  # label only; Georgist may change


def _num(v: Any) -> float | None:
    return None if v is None else float(v)


def _per(rent: float | None, lo: float | None, hi: float | None, denom: float | None) -> dict[str, float | None]:
    if rent is None or not denom:
        return {"value": None, "low": None, "high": None}
    return {
        "value": round(rent / denom, 2),
        "low": round(lo / denom, 2) if lo is not None else None,
        "high": round(hi / denom, 2) if hi is not None else None,
    }


def _unavailable(status: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "value": None, "low": None, "high": None, **extra}


DWELLINGS_MISSING = "dwellings_count_missing_for_price_year"
POPULATION_MISSING = "population_count_missing_for_price_year"
DWELLINGS_DISAGREE = "dwellings_differ_from_valuation_row"
ZERO_DWELLINGS = "zero_dwellings"
POP_DWELLINGS_MISMATCH = "pop_dwellings_mismatch"
NOT_APPLICABLE = "not_applicable"
# Figures that must be null (never 0) for a zero-dwelling zone (rules v0.7).
ZERO_DWELLING_NULL_COLUMNS = ("measured_rent", "measured_rent_per_dwelling", "uncertainty_low", "uncertainty_high",
                              "rent_per_res_ha", "land_value", "land_value_zone_total", "policy_rent",
                              "infra_share", "planning_uplift")
DWELLINGS_SOURCE = "datazones.dwellings_by_year.dwellings_total"
POPULATION_SOURCE = "datazones.zone_spine.population"


def matching_count(surface: Mapping[str, Any], count: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """The count only if it is for the row's zone vintage and count_year == price_year; else None."""
    if not count:
        return None
    if count.get("vintage") != surface.get("vintage"):
        return None
    if count.get("count_year") is None or surface.get("price_year") is None:
        return None
    if int(count["count_year"]) != int(surface["price_year"]):
        return None
    return count


# datazones.zone_spine.flags: ONE text column, ';'-separated, '' = no flags (Data Zones README;
# loaded with FORCE_NOT_NULL so '' stays ''). Flags are lower-case snake_case tokens.
ZONE_FLAG_SEPARATOR = ";"
SPINE_FLAGS = (ZERO_DWELLINGS, POP_DWELLINGS_MISMATCH)


def parse_zone_flags(flags: str | None) -> frozenset[str]:
    """Split a zone_spine `flags` cell into its flag tokens. None or '' => no flags."""
    if flags is None:
        return frozenset()
    if not isinstance(flags, str):
        raise TypeError(f"zone_spine.flags must be read as text, got {type(flags).__name__}")
    return frozenset(t.strip() for t in flags.split(ZONE_FLAG_SEPARATOR) if t.strip())


def spine_from_flags(flags: str | None, *, present: bool = True) -> dict[str, bool] | None:
    """The engine's spine flags derived from the zone_spine `flags` string. None = no spine row."""
    if not present:
        return None
    tokens = parse_zone_flags(flags)
    return {f: f in tokens for f in SPINE_FLAGS}


def zero_dwellings(spine: Mapping[str, Any] | None) -> bool:
    """Rules v0.7: the `zero_dwellings` token in datazones.zone_spine.flags is the SINGLE source.
    True means the zone has no residential surface rent (not applicable, never 0), whatever the
    surface row or any RoS price says. No spine row = not flagged."""
    return bool(spine and spine.get("zero_dwellings") is True)


def pop_dwellings_mismatch(spine: Mapping[str, Any] | None) -> bool:
    return bool(spine and spine.get("pop_dwellings_mismatch") is True)


def surface_views(
    surface: Mapping[str, Any] | None,
    denominators: Mapping[str, Any] | None,
    *,
    shown: bool,
    dwelling_count: Mapping[str, Any] | None = None,
    population_count: Mapping[str, Any] | None = None,
    spine: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """`surface` is the (public) surface row; `shown` False when it is absent or withheld.

    `dwelling_count` / `population_count`: Data Zones rows {vintage, count_year, total_dwellings |
    population, ...}. Ones that do not match (vintage, price_year) are ignored, never used.
    """
    d = denominators or {}
    base = {"default": DEFAULT_VIEW, "order": list(VIEW_ORDER), "unit": "GBP per year", "flags": []}
    if surface is not None and shown and zero_dwellings(spine):
        return {**base, "flags": [ZERO_DWELLINGS],
                "views": {v: _unavailable(NOT_APPLICABLE, flag="zero dwellings: no residential surface rent")
                          for v in VIEW_ORDER}}
    if surface is None or not shown or _num(surface.get("measured_rent")) is None:
        status = "not_available" if surface is None or shown else "withheld"
        return {**base, "views": {v: _unavailable(status) for v in VIEW_ORDER}}
    flags: list[str] = base["flags"]

    rent = _num(surface["measured_rent"])
    lo, hi = _num(surface.get("uncertainty_low")), _num(surface.get("uncertainty_high"))
    views: dict[str, Any] = {}

    row_ha = _num(surface.get("residential_land_ha"))
    res_ha, settle_ha = _num(d.get("residential_land_ha")), _num(d.get("settlement_area_ha"))
    if row_ha:  # Valuation's own figure (GIS residential land, or settlement area tagged rough)
        rough = bool(surface.get("res_land_rough"))
        views["per_residential_hectare"] = {
            "status": "interim_rough" if rough else "ok", **_per(rent, lo, hi, row_ha),
            "denominator": "settlement_area_ha" if rough else "residential_land_ha", "denominator_value": row_ha,
            "denominator_source": "surface_rent_dz",
            **({"flag": "rough: zone area inside NRS settlement, not residential land"} if rough else {}),
        }
    elif res_ha:
        views["per_residential_hectare"] = {"status": "ok", **_per(rent, lo, hi, res_ha),
                                            "denominator": "residential_land_ha", "denominator_value": res_ha,
                                            "denominator_source": d.get("residential_land_source")}
    elif settle_ha:
        views["per_residential_hectare"] = {"status": "interim_rough", **_per(rent, lo, hi, settle_ha),
                                            "denominator": "settlement_area_ha", "denominator_value": settle_ha,
                                            "denominator_source": d.get("settlement_source"),
                                            "flag": "rough: zone area inside NRS settlement, not residential land"}
    else:
        views["per_residential_hectare"] = _unavailable(PENDING, denominator="residential_land_ha")

    price_year = surface.get("price_year")
    # Dwellings: Data Zones' datazones.dwellings_by_year.dwellings_total (NRS council tax, Sept)
    # at count_year = price_year, same vintage. Not assessor_dwellings_dec, and not Valuation's own
    # `dwellings` (that only raises a disagreement flag when it is for the same year).
    own_same_year = (
        surface.get("count_year") is not None and price_year is not None
        and int(surface["count_year"]) == int(price_year)
    )
    own_shs = _num(surface.get("second_home_share")) if own_same_year else None
    own_vac = _num(surface.get("vacant_share")) if own_same_year else None
    dc = matching_count(surface, dwelling_count)
    if dc is not None:
        n_dw, dw_source = dc.get("total_dwellings"), DWELLINGS_SOURCE
        shs = _num(dc.get("second_home_share"))
        vac = _num(dc.get("vacant_share"))
        shs = own_shs if shs is None else shs
        vac = own_vac if vac is None else vac
        own = surface.get("dwellings")
        if n_dw and own and own_same_year and int(own) != int(n_dw):
            flags.append(DWELLINGS_DISAGREE)
    else:
        n_dw, dw_source, shs, vac = None, None, own_shs, own_vac
    if n_dw:
        views["per_dwelling"] = {"status": "ok", **_per(rent, lo, hi, float(n_dw)),
                                 "denominator": "dwellings (NRS total, incl. vacant and second homes)",
                                 "denominator_value": n_dw, "denominator_year": price_year,
                                 "denominator_source": dw_source}
    else:
        flags.append(DWELLINGS_MISSING)
        views["per_dwelling"] = _unavailable(PENDING, denominator="dwellings", flag=f"no dwelling count for "
                                             f"{surface.get('vintage')} {price_year}; not taken from another year")

    pc = matching_count(surface, population_count)
    second = {"second_home_share": shs, "second_home_share_status": "ok" if shs is not None else PENDING,
              "vacant_share": vac}
    if pop_dwellings_mismatch(spine):
        flags.append(POP_DWELLINGS_MISMATCH)
        views["per_resident"] = _unavailable("not_available", denominator="population", reason=POP_DWELLINGS_MISMATCH,
                                             **second, flag="Data Zones flags population and dwellings as "
                                             "inconsistent for this zone; per-resident figure withheld")
    elif pc is not None and pc.get("population"):
        views["per_resident"] = {"status": "ok", **_per(rent, lo, hi, float(pc["population"])),
                                 "denominator": "population", "denominator_value": pc["population"],
                                 "denominator_year": price_year, "denominator_source": POPULATION_SOURCE,
                                 **second}
        if shs is not None and shs >= HIGH_SECOND_HOME_SHARE:
            views["per_resident"]["flag"] = "high second-home share: per-resident figure looks high"
    else:
        flags.append(POPULATION_MISSING)
        views["per_resident"] = _unavailable(PENDING, denominator="population", **second,
                                             flag=f"no population count for {surface.get('vintage')} "
                                             f"{price_year}; not taken from another year")
    return {**base, "views": views}
