"""Place view — per-hectare ledger stack (zone grain).

Authoritative ROWS / CHECKS / SCEPTIC NEEDS:
``docs/georgist-ledger-accounting-rules.md`` (project store) and
``docs/FRONTEND_IA.md`` §4 Place view.

Public payload proves one rent per use via stack structure:
- Headline rows (market and proxy) visibly compose toward a total.
- Row 1a (planning uplift) already included in surface — never added.
- Shadow rows in a separate stack — never summed into the headline.
- Oil & gas + benchmarks outside both, labelled.
- Zone-level only; nothing published for blocked zones.
- Amounts are placeholders until ECONOMIC_RULES / calibration approve £.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from georgist.ledger import ledger_benchmarks
from georgist.publication_rules import ZONE_CODE_RE

CONSTRAINT_RULE = "Constraint: changes best use, adds no value"

# Placeholder until ECONOMIC_RULES approval — never a modelled AGR £ figure.
AMOUNT_PH = "—"

# Rows that belong in the market and proxy headline stack (and may sum).
# 1a is already included in 1 and is listed for indent drawing only (in_total=False).
# Row 6 is market_or_shadow: default shadow until lease prices exist.
HEADLINE_ROW_IDS = ("1", "2", "3", "4")
SHADOW_ROW_IDS = ("5", "6", "7", "8", "10")
OUTSIDE_ROW_IDS = ("9",)

_ROW_DEFS: dict[str, dict[str, Any]] = {
    "1": {
        "label": "Surface site rent",
        "tag": "market_or_proxy",
        "status": "not_yet",
        "status_note": (
            "Best permitted use. Public £ withheld until ECONOMIC_RULES / calibration."
        ),
        "parent_id": None,
        "nested": False,
        "in_total": True,
        "stack": "headline",
    },
    "1a": {
        "label": "Planning uplift",
        "tag": "already_included",
        "status": "not_yet",
        "status_note": (
            "Already included in Surface site rent — never added as a sibling total."
        ),
        "parent_id": "1",
        "nested": True,
        "in_total": False,
        "stack": "headline",
    },
    "2": {
        "label": "Mineral rent",
        "tag": "proxy",
        "status": "not_yet",
        "status_note": "Royalty/tonne, below ground. Stated difference only (C-hectare).",
        "parent_id": None,
        "nested": False,
        "in_total": True,
        "stack": "headline",
    },
    "3": {
        "label": "Onshore wind + hydro resource rent",
        "tag": "proxy",
        "status": "partial",
        "status_note": (
            "Site rent minus footprint surface rent. Inventory may paint; £ withheld."
        ),
        "parent_id": None,
        "nested": False,
        "in_total": True,
        "stack": "headline",
    },
    "4": {
        "label": "Seabed & foreshore",
        "tag": "market",
        "status": "not_yet",
        "status_note": "CES offshore wind, cables, moorings, foreshore.",
        "parent_id": None,
        "nested": False,
        "in_total": True,
        "stack": "headline",
    },
    "5": {
        "label": "Aquaculture licence rent",
        "tag": "shadow",
        "status": "not_yet",
        "status_note": "Estimate — total minus CES seabed paid. Separate stack.",
        "parent_id": None,
        "nested": False,
        "in_total": True,
        "stack": "shadow",
    },
    "6": {
        "label": "Fisheries quota",
        "tag": "shadow",
        "status": "not_yet",
        "status_note": "Market if lease prices, else shadow (default: shadow stack).",
        "parent_id": None,
        "nested": False,
        "in_total": True,
        "stack": "shadow",
    },
    "7": {
        "label": "Water scarcity",
        "tag": "shadow",
        "status": "not_yet",
        "status_note": (
            "Estimate, ~0 when published. Not shown as a money value while not yet."
        ),
        "parent_id": None,
        "nested": False,
        "in_total": True,
        "stack": "shadow",
    },
    "8": {
        "label": "Unpriced peat/soil carbon",
        "tag": "shadow",
        "status": "not_yet",
        "status_note": "Only unpriced carbon; timber/credits stay in row 1.",
        "parent_id": None,
        "nested": False,
        "in_total": True,
        "stack": "shadow",
    },
    "9": {
        "label": "Oil & gas",
        "tag": "reported",
        "status": "excluded",
        "status_note": "UK-reserved — outside Scottish total (headline and shadow).",
        "parent_id": None,
        "nested": False,
        "in_total": False,
        "stack": "outside",
        "outside_scottish_total": True,
    },
    "10": {
        "label": "Ecosystem services",
        "tag": "shadow",
        "status": "not_yet",
        "status_note": "Estimate, later.",
        "parent_id": None,
        "nested": False,
        "in_total": True,
        "stack": "shadow",
    },
}

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


def _row(row_id: str) -> dict[str, Any]:
    base = _ROW_DEFS[row_id]
    out: dict[str, Any] = {
        "id": row_id,
        "label": base["label"],
        "tag": base["tag"],
        "status": base["status"],
        "status_note": base["status_note"],
        "parent_id": base["parent_id"],
        "nested": base["nested"],
        "in_total": base["in_total"],
        "stack": base["stack"],
        "amount_placeholder": AMOUNT_PH,
        # Explicit null — never a modelled public AGR £ before ECONOMIC_RULES.
        "amount_gbp_per_ha": None,
    }
    if base.get("outside_scottish_total"):
        out["outside_scottish_total"] = True
    return out


def headline_sum_row_ids(rows: list[Mapping[str, Any]]) -> list[str]:
    """Ids that compose the headline total (excludes 1a already included in surface)."""
    return [str(r["id"]) for r in rows if r.get("in_total") and not r.get("nested")]


def shadow_sum_row_ids(rows: list[Mapping[str, Any]]) -> list[str]:
    """Ids that compose the shadow total (never mixed into headline)."""
    return [str(r["id"]) for r in rows if r.get("in_total")]


def _blocked_payload(zone_code: str, *, zone_name: str | None = None) -> dict[str, Any]:
    return {
        "contract": "place_hectare_stack_v1",
        "published": False,
        "reason": "blocked",
        "grain": "zone-level only; never plots; nothing published for blocked zones",
        "zone": {
            "code": zone_code,
            "name": zone_name,
            "publication_status": "blocked",
        },
        "note": (
            "Nothing published for blocked zones "
            "(publication_status=blocked — ceiling breach / hold rules)."
        ),
        "headline": None,
        "shadow": None,
        "outside": None,
        "constraints": None,
        "publication_note": (
            "Blocked zone — no per-hectare stack and no modelled AGR £."
        ),
    }


def place_hectare_stack(
    zone_code: str,
    *,
    zone_name: str | None = None,
    publication_status: str = "ok",
) -> dict[str, Any]:
    """Assemble the public per-hectare stack for one Data Zone.

    ``publication_status="blocked"`` returns an unpublished shell with no rows.
    Amounts are always placeholders until ECONOMIC_RULES approve public £.
    """
    code = (zone_code or "").strip().upper()
    if not ZONE_CODE_RE.match(code):
        raise ValueError(f"zone code {zone_code!r} is not a Data Zone code")

    status = (publication_status or "ok").strip().lower()
    if status == "blocked":
        return _blocked_payload(code, zone_name=zone_name)

    # Headline visual order: surface, nested 1a under it, then 2–4.
    headline_rows = [_row("1"), _row("1a"), _row("2"), _row("3"), _row("4")]
    shadow_rows = [_row(i) for i in SHADOW_ROW_IDS]
    outside_rows = [_row(i) for i in OUTSIDE_ROW_IDS]

    return {
        "contract": "place_hectare_stack_v1",
        "published": True,
        "grain": "zone-level only; never plots; nothing published for blocked zones",
        "zone": {
            "code": code,
            "name": zone_name,
            "publication_status": status if status else "ok",
        },
        "publication_note": (
            "Per-hectare stack (Annual Ground Rent breakdown). "
            "Public AGR £ withheld until ECONOMIC_RULES / calibration. "
            "Placeholders are not a money value. Row 1a is already included "
            "in Surface site rent (indented, never added). "
            "Estimate total is separate and never summed into the headline. "
            "Oil & gas and benchmarks sit outside both."
        ),
        "headline": {
            "label": "Headline (market and proxy totals)",
            "unit": "£/ha/year",
            "rows": headline_rows,
            "sum_row_ids": headline_sum_row_ids(headline_rows),
            "total_placeholder": AMOUNT_PH,
            "total_note": (
                "Visually stacked rows that add to this total: "
                + ", ".join(headline_sum_row_ids(headline_rows))
                + ". Row 1a already included in Surface site rent — excluded from the sum."
            ),
        },
        "shadow": {
            "label": "Estimate (separate — never summed into headline)",
            "unit": "£/ha/year",
            "rows": shadow_rows,
            "sum_row_ids": shadow_sum_row_ids(shadow_rows),
            "total_placeholder": AMOUNT_PH,
            "total_note": (
                "Estimate stack total is separate from the headline "
                "(C-totals). Never added into market or proxy totals."
            ),
        },
        "outside": {
            "label": "Outside Scottish total",
            "rows": outside_rows,
            "benchmarks": ledger_benchmarks(),
            "benchmark_label": "benchmark only, not inputs",
            "note": (
                "Oil & gas (row 9) is reported UK-reserved and sits "
                "outside the Scottish totals. Benchmarks are shown "
                "alongside the breakdown and are never inputs."
            ),
        },
        "constraints": list(_CONSTRAINTS),
        "checks_url": "/data",
    }


def is_zone_code(value: str) -> bool:
    return bool(ZONE_CODE_RE.match((value or "").strip().upper()))


def lookup_zone_publication_status(zone_code: str) -> str:
    """Return ``ok`` or ``blocked`` from ``surface_rent_dz`` when the DB is up.

    Falls back to ``ok`` when the table/row is missing or the DB is unavailable
    so the public place page can still show the placeholder stack skeleton.
    Never invents rent £.
    """
    code = (zone_code or "").strip().upper()
    if not ZONE_CODE_RE.match(code):
        return "ok"
    try:
        from georgist.db import cursor

        with cursor(dict_rows=True) as cur:
            cur.execute(
                """
                SELECT publication_status
                FROM surface_rent_dz
                WHERE code = %s
                ORDER BY vintage DESC
                LIMIT 1
                """,
                (code,),
            )
            row = cur.fetchone()
        if not row:
            return "ok"
        status = row.get("publication_status") or "ok"
        return "blocked" if str(status).lower() == "blocked" else "ok"
    except Exception:
        return "ok"


# Re-export for tests / callers that only need the pattern.
ZONE_CODE_PATTERN = re.compile(ZONE_CODE_RE.pattern)
