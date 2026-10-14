"""Pre-review checklist — public runtime JSON / grain guards.

Built-HTML greps miss browser-loaded JSON from /api/*.json — walk those
payloads' visitor-facing string values here.

Pins AGENTS.md Pre-review checklist items that belong in backend CI:
banned visitor words (ledger, natural capital, headline, shadow), £ figures,
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
from layers.ledger import ledger_payload
from layers.platform import platform_catalog

_LEDGER_WORD = re.compile(r"\bledger\b", re.IGNORECASE)
_NATURAL_CAPITAL = re.compile(r"natural\s+capital", re.IGNORECASE)
# Keep the slash form; also ban each word alone in visitor prose (SW-015).
_HEADLINE_SHADOW_SLASH = re.compile(r"headline\s*/\s*shadow", re.IGNORECASE)
_HEADLINE_WORD = re.compile(r"\bheadline\b", re.IGNORECASE)
_SHADOW_WORD = re.compile(r"\bshadow\b", re.IGNORECASE)
# £ figure = currency symbol with a numeric amount (not unit labels / "£ withheld").
_POUND_FIGURE = re.compile(r"£\s*[\d,]+(?:\.\d+)?|[\d,]+\s*£")

# Machine / non-prose keys — not shown as visitor copy in the UI.
# tag / value_tier / stack stay machine values (market|proxy|shadow etc.).
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
        "value_tier",
        "group",
        "ledger_role",
        "ledger_row",
        "ui_surface",
    }
)

# Public API JSON builders exercised without BACKEND_URL / PostGIS.
_PUBLIC_API_JSON_BUILDERS: list[tuple[str, Any]] = [
    ("/api/ledger.json", lambda: ledger_catalog()),
    ("/api/place-stack.json", lambda: place_hectare_stack("S01010264", zone_name="City Centre South")),
    ("/api/catalog.json", platform_catalog),
    ("/ledger", ledger_payload),  # legacy public shape; same visitor rules
]

_ALLOWED_TAGS = frozenset({"market", "proxy", "shadow", "reported", "market_or_proxy", "already_included"})


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


def _collect_tags(obj: Any, *, key: str | None = None) -> list[str]:
    """Collect machine tag / value_tier string values (any depth)."""
    found: list[str] = []
    if isinstance(obj, dict):
        for child_key, value in obj.items():
            if child_key in ("tag", "value_tier") and isinstance(value, str):
                found.append(value)
            found.extend(_collect_tags(value, key=str(child_key)))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_collect_tags(item, key=key))
    return found


def _assert_sw015_visitor_bans(payload: dict[str, Any], label: str) -> None:
    """SW-015 add-only: headline, shadow, natural capital in visitor prose."""
    texts = _visitor_strings(payload)
    capital_hits = [t for t in texts if _NATURAL_CAPITAL.search(t)]
    assert not capital_hits, (
        f"{label} visitor text contains 'natural capital':\n"
        + "\n".join(repr(h[:200]) for h in capital_hits)
    )
    slash_hits = [t for t in texts if _HEADLINE_SHADOW_SLASH.search(t)]
    assert not slash_hits, (
        f"{label} visitor text contains 'headline/shadow':\n"
        + "\n".join(repr(h[:200]) for h in slash_hits)
    )
    headline_hits = [t for t in texts if _HEADLINE_WORD.search(t)]
    assert not headline_hits, (
        f"{label} visitor text contains 'headline':\n"
        + "\n".join(repr(h[:200]) for h in headline_hits)
    )
    shadow_hits = [t for t in texts if _SHADOW_WORD.search(t)]
    assert not shadow_hits, (
        f"{label} visitor text contains 'shadow':\n"
        + "\n".join(repr(h[:200]) for h in shadow_hits)
    )


def _assert_public_visitor_copy(payload: dict[str, Any], label: str) -> None:
    texts = _visitor_strings(payload)
    ledger_hits = [t for t in texts if _LEDGER_WORD.search(t)]
    assert not ledger_hits, f"{label} visitor text contains 'ledger':\n" + "\n".join(
        repr(h[:200]) for h in ledger_hits
    )
    _assert_sw015_visitor_bans(payload, label)
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
    assert "Scottish totals" in body["headline"]["label"]
    assert "Estimate" in body["shadow"]["label"]
    assert "headline" not in body["headline"]["label"].lower()
    assert "shadow" not in body["shadow"]["label"].lower()


def test_ledger_json_runtime_copy_has_no_ledger_word():
    payload = ledger_catalog()
    _assert_public_visitor_copy(payload, "ledger.json")
    oil = next(r for r in payload["rows"] if r["id"] == "9")
    assert oil["note"] == (
        "Reported alongside the breakdown; outside the Scottish totals."
    )


def test_all_public_api_json_visitor_copy_bans_headline_shadow_natural_capital():
    """Walk public API JSON builders — SW-015 visitor bans (add-only)."""
    for path, builder in _PUBLIC_API_JSON_BUILDERS:
        payload = builder()
        assert isinstance(payload, dict), path
        _assert_sw015_visitor_bans(payload, path)


def test_api_tag_values_still_market_proxy_shadow():
    """Machine tag values stay market/proxy/shadow (visitor labels may differ)."""
    ledger = ledger_catalog()
    stack = place_hectare_stack("S01010264", zone_name="City Centre South")
    tags = set(_collect_tags(ledger)) | set(_collect_tags(stack))
    assert tags <= _ALLOWED_TAGS
    assert {"market", "proxy", "shadow"} <= tags
    # Explicit row pins — API values unchanged by SW-015 wording.
    by_id = {r["id"]: r for r in ledger["rows"]}
    assert by_id["1"]["tag"] in {"market", "proxy", "market_or_proxy"}
    assert by_id["5"]["tag"] == "shadow"
    assert by_id["2"]["tag"] == "proxy"
    shadow_rows = stack["shadow"]["rows"]
    assert any(r["tag"] == "shadow" for r in shadow_rows)


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
