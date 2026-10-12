from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from agr.config import CONFIG_PATH, load_config
from agr.fiscal import basket_total_gbp
from layers.ownership_value import scenario_ownership_relief_gbp

POLICY_PATH = CONFIG_PATH.parent / "policy.yaml"

VALID_SCENARIOS = (
    "full_agr",
    "replace_income_tax",
    "revenue_neutral",
    "replace_full_basket",
)


@dataclass(frozen=True)
class ScenarioCharge:
    id: str
    label: str
    annual_charge_gbp: float
    description: str
    effective_rate: float | None = None


def _economic_annual_rent(
    site_rental_per_sqm: float,
    area_sqm: float,
    capture_rate: float,
) -> float:
    return site_rental_per_sqm * area_sqm * capture_rate


def compute_scenarios(
    *,
    site_rental_per_sqm: float,
    despeculated_site_capital_per_sqm: float,
    area_sqm: float,
    capture_rate: float,
    config: dict | None = None,
) -> tuple[float, dict[str, ScenarioCharge]]:
    """Return full economic rent and per-scenario annual charges for one square."""
    config = config or load_config()
    scenarios_cfg = config["scenarios"]
    macro = config["macro"]

    economic_rent = _economic_annual_rent(site_rental_per_sqm, area_sqm, capture_rate)
    despeculated_site_value = despeculated_site_capital_per_sqm * area_sqm

    full_cfg = scenarios_cfg["full_agr"]
    full_charge = economic_rent * full_cfg["capture_rate"]

    income_tax_target = macro["scotland_income_tax_replacement_gbp"]
    estimated_total_rent = macro["estimated_scotland_annual_rent_gbp"]
    income_tax_rate = income_tax_target / estimated_total_rent
    income_tax_charge = economic_rent * income_tax_rate

    revenue_cfg = scenarios_cfg["revenue_neutral"]
    revenue_rate = revenue_cfg["rate_per_pound"]
    revenue_charge = despeculated_site_value * revenue_rate

    basket = basket_total_gbp(config)
    full_basket_rate = basket / estimated_total_rent if estimated_total_rent else 0.0
    full_basket_charge = economic_rent * full_basket_rate
    full_basket_cfg = scenarios_cfg.get("replace_full_basket") or {}
    full_basket_label = full_basket_cfg.get(
        "label", "Replace all listed taxes (neutral)"
    )

    charges = {
        "full_agr": ScenarioCharge(
            id="full_agr",
            label=full_cfg["label"],
            annual_charge_gbp=round(full_charge, 2),
            description=(
                "Full annual economic ground rent for this place (valuer residual). "
                "National full collection exceeds today’s tax basket — surplus for services "
                "or citizen dividend. High-rent locations contribute most."
            ),
            effective_rate=full_cfg["capture_rate"],
        ),
        "replace_income_tax": ScenarioCharge(
            id="replace_income_tax",
            label=scenarios_cfg["replace_income_tax"]["label"],
            annual_charge_gbp=round(income_tax_charge, 2),
            description=(
                f"Scales map economic rent so Scotland raises "
                f"£{income_tax_target / 1e9:.1f}bn if the national pool is "
                f"£{estimated_total_rent / 1e9:.0f}bn (Sandilands). "
                "Uses the national pool ratio, not a sum of map cells."
            ),
            effective_rate=round(income_tax_rate, 4),
        ),
        "revenue_neutral": ScenarioCharge(
            id="revenue_neutral",
            label=revenue_cfg["label"],
            annual_charge_gbp=round(revenue_charge, 2),
            description=(
                f"Charge {revenue_rate * 100:.2f}% of this place’s economic site capital "
                "(Wightman-style CT + NDR replacement on residual capital)."
            ),
            effective_rate=revenue_rate,
        ),
        "replace_full_basket": ScenarioCharge(
            id="replace_full_basket",
            label=full_basket_label,
            annual_charge_gbp=round(full_basket_charge, 2),
            description=(
                f"Scales map economic rent so national collection matches the fiscal basket "
                f"(£{basket / 1e9:.1f}bn: income tax + Council Tax + NDR). "
                "Revenue-neutral on listed taxes; high-rent places still pay most."
            ),
            effective_rate=round(full_basket_rate, 4),
        ),
    }
    return round(economic_rent, 2), charges


