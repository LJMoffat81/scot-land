"""Pre-review checklist — public runtime JSON / grain guards.

Built-HTML greps miss browser-loaded JSON from /api/place-stack.json and
/api/ledger.json — walk those payloads' visitor-facing string values here.

Pins AGENTS.md Pre-review checklist items that belong in backend CI:
banned visitor words (ledger, natural capital, headline/shadow), £ figures,
nothing finer than Data Zone for modelled/proxy values, and the place_stack
``outside the Scottish totals`` wording.

Rent/value group names are enforced against ``RENT_GROUP_NAMES`` in
``frontend/scripts/test-prereview-rent-groups.mjs`` (not by scanning source text).
"""

from __future__ import annotations

import re
from typing import Any

from georgist import publication_rules as pr
from georgist.ledger import ledger_catalog
from georgist.place_stack import place_hectare_stack

_LEDGER_WORD = re.compile(r"\bledger\b", re.IGNORECASE)
_NATURAL_CAPITAL = re.compile(r"natural\s+capital", re.IGNORECASE)
_HEADLINE_SHADOW = re.compile(r"headline\s*/\s*shadow", re.IGNORECASE)
# £ figure = currency symbol with a numeric amount (not unit labels / "£ withheld").
_POUND_FIGURE = re.compile(r"£\s*[\d,]+(?:\.\d+)?|[\d,]+\s*£")

# Machine / non-prose keys — not shown as visitor copy in the UI.
_SKIP_KEYS = frozenset(
    {
        "kind",
        "spec",
        "id",
        "contract",
        "document",
        "run_hash",
        "definition",
        "licence_url",
        "source_url",
        "checks_url",
        "sum_row_ids",
        "parent_id",
        "nested_under",
        "stack",
        "tag",
        "status",
        "version",
    }
)


def _visitor_strings(obj: Any, *, key: str | None = None) -> list[str]:
    if key is not None and key in _SKIP_KEYS:
        return []
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        out: list[str] = []
        for child_key, value in obj.items():
            out.extend(_visitor_strings(value, key=str(child_key)))
        return out
    if isinstance(obj, list):
        out = []
        for item in obj:
            out.extend(_visitor_strings(item, key=key))
        return out
    return []


def _assert_public_visitor_copy(payload: dict[str, Any], label: str) -> None:
    texts = _visitor_strings(payload)
    ledger_hits = [t for t in texts if _LEDGER_WORD.search(t)]
    assert not ledger_hits, f"{label} visitor text contains 'ledger':\n" + "\n".join(
        repr(h[:200]) for h in ledger_hits
    )
    capital_hits = [t for t in texts if _NATURAL_CAPITAL.search(t)]
    assert not capital_hits, (
        f"{label} visitor text contains 'natural capital':\n"
        + "\n".join(repr(h[:200]) for h in capital_hits)
    )
    slash_hits = [t for t in texts if _HEADLINE_SHADOW.search(t)]
    assert not slash_hits, (
        f"{label} visitor text contains 'headline/shadow':\n"
        + "\n".join(repr(h[:200]) for h in slash_hits)
    )
    pound_hits = [t for t in texts if _POUND_FIGURE.search(t)]
    assert not pound_hits, (
        f"{label} visitor text contains a £ figure:\n"
        + "\n".join(repr(h[:200]) for h in pound_hits)
    )


def test_place_stack_runtime_copy_has_no_ledger_word():
    body = place_hectare_stack("S01010264", zone_name="City Centre South")
    _assert_public_visitor_copy(body, "place-stack")
    note = body["outside"]["note"]
    assert "outside the Scottish totals" in note
    assert (
        "Benchmarks are shown alongside the breakdown and are never inputs."
        in note
    )


def test_ledger_json_runtime_copy_has_no_ledger_word():
    payload = ledger_catalog()
    _assert_public_visitor_copy(payload, "ledger.json")
    oil = next(r for r in payload["rows"] if r["id"] == "9")
    assert oil["note"] == (
        "Reported alongside the breakdown; outside the Scottish totals."
    )


def test_prereview_nothing_finer_than_data_zone_for_modelled_values():
    """Published modelled/proxy values stay at Data Zone grain (or coarser)."""
    assert pr.PRIVATE_GRAIN == frozenset({"parcel", "plot", "uprn", "building"})
    for path, rule in pr.PUBLIC_ROUTE_RULES.items():
        if rule.geometry_level in pr.PRIVATE_GRAIN:
            assert not rule.carries_values, (
                f"{path}: private grain must not carry public values"
            )
        if rule.carries_values and rule.geometry_level != "zone":
            assert rule.value_basis == "measured", path
            assert rule.sources <= pr.SITE_PUBLIC_SOURCES, path

    # Place stack accepts Data Zone codes only.
    try:
        place_hectare_stack("EH1 1YZ")
        assert False, "expected ValueError for non-zone grain"
    except ValueError as exc:
        assert "Data Zone" in str(exc)
