"""Pre-review checklist — public runtime JSON / grain / group-name guards.

Built-HTML greps miss browser-loaded JSON from /api/place-stack.json and
/api/ledger.json — walk those payloads' visitor-facing string values here.

Also pins AGENTS.md Pre-review checklist items that belong in backend CI:
banned visitor words (ledger, natural capital), £ figures, rent group names,
nothing finer than Data Zone for modelled/proxy values, and the place_stack
``outside the Scottish totals`` wording.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from georgist import publication_rules as pr
from georgist.ledger import ledger_catalog
from georgist.place_stack import place_hectare_stack

_REPO = Path(__file__).resolve().parents[2]
_PLACE_CARD = _REPO / "frontend" / "lib" / "placeCard.ts"
_MAP_GROUPS = _REPO / "frontend" / "lib" / "mapLayerGroups.ts"
_DATA_GROUPS = _REPO / "frontend" / "lib" / "dataSourceGroups.ts"

_LEDGER_WORD = re.compile(r"\bledger\b", re.IGNORECASE)
_NATURAL_CAPITAL = re.compile(r"natural\s+capital", re.IGNORECASE)
# £ figure = currency symbol with a numeric amount (not unit labels / "£ withheld").
_POUND_FIGURE = re.compile(r"£\s*[\d,]+(?:\.\d+)?|[\d,]+\s*£")

_ALLOWED_RENT_GROUPS = frozenset(
    {
        "Land",
        "Natural resource rents",
        "Services of nature",
    }
)

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


def test_prereview_rent_group_names_only_allowed_three():
    """Value/rent group headings must be Land / Natural resource rents / Services of nature."""
    place_card = _PLACE_CARD.read_text(encoding="utf-8")
    start = place_card.index("function defaultAgrRows")
    end = place_card.find("\nexport function", start)
    assert end > start, "defaultAgrRows block not found"
    # Top-level row labels only (skip nested of_which labels).
    block = place_card[start:end]
    labels = re.findall(
        r'^\s+label:\s*"([^"]+)"',
        block,
        flags=re.MULTILINE,
    )
    # Nested "of which: …" sits deeper; keep only the three group headings.
    group_labels = [lab for lab in labels if not lab.startswith("of which")]
    assert group_labels, "defaultAgrRows labels not found"
    unexpected = [lab for lab in group_labels if lab not in _ALLOWED_RENT_GROUPS]
    assert not unexpected, (
        "rent/value group names must be only "
        f"{sorted(_ALLOWED_RENT_GROUPS)}; got unexpected {unexpected}"
    )
    assert set(group_labels) == _ALLOWED_RENT_GROUPS

    map_src = _MAP_GROUPS.read_text(encoding="utf-8")
    for needle in (
        'return "Land"',
        'return "Natural resource rents"',
        'return "Services of nature"',
    ):
        assert needle in map_src, f"mapLayerGroupLabel missing {needle}"

    data_src = _DATA_GROUPS.read_text(encoding="utf-8")
    for needle in (
        'return "Land"',
        'return "Natural resource rents"',
        'return "Services of nature"',
    ):
        assert needle in data_src, f"dataSourceGroupLabel missing {needle}"


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
