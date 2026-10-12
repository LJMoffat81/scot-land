"""Wealth routes must return 503 when data/DB is missing — never invented figures."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/layers/georgist/surface-rent",
        "/layers/georgist/resource-rent",
        "/layers/georgist/eco-rent",
    ],
)
def test_wealth_layers_503_without_processed_files(client, path):
    r = client.get(path)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "")
    assert "not available" in detail.lower() or "missing" in detail.lower()
    # Never serve mock harvests on the public path
    assert "MOCK" not in r.text
    assert "features" not in r.json()


def test_georgist_wealth_503_without_database(client, monkeypatch):
    from georgist.aggregator import DatabaseUnavailable

    def _boom(*_a, **_k):
        raise DatabaseUnavailable("no postgis in this test")

    monkeypatch.setattr(
        "api.main.aggregator.get_total_wealth",
        _boom,
    )
    r = client.get(
        "/georgist/wealth",
        params={"lat": 55.86, "lng": -4.25, "zone_id": "S01008677"},
    )
    assert r.status_code == 503, r.text
    assert "unavailable" in r.json()["detail"].lower()


def test_aggregator_raises_when_db_unreachable():
    from georgist.aggregator import DatabaseUnavailable, WealthAggregator

    agg = WealthAggregator(
        db_config={
            "dbname": "does_not_exist",
            "user": "nobody",
            "password": "x",
            "host": "127.0.0.1",
            "port": "1",
        }
    )
    with pytest.raises(DatabaseUnavailable):
        agg.get_total_wealth("S01008677", 55.86, -4.25)
