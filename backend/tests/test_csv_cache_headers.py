"""Every CSV route is cacheable and ignores the deploy query.

The test builds its own app. It does not import api.main_platform, which
would patch the core app for the rest of the pytest process.
"""

import api.main as core
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.platform_routes import router


def _walk(routes) -> list[str]:
    paths: list[str] = []
    for route in routes:
        path = getattr(route, "path", "") or ""
        methods = getattr(route, "methods", None) or set()
        if path.endswith(".csv") and "GET" in methods:
            paths.append(path)
        nested = getattr(route, "original_router", None)
        if nested is not None:
            paths.extend(_walk(nested.routes))
        child = getattr(route, "routes", None)
        if child:
            paths.extend(_walk(child))
    return paths


def _csv_paths(app) -> list[str]:
    return sorted(set(_walk(app.routes)))


def _patch_layers(monkeypatch) -> None:
    monkeypatch.setattr("layers.vdl.by_council_hectares", lambda: {})
    monkeypatch.setattr("layers.open_stats.by_council_hectares", lambda: {})
    monkeypatch.setattr("layers.council_metrics.by_council_hectares", lambda: {})


@pytest.fixture
def csv_app(monkeypatch):
    original = core._square_response
    before = tuple(_csv_paths(core.app))
    _patch_layers(monkeypatch)
    app = FastAPI()
    app.include_router(router)
    yield app
    assert core._square_response is original
    assert core._square_response.__name__ != "_square_with_platform"
    assert tuple(_csv_paths(core.app)) == before


def test_every_csv_route_sets_cache_control_and_ignores_v(csv_app):
    client = TestClient(csv_app)
    paths = _csv_paths(csv_app)
    assert paths, "expected at least one CSV route"
    for path in paths:
        plain = client.get(path)
        versioned = client.get(path, params={"v": "abc1234"})
        assert plain.status_code == 200, path
        assert versioned.status_code == 200, path
        assert plain.headers["content-type"].startswith("text/csv"), path
        assert plain.headers["cache-control"] == "public, max-age=300", path
        assert versioned.headers["cache-control"] == "public, max-age=300", path
        assert plain.text == versioned.text, path


def test_csv_fixture_leaves_the_core_app_alone(csv_app):
    """While the fresh app is mounted, and again after its fixture tears down."""
    original_name = core._square_response.__name__
    before = _csv_paths(core.app)
    client = TestClient(csv_app)
    paths = _csv_paths(csv_app)
    assert paths, "expected at least one CSV route"
    assert client.get(paths[0]).status_code == 200
    assert original_name != "_square_with_platform"
    assert core._square_response.__name__ == original_name
    assert not any(path.endswith(".csv") for path in before)
