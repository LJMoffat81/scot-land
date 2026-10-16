"""API import and liveness — main must boot without missing modules."""

from __future__ import annotations

from collections import Counter

from fastapi.testclient import TestClient

from api.main import app, create_app, registered_routes


def test_api_main_imports():
    import api.main

    assert api.main.app.title == "Scot-LAND API"


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body.get("version")
    assert set(body) == {"status", "version"}
    # HEALTH-TRIM / SW-037: no operator notes, env names, or modelled AGR £ on public /health.
    text = r.text
    for banned in (
        "ENABLE_INTERNAL_ENDPOINTS",
        "INTERNAL_API_TOKEN",
        "modelled AGR",
        "w3w-grid",
        "£",
    ):
        assert banned not in text, banned


def test_health_trim_no_internal_leakage(monkeypatch):
    """Even with internal endpoints mounted, /health stays status + version only."""
    monkeypatch.setenv("ENABLE_INTERNAL_ENDPOINTS", "1")
    monkeypatch.setenv("INTERNAL_API_TOKEN", "test-internal-token")

    r = TestClient(create_app()).get("/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"status", "version"}
    text = r.text
    for banned in (
        "ENABLE_INTERNAL_ENDPOINTS",
        "INTERNAL_API_TOKEN",
        "modelled AGR",
        "w3w-grid",
        "£",
        "routers",
        "git_commit",
    ):
        assert banned not in text, banned


def test_no_duplicate_surface_rent_route():
    # Wealth routes live on an included router; walk with registered_routes.
    paths = [path for _method, path in registered_routes(app) if path == "/layers/georgist/surface-rent"]
    assert Counter(paths)["/layers/georgist/surface-rent"] == 1
