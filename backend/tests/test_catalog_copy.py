"""Visitor catalogue copy — plain English, no banned jargon."""

from __future__ import annotations

import re

from layers.catalog_copy import (
    PLAIN_DESCRIPTIONS,
    apply_visitor_catalog_copy,
    visitor_description,
)

_JARGON = re.compile(
    r"PostGIS|LayersPanel|MapServer|value_tier|python\s+-m|\bbbox\b|"
    r"503\s+when\s+unloaded|fixture|\bCI\b|£0",
    re.IGNORECASE,
)


def test_plain_descriptions_have_no_jargon():
    for layer_id, text in PLAIN_DESCRIPTIONS.items():
        assert not _JARGON.search(text), (layer_id, text)


def test_apply_visitor_catalog_copy_moves_technical_to_developer_note():
    payload = {
        "layers": [
            {
                "id": "vdl",
                "label": "Vacant land",
                "description": (
                    "SVDLS from PostGIS ingest (503 when unloaded). "
                    "value_tier=proxy. No £0 rent."
                ),
                "licence_url": "https://example.test/ogl",
            },
            {
                "id": "mystery",
                "label": "Mystery",
                "description": "Loaded via python -m etl.thing from MapServer bbox.",
                "licence_url": "https://example.test/ogl",
            },
        ]
    }
    out = apply_visitor_catalog_copy(payload)
    by_id = {row["id"]: row for row in out["layers"]}
    assert by_id["vdl"]["description"] == PLAIN_DESCRIPTIONS["vdl"]
    assert "PostGIS" in by_id["vdl"]["developer_note"]
    assert not _JARGON.search(by_id["vdl"]["description"])
    assert not _JARGON.search(by_id["mystery"]["description"])
    assert "python -m" in by_id["mystery"]["developer_note"]


def test_visitor_description_known_ids():
    assert "Data Zone" in visitor_description({"id": "data_zones"})
    assert "2022" in visitor_description({"id": "data_zones"})
