"""Data Zones zone_spine `flags`: ONE text column, ';'-separated, '' = no flags.

Read as text (pandas converters={"flags": str}); test membership on the split tokens, never an
exact match; index columns with z["flags"] (z.flags is the pandas DataFrame.flags attribute).
"""

import re

import pandas as pd
import pytest

from georgist.display_views import parse_zone_flags, spine_from_flags, surface_views, zero_dwellings
from paths import PROCESSED_DIR

SPINE = PROCESSED_DIR / "datazones" / "zone_spine.csv"
ZERO = {"S01010206", "S01010226", "S01010227"}
MISMATCH = {"S01011598", "S01010227"}


@pytest.fixture(scope="module")
def spine():
    if not SPINE.is_file():
        pytest.skip("data/processed/datazones not present")
    return pd.read_csv(SPINE, converters={"flags": str})


def _with(z, flag):
    return z[z["flags"].map(lambda s: flag in s.split(";"))]


def test_flags_are_strings_never_nan(spine):
    assert spine["flags"].map(type).eq(str).all()
    assert (spine["flags"] == "").sum() == len(spine) - 7


def test_separator_is_semicolon_and_tokens_are_snake_case(spine):
    tokens = {t for s in spine["flags"] for t in s.split(";") if s}
    assert tokens and all(re.fullmatch(r"[a-z0-9_]+", t) for t in tokens), tokens
    assert not spine["flags"].str.contains(r"[,|]").any()


def test_real_zero_dwellings_and_mismatch_zones(spine):
    zero, mismatch = _with(spine, "zero_dwellings"), _with(spine, "pop_dwellings_mismatch")
    assert set(zero["code"]) == ZERO and set(mismatch["code"]) == MISMATCH
    assert set(zero["vintage"]) == set(mismatch["vintage"]) == {2011}  # join on (code, vintage)
    assert (zero["dwellings"] == 0).all()
    assert set(spine.loc[spine["flags"] != "", "vintage"]) == {2011}  # all 7 flagged rows are 2011


def test_multi_flag_cell_s01010227(spine):
    cell = spine.loc[(spine["code"] == "S01010227") & (spine["vintage"] == 2011), "flags"].item()
    assert cell != "zero_dwellings"  # an exact match would miss it
    assert spine_from_flags(cell) == {"zero_dwellings": True, "pop_dwellings_mismatch": True}
    assert parse_zone_flags(cell) >= {"zero_dwellings", "pop_dwellings_mismatch"}


def test_engine_parser_agrees_with_split_membership(spine):
    for code, vintage, cell in spine[["code", "vintage", "flags"]].itertuples(index=False):
        s = spine_from_flags(cell)
        assert s["zero_dwellings"] == ("zero_dwellings" in cell.split(";")), (code, vintage)
        assert s["pop_dwellings_mismatch"] == ("pop_dwellings_mismatch" in cell.split(";")), (code, vintage)


@pytest.mark.parametrize("cell, zero, mismatch", [
    ("", False, False),
    ("zero_dwellings", True, False),
    ("absent_from_ros_price_file;pop_dwellings_mismatch", False, True),
    ("no_census2022_household_residents;zero_dwellings;pop_dwellings_mismatch", True, True),
    ("not_zero_dwellings", False, False),  # token match, not substring
    (" zero_dwellings ; pop_dwellings_mismatch ", True, True),
])
def test_parse(cell, zero, mismatch):
    assert spine_from_flags(cell) == {"zero_dwellings": zero, "pop_dwellings_mismatch": mismatch}


def test_no_spine_row_is_not_flagged_and_non_text_is_refused():
    assert spine_from_flags(None, present=False) is None and not zero_dwellings(None)
    assert spine_from_flags(None) == {"zero_dwellings": False, "pop_dwellings_mismatch": False}
    with pytest.raises(TypeError):
        parse_zone_flags(float("nan"))


def test_multi_flag_spine_makes_views_not_applicable():
    spine = spine_from_flags("no_census2022_household_residents;zero_dwellings;pop_dwellings_mismatch")
    out = surface_views({"measured_rent": 1000.0, "vintage": 2011, "price_year": 2025}, None, shown=True, spine=spine)
    assert "zero_dwellings" in out["flags"]
    assert all(v["status"] == "not_applicable" and v["value"] is None for v in out["views"].values())
