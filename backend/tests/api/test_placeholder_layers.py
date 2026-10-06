"""Mock resource/eco layers: absent from public endpoints; internal endpoints only, behind a flag."""

import pytest

from georgist.eco_harvester import build_eco_features
from georgist.resource_harvester import build_resource_features

PUBLIC = ["/layers/georgist/resource-rent", "/layers/georgist/eco-rent"]


@pytest.mark.parametrize("build", [build_resource_features, build_eco_features])
def test_builders_tag_placeholder(build):
    geo = build()
    assert geo["meta"]["quality"] == "placeholder"
    for f in geo["features"]:
        assert f["properties"]["quality"] == "placeholder"
        assert f["properties"]["in_totals"] is False
        assert "rent_per_ha" not in f["properties"]


@pytest.mark.parametrize("path", PUBLIC)
def test_public_layers_never_serve_mocks(client, path):
    r = client.get(path)
    assert r.status_code == 503  # no DB here; never a mock fallback
    assert "features" not in r.json() and "MOCK" not in r.text
    assert "X-Wealth-Quality" not in r.headers


def _client(monkeypatch, flag):
    from fastapi.testclient import TestClient

    from api.main import create_app

    if flag is None:
        monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
    else:
        monkeypatch.setenv("ENABLE_INTERNAL_ENDPOINTS", flag)
    return TestClient(create_app())


@pytest.mark.parametrize("flag", [None, "", "0", "false", "no"])
def test_internal_endpoints_off_by_default(monkeypatch, flag):
    c = _client(monkeypatch, flag)
    for path in ["/internal/layers/georgist/resource-rent", "/internal/layers/georgist/eco-rent",
                 "/internal/georgist/wealth?lat=55.95&lng=-3.19&zone_id=S01008677",
                 "/internal/georgist/surface-rent/S01008677"]:
        assert c.get(path).status_code == 404, path
    assert c.get("/health").json()["routers"]["api.internal_routes"]["loaded"] is False


@pytest.mark.parametrize("path", ["/internal/layers/georgist/resource-rent", "/internal/layers/georgist/eco-rent"])
def test_internal_mock_layers_when_enabled(monkeypatch, path):
    c = _client(monkeypatch, "1")
    r = c.get(path)
    assert r.status_code == 200
    assert r.headers["X-Wealth-Quality"] == "placeholder" and r.headers["X-Wealth-Internal"] == "true"
    body = r.json()
    assert body["meta"]["internal"] is True and body["meta"]["in_totals"] is False
    assert all(f["properties"]["in_totals"] is False for f in body["features"])


def test_internal_wealth_still_fails_loudly_without_db(monkeypatch):
    c = _client(monkeypatch, "true")
    r = c.get("/internal/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": "S01008677"})
    assert r.status_code == 503
    assert c.get("/internal/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": "unknown"}).status_code == 422
