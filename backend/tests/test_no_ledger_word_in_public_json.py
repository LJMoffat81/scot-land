"""Runtime API copy must not ship the visitor word ``ledger``.

Built-HTML greps miss browser-loaded JSON from /api/place-stack.json and
/api/ledger.json — walk those payloads' visitor-facing string values here.
"""

from __future__ import annotations

import re
from typing import Any

from georgist.ledger import ledger_catalog
from georgist.place_stack import place_hectare_stack

_LEDGER_WORD = re.compile(r"\bledger\b", re.IGNORECASE)

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


def _assert_no_ledger_word(payload: dict[str, Any], label: str) -> None:
    hits = [
        text
        for text in _visitor_strings(payload)
        if _LEDGER_WORD.search(text)
    ]
    assert not hits, f"{label} visitor text contains 'ledger':\n" + "\n".join(
        repr(h[:200]) for h in hits
    )


def test_place_stack_runtime_copy_has_no_ledger_word():
    body = place_hectare_stack("S01010264", zone_name="City Centre South")
    _assert_no_ledger_word(body, "place-stack")
    assert (
        "Benchmarks are shown alongside the breakdown and are never inputs."
        in body["outside"]["note"]
    )


def test_ledger_json_runtime_copy_has_no_ledger_word():
    payload = ledger_catalog()
    _assert_no_ledger_word(payload, "ledger.json")
    oil = next(r for r in payload["rows"] if r["id"] == "9")
    assert oil["note"] == (
        "Reported alongside the breakdown; outside the Scottish totals."
    )
