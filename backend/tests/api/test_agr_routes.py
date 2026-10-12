"""AGR public router mounts under publication declarations; modelled £ is internal."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _app(monkeypatch, *, internal: bool = False):
    from api.main import create_app

    if internal:
        monkeypatch.setenv("ENABLE_INTERNAL_ENDPOINTS", "1")
        monkeypatch.setenv("INTERNAL_API_TOKEN", "test-internal-token")
    else:
        monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
        monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    return create_app()


def test_agr_router_loads_when_publication_declarations_present(monkeypatch):
    """Regression: missing declarations used to skip the whole router at startup."""
    from api.main import ROUTER_STATUS, registered_routes

    app = _app(monkeypatch)
    assert ROUTER_STATUS["api.agr_routes"]["loaded"] is True
    paths = {p for _, p in registered_routes(app)}
    # Public map layers / search
    assert "/layers/catalog" in paths
    assert "/layers/councils" in paths
    assert "/place" in paths
    assert "/address" in paths
    assert "/postcode/{postcode}" in paths
    assert "/layers/context/{layer_id}/tiles/{z}/{x}/{y}" in paths
    # Modelled residual AGR £ stays off the public surface
    assert "/square" not in paths
    assert "/layers/councils-agr" not in paths
    assert "/fiscal/summary" not in paths
    assert "/layers/w3w-grid" not in paths


def test_public_postcode_is_location_only(monkeypatch):
    client = TestClient(_app(monkeypatch))
    # Unknown postcode → 404 from postcodes.io (or 502 offline); shape must not be AGR.
    # Use a well-formed Scottish-looking code; network may 404/502 — either is fine.
    r = client.get("/postcode/G21DU")
    if r.status_code == 200:
        body = r.json()
        assert body.get("agr") is None
        assert body.get("status") == "location_only"
        assert "lat" in body and "lng" in body
    else:
        assert r.status_code in {404, 502}


def test_modelled_agr_routes_are_internal_with_auth(monkeypatch):
    public = TestClient(_app(monkeypatch))
    assert public.get("/square", params={"lat": 55.86, "lng": -4.25}).status_code == 404
    assert public.get("/layers/councils-agr").status_code == 404
    assert public.get("/fiscal/summary").status_code == 404

    internal = TestClient(_app(monkeypatch, internal=True))
    assert internal.get(
        "/internal/agr/square",
        params={"lat": 55.86, "lng": -4.25},
    ).status_code == 401

    ok = internal.get(
        "/internal/agr/square",
        params={"lat": 55.86, "lng": -4.25},
        headers={"Authorization": "Bearer test-internal-token"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body.get("internal") is True
    assert body.get("publication_status") == "blocked"


def test_health_reports_agr_loaded(monkeypatch):
    r = TestClient(_app(monkeypatch)).get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["routers"]["api.agr_routes"]["loaded"] is True
    assert body.get("publication_geometry") == "public_shapes_modelled_agr_internal"
