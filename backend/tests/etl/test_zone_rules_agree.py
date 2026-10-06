"""Our loader's vintage/code ranges agree with GIS's shared zone_rules.py and Valuation's surface_zones."""

import importlib.util
from pathlib import Path

import pytest

from etl import load_processed as lp
from georgist import dz_lookup, surface_zones

ZONE_RULES = Path(__file__).resolve().parents[3] / "etl" / "gis" / "zone_rules.py"


def _gis_rules():
    if not ZONE_RULES.is_file():
        pytest.skip("etl/gis/zone_rules.py not present")
    spec = importlib.util.spec_from_file_location("gis_zone_rules", ZONE_RULES)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _codes(lo_hi):
    lo, hi = lo_hi
    return f"S01{lo:06d}", f"S01{hi:06d}"


def test_ranges_agree_with_gis_and_valuation():
    gis = _gis_rules()
    ours = {v: _codes(r) for v, r in dz_lookup.DZ_RANGES.items()}
    assert ours == gis.RANGE
    assert ours == {v: _codes(r) for v, r in surface_zones.CODE_RANGES.items()}
    assert tuple(lp.ZONE_VINTAGES) == tuple(sorted(gis.RANGE)) == surface_zones.VINTAGES
    assert {v: hi - lo + 1 for v, (lo, hi) in dz_lookup.DZ_RANGES.items()} == gis.NZONES
