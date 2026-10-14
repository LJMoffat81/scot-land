"""SW-031/032: OpenAPI summaries must not say natural capital, ledger, or £."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from api.main import app

_BANNED = (
    (re.compile(r"natural\s+capital", re.IGNORECASE), "natural capital"),
    (re.compile(r"\bledger\b", re.IGNORECASE), "ledger"),
    (re.compile(r"£"), "£"),
)

_LEDGER_SUMMARY = "Land rent by Data Zone (developer)"


def test_get_ledger_openapi_summary_renamed():
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    op = schema["paths"]["/ledger"]["get"]
    assert op["summary"] == _LEDGER_SUMMARY
    assert "Natural Capital" not in (op.get("summary") or "")


def test_openapi_summaries_ban_natural_capital_ledger_pound():
    """Additive guard: every OpenAPI *summary* is clean (machine paths exempt)."""
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    violations: list[str] = []
    for path, methods in (schema.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            summary = op.get("summary") or ""
            if not isinstance(summary, str) or not summary.strip():
                continue
            for pattern, name in _BANNED:
                if pattern.search(summary):
                    violations.append(f"{method.upper()} {path}: summary has {name!r}: {summary!r}")
    assert not violations, "OpenAPI summary bans:\n" + "\n".join(violations)
