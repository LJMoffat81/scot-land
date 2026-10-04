from __future__ import annotations

from dataclasses import asdict, dataclass, field

from agr.areas import CouncilArea, lookup_council
from agr.config import load_config
from agr.scenarios import compute_scenarios, resolve_active_scenario, scenario_to_dict
from agr.valuation import assess_for_agr_roll
from agr.wide_range import wide_range_for
from spatial.grid import GridSquare
from spatial.parcels import lookup_parcel
from spatial.polygons import lookup_council_boundary, lookup_glasgow_ward_18
from spatial.urban_rural import NotLand


@dataclass
class AgrBreakdown:
    annual_ground_rent_gbp: float
    economic_annual_rent_gbp: float
    active_scenario: str
    site_rental_per_sqm_gbp: float
    site_capital_per_sqm_gbp: float
    despeculated_site_capital_per_sqm_gbp: float
    despeculated_site_value_gbp: float
    site_share_used: float | None
    yield_rate: float
    capture_rate: float
    confidence: str
    method: str
    disclaimer: str
    notes: list[str]
    council_code: str
    council_name: str
    average_price_gbp: int | None
    lookup_method: str
    parcel_id: str | None
    parcel_area_sqm: float | None
    ward_name: str | None
    scenarios: dict[str, dict]
    # Equal-share (Ogilvie / Paine framing)
    equal_share_enabled: bool
    equal_share_rent_per_person_gbp: float | None
    square_as_fraction_of_equal_claim: float | None
    scotland_population: int | None
    # Integrity
    estimate_kind: str
    estimate_label: str
    site_share_source: str
    national_rent_pool_gbp: float
    integrity_caveats: list[str]
    # Valuer roll assessment
    habu: str
    hope_value_excluded: bool
    market_value_gbp: float | None
    rebuild_cost_new_gbp: float | None
    drc_improvements_gbp: float | None
    site_capital_market_per_sqm_gbp: float
    roll_annual_rent_notional_plot_gbp: float
    roll_annual_rent_parcel_gbp: float | None
    notional_plot_sqm: float
    pickard_factor: float
    pickard_label: str
    assessment: dict = field(default_factory=dict)
    sensitivity_overrides: dict = field(default_factory=dict)
    wide_range: bool = False
    wide_range_ratio: float | None = None
    basis: str = "town"


def _equal_share_fields(economic_rent: float, config: dict) -> tuple[bool, float | None, float | None, int | None]:
    equal_cfg = config.get("equal_share") or {}
    if not equal_cfg.get("enabled", False):
        return False, None, None, None

    population = int(equal_cfg.get("scotland_population") or 0)
    rent_pool = float(config["macro"]["estimated_scotland_annual_rent_gbp"])
    if population <= 0 or rent_pool <= 0:
        return True, None, None, population or None

    per_person = rent_pool / population
    fraction = economic_rent / per_person if per_person > 0 else None
    return True, round(per_person, 2), (round(fraction, 6) if fraction is not None else None), population


