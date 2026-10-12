"""SYNTHETIC fixtures only. Nothing here is real RoS/NRS/SG data.

Zone codes S010134xx sit inside the DZ2011 range (codes are validated, 2026-10-06); every row is SYNTHETIC.
"""

import copy

import pytest

from georgist import surface_rent as sr

SYNTHETIC_RATES = {  # SYNTHETIC £/m², test-only. Not a rebuild cost estimate.
    "detached": 2000.0,
    "semi_detached": 1800.0,
    "terraced": 1700.0,
    "flat_purpose_built": 1900.0,
    "flat_conversion": 2100.0,
    "other": 1850.0,
}
SYNTHETIC_BAND = {t: {"low": r * 0.8, "central": r, "high": r * 1.3} for t, r in SYNTHETIC_RATES.items()}


@pytest.fixture
def cfg():
    return copy.deepcopy(sr.load_config())


@pytest.fixture
def rates():
    return dict(SYNTHETIC_RATES)


@pytest.fixture
def band():
    return copy.deepcopy(SYNTHETIC_BAND)
