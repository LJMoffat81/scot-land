"""Professional valuation service facade.

Single entry for API and batch jobs. Keeps residual engine as default method;
sales store powers comparable residual cross-checks when data is loaded.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from agr.areas import CouncilArea, _councils_by_code
from agr.config import load_config
from agr.engine import AgrBreakdown, calculate_square_agr
from agr.overrides import merge_config_overrides
from agr.scenarios import charge_after_policy, policy_spec
from agr.sales_comps import build_sales_comp_report
from datasources.sales_store import SalesStore
from spatial.grid import GridSquare, snap_to_w3w_grid


def _apply_policy_after_valuation(breakdown: AgrBreakdown) -> AgrBreakdown:
    """Policy sits on top of the valuation rent. It does not rewrite the valuation."""
    spec = policy_spec(breakdown.active_scenario)
    if spec is None:
        return breakdown
    charge = charge_after_policy(breakdown.economic_annual_rent_gbp, spec)
    if charge == breakdown.annual_ground_rent_gbp:
        return breakdown
    breakdown.annual_ground_rent_gbp = charge
    current = breakdown.scenarios.get(breakdown.active_scenario)
    if isinstance(current, dict):
        current["annual_charge_gbp"] = charge
    return breakdown


class ValuationService:
    """Orchestrates place → assessment → optional sales context."""

    def __init__(
        self,
        *,
        config: dict | None = None,
        sales: SalesStore | None = None,
    ):
        self.config = config if config is not None else load_config()
        self.sales = sales

    @classmethod
    def default(cls) -> ValuationService:
        sales = None
        try:
            # Prefer licensed extract when present
            licensed = SalesStore.try_load_licensed("sales.jsonl")
            if licensed is not None and len(licensed) > 0:
                sales = licensed
            else:
                sales = SalesStore.load_default_fixture()
        except FileNotFoundError:
            sales = SalesStore()
        return cls(sales=sales)

    def with_sensitivity(
        self,
        *,
        yield_rate: float | None = None,
        urban_speculation_discount: float | None = None,
        farmland_market_to_productive: float | None = None,
    ) -> ValuationService:
        cfg = merge_config_overrides(
            self.config,
            yield_rate=yield_rate,
            urban_speculation_discount=urban_speculation_discount,
            farmland_market_to_productive=farmland_market_to_productive,
        )
        return ValuationService(config=cfg, sales=self.sales)

    def assess_point(
        self,
        lat: float,
        lng: float,
        *,
        scenario: str | None = "full_agr",
    ) -> AgrBreakdown:
        square = snap_to_w3w_grid(lat, lng)
        return self.assess_square(square, scenario=scenario)

    def assess_square(
        self,
        square: GridSquare,
        *,
        scenario: str | None = "full_agr",
    ) -> AgrBreakdown:
        breakdown = calculate_square_agr(square, scenario=scenario, config=self.config)
        return _apply_policy_after_valuation(breakdown)

    def assess_council_layer(
        self,
        code: str,
        lat: float,
        lng: float,
        scenario: str | None = "full_agr",
    ) -> AgrBreakdown:
        """Council choropleth: urban home plot, never the centroid's rural rule."""
        raw = _councils_by_code()[code]
        council = CouncilArea(
            code=raw["code"],
            name=raw["name"],
            average_price_gbp=int(raw["average_price_gbp"]),
            annual_change_pct=raw.get("annual_change_pct"),
            rural=False,
            distance_km=0.0,
            lookup_method="council_layer",
        )
        square = snap_to_w3w_grid(lat, lng)
        breakdown = calculate_square_agr(
            square,
            scenario=scenario,
            config=self.config,
            council=council,
            use_zone_price=False,
        )
        return _apply_policy_after_valuation(breakdown)

    def sales_context(self, lat: float, lng: float, *, limit: int = 10) -> dict[str, Any]:
        """Nearby sales + extraction residual cross-check."""
        if self.sales is None or len(self.sales) == 0:
            return {
                "available": False,
                "reason": "No sales store loaded. Ingest ROS/licensed data or fixtures.",
                "count": 0,
                "nearest": [],
                "comp_report": None,
            }

        report = build_sales_comp_report(
            lat, lng, self.sales, config=self.config, limit=limit
        )
        return {
            "available": report.available,
            "count": report.sample_count,
            "store_summary": self.sales.summary(),
            "comp_report": report.to_dict(),
            "nearest": report.comps,
            "disclaimer": report.disclaimer,
        }

    def assess_with_context(
        self,
        lat: float,
        lng: float,
        *,
        scenario: str | None = "full_agr",
        include_sales: bool = True,
    ) -> dict[str, Any]:
        breakdown = self.assess_point(lat, lng, scenario=scenario)
        payload: dict[str, Any] = {
            "method_family": "valuer_residual_roll",
            "agr": asdict(breakdown),
        }
        if include_sales:
            payload["sales_context"] = self.sales_context(lat, lng)
        return payload
