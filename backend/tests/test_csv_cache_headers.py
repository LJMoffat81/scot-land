"""Every CSV route is cacheable and ignores the deploy query."""

from fastapi.testclient import TestClient


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


def test_every_csv_route_sets_cache_control_and_ignores_v(monkeypatch):
    from api.main_platform import app

    monkeypatch.setattr("layers.vdl.by_council_hectares", lambda: {})
    monkeypatch.setattr("layers.open_stats.by_council_hectares", lambda: {})
    monkeypatch.setattr("layers.council_metrics.by_council_hectares", lambda: {})
    client = TestClient(app)
    paths = _csv_paths(app)
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
