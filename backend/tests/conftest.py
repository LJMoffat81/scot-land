"""Keep the suite off the data-zone boundary service.

A click resolves a 2011 data zone over the network. Tests stub that seam.
A test that needs a zone sets agr.engine.zone_code_at itself.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _offline_data_zone(monkeypatch):
    monkeypatch.setattr("agr.engine.zone_code_at", lambda lat, lng: None)
