"""SEA-EXTENT-2 — SE-P1 / SE-P2: frontend credit locked to registry attribution."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from layers.registry.loader import registry

REPO = Path(__file__).resolve().parents[2]
ATTRIBUTION_TS = REPO / "frontend" / "lib" / "mapAttributionLine.ts"

_CREDIT_RE = re.compile(
    r'export const SCOTLAND_EXTENT_CREDIT\s*=\s*\n?\s*"([^"]*)"\s*;',
    re.MULTILINE,
)

_DRIFT_MSG = (
    "SEA-EXTENT-2: frontend credit drift: "
    "SCOTLAND_EXTENT_CREDIT != registry scotland-extent attribution"
)


def _extract_scotland_extent_credit(text: str, path: Path) -> str:
    match = _CREDIT_RE.search(text)
    if match is None:
        raise AssertionError(
            f"SEA-EXTENT-2: SCOTLAND_EXTENT_CREDIT not found in {path}"
        )
    return match.group(1)


def assert_scotland_extent_credit(path: Path) -> None:
    """SE-P1: SCOTLAND_EXTENT_CREDIT in ``path`` must match registry attribution.

    Mutation: drop the ``credit != expected`` comparison → negative year-drift
    test stays green under pytest.raises (no raise) and turns red.
    """
    text = path.read_text(encoding="utf-8")
    credit = _extract_scotland_extent_credit(text, path)
    expected = " ".join(
        registry()["scotland-extent"].raw["attribution"].split()
    )
    if credit != expected:
        raise AssertionError(_DRIFT_MSG)


def test_se_p1_scotland_extent_credit_matches_registry():
    assert_scotland_extent_credit(ATTRIBUTION_TS)


def test_se_p1_negative_year_drift(tmp_path: Path):
    src = ATTRIBUTION_TS.read_text(encoding="utf-8")
    assert "2026" in src
    copy = tmp_path / "mapAttributionLine.ts"
    copy.write_text(src.replace("2026", "2025", 1), encoding="utf-8")
    with pytest.raises(
        AssertionError,
        match=(
            r"^SEA-EXTENT-2: frontend credit drift: "
            r"SCOTLAND_EXTENT_CREDIT != registry scotland-extent attribution$"
        ),
    ):
        assert_scotland_extent_credit(copy)


def test_se_p2_missing_literal_raises(tmp_path: Path):
    copy = tmp_path / "mapAttributionLine.ts"
    copy.write_text("// no scotland extent credit\n", encoding="utf-8")
    with pytest.raises(
        AssertionError,
        match=r"^SEA-EXTENT-2: SCOTLAND_EXTENT_CREDIT not found in (.+)$",
    ):
        assert_scotland_extent_credit(copy)