def scenario_to_dict(charge: ScenarioCharge) -> dict:
    return {
        "id": charge.id,
        "label": charge.label,
        "annual_charge_gbp": charge.annual_charge_gbp,
        "description": charge.description,
        "effective_rate": charge.effective_rate,
    }


@lru_cache(maxsize=1)
def load_policy() -> dict:
    """Charge settings. Cached; callers must not mutate the returned dict."""
    if not POLICY_PATH.exists():
        raise ValueError(f"Missing {POLICY_PATH.name}")
    with POLICY_PATH.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict) or not isinstance(document.get("scenarios"), dict):
        raise ValueError("policy.yaml is missing scenarios")
    return document


def policy_spec(scenario_id: str) -> dict | None:
    spec = (load_policy().get("scenarios") or {}).get(scenario_id)
    if isinstance(spec, dict):
        return spec
    return None


def is_placeholder(scenario_id: str) -> bool:
    spec = policy_spec(scenario_id)
    if spec is None:
        return False
    if spec.get("status") == "placeholder":
        return True
    return spec.get("tau") is None and spec.get("reliefs") is None and spec.get("phasing") is None


def _relief_total(reliefs: list) -> float:
    if not isinstance(reliefs, list):
        raise ValueError("scenario not set")
    total = 0.0
    for item in reliefs:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("scenario not set")
        total += float(item)
    return total


def _phasing_share(phasing: list) -> float:
    """Share in force for the published charge. That is the year-1 share."""
    if not isinstance(phasing, list) or not phasing:
        raise ValueError("scenario not set")
    earliest = None
    for phase in phasing:
        if not isinstance(phase, dict):
            raise ValueError("scenario not set")
        year = phase.get("year")
        share = phase.get("share")
        if year is None or share is None:
            raise ValueError("scenario not set")
        if int(year) == 1:
            return float(share)
        if earliest is None or int(year) < earliest[0]:
            earliest = (int(year), float(share))
    if earliest is None:
        raise ValueError("scenario not set")
    return earliest[1]


def charge_after_policy(
    rent_gbp: float,
    spec: dict,
    *,
    owners: list | None = None,
) -> float:
    """charge = tau x phasing share x (rent - reliefs), after valuation.

    Ownership (public / Common Good / LA) never rewrites the valuation rent.
    Named ``ownership_reliefs`` on the scenario spec are the only place an
    ownership tax exemption may reduce the **charge**.
    """
    if spec.get("status") == "placeholder":
        raise ValueError("scenario not set")
    tau = spec.get("tau")
    reliefs = spec.get("reliefs")
    phasing = spec.get("phasing")
    if tau is None or reliefs is None or phasing is None:
        raise ValueError("scenario not set")
    tau_value = float(tau)
    relief_total = _relief_total(reliefs)
    ownership_relief = scenario_ownership_relief_gbp(
        rent_gbp,
        owners,
        spec.get("ownership_reliefs"),
    )
    relief_total = float(relief_total) + float(ownership_relief)
    share = _phasing_share(phasing)
    # tau 1, no relief and a full first-year share is today's charge, to the penny.
    if tau_value == 1.0 and share == 1.0 and relief_total == 0.0:
        return float(rent_gbp)
    return round(tau_value * share * (float(rent_gbp) - relief_total), 2)


def resolve_active_scenario(scenario: str | None) -> str:
    if scenario is None:
        return "full_agr"
    if is_placeholder(scenario):
        raise ValueError("scenario not set")
    if scenario not in VALID_SCENARIOS:
        raise ValueError(
            f"Unknown scenario '{scenario}'. Choose: {', '.join(VALID_SCENARIOS)}"
        )
    return scenario
