"""GET /ledger — Natural capital ledger contract (rows + constraints, no AGR £)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from layers.ledger import CONSTRAINT_RULE, ledger_payload

client = TestClient(app)

EXPECTED_ROW_IDS = ["1", "1a", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
EXPECTED_CONSTRAINT_IDS = ["designations", "flood", "crofting", "lca"]


def test_ledger_payload_shape():
    body = ledger_payload()
    assert body["version"] == 1
    assert [row["id"] for row in body["rows"]] == EXPECTED_ROW_IDS
    assert [c["id"] for c in body["constraints"]] == EXPECTED_CONSTRAINT_IDS
    nested = next(row for row in body["rows"] if row["id"] == "1a")
    assert nested["nested"] is True
    assert nested["parent_id"] == "1"
    oil = next(row for row in body["rows"] if row["id"] == "9")
    assert oil["outside_scottish_total"] is True
    for constraint in body["constraints"]:
        assert constraint["rule"] == CONSTRAINT_RULE
    # Public amounts are placeholders — never numeric AGR £.
    for row in body["rows"]:
        assert row["amount_placeholder"] == "—"
        assert "agr" not in row["amount_placeholder"].lower()


def test_ledger_route_returns_rows_and_constraints():
    r = client.get("/ledger")
    assert r.status_code == 200
    body = r.json()
    assert [row["id"] for row in body["rows"]] == EXPECTED_ROW_IDS
    assert [c["id"] for c in body["constraints"]] == EXPECTED_CONSTRAINT_IDS
    assert "Constraint: changes best use, adds no value" in body["constraints"][0]["rule"]
    assert "£0" not in body["constraints"][0]["rule"]
    assert "market+proxy" not in body.get("brief", "")
    dumped = str(body)
    assert "£0" not in dumped
    assert "market+proxy" not in dumped
    # No modelled rent figures in the public ledger body.
    dumped = r.text
    assert "annual_ground_rent" not in dumped
    assert "site_rental_per_sqm" not in dumped
    for row in body["rows"]:
        assert row["amount_placeholder"] == "—"
        assert "£" not in row["amount_placeholder"]
