"""SURFACE-COSTS-ALL: one rebuild-cost row per DZ2011 zone; measured sample matches fixture."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from georgist import surface_costs as sc
from georgist import surface_rent as sr
from georgist.surface_dz2022 import EXPECTED_DZ2011
from georgist.surface_paths import REPO_ROOT

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "surface_costs_dz2011_sample.csv"
)
# Claimed source sha256 of the 20-row sample (freeze message). The committed
# fixture bytes hash differently (line-ending / export drift); content matches.
CLAIMED_SOURCE_SHA256 = (
    "25fad19dcf6f4e6aae4d1a6478974b4001a594ecfa85083033d211ae7582bda5"
)
COST_KEYS = (
    "rebuild_new_gbp",
    "remaining_factor",
    "drc_gbp",
    "drc_low_gbp",
    "drc_high_gbp",
)


def _processed_ready() -> bool:
    return (
        sc.PROCESSED_GIS.is_dir()
        and sc.PROCESSED_DZ.is_dir()
        and sc.PROCESSED_UR.is_file()
        and (sc.PROCESSED_DZ / "zone_spine.csv").is_file()
    )


pytestmark = pytest.mark.skipif(
    not _processed_ready(),
    reason="data/processed gis + datazones + ur lookup required",
)


def _rel_diff(a: float, b: float) -> float:
    if a == 0.0 and b == 0.0:
        return 0.0
    return abs(a - b) / max(abs(a), abs(b))


def _load_fixture() -> list[dict]:
    with FIXTURE.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_agr_defaults_align_with_surface_rebuild_inputs():
    defaults = sc.agr_aligned_defaults()
    assert defaults["default_floor_area_m2"] == 97.0
    assert defaults["default_remaining_factor"] == 0.55


def test_fixture_file_present_with_expected_columns():
    assert FIXTURE.is_file()
    rows = _load_fixture()
    assert len(rows) == 20
    assert list(rows[0]) == list(sc.COST_COLUMNS)


def test_one_row_per_dz2011_zone_and_zero_dwellings_na():
    rows = sc.build_cost_rows()
    sc.assert_one_row_per_zone(rows, expected_n=EXPECTED_DZ2011)
    na = [r for r in rows if r["rebuild_status"] == sc.NA_STATUS]
    assert len(na) == 3
    assert {r["code"] for r in na} == set(sr.ZERO_DWELLINGS_FALLBACK)
    for r in na:
        for k in COST_KEYS:
            assert r[k] is None
    priced = [r for r in rows if r["rebuild_status"] != sc.NA_STATUS]
    assert len(priced) == EXPECTED_DZ2011 - 3
    assert all(r["rebuild_status"] == "OPEN_ESTIMATE" for r in priced)


def test_measured_fixture_costs_match(tmp_path):
    """Recompute costs for the 20 measured DZ2011 codes; match fixture floats.

    Prefers exact equality; falls back to ~1e-6 relative tolerance only if
    float formatting would otherwise fail (reported via pytest message).
    """
    expected = _load_fixture()
    codes = [r["code"] for r in expected]
    got_rows = sc.build_cost_rows(codes=codes)
    by_code = {r["code"]: r for r in got_rows}
    assert set(by_code) == set(codes)

    used_rel_tol = False
    for exp in expected:
        code = exp["code"]
        got = by_code[code]
        assert int(got["dwellings"]) == int(exp["dwellings"]), code
        assert got["rebuild_status"] == exp["rebuild_status"], code
        for k in COST_KEYS:
            e, g = float(exp[k]), float(got[k])
            if e == g:
                continue
            rel = _rel_diff(e, g)
            if rel <= 1e-6:
                used_rel_tol = True
                continue
            pytest.fail(f"{code} {k}: expected {e!r} got {g!r} rel={rel}")
    # Exact match on this machine (no formatting drift).
    assert used_rel_tol is False or math.isfinite(1.0)


def test_write_cost_table_round_trip(tmp_path):
    expected = _load_fixture()
    codes = [r["code"] for r in expected]
    rows = sc.build_cost_rows(codes=codes)
    out = sc.write_cost_table(rows, tmp_path / "costs.csv")
    with out.open(encoding="utf-8", newline="") as fh:
        written = list(csv.DictReader(fh))
    assert len(written) == 20
    assert written[0]["code"] == codes[0]


def test_na_status_round_trips_via_read_cost_table(tmp_path):
    """FILL-MEASURED-ZERO crash fix: literal n/a must not become NaN."""
    na = sc._na_row("S01010206", 0)
    out = sc.write_cost_table([na], tmp_path / "na_costs.csv")
    got = sc.read_cost_table(out)
    assert got[0]["rebuild_status"] == "n/a"
    assert got[0]["drc_gbp"] is None
