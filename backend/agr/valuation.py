"""Valuer-style residual assessment for an AGR roll (Wightman / SLRG).

Assessment steps (open-data approximation of professional practice):

1. HABU — existing authorised use (residential urban / agriculture rural).
   Hope value is excluded from the *basis of assessment* policy; market HPI is
   still existing-use transaction evidence (best open proxy).
2. Market value (MV) of one typical improved dwelling. The published urban price
   is the data-zone median (shrunk when the count is thin). The council median
   is the comparison and the fallback. It does not estimate land share or yield.
3. Depreciated replacement cost (DRC) of improvements — rebuild £/m² × floor area
   × regional factor × remaining-value factor (Wightman residual strip).
4. Site capital (market residual) = max(0, MV − DRC), with an 85% ceiling that
   is a bound, not an estimate. The old 15% floor is a sensitivity only.
5. Economic site capital — Pickard adjustment so the roll charges economic rent,
   not speculative capital (farm productive factor; urban speculation discount).
6. Annual ground rent (roll base) = economic site capital × rentalisation yield,
   for one average dwelling. A parcel uses a capped area elasticity, not £/m² × area.

The £/m² rate and the 9 m² cell are diagnostic. Rural rent stays the category £/ha.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from agr.areas import CouncilArea
from agr.config import load_config
from agr.yield_config import scale_rent, yield_band_from_config

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
    # Old 15–85% clamp of the market residual, before Pickard. Not the published charge.
    site_capital_clamped_sensitivity_gbp: float | None = None
    # Council median kept beside the published urban MV. Not a second charge.
    mv_council_gbp: float | None = None
    # Georgist INTERNAL yield band (rents shown as band, not a point).
    yield_rate_low: float | None = None
    yield_rate_high: float | None = None
    yield_high_clipped_at_cap: bool = False
    yield_result_hash: str | None = None
    roll_annual_rent_notional_plot_low_gbp: float | None = None
    roll_annual_rent_notional_plot_high_gbp: float | None = None
    roll_annual_rent_parcel_low_gbp: float | None = None
    roll_annual_rent_parcel_high_gbp: float | None = None
    rent_display: str = "band"
    value_basis: str = "proxy"
    bed_mapping_sensitive: bool = True
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


def _clamped_site_sensitivity(raw_site: float, mv: float, min_share: float, max_share: float) -> float:
    """Old 15–85% clamp of the market residual, before Pickard. Not published."""
    if mv <= 0:
        return 0.0
    implied = raw_site / mv
    if implied < min_share:
        return mv * min_share
    if implied > max_share:
        return mv * max_share
    return max(0.0, raw_site)


def _urban_residual_drc(
    council: CouncilArea,
    config: dict,
    parcel_area_sqm: float | None,
    *,
    market_value_gbp: float | None = None,
    mv_council_gbp: float | None = None,
    price_notes: list[str] | None = None,
) -> RollAssessment:
    """Wightman residual: MV − DRC of buildings, HABU = existing residential.

    The headline is one average dwelling. A parcel is that dwelling rent times
    a capped area ratio to an elasticity. £/m² times parcel area is not published.
    """
    valuer = config.get("valuer_roll") or {}
    valuation = config["valuation"]
    despec = config["despeculation"]
    per_square = config["per_square"]

    floor_sqm = float(valuer.get("typical_dwelling_sqm", valuation.get("typical_dwelling_sqm", 85)))
    plot_sqm = float(valuer.get("typical_plot_sqm", 280))
    yband = yield_band_from_config(config)
    yield_rate = float(valuer.get("yield_rate", valuation.get("yield_rate", yband.central)))
    remaining = float(
        (valuer.get("depreciation") or {}).get("average_stock_remaining_factor", 0.55)
    )
    min_share = float((valuer.get("residual") or {}).get("min_site_share", 0.15))
    max_share = float((valuer.get("residual") or {}).get("max_site_share", 0.85))
    eta = float(valuer.get("area_elasticity", 0.35))
    max_area_ratio = float(valuer.get("max_area_ratio", 4.0))
    grid_sqm = float(per_square.get("area_sqm", 9))

    mv_council = float(council.average_price_gbp if mv_council_gbp is None else mv_council_gbp)
    mv = float(council.average_price_gbp if market_value_gbp is None else market_value_gbp)
    region_factor = _region_rebuild_factor(council.code, config)
    rebuild_m2 = _blended_rebuild_per_m2(config)
    rebuild_new = floor_sqm * rebuild_m2 * region_factor
    drc = rebuild_new * remaining

    raw_site = mv - drc
    sensitivity = _clamped_site_sensitivity(raw_site, mv, min_share, max_share)
    ceiling_binds = False
    if mv <= 0:
        site_market = 0.0
        site_share_implied = 0.0
        margin_note = "Zero market value."
    elif raw_site <= 0:
        site_market = 0.0
        site_share_implied = 0.0
        margin_note = "The residual is at or below the margin."
    elif raw_site / mv > max_share:
        site_market = mv * max_share
        site_share_implied = site_market / mv
        ceiling_binds = True
        margin_note = (
            f"The {max_share:.0%} ceiling binds (MV − DRC was {raw_site / mv:.0%} of MV)."
        )
    else:
        site_market = raw_site
        site_share_implied = site_market / mv
        margin_note = None

    site_market_r = round(site_market, 2)
    pickard = float(despec.get("urban_speculation_discount", 0.70))
    site_economic = round(site_market_r * pickard, 2)
    dwelling_rent = round(site_economic * yield_rate, 2)
    effective_rate = pickard * yield_rate

    site_per_sqm_market = site_market_r / plot_sqm if plot_sqm > 0 else 0.0
    site_per_sqm_economic = site_economic / plot_sqm if plot_sqm > 0 else 0.0
    rent_per_sqm_market = site_per_sqm_market * yield_rate
    rent_per_sqm_economic = dwelling_rent / plot_sqm if plot_sqm > 0 else 0.0

    geography = list(price_notes or [])
    if market_value_gbp is None and not geography:
        geography.append("Published MV is the council median. This rate is not a data-zone price.")

    notes = [
        "Valuer residual (Wightman): site capital = market value − DRC of improvements.",
        "HABU = existing residential use (authorised-consent / existing-use rule); hope value excluded from assessment policy.",
        *geography,
        (
            f"MV (improved dwelling) = £{mv:,.0f}. "
            f"Council median for comparison (mv_council_gbp) = £{mv_council:,.0f}."
        ),
        (
            "A data-zone house price is the price of an improved dwelling. "
            "It does not estimate land share, yield, the Pickard factor, or area elasticity. "
            "Those stay labelled assumptions."
        ),
        f"Rebuild new ≈ {floor_sqm:.0f} m² × £{rebuild_m2:,.0f}/m² × region {region_factor:.2f} = £{rebuild_new:,.0f}.",
        f"DRC = rebuild × stock remaining factor {remaining:.0%} = £{drc:,.0f}.",
        (
            f"Market residual site capital (one dwelling on a {plot_sqm:.0f} m² plot) "
            f"= £{site_market_r:,.0f} ({site_share_implied:.0%} of MV)."
        ),
        f"The {max_share:.0%} site-share ceiling is a bound, not an estimate.",
        (
            f"Pickard urban economic factor {pickard:.0%} applied to residual site capital "
            "(speculative premium)."
        ),
        (
            f"Annual economic rent band = economic site capital × yield band "
            f"{yband.low:.2%}–{yband.high:.2%} (central {yield_rate:.2%}; "
            f"hash {yband.result_hash})."
        ),
        (
            f"Yield decomposition (INTERNAL): r {yband.r:.2%} + p {yband.p:.2%} − g {yband.g:.2%} "
            f"= {yband.central_from_decomposition:.2%}."
            + (" High end clipped at the 4.5% cap." if yband.high_clipped_at_cap else "")
        ),
        (
            f"Effective central rate = {pickard:.2f} × {yield_rate:.2f} = {effective_rate:.3f}. "
            "Rents are shown as a band, not a point. publication_status=blocked."
        ),
        "The £/m² rate and the 9 m² cell are diagnostic. They are not the parcel charge.",
        "Research estimate (INTERNAL provisional), not an official valuation or a tax bill.",
    ]
    if margin_note:
        notes.append(margin_note)
    if ceiling_binds:
        notes.append("The ceiling binds on this residual.")

    confidence = "high" if council.distance_km < 8 and council.lookup_method == "boundary" else "medium"
    if council.lookup_method == "centroid_fallback":
        confidence = "medium"
        notes.append(
            f"Boundary miss — nearest centroid {council.distance_km} km ({council.name})."
        )

    parcel_rent = None
    if parcel_area_sqm and parcel_area_sqm > 0 and plot_sqm > 0:
        raw_ratio = parcel_area_sqm / plot_sqm
        used_ratio = min(raw_ratio, max_area_ratio)
        parcel_rent = round(dwelling_rent * (used_ratio ** eta), 2)
        notes.append(
            f"Parcel roll line (central): £{parcel_rent:,.2f}/year = dwelling rent "
            f"£{dwelling_rent:,.2f} × ({used_ratio:.3f})^{eta:.2f}. Display as yield band."
        )
        notes.append(
            f"Area elasticity {eta:.2f} is a labelled assumption. "
            f"Reference plot {plot_sqm:.0f} m²."
        )
        if raw_ratio > max_area_ratio:
            notes.append(
                f"The area-ratio cap binds at {max_area_ratio:g} "
                f"(parcel is {raw_ratio:.1f} times the {plot_sqm:.0f} m² reference plot)."
            )

    plot_lo, plot_hi = scale_rent(dwelling_rent, yband)
    parcel_lo, parcel_hi = scale_rent(parcel_rent, yband)

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
        site_capital_market_gbp=site_market_r,
        site_capital_economic_gbp=site_economic,
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
        roll_annual_rent_notional_plot_gbp=dwelling_rent,
        roll_annual_rent_parcel_gbp=parcel_rent,
        parcel_area_sqm=parcel_area_sqm,
        site_capital_clamped_sensitivity_gbp=round(sensitivity, 2),
        mv_council_gbp=round(mv_council, 2),
        yield_rate_low=yband.low,
        yield_rate_high=yband.high,
        yield_high_clipped_at_cap=yband.high_clipped_at_cap,
        yield_result_hash=yband.result_hash,
        roll_annual_rent_notional_plot_low_gbp=plot_lo,
        roll_annual_rent_notional_plot_high_gbp=plot_hi,
        roll_annual_rent_parcel_low_gbp=parcel_lo,
        roll_annual_rent_parcel_high_gbp=parcel_hi,
        rent_display="band",
        value_basis=yband.value_basis,
        bed_mapping_sensitive=yband.bed_mapping_sensitive,
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

    yband = yield_band_from_config(config)
    yield_rate = float(valuer.get("yield_rate", valuation.get("yield_rate", yband.central)))
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
    plot_rent = round(rent_per_sqm * notional_plot, 2)

    notes = [
        "Rural productive assessment (Pickard / land-use category).",
        "HABU = agriculture (existing rural use); hope value excluded.",
        "Uniform category rent across Scotland. Urban area elasticity is not applied.",
        f"Category capital £{agriculture_ha:,.0f}/ha (2009) × HPI factor {hpi_factor:.2f} = £{marketish_per_ha:,.0f}/ha.",
        f"Pickard farmland productive factor {pickard:.0%} (market ≈ 5× productive in Pickard 2018).",
        (
            f"Economic site capital £{economic_per_ha:,.0f}/ha; annual rent band at "
            f"{yband.low:.2%}–{yband.high:.2%} (central {yield_rate:.2%}; hash {yband.result_hash})."
        ),
        f"Council: {council.name} ({council.code}).",
        "Research estimate (INTERNAL provisional), not an official valuation or a tax bill.",
    ]
    confidence = "medium" if council.distance_km < 25 else "low"

    parcel_rent = None
    if parcel_area_sqm and parcel_area_sqm > 0:
        parcel_rent = round(rent_per_sqm * parcel_area_sqm, 2)

    plot_lo, plot_hi = scale_rent(plot_rent, yband)
    parcel_lo, parcel_hi = scale_rent(parcel_rent, yband)

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
        roll_annual_rent_notional_plot_gbp=plot_rent,
        roll_annual_rent_parcel_gbp=parcel_rent,
        parcel_area_sqm=parcel_area_sqm,
        yield_rate_low=yband.low,
        yield_rate_high=yband.high,
        yield_high_clipped_at_cap=yband.high_clipped_at_cap,
        yield_result_hash=yband.result_hash,
        roll_annual_rent_notional_plot_low_gbp=plot_lo,
        roll_annual_rent_notional_plot_high_gbp=plot_hi,
        roll_annual_rent_parcel_low_gbp=parcel_lo,
        roll_annual_rent_parcel_high_gbp=parcel_hi,
        rent_display="band",
        value_basis=yband.value_basis,
        bed_mapping_sensitive=yband.bed_mapping_sensitive,
        notes=notes,
    )


def assess_for_agr_roll(
    council: CouncilArea,
    config: dict | None = None,
    *,
    parcel_area_sqm: float | None = None,
    market_value_gbp: float | None = None,
    mv_council_gbp: float | None = None,
    price_notes: list[str] | None = None,
) -> RollAssessment:
    """Primary entry: valuer-style residual / productive assessment.

    A rural assessment ignores a house-price override. Urban area elasticity
    is not applied on the category rent.
    """
    config = config or load_config()
    if council.rural:
        return _rural_productive(council, config, parcel_area_sqm)
    return _urban_residual_drc(
        council,
        config,
        parcel_area_sqm,
        market_value_gbp=market_value_gbp,
        mv_council_gbp=mv_council_gbp,
        price_notes=price_notes,
    )


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
