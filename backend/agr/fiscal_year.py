"""Compare a GERS year with the Group's rent rule.

GERS is what government raises and spends. The potential rent is half of
that year's national income, the Scottish Land Revenue Group's rule.
ATCOR says today's taxes have already come out of rent. Ricardo's law
says only the surplus over the margin is rent. Neither figure replaces
the parcel rent.
"""

from __future__ import annotations

from pathlib import Path

import yaml

FISCAL_DIR = Path(__file__).resolve().parents[2] / "data" / "fiscal"

ATCOR = (
    "All Taxes Come Out of Rent. A tax on wages, trade, or buildings "
    "reduces what people can pay for land, so today's revenue is the "
    "picture with the rent squeezed, not the rent a land charge would collect."
)

EBCOR = (
    "Excess Burden Comes Out of Rent. The waste of those taxes can also "
    "return to rent. That is a judgement, and this comparison adds no extra billion for it."
)

RICARDO = (
    "Ricardo's law of rent: the rent of a piece of land is the surplus over "
    "the least productive land in use. Land at that margin pays nothing. "
    "The national figure is that surplus, not a flat charge on every square metre."
)


def load_gers(year_id: str = "gers-2025-26") -> dict:
    path = FISCAL_DIR / f"{year_id}.yml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def compare_gers(snapshot: dict, config: dict) -> dict:
    """Refresh the Group's half-of-income rule. Do not change the signed pool."""
    revenue = int(snapshot["revenue_gbp"])
    balance = int(snapshot["net_fiscal_balance_gbp"])
    spending = revenue - balance
    share_of_gdp = float(snapshot["revenue_share_of_gdp"])
    gdp = revenue / share_of_gdp
    rule = float(config["macro"]["rent_share_of_gdp"])
    signed_pool = int(config["macro"]["estimated_scotland_annual_rent_gbp"])
    refreshed = gdp * rule
    return {
        "gers_id": snapshot["id"],
        "published": snapshot["published"],
        "url": snapshot["url"],
        "revenue_gbp": revenue,
        "spending_gbp": spending,
        "net_fiscal_balance_gbp": balance,
        "gdp_gbp": gdp,
        "rent_share_of_gdp": rule,
        "signed_pool_gbp": signed_pool,
        "refreshed_rent_gbp": refreshed,
        "above_taxes_gbp": refreshed - revenue,
        "above_spending_gbp": refreshed - spending,
        "taxes": snapshot.get("taxes") or {},
        "atcor": ATCOR,
        "ebcor": EBCOR,
        "ricardo": RICARDO,
    }
