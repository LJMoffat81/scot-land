"""Wealth routes must return 503 when data/DB is missing — never invented figures.

Preserves the PR #3 honesty contract on top of the Wealth Engine v1 routes:
missing PostGIS / empty publishable tables → HTTP 503, never mock harvests.
"""

from __future__ import annotations

import pytest

_DB_ENV = (
    "DATABASE_URL",
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "PGDATABASE",
    "PGSERVICE",
)


@pytest.fixture
def offline_client(monkeypatch):
    """Client with no database configured — honesty path, not CI PostGIS."""
    for var in _DB_ENV:
        monkeypatch.delenv(var, raising=False)
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    [
        "/layers/georgist/surface-rent",
        "/layers/georgist/resource-rent",
        "/layers/georgist/eco-rent",
    ],
)
def test_wealth_layers_503_without_processed_files(offline_client, path):
    r = offline_client.get(path)
    assert r.status_code == 503, r.text
    body = r.json()
    detail = body.get("detail", "")
    detail_text = detail if isinstance(detail, str) else str(detail).lower()
    # Wealth Engine returns structured detail; accept either phrase form.
    assert (
        "not available" in detail_text.lower()
        or "missing" in detail_text.lower()
        or "not_built" in detail_text.lower()
        or "unavailable" in detail_text.lower()
        or "not_configured" in detail_text.lower()
    )
    # Never serve mock harvests on the public path
    assert "MOCK" not in r.text
    assert "features" not in body


def test_georgist_wealth_503_without_database(offline_client):
    """No DATABASE_URL → 503. Never invent wealth figures."""
    r = offline_client.get(
        "/georgist/wealth",
        params={"lat": 55.86, "lng": -4.25, "zone_id": "S01008677"},
    )
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "")
    detail_text = detail if isinstance(detail, str) else str(detail).lower()
    assert "unavailable" in detail_text.lower() or "not_configured" in detail_text.lower()


def test_aggregator_raises_when_db_unreachable(monkeypatch):
    from georgist import db
    from georgist.aggregator import aggregator

    def _boom():
        raise db.DatabaseUnavailable("no postgis in this test")

    monkeypatch.setattr(db, "cursor", _boom)
    with pytest.raises(db.DatabaseUnavailable):
        aggregator.get_total_wealth("S01008677", 2011, 55.86, -4.25)
