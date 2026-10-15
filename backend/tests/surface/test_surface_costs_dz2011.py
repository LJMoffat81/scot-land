"""SURFACE-COSTS-ALL / STRICT: one rebuild-cost row per DZ2011; measured sample exact match.

The 20-row fixture equality path uses committed inputs under
``tests/fixtures/surface_costs_dz2011_inputs/`` so CI always runs it even when
``data/processed`` is absent. Full-nation coverage still needs processed GIS.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from georgist import surface_costs as sc
from georgist import surface_rent as sr
from georgist.surface_dz2022 import EXPECTED_DZ2011

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "surface_costs_dz2011_sample.csv"
)
INPUTS = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "surface_costs_dz2011_inputs"
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


def _load_fixture() -> list[dict]:
    with FIXTURE.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _build_rows_from_fixture_inputs() -> list[dict]:
    """Recompute the 20 measured costs from committed zone inputs (no data/processed)."""
    expected = _load_fixture()
    codes = [r["code"] for r in expected]
    cfg = sr.load_config()
    defaults = sc.agr_aligned_defaults(cfg)
    base_year = sr.rebuild_price_base_year(cfg)
    band = sr.rebuild_band(cfg, base_year)
    rebuild_status = str(cfg["rebuild"]["status"])

    epc = pd.read_csv(INPUTS / "epc_dz_rollup.csv").set_index("code")
    nrs = pd.read_csv(INPUTS / "nrs_dwelling_mix_2011_fallback.csv").set_index("code")
    with (INPUTS / "estate_rows.json").open(encoding="utf-8") as fh:
        estate_rows = {str(r["code"]): r for r in json.load(fh)}
    with (INPUTS / "dwellings.json").open(encoding="utf-8") as fh:
        dwell = {str(r["code"]): r["dwellings"] for r in json.load(fh)}

    rows: list[dict] = []
    for code in codes:
        erow = epc.loc[code].to_dict() if code in epc.index else None
        n17 = nrs.loc[code].to_dict() if code in nrs.index else None
        rebuilds = sc.zone_cost_rebuilds(
            code,
            epc_row=erow,
            nrs2017_row=n17,
            estate_row=estate_rows.get(code),
            cfg=cfg,
            band=band,
            valuation_year=base_year,
            defaults=defaults,
        )
        rows.append(
            sc._cost_row(
                code,
                dwell.get(code),
                rebuilds=rebuilds,
                rebuild_status=rebuild_status,
            )
        )
    return rows


def test_agr_defaults_align_with_surface_rebuild_inputs():
    defaults = sc.agr_aligned_defaults()
    assert defaults["default_floor_area_m2"] == 97.0
    assert defaults["default_remaining_factor"] == 0.55


def test_fixture_file_present_with_expected_columns():
    assert FIXTURE.is_file()
    rows = _load_fixture()
    assert len(rows) == 20
    assert list(rows[0]) == list(sc.COST_COLUMNS)
    assert (INPUTS / "epc_dz_rollup.csv").is_file()
    assert (INPUTS / "nrs_dwelling_mix_2011_fallback.csv").is_file()
    assert (INPUTS / "estate_rows.json").is_file()
    assert (INPUTS / "dwellings.json").is_file()


@pytest.mark.skipif(
    not _processed_ready(),
    reason="data/processed gis + datazones + ur lookup required (full-nation only)",
)
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


def test_measured_fixture_costs_match_strict():
    """Recompute costs for the 20 measured DZ2011 codes; strict float equality.

    Always runs in CI via committed fixture inputs (no data/processed skip).
    """
    expected = _load_fixture()
    got_rows = _build_rows_from_fixture_inputs()
    by_code = {r["code"]: r for r in got_rows}
    assert set(by_code) == {r["code"] for r in expected}

    for exp in expected:
        code = exp["code"]
        got = by_code[code]
        assert int(got["dwellings"]) == int(exp["dwellings"]), code
        assert got["rebuild_status"] == exp["rebuild_status"], code
        for k in COST_KEYS:
            e, g = float(exp[k]), float(got[k])
            assert e == g, f"{code} {k}: expected {e!r} got {g!r}"


def test_write_cost_table_round_trip(tmp_path):
    expected = _load_fixture()
    codes = [r["code"] for r in expected]
    rows = _build_rows_from_fixture_inputs()
    out = sc.write_cost_table(rows, tmp_path / "costs.csv")
    with out.open(encoding="utf-8", newline="") as fh:
        written = list(csv.DictReader(fh))
    assert len(written) == 20
    assert written[0]["code"] == codes[0]
    for exp, got in zip(expected, written):
        assert got["code"] == exp["code"]
        for k in COST_KEYS:
            assert float(got[k]) == float(exp[k]), f"{exp['code']} {k}"


def test_na_status_round_trips_via_read_cost_table(tmp_path):
    """FILL-MEASURED-ZERO crash fix: literal n/a must not become NaN."""
    na = sc._na_row("S01010206", 0)
    out = sc.write_cost_table([na], tmp_path / "na_costs.csv")
    got = sc.read_cost_table(out)
    assert got[0]["rebuild_status"] == "n/a"
    assert got[0]["drc_gbp"] is None
