"""Hedonic unit tests do not need the AGR / spatial offline stub."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _offline_data_zone():
    """Override root autouse fixture — avoid importing agr.engine / shapely."""
    yield
