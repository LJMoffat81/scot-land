"""Visitor catalogue descriptions via open_stats.catalog_json — no banned jargon.

Runs in CI without BACKEND_URL / PostGIS (pure Python).
"""

from __future__ import annotations

import re

from layers.open_stats import catalog_json

_JARGON = re.compile(
    r"PostGIS|LayersPanel|MapServer|value_tier|python\s+-m|\bbbox\b|"
    r"503\s+when\s+unloaded|fixture|\bCI\b|£0|natural capital|"
    r"Limits use \(not a money value\)",
    re.IGNORECASE,
)


def test_catalog_json_visitor_descriptions_have_no_jargon():
    payload = catalog_json()
    layers = payload.get("layers") or []
    assert layers, "catalogue must list layers"
    violations: list[str] = []
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        lid = layer.get("id") or "?"
        for field in ("description", "label", "attribution"):
            text = layer.get(field)
            if not isinstance(text, str) or not text.strip():
                continue
            hit = _JARGON.search(text)
            if hit:
                violations.append(f"{lid}.{field}: {hit.group(0)!r} in {text[:160]!r}")
    assert not violations, "jargon in visitor catalogue:\n" + "\n".join(violations)


def test_catalog_json_moves_technical_to_developer_note():
    payload = catalog_json()
    by_id = {row["id"]: row for row in payload["layers"] if isinstance(row, dict)}
    # Source-cleaned layers should expose developer_note when technical detail remains.
    assert "data_zones" in by_id
    assert "PostGIS" not in (by_id["data_zones"].get("description") or "")
    assert "sssi" in by_id
    assert "Constraint: changes best use, adds no value" in (
        by_id["sssi"].get("description") or ""
    )
