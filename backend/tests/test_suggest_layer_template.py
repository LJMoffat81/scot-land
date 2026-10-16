"""SUGGEST-LAYER-1 issue form: parses, and does not ask for personal data."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / ".github" / "ISSUE_TEMPLATE" / "suggest-layer.yml"

REQUIRED_LABELS = (
    "What is the layer?",
    "Data source link",
    "Why it matters for land value",
)
OPTIONAL_LABEL = "Licence (if known)"
PERSONAL = re.compile(
    r"\b(e-?mail|location|phone|postcode|address|your name)\b",
    re.IGNORECASE,
)


def test_suggest_layer_template_parses_without_personal_fields():
    document = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    assert document["labels"] == ["layer-suggestion"]

    fields = [item for item in document["body"] if item.get("type") != "markdown"]
    labels = [item["attributes"]["label"] for item in fields]
    assert labels == [*REQUIRED_LABELS, OPTIONAL_LABEL]

    required = [bool(item["validations"]["required"]) for item in fields]
    assert required == [True, True, True, False]

    for item in fields:
        label = item["attributes"]["label"]
        field_id = str(item["id"])
        assert PERSONAL.search(label) is None
        assert PERSONAL.search(field_id) is None
        assert label.strip().lower() != "name"

    raw = TEMPLATE.read_text(encoding="utf-8").lower()
    assert "email" not in raw
    assert "e-mail" not in raw
    assert "location" not in raw