def calculate_square_agr(
    square: GridSquare,
    scenario: str | None = None,
    config: dict | None = None,
    council: CouncilArea | None = None,
) -> AgrBreakdown:
    config = config if config is not None else load_config()
    per_square = config["per_square"]
    integrity = config.get("integrity") or {}
    active_scenario = resolve_active_scenario(scenario)
    sensitivity = dict(config.get("_sensitivity_overrides") or {})

    if council is None:
        if lookup_council_boundary(square.lat, square.lng) is None:
            raise NotLand(square.lat, square.lng)
        council = lookup_council(square.lat, square.lng)
    parcel = lookup_parcel(square.lat, square.lng)
    ward = lookup_glasgow_ward_18(square.lat, square.lng)

    parcel_area = parcel.area_sqm if parcel else None
    assessment = assess_for_agr_roll(council, config, parcel_area_sqm=parcel_area)

    if parcel is not None and assessment.confidence == "medium":
        assessment.confidence = "high"
        assessment.notes.append(
            f"ROS INSPIRE cadastral parcel {parcel.label} ({parcel.area_sqm:,.0f} sqm) on roll."
        )

    area_sqm = float(per_square["area_sqm"])
    capture_rate = float(per_square["agr_capture_rate"])
    site_rental_per_sqm = assessment.annual_rent_economic_per_sqm_gbp
    despeculated_capital_per_sqm = assessment.site_capital_economic_per_sqm_gbp
    market_capital_per_sqm = assessment.site_capital_market_per_sqm_gbp

    economic_rent, scenario_charges = compute_scenarios(
        site_rental_per_sqm=site_rental_per_sqm,
        despeculated_site_capital_per_sqm=despeculated_capital_per_sqm,
        area_sqm=area_sqm,
        capture_rate=capture_rate,
        config=config,
    )
    active_charge = scenario_charges[active_scenario].annual_charge_gbp

    eq_enabled, eq_per_person, eq_fraction, eq_pop = _equal_share_fields(economic_rent, config)
    rent_pool = float(config["macro"]["estimated_scotland_annual_rent_gbp"])

    notes = [
        *assessment.notes,
        f"Council resolved via {council.lookup_method} polygon lookup.",
        (
            f"Macro vs map: Sandilands national rent pool is £{rent_pool / 1e9:.0f}bn "
            "(equal-share + income-tax scaling). Roll residual is independent and not "
            "calibrated so all cells sum to that pool."
        ),
        "Smith/Wightman: charge is on ground-rent of the site after stripping buildings (DRC).",
        "Pickard: economic rent base after removing speculative capital premium.",
    ]
    if sensitivity:
        notes.append(f"Sensitivity overrides active (research): {sensitivity}")
    if eq_enabled and eq_per_person is not None and eq_fraction is not None:
        notes.append(
            f"Ogilvie/Paine/Unitism equal-share (national pool): one Scot ≈ £{eq_per_person:,.0f}/year; "
            f"this cell’s roll economic rent is {eq_fraction * 100:.4f}% of that claim "
            f"(could fund services or a citizen dividend)."
        )
        notes.append(
            "Martin Adams (Unitism): community collects land rental value; wages and buildings untaxed."
        )
        notes.append(
            "Lars Doucet / CLE: next roll upgrade path is sales-based mass appraisal (OpenAVMKit), "
            "not a change to SLRG residual policy."
        )
    if ward is not None:
        notes.append(
            f"Location within Glasgow Ward {ward.ward_number} ({ward.ward_name}) validation area."
        )

    site_share_source = (
        f"implied_residual_{assessment.site_share_implied:.0%}"
        if assessment.site_share_implied is not None
        else "productive_land_use"
    )
    wide_range, wide_range_ratio = wide_range_for(council.code)
    basis = "countryside" if council.rural else "town"

    return AgrBreakdown(
        annual_ground_rent_gbp=active_charge,
        economic_annual_rent_gbp=round(economic_rent, 2),
        active_scenario=active_scenario,
        site_rental_per_sqm_gbp=round(site_rental_per_sqm, 4),
        site_capital_per_sqm_gbp=round(market_capital_per_sqm, 4),
        despeculated_site_capital_per_sqm_gbp=round(despeculated_capital_per_sqm, 4),
        despeculated_site_value_gbp=round(despeculated_capital_per_sqm * area_sqm, 2),
        site_share_used=assessment.site_share_implied,
        yield_rate=assessment.yield_rate,
        capture_rate=capture_rate,
        confidence=assessment.confidence,
        method=assessment.method,
        disclaimer=config["disclaimer"],
        notes=notes,
        council_code=council.code,
        council_name=council.name,
        average_price_gbp=council.average_price_gbp if not council.rural else None,
        lookup_method=council.lookup_method,
        parcel_id=parcel.label if parcel else None,
        parcel_area_sqm=parcel.area_sqm if parcel else None,
        ward_name=ward.ward_name if ward else None,
        scenarios={key: scenario_to_dict(value) for key, value in scenario_charges.items()},
        equal_share_enabled=eq_enabled,
        equal_share_rent_per_person_gbp=eq_per_person,
        square_as_fraction_of_equal_claim=eq_fraction,
        scotland_population=eq_pop,
        estimate_kind=integrity.get("estimate_kind", "valuer_residual_roll"),
        estimate_label=integrity.get(
            "estimate_label", "Valuer residual AGR roll (open-data approximation)"
        ),
        site_share_source=site_share_source,
        national_rent_pool_gbp=rent_pool,
        integrity_caveats=list(integrity.get("caveats") or []),
        habu=assessment.habu,
        hope_value_excluded=assessment.hope_value_excluded,
        market_value_gbp=assessment.market_value_gbp,
        rebuild_cost_new_gbp=assessment.rebuild_cost_new_gbp,
        drc_improvements_gbp=assessment.drc_improvements_gbp,
        site_capital_market_per_sqm_gbp=assessment.site_capital_market_per_sqm_gbp,
        roll_annual_rent_notional_plot_gbp=assessment.roll_annual_rent_notional_plot_gbp,
        roll_annual_rent_parcel_gbp=assessment.roll_annual_rent_parcel_gbp,
        notional_plot_sqm=assessment.notional_plot_sqm,
        pickard_factor=assessment.pickard_factor,
        pickard_label=assessment.pickard_label,
        assessment=assessment.to_dict(),
        sensitivity_overrides=sensitivity,
        wide_range=wide_range,
        wide_range_ratio=wide_range_ratio,
        basis=basis,
    )


def breakdown_to_dict(breakdown: AgrBreakdown) -> dict:
    return asdict(breakdown)
