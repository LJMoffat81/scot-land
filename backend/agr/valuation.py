"""Valuer-style residual assessment for an AGR roll (Wightman / SLRG).

Assessment steps (open-data approximation of professional practice):

1. HABU — existing authorised use (residential urban / agriculture rural).
   Hope value is excluded from the *basis of assessment* policy; market HPI is
   still existing-use transaction evidence (best open proxy).
2. Market value (MV) of a typical improved property at the location (council HPI).
3. Depreciated replacement cost (DRC) of improvements — rebuild £/m² × floor area
   × regional factor × remaining-value factor (Wightman residual strip).
4. Site capital (market residual) = max(0, MV − DRC), clamped to share bounds.
5. Economic site capital — Pickard adjustment so the roll charges economic rent,
   not speculative capital (farm productive factor; urban speculation discount).
6. Annual ground rent (roll base) = economic site capital × rentalisation yield.

Per-square map figures use £/sqm × grid area. Parcel and notional dwelling-plot
assessments are also reported when areas are known.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from agr.areas import CouncilArea
from agr.config import load_config

HPI_BASE_INDEX = 100.0


@dataclass
class RollAssessment:
    """One valuer-style residual assessment (per square + roll components)."""

    method: str
    confidence: str
    habu: str
    hope_value_excluded: bool
    # Composite property (typical dwelling) used for residual
    market_value_gbp: float | None
    dwelling_floor_sqm: float | None
    rebuild_cost_new_gbp: float | None
    depreciation_remaining_factor: float | None
    drc_improvements_gbp: float | None
    # Site capital — whole notional plot / assessment unit
    site_capital_market_gbp: float
    site_capital_economic_gbp: float
    site_share_implied: float | None
    notional_plot_sqm: float
    # Intensities
    site_capital_market_per_sqm_gbp: float
    site_capital_economic_per_sqm_gbp: float
    annual_rent_economic_per_sqm_gbp: float
    annual_rent_market_per_sqm_gbp: float
    yield_rate: float
    pickard_factor: float
    pickard_label: str
    # Roll lines (annual £)
    roll_annual_rent_per_sqm_gbp: float
    roll_annual_rent_grid_square_gbp: float
    roll_annual_rent_notional_plot_gbp: float
    roll_annual_rent_parcel_gbp: float | None
    parcel_area_sqm: float | None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _hpi_adjustment_factor(config: dict) -> float:
    from agr.areas import COUNCILS_PATH
    import json

    if not COUNCILS_PATH.exists():
        return 2.5
    with COUNCILS_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    current_index = payload.get("scotland_hpi_index")
    if not current_index:
        return 2.5
    return current_index / HPI_BASE_INDEX


def _region_rebuild_factor(council_code: str, config: dict) -> float:
    rebuild = config.get("valuer_roll", {}).get("rebuild", {})
    factors = rebuild.get("region_factors") or {}
    return float(factors.get(council_code, factors.get("default", 1.0)))


def _rebuild_rate(rebuild: dict, key: str) -> float:
    if key not in rebuild:
        raise KeyError(key)
    return float(rebuild[key])


def _blended_rebuild_per_m2(config: dict) -> float:
    rebuild = config.get("valuer_roll", {}).get("rebuild", {})
    mix = config.get("valuer_roll", {}).get("property_mix") or {}
    house = _rebuild_rate(rebuild, "house_gbp_per_m2")
    flat = _rebuild_rate(rebuild, "flat_gbp_per_m2")
    house_share = float(mix.get("house_share", 0.75))
    flat_share = float(mix.get("flat_share", 0.25))
    total = house_share + flat_share
    if total <= 0:
        return house
    return (house * house_share + flat * flat_share) / total


def _urban_residual_drc(
    council: CouncilArea,
    config: dict,
    parcel_area_sqm: float | None,
) -> RollAssessment:
    """Wightman residual: MV − DRC of buildings, HABU = existing residential."""
    valuer = config.get("valuer_roll") or {}
    valuation = config["valuation"]
    despec = config["despeculation"]
    per_square = config["per_square"]

    floor_sqm = float(valuer.get("typical_dwelling_sqm", valuation.get("typical_dwelling_sqm", 85)))
    plot_sqm = float(valuer.get("typical_plot_sqm", 280))
    yield_rate = float(valuer.get("yield_rate", valuation.get("yield_rate", 0.05)))
    remaining = float(
        (valuer.get("depreciation") or {}).get("average_stock_remaining_factor", 0.55)
    )
    min_share = float((valuer.get("residual") or {}).get("min_site_share", 0.15))
    max_share = float((valuer.get("residual") or {}).get("max_site_share", 0.85))
    grid_sqm = float(per_square.get("area_sqm", 9))

    mv = float(council.average_price_gbp)
    region_factor = _region_rebuild_factor(council.code, config)
    rebuild_m2 = _blended_rebuild_per_m2(config)
    rebuild_new = floor_sqm * rebuild_m2 * region_factor
    drc = rebuild_new * remaining

    raw_site = mv - drc
    # Clamp implied site share to valuation-practice bounds
    if mv > 0:
        implied = raw_site / mv
        if implied < min_share:
            site_market = mv * min_share
            clamp_note = f"Residual clamped to minimum site share {min_share:.0%} (MV − DRC was {implied:.0%})."
        elif implied > max_share:
            site_market = mv * max_share
            clamp_note = f"Residual clamped to maximum site share {max_share:.0%} (MV − DRC was {implied:.0%})."
        else:
            site_market = max(0.0, raw_site)
            clamp_note = None
        site_share_implied = site_market / mv
    else:
        site_market = 0.0
        site_share_implied = 0.0
        clamp_note = "Zero market value."

    # Attribute residual to notional plot, then per sqm
    site_per_sqm_market = site_market / plot_sqm if plot_sqm > 0 else 0.0

    pickard = float(despec.get("urban_speculation_discount", 0.70))
    site_per_sqm_economic = site_per_sqm_market * pickard
    site_economic_plot = site_market * pickard

    rent_per_sqm_market = site_per_sqm_market * yield_rate
    rent_per_sqm_economic = site_per_sqm_economic * yield_rate

    notes = [
        "Valuer residual (Wightman): site capital = market value − DRC of improvements.",
        f"HABU = existing residential use (authorised-consent / existing-use rule); hope value excluded from assessment policy.",
        f"MV (council HPI average dwelling) = £{mv:,.0f}.",
        f"Rebuild new ≈ {floor_sqm:.0f} m² × £{rebuild_m2:,.0f}/m² × region {region_factor:.2f} = £{rebuild_new:,.0f}.",
        f"DRC = rebuild × stock remaining factor {remaining:.0%} = £{drc:,.0f}.",
        f"Market residual site capital (notional {plot_sqm:.0f} m² plot) = £{site_market:,.0f} ({site_share_implied:.0%} of MV).",
        f"Pickard urban economic factor {pickard:.0%} applied to residual site capital (speculative premium).",
        f"Annual economic rent = economic site capital × yield {yield_rate:.0%}.",
    ]
    if clamp_note:
        notes.append(clamp_note)

    confidence = "high" if council.distance_km < 8 and council.lookup_method == "boundary" else "medium"
    if council.lookup_method == "centroid_fallback":
        confidence = "medium"
        notes.append(
            f"Boundary miss — nearest centroid {council.distance_km} km ({council.name})."
        )

    parcel_rent = None
    if parcel_area_sqm and parcel_area_sqm > 0:
        parcel_rent = round(rent_per_sqm_economic * parcel_area_sqm, 2)
        notes.append(
            f"Parcel roll line: £{parcel_rent:,.2f}/year on {parcel_area_sqm:,.0f} m² cadastral area."
        )

    return RollAssessment(
        method="residual_drc",
        confidence=confidence,
        habu="existing_residential",
        hope_value_excluded=True,
        market_value_gbp=round(mv, 2),
        dwelling_floor_sqm=floor_sqm,
        rebuild_cost_new_gbp=round(rebuild_new, 2),
        depreciation_remaining_factor=remaining,
        drc_improvements_gbp=round(drc, 2),
        site_capital_market_gbp=round(site_market, 2),
        site_capital_economic_gbp=round(site_economic_plot, 2),
        site_share_implied=round(site_share_implied, 4),
        notional_plot_sqm=plot_sqm,
        site_capital_market_per_sqm_gbp=round(site_per_sqm_market, 2),
        site_capital_economic_per_sqm_gbp=round(site_per_sqm_economic, 2),
        annual_rent_economic_per_sqm_gbp=round(rent_per_sqm_economic, 4),
        annual_rent_market_per_sqm_gbp=round(rent_per_sqm_market, 4),
        yield_rate=yield_rate,
        pickard_factor=pickard,
        pickard_label="urban_speculation_discount",
        roll_annual_rent_per_sqm_gbp=round(rent_per_sqm_economic, 4),
        roll_annual_rent_grid_square_gbp=round(rent_per_sqm_economic * grid_sqm, 2),
        roll_annual_rent_notional_plot_gbp=round(rent_per_sqm_economic * plot_sqm, 2),
        roll_annual_rent_parcel_gbp=parcel_rent,
        parcel_area_sqm=parcel_area_sqm,
        notes=notes,
    )


def _rural_productive(
    council: CouncilArea,
    config: dict,
    parcel_area_sqm: float | None,
) -> RollAssessment:
    """Rural roll: productive land capital (Pickard), not farm-sale speculation."""
    valuer = config.get("valuer_roll") or {}
    valuation = config["valuation"]
    despec = config["despeculation"]
    per_square = config["per_square"]
    land_use = config["land_use_values_gbp_per_ha_2009"]

    yield_rate = float(valuer.get("yield_rate", valuation.get("yield_rate", 0.05)))
    pickard = float(despec.get("farmland_market_to_productive", 0.20))
    grid_sqm = float(per_square.get("area_sqm", 9))
    # Notional rural assessment unit = 1 ha for roll display, still report /sqm
    notional_plot = 10_000.0

    hpi_factor = _hpi_adjustment_factor(config)
    # Benchmark is already a land-use capital figure (2009); treat as closer to
    # productive/category value, then apply Pickard factor for market→productive
    # if benchmarks were market-based historically. Config agriculture is low
    # (productive-oriented); still apply Pickard for consistency with SLRG.
    agriculture_ha = float(land_use["agriculture"])
    marketish_per_ha = agriculture_ha * hpi_factor
    economic_per_ha = marketish_per_ha * pickard
    economic_per_sqm = economic_per_ha / 10_000.0
    market_per_sqm = marketish_per_ha / 10_000.0

    rent_per_sqm = economic_per_sqm * yield_rate
    rent_market_per_sqm = market_per_sqm * yield_rate

    notes = [
        "Rural productive assessment (Pickard / land-use category).",
        "HABU = agriculture (existing rural use); hope value excluded.",
        f"Category capital £{agriculture_ha:,.0f}/ha (2009) × HPI factor {hpi_factor:.2f} = £{marketish_per_ha:,.0f}/ha.",
        f"Pickard farmland productive factor {pickard:.0%} (market ≈ 5× productive in Pickard 2018).",
        f"Economic site capital £{economic_per_ha:,.0f}/ha; annual rent at {yield_rate:.0%} yield.",
        f"Council: {council.name} ({council.code}).",
    ]
    confidence = "medium" if council.distance_km < 25 else "low"

    parcel_rent = None
    if parcel_area_sqm and parcel_area_sqm > 0:
        parcel_rent = round(rent_per_sqm * parcel_area_sqm, 2)

    return RollAssessment(
        method="productive_land_use",
        confidence=confidence,
        habu="existing_agriculture",
        hope_value_excluded=True,
        market_value_gbp=None,
        dwelling_floor_sqm=None,
        rebuild_cost_new_gbp=None,
        depreciation_remaining_factor=None,
        drc_improvements_gbp=None,
        site_capital_market_gbp=round(marketish_per_ha, 2),
        site_capital_economic_gbp=round(economic_per_ha, 2),
        site_share_implied=None,
        notional_plot_sqm=notional_plot,
        site_capital_market_per_sqm_gbp=round(market_per_sqm, 4),
        site_capital_economic_per_sqm_gbp=round(economic_per_sqm, 4),
        annual_rent_economic_per_sqm_gbp=round(rent_per_sqm, 6),
        annual_rent_market_per_sqm_gbp=round(rent_market_per_sqm, 6),
        yield_rate=yield_rate,
        pickard_factor=pickard,
        pickard_label="farmland_market_to_productive",
        roll_annual_rent_per_sqm_gbp=round(rent_per_sqm, 6),
        roll_annual_rent_grid_square_gbp=round(rent_per_sqm * grid_sqm, 4),
        roll_annual_rent_notional_plot_gbp=round(rent_per_sqm * notional_plot, 2),
        roll_annual_rent_parcel_gbp=parcel_rent,
        parcel_area_sqm=parcel_area_sqm,
        notes=notes,
    )


def assess_for_agr_roll(
    council: CouncilArea,
    config: dict | None = None,
    *,
    parcel_area_sqm: float | None = None,
) -> RollAssessment:
    """Primary entry: valuer-style residual / productive assessment."""
    config = config or load_config()
    if council.rural:
        return _rural_productive(council, config, parcel_area_sqm)
    return _urban_residual_drc(council, config, parcel_area_sqm)


def residual_site_capital_per_sqm(
    council: CouncilArea,
    config: dict | None = None,
) -> tuple[float, str, str, list[str]]:
    """Backward-compatible helper: economic site capital £/sqm + metadata."""
    assessment = assess_for_agr_roll(council, config)
    return (
        assessment.site_capital_economic_per_sqm_gbp,
        assessment.method,
        assessment.confidence,
        assessment.notes,
    )
