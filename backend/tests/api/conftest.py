"""API/Wealth tests. Every test starts with NO database configured."""

import pytest

DB_ENV = ("DATABASE_URL", "PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE", "PGSERVICE")


@pytest.fixture(autouse=True)
def no_database(monkeypatch):
    for var in DB_ENV:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)
