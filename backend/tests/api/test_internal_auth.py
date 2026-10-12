"""/internal auth: never fall open, even in dev."""

from __future__ import annotations

import pytest

from api.internal_auth import ENV_TOKEN

PATHS = [
    "/internal/layers/georgist/resource-rent",
    "/internal/layers/georgist/eco-rent",
    "/internal/georgist/surface-rent/S01008677",
]


def _client(monkeypatch, *, enabled=True, token: str | None = "test-secret-token"):
    from fastapi.testclient import TestClient

    from api.main import create_app

    if enabled:
        monkeypatch.setenv("ENABLE_INTERNAL_ENDPOINTS", "1")
    else:
        monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
    if token is None:
        monkeypatch.delenv(ENV_TOKEN, raising=False)
    else:
        monkeypatch.setenv(ENV_TOKEN, token)
    return TestClient(create_app())


@pytest.mark.parametrize("path", PATHS)
def test_no_token_returns_401_when_secret_configured(monkeypatch, path):
    c = _client(monkeypatch, token="correct-token")
    r = c.get(path)
    assert r.status_code == 401, path
    assert r.json()["detail"]["error"] == "unauthorized"


@pytest.mark.parametrize("path", PATHS)
def test_wrong_token_returns_401(monkeypatch, path):
    c = _client(monkeypatch, token="correct-token")
    r = c.get(path, headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 401, path
    assert r.json()["detail"]["error"] == "unauthorized"


@pytest.mark.parametrize("path", PATHS)
def test_valid_bearer_token_allowed(monkeypatch, path):
    c = _client(monkeypatch, token="correct-token")
    r = c.get(path, headers={"Authorization": "Bearer correct-token"})
    assert r.status_code != 401 and r.status_code != 403, (path, r.status_code, r.text)
    # surface-rent needs DB (503); mock layers are 200
    assert r.status_code in (200, 503, 404)


@pytest.mark.parametrize("path", PATHS)
def test_valid_api_key_header_allowed(monkeypatch, path):
    c = _client(monkeypatch, token="correct-token")
    r = c.get(path, headers={"X-API-Key": "correct-token"})
    assert r.status_code != 401 and r.status_code != 403, (path, r.status_code, r.text)


@pytest.mark.parametrize("path", PATHS)
def test_unset_secret_locks_endpoints(monkeypatch, path):
    """Flag on but no INTERNAL_API_TOKEN → locked (403), never open."""
    c = _client(monkeypatch, token=None)
    health = c.get("/health").json()["routers"]["api.internal_routes"]
    assert health["loaded"] is True and health["auth"] == "locked"
    r = c.get(path, headers={"Authorization": "Bearer anything"})
    assert r.status_code == 403, path
    assert r.json()["detail"]["error"] == "internal_locked"


def test_flag_off_still_404(monkeypatch):
    c = _client(monkeypatch, enabled=False, token="correct-token")
    assert c.get("/internal/layers/georgist/resource-rent").status_code == 404
