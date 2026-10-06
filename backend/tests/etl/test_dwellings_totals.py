"""Data Zones dwellings totals per zone version, and GIS residential land joined to them.

Each zone version is checked against ITS OWN NRS 2025 total. The two versions differ (the 2022
zones carry 53 fewer dwellings), so they are never asserted equal.
"""

import pandas as pd
import pytest

from paths import PROCESSED_DIR

NRS_2025_TOTAL = {2011: 2_757_376, 2022: 2_757_323}
DBY = PROCESSED_DIR / "datazones" / "dwellings_by_year.csv"
RES = PROCESSED_DIR / "gis" / "dz_residential_land.csv"


@pytest.fixture(scope="module")
def dby2025():
    if not DBY.is_file():
        pytest.skip("data/processed/datazones not present")
    d = pd.read_csv(DBY, usecols=["code", "vintage", "count_year", "dwellings_total"])
    return d[d["count_year"] == 2025]


@pytest.mark.parametrize("vintage", [2011, 2022])
def test_each_vintage_matches_its_own_nrs_2025_total(dby2025, vintage):
    assert int(dby2025.loc[dby2025["vintage"] == vintage, "dwellings_total"].sum()) == NRS_2025_TOTAL[vintage]


def test_residential_land_dwellings_match_data_zones_on_every_row(dby2025):
    if not RES.is_file():
        pytest.skip("gis/dz_residential_land.csv not present")
    res = pd.read_csv(RES, usecols=["code", "vintage", "dwellings_total_2025"])
    j = res.merge(dby2025, on=["code", "vintage"], how="left", validate="one_to_one")
    assert len(j) == 14_368 and j["dwellings_total"].notna().all()
    assert (j["dwellings_total_2025"] == j["dwellings_total"]).all()
