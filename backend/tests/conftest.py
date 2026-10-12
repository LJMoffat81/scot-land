"""Shared fixtures for the backend suite.

Stubs the data-zone network seam so unit tests stay offline.
PostGIS-dependent tests may skip when WEALTH_TEST_DATABASE_URL is unset.
"""

from __future__ import annotations

import os

import pytest


def pytest_configure(config):
    """CI may set WEALTH_REQUIRE_POSTGIS=1 to force PostGIS suites to run."""
    if os.getenv("WEALTH_REQUIRE_POSTGIS") == "1" and not os.getenv(
        "WEALTH_TEST_DATABASE_URL", ""
    ).strip():
        raise pytest.UsageError(
            "WEALTH_REQUIRE_POSTGIS=1 but WEALTH_TEST_DATABASE_URL is not set"
        )


@pytest.fixture(autouse=True)
def _offline_data_zone(monkeypatch):
    monkeypatch.setattr("agr.engine.zone_code_at", lambda lat, lng: None)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)
