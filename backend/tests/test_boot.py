"""API import and liveness — main must boot without missing modules."""

from __future__ import annotations


def test_api_main_imports():
    import api.main

    assert api.main.app.title == "Scot-LAND API"


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "scot-land"
    assert "version" in body


def test_no_duplicate_surface_rent_route():
    from collections import Counter

    from api.main import app

    paths = [
        getattr(route, "path", None)
        for route in app.routes
        if getattr(route, "path", None) == "/layers/georgist/surface-rent"
    ]
    assert Counter(paths)["/layers/georgist/surface-rent"] == 1
