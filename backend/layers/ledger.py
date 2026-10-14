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
            "Planning uplift: an 'of which' figure inside the land part, never added again"
        ),
        "amount_placeholder": "—",
    },
    {
        "id": "2",
        "label": "Mineral rent",
        "parent_id": None,
        "nested": False,
        "tag": "proxy",
        "status": "not_yet",
        "status_note": "Royalty/tonne, below ground. Not yet on the public breakdown.",
        "amount_placeholder": "—",
    },
    {
        "id": "3",
        "label": "Onshore wind + hydro resource rent",
        "parent_id": None,
        "nested": False,
        "tag": "proxy",
        "status": "partial",
        "status_note": (
            "Site rent minus footprint surface rent. Inventory layers may paint; "
            "figures not published yet."
        ),
        "amount_placeholder": "—",
    },
    {
        "id": "4",
        "label": "Seabed & foreshore",
        "parent_id": None,
        "nested": False,
        "tag": "market",
        "status": "not_yet",
        "status_note": "CES offshore wind, cables, moorings, foreshore.",
        "amount_placeholder": "—",
    },
    {
        "id": "5",
        "label": "Aquaculture licence rent",
        "parent_id": None,
        "nested": False,
        "tag": "shadow",
        "status": "not_yet",
        "status_note": "Estimate — total minus CES seabed paid. Drawn in estimate stack later.",
        "amount_placeholder": "—",
    },
    {
        "id": "6",
        "label": "Fisheries quota",
        "parent_id": None,
        "nested": False,
        "tag": "market_or_proxy",
        "status": "not_yet",
        "status_note": "Market if lease prices, else estimate.",
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
        "label": "Unpriced peat/soil carbon",
        "parent_id": None,
        "nested": False,
        "tag": "shadow",
        "status": "not_yet",
        "status_note": "Only unpriced carbon; timber/credits stay in row 1.",
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
        "label": "Ecosystem services",
        "parent_id": None,
        "nested": False,
        "tag": "shadow",
        "status": "not_yet",
        "status_note": "Estimate, later.",
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
