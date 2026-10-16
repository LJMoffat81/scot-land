"""Annual Ground Rent breakdown payload for GET /ledger.

Authoritative ROWS / Constraints: project store georgist-ledger-accounting-rules
and docs/FRONTEND_IA.md. Public amounts are placeholders — no AGR £ until
ECONOMIC_RULES / calibration approve publication.
"""

from __future__ import annotations

from typing import Any

CONSTRAINT_RULE = "Constraint: changes best use, adds no value"

_ROWS: list[dict[str, Any]] = [
    {
        "id": "1",
        "label": "Land",
        "parent_id": None,
        "nested": False,
        "tag": "market_or_proxy",
        "status": "not_yet",
        "status_note": (
            "Best permitted use. Figures are being checked and aren't published yet."
        ),
        "amount_placeholder": "—",
    },
    {
        "id": "1a",
        "label": "Planning uplift",
        "parent_id": "1",
        "nested": True,
        "tag": "already_included",
        "status": "not_yet",
        "status_note": (
            "Value from planning permission. Part of the land figure, not added again."
        ),
        "amount_placeholder": "—",
    },
    {
        "id": "2",
        "label": "Minerals and quarries",
        "parent_id": None,
        "nested": False,
        "tag": "proxy",
        "status": "not_yet",
        "status_note": "The royalty paid for each tonne taken from the ground.",
        "amount_placeholder": "—",
    },
    {
        "id": "3",
        "label": "Wind and hydro sites on land",
        "parent_id": None,
        "nested": False,
        "tag": "proxy",
        "status": "partial",
        "status_note": (
            "The extra rent a wind or hydro site earns over ordinary land rent."
        ),
        "amount_placeholder": "—",
    },
    {
        "id": "4",
        "label": "Seabed and shore",
        "parent_id": None,
        "nested": False,
        "tag": "market",
        "status": "not_yet",
        "status_note": (
            "Rent Crown Estate Scotland charges for offshore wind, cables, "
            "moorings and the shore."
        ),
        "amount_placeholder": "—",
    },
    {
        "id": "5",
        "label": "Fish farm sites",
        "parent_id": None,
        "nested": False,
        "tag": "proxy",
        "status": "not_yet",
        "status_note": "Total minus the seabed lease paid to Crown Estate Scotland.",
        "amount_placeholder": "—",
    },
    {
        "id": "6",
        "label": "Fishing quota",
        "parent_id": None,
        "nested": False,
        "tag": "proxy",
        "status": "not_yet",
        "status_note": "Market if lease prices, else modelled.",
        "amount_placeholder": "—",
    },
    {
        "id": "7",
        "label": "Water scarcity",
        "parent_id": None,
        "nested": False,
        "tag": "shadow",
        "status": "not_yet",
        "status_note": (
            "Estimate, ~0 when published. Not shown as a money value while not yet."
        ),
        "amount_placeholder": "—",
    },
    {
        "id": "8",
        "label": "Carbon held in peat and soil",
        "parent_id": None,
        "nested": False,
        "tag": "shadow",
        "status": "not_yet",
        "status_note": (
            "Carbon with no market price. Timber and carbon credits are counted with the land."
        ),
        "amount_placeholder": "—",
    },
    {
        "id": "9",
        "label": "Oil & gas",
        "parent_id": None,
        "nested": False,
        "tag": "reported",
        "status": "excluded",
        "status_note": "UK-reserved — outside the Scottish totals.",
        "amount_placeholder": "—",
        "outside_scottish_total": True,
    },
    {
        "id": "10",
        "label": "Other services of nature, such as flood control",
        "parent_id": None,
        "nested": False,
        "tag": "shadow",
        "status": "not_yet",
        "status_note": "Estimate. Not worked out yet.",
        "amount_placeholder": "—",
    },
]

_CONSTRAINTS: list[dict[str, str]] = [
    {"id": "designations", "label": "Designations", "rule": CONSTRAINT_RULE},
    {"id": "flood", "label": "Flood", "rule": CONSTRAINT_RULE},
    {
        "id": "crofting",
        "label": "Crofting / common grazings",
        "rule": CONSTRAINT_RULE,
    },
    {
        "id": "lca",
        "label": "Land Capability for Agriculture (LCA)",
        "rule": CONSTRAINT_RULE,
    },
]


def ledger_payload() -> dict[str, Any]:
    """Public ledger skeleton — rows + constraints; no published rent £."""
    return {
        "version": 1,
        "brief": (
            "Annual Ground Rent breakdown: where the value comes from — "
            "ROWS 1–10 + 1a already included in surface; "
            "Constraint: changes best use, adds no value"
        ),
        "publication_note": (
            "Zone-level only. Figures are being checked and aren't published yet."
        ),
        "rows": list(_ROWS),
        "constraints": list(_CONSTRAINTS),
    }
