"""Sales-comparable residual cross-check (professional pipeline).

Uses nearby completed sales + DRC extraction when floor area is known.
Does not replace the primary HPI residual until production-eligible ROS data
is loaded and signed off.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median
from typing import Any

from agr.config import load_config
from datasources.rebuild import blended_rebuild_per_m2, region_factor
from datasources.sales_schema import SalesTransaction
from datasources.sales_store import SalesStore


@dataclass
class SalesCompReport:
    available: bool
    production_ready: bool
    sample_count: int
    production_eligible_count: int
    synthetic_count: int
    median_price_gbp: float | None
    median_implied_site_share: float | None
    median_site_capital_per_sqm_gbp: float | None
    median_annual_rent_per_sqm_gbp: float | None
    yield_rate: float
    max_km: float
    method: str
    disclaimer: str
    comps: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _drc_for_sale(tx: SalesTransaction, config: dict) -> float | None:
    if tx.floor_area_sqm is None or tx.floor_area_sqm <= 0:
        return None
    rebuild_m2 = blended_rebuild_per_m2(config)
    code = tx.council_code or "default"
    # region_factor expects council code; default key used inside helper
    factor = region_factor(code, config)
    remaining = float(
        (config.get("valuer_roll") or {})
        .get("depreciation", {})
        .get("average_stock_remaining_factor", 0.55)
    )
    return tx.floor_area_sqm * rebuild_m2 * factor * remaining


def build_sales_comp_report(
    lat: float,
    lng: float,
    sales: SalesStore,
    *,
    config: dict | None = None,
    limit: int = 12,
    max_km: float = 2.5,
) -> SalesCompReport:
    config = config or load_config()
    yield_rate = float(
        (config.get("valuer_roll") or {}).get(
            "yield_rate",
            config.get("valuation", {}).get("yield_rate", 0.05),
        )
    )
    plot_sqm = float((config.get("valuer_roll") or {}).get("typical_plot_sqm", 280))

    nearest = sales.nearest(lat, lng, limit=limit, max_km=max_km)
    comps: list[dict[str, Any]] = []
    site_shares: list[float] = []
    site_per_sqm: list[float] = []
    prices: list[float] = []
    prod_n = 0
    syn_n = 0

    for dist, tx in nearest:
        if tx.provenance.is_synthetic():
            syn_n += 1
        if tx.provenance.is_production_eligible():
            prod_n += 1

        prices.append(float(tx.price_gbp))
        drc = _drc_for_sale(tx, config)
        implied_share = None
        site_cap = None
        site_psqm = None
        annual_psqm = None
        plot = tx.plot_area_sqm if tx.plot_area_sqm and tx.plot_area_sqm > 0 else plot_sqm

        if drc is not None and tx.price_gbp > 0:
            site_cap = max(0.0, tx.price_gbp - drc)
            implied_share = site_cap / tx.price_gbp
            site_psqm = site_cap / plot
            annual_psqm = site_psqm * yield_rate
            site_shares.append(implied_share)
            site_per_sqm.append(site_psqm)

        comps.append(
            {
                "distance_km": round(dist, 3),
                "price_gbp": tx.price_gbp,
                "transfer_date": tx.transfer_date,
                "postcode": tx.postcode,
                "property_type": tx.property_type,
                "floor_area_sqm": tx.floor_area_sqm,
                "drc_gbp": round(drc, 2) if drc is not None else None,
                "implied_site_capital_gbp": round(site_cap, 2) if site_cap is not None else None,
                "implied_site_share": round(implied_share, 4) if implied_share is not None else None,
                "site_capital_per_sqm_gbp": round(site_psqm, 2) if site_psqm is not None else None,
                "annual_rent_per_sqm_gbp": round(annual_psqm, 4) if annual_psqm is not None else None,
                "production_eligible": tx.provenance.is_production_eligible(),
                "provenance": tx.provenance.to_dict(),
            }
        )

    production_ready = prod_n >= 3 and syn_n == 0
    disclaimer = (
        "Sales-comparable residual is a cross-check only. "
        "Primary AGR remains the council HPI valuer residual unless production-eligible "
        "ROS/licensed sales are loaded and signed off. "
    )
    if syn_n:
        disclaimer += (
            f"{syn_n} nearby row(s) are synthetic fixtures — not real market evidence. "
        )
    if not nearest:
        disclaimer += "No sales within search radius."

    return SalesCompReport(
        available=len(nearest) > 0,
        production_ready=production_ready,
        sample_count=len(nearest),
        production_eligible_count=prod_n,
        synthetic_count=syn_n,
        median_price_gbp=float(median(prices)) if prices else None,
        median_implied_site_share=float(median(site_shares)) if site_shares else None,
        median_site_capital_per_sqm_gbp=float(median(site_per_sqm)) if site_per_sqm else None,
        median_annual_rent_per_sqm_gbp=(
            float(median(site_per_sqm)) * yield_rate if site_per_sqm else None
        ),
        yield_rate=yield_rate,
        max_km=max_km,
        method="sales_extraction_residual",
        disclaimer=disclaimer.strip(),
        comps=comps,
    )
