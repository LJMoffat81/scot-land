"""Harvester tests on SYNTHETIC files written to tmp_path (not real data)."""

import pandas as pd
import pytest

from georgist import surface_harvester as sh


def _ros_csv(path):
    rows = []
    for year, n, mean, med in ((2022, 12, 150000, 140000), (2023, 3, None, None)):
        rows.append(("S01013401", "SYNTHETIC zone 1", "2011 Data Zones", year, "Count", "Number of sales", n, "Number of sales"))
        if mean is not None:
            rows.append(("S01013401", "SYNTHETIC zone 1", "2011 Data Zones", year, "Mean", "Pounds (GBP)", mean, "Price - Mean"))
            rows.append(("S01013401", "SYNTHETIC zone 1", "2011 Data Zones", year, "Median", "Pounds (GBP)", med, "Price - Median"))
    rows.append(("S01013402", "SYNTHETIC zone 2", "2011 Data Zones", 2022, "Median", "Pounds (GBP)", 90000, "Price - Median"))
    cols = ["GeographyCode", "GeographyName", "GeographyType", "DateCode", "Measurement", "Units", "Value", "Sales"]
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False)


def test_ros_long_to_tidy_with_suppression_and_stamp(tmp_path):
    p = tmp_path / "ros_SYNTHETIC.csv"
    _ros_csv(p)
    with pytest.raises(ValueError):
        sh.load_ros_sales(p)  # pinned sha must not match a synthetic file
    df = sh.load_ros_sales(p, expected_sha256=None, licence="synthetic-test-only", synthetic=True)
    z1 = df[df.code == "S01013401"].set_index("year")
    assert z1.loc[2022, "price_mean_gbp"] == 150000 and not z1.loc[2022, "suppressed"]
    assert z1.loc[2023, "suppressed"] and pd.isna(z1.loc[2023, "price_median_gbp"])
    assert z1.loc[2023, "sales_n"] == 3
    z2 = df[df.code == "S01013402"].set_index("year")
    assert z2.loc[2023, "suppressed"]  # absent zone-year made explicit
    prov = df.attrs["provenance"]
    assert prov["synthetic"] and prov["licence"] == "synthetic-test-only"
    assert set(df.vintage) == {2011} and (df.licence == "synthetic-test-only").all()


def _nrs_xlsx(path, sheet, with_type):
    header = ["Data Zone code", "Data zone name", "Council area code", "Council area name",
              "Total number of dwellings", "Dwellings per hectare"] + [f"Council Tax band:\n{b}" for b in "ABCDEFGH"]
    row = ["S01013401", "SYNTHETIC zone 1", "S12999999", "SYNTHETIC council", 500, 12.5] + [60] * 8 + ([] if not with_type else [])
    if with_type:
        header += ["Type of dwelling: Detached", "Type of dwelling: Semidetached", "Number of rooms in dwelling: 7+"]
        row += [100, 200, 20]
    top = [["SYNTHETIC title"], ["SYNTHETIC note"], ["note"], ["Back to contents"]]
    with pd.ExcelWriter(path) as w:
        pd.DataFrame(top + [header, row]).to_excel(w, sheet_name=sheet, header=False, index=False)


@pytest.mark.parametrize("with_type", [False, True])
def test_nrs_loader(tmp_path, with_type):
    p = tmp_path / "nrs_SYNTHETIC.xlsx"
    _nrs_xlsx(p, "2017", with_type)
    df = sh.load_nrs_dwellings(p, year=2017, vintage=2011, licence="synthetic-test-only", synthetic=True)
    assert len(df) == 1 and df.loc[0, "dwellings"] == 500 and df.loc[0, "ct_h"] == 60
    assert bool(df.loc[0, "has_type_rooms"]) is with_type
    if with_type:
        assert df.loc[0, "type_semi_detached"] == 200 and df.loc[0, "rooms_7plus"] == 20
    assert df.attrs["provenance"]["vintage"] == "DZ2011; year 2017 sheet"
    with pytest.raises(ValueError):
        sh.load_nrs_dwellings(p, year=2017, vintage="DZ2001")


def test_urc_loader_cp1252(tmp_path):
    p = tmp_path / "urc_SYNTHETIC.csv"
    text = ("DZ22_Code,DZ22_Name,UR2_Code,UR2_Name,UR3_Code,UR3_Name,UR6_Code,UR6_Name,UR8_Code,UR8_Name\n"
            "S01020801,SYNTHETIC\xa0zone,2,Rural,3,Rural,6,Remote Rural,8,Very Remote Rural\n")
    p.write_bytes(text.encode("cp1252"))
    df = sh.load_urban_rural_lookup(p, licence="synthetic-test-only", synthetic=True)
    assert df.loc[0, "ur6_class"] == 6 and df.loc[0, "vintage"] == 2022
    assert df.attrs["provenance"]["synthetic"]


def _hpi_csv(path, months=range(1, 13), year=2023, extra_target=True):
    """SYNTHETIC UK HPI-shaped file: one council, flat 2023, +10% (all) by Apr 2025."""
    cols = ["Date", "RegionName", "AreaCode", "AveragePrice", "Index"]
    for t in ("Detached", "SemiDetached", "Terraced", "Flat"):
        cols += [f"{t}Price", f"{t}Index"]
    rows = []
    for m in months:
        rows.append([f"01/{m:02d}/{year}", "SYNTHETIC council", "S12999999", 200000, 100.0,
                     400000, 100.0, 250000, 100.0, 180000, 100.0, 120000, 100.0])
    if extra_target:
        rows.append(["01/04/2025", "SYNTHETIC council", "S12999999", 220000, 110.0,
                     440000, 110.0, 270000, 108.0, 190000, 105.0, 130000, 104.0])
    rows.append(["01/04/2025", "England", "E92000001", 1, 1.0, 1, 1.0, 1, 1.0, 1, 1.0, 1, 1.0])
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False)


def test_uk_hpi_loader_and_points(tmp_path):
    p = tmp_path / "hpi_SYNTHETIC.csv"
    _hpi_csv(p)
    with pytest.raises(ValueError):
        sh.load_uk_hpi(p)  # pinned sha must not match a synthetic file
    df = sh.load_uk_hpi(p, expected_sha256=None, licence="synthetic-test-only", synthetic=True)
    assert set(df.council_code) == {"S12999999"}  # S12 councils only
    pts = sh.council_hpi_points(df, base_year=2023, target_month="2025-04")
    h = pts["S12999999"]
    assert h.base_index["all"] == 100.0 and h.target_index["detached"] == 110.0 and h.base_price["flat"] == 120000
    short = tmp_path / "hpi_short_SYNTHETIC.csv"
    _hpi_csv(short, months=range(1, 12))
    with pytest.raises(ValueError):  # an incomplete base year is refused, never filled
        sh.council_hpi_points(sh.load_uk_hpi(short, expected_sha256=None), base_year=2023, target_month="2025-04")
