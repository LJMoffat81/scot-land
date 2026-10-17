"""SYNTHETIC dry run. The B2 CLI runs in-process. No market price file."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from georgist.v14_b2 import PIN_TABLE as B2_PINS
from georgist.v14_d7_chain import PIN_TABLE as D7_PINS
from georgist.v14_d7_chain import execute_filter1, execute_filter2, sha256_file
from scripts.build_v14_b2 import B2Error, build
from v14_dryrun.dryrun import FILTERS, _sales_rows, _sold_rows, _write, run


def test_pr2_dryrun_b2_chain(tmp_path: Path) -> None:
    """SYNTHETIC. B2 accepts D7 only through the pinned chain and fits S-x2."""
    result = run(tmp_path)
    assert result["status"] == "passed"
    payload = json.loads(Path(result["out"]).read_text(encoding="utf-8"))
    assert payload["label"] == "SYNTHETIC"
    assert payload["fidelity_adaptation"] == "bedrooms_o_d1"
    assert payload["d7_sha256"]
    assert payload["d7_provenance"]["filter2_output_sha256"] == payload["d7_sha256"]
    assert payload["d7_provenance"]["filter1_script_sha256"] == (
        "849081cdad05aad0a8ed4f84eacdf2bc155af5082d03a0fad459b9777097a564"
    )
    assert payload["d7_provenance"]["filter2_script_sha256"] == (
        "e4b3561b38ad982a6ffa8124156bfdc2ce3fa84ff93fb60c3e82543839dc2f8d"
    )
    assert payload["fit"]["s_x2"] == "fit"


def test_b2_floors_and_fit_rows_drop_source_2024(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. A 2024 source row never becomes a floor or a fit row."""
    sales = tmp_path / "house_sales.csv"
    plots = tmp_path / "plot_split.csv"
    crosswalk = tmp_path / "crosswalk.csv"
    sold = tmp_path / "sold_tfa.csv"
    access = tmp_path / "access.csv"
    bedrooms = tmp_path / "bedrooms.csv"
    out1 = tmp_path / "filter1.csv"
    out2 = tmp_path / "filter2.csv"
    sales_header = [
        "GeographyCode",
        "GeographyName",
        "GeographyType",
        "DateCode",
        "Measurement",
        "Units",
        "Value",
        "Sales",
        "cell",
        "a_m2",
        "ratio_mean",
        "iz",
        "ca",
        "ur3",
        "flat_share",
    ]
    _write(sales, sales_header, _sales_rows())
    _write(plots, ["dz2022_code", "method_flags"], [["Z1", "low_parcel_coverage_lt0.5"]])
    _write(crosswalk, ["dz2011_code", "dz2022_code", "uprn_count"], [["D1", "Z1", "4"]])
    sold_rows = [row + ["SYNTHETIC"] for row in _sold_rows()]
    sold_rows.append(["Z1", "2024", "99", "SYNTHETIC"])
    sold_rows.append(["Z1", "2019-2024", "99", "SYNTHETIC"])
    _write(sold, ["code", "year", "sold_tfa_mean", "label"], sold_rows, comment=False)
    _write(access, ["code", "vintage", "job_access"], [["Z1", "2011", "1.5"]])
    _write(
        bedrooms,
        ["dz2022_code", "households_total", "share_1", "share_3", "share_4plus"],
        [["Z1", "10", "0.5", "0.3", "0.2"]],
    )
    source_text = sold.read_text(encoding="utf-8")
    assert "SYNTHETIC" in source_text
    assert "2024" in source_text
    script1 = FILTERS / "filter1_drop_year_2024.py"
    script2 = FILTERS / "filter2_keep_2019_2023.py"
    saved_d7 = dict(D7_PINS)
    saved_b2 = dict(B2_PINS)
    fitted_years: list[int] = []
    real_fit = build.__globals__["fit_headline"]

    def spy(rows, d7_sha256=None):
        fitted_years.extend(int(row["year"]) for row in rows)
        return real_fit(rows, d7_sha256=d7_sha256)

    monkeypatch.setattr("scripts.build_v14_b2.fit_headline", spy)
    try:
        execute_filter1(script1, sold, out1)
        execute_filter2(script2, out1, out2)
        data_rows = [line for line in out2.read_text(encoding="utf-8").splitlines() if line.strip()][1:]
        D7_PINS["source"] = sha256_file(sold)
        D7_PINS["filter1_output"] = sha256_file(out1)
        D7_PINS["filter2_output"] = sha256_file(out2)
        D7_PINS["row_count"] = len(data_rows)
        B2_PINS["low_parcel_count"] = 1
        B2_PINS["house_sales"] = sha256_file(sales)
        payload = build(
            Namespace(
                house_sales=sales,
                plot_split=plots,
                crosswalk=crosswalk,
                sold_tfa=sold,
                access=access,
                bedrooms=bedrooms,
                filter1_script=script1,
                filter1_output=out1,
                filter2_script=script2,
                filter2_output=out2,
            )
        )
    finally:
        D7_PINS.clear()
        D7_PINS.update(saved_d7)
        B2_PINS.clear()
        B2_PINS.update(saved_b2)
    floor_years = {int(row["year"]) for row in payload["sold_tfa"]}
    fit_years = {int(row["year"]) for row in payload["fit_rows"]}
    assert 2024 not in floor_years
    assert 2024 not in fit_years
    assert 2021 in floor_years
    assert fitted_years
    assert 2024 not in fitted_years


def test_fit_rows_use_filter2_when_source_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. fit_rows take the filter2 floor, not the differing source floor."""
    sales = tmp_path / "house_sales.csv"
    plots = tmp_path / "plot_split.csv"
    crosswalk = tmp_path / "crosswalk.csv"
    sold = tmp_path / "sold_tfa.csv"
    access = tmp_path / "access.csv"
    bedrooms = tmp_path / "bedrooms.csv"
    out1 = tmp_path / "filter1.csv"
    out2 = tmp_path / "filter2.csv"
    sales_header = [
        "GeographyCode",
        "GeographyName",
        "GeographyType",
        "DateCode",
        "Measurement",
        "Units",
        "Value",
        "Sales",
        "cell",
        "a_m2",
        "ratio_mean",
        "iz",
        "ca",
        "ur3",
        "flat_share",
    ]
    _write(sales, sales_header, _sales_rows())
    _write(plots, ["dz2022_code", "method_flags"], [["Z1", "low_parcel_coverage_lt0.5"]])
    _write(crosswalk, ["dz2011_code", "dz2022_code", "uprn_count"], [["D1", "Z1", "4"]])
    source_rows = [row + ["SYNTHETIC"] for row in _sold_rows()]
    source_rows.append(["Z1", "2024", "999", "SYNTHETIC"])
    _write(sold, ["code", "year", "sold_tfa_mean", "label"], source_rows, comment=False)
    filtered = ["code,year,sold_tfa_mean,label"]
    for zone in ("Z1", "Z2", "Z3", "Z4"):
        for year in range(2019, 2024):
            filtered.append(f"{zone},{year},222,SYNTHETIC")
    filtered_text = "\n".join(filtered) + "\n"
    _write(access, ["code", "vintage", "job_access"], [["Z1", "2011", "1.5"]])
    _write(
        bedrooms,
        ["dz2022_code", "households_total", "share_1", "share_3", "share_4plus"],
        [["Z1", "10", "0.5", "0.3", "0.2"]],
    )
    script1 = FILTERS / "filter1_drop_year_2024.py"
    script2 = FILTERS / "filter2_keep_2019_2023.py"
    saved_d7 = dict(D7_PINS)
    saved_b2 = dict(B2_PINS)

    def write_filter2(_script: Path, _source: Path, dest: Path) -> None:
        dest.write_text(filtered_text, encoding="utf-8")

    monkeypatch.setattr("georgist.v14_d7_chain.execute_filter2", write_filter2)
    try:
        execute_filter1(script1, sold, out1)
        write_filter2(script2, out1, out2)
        data_rows = [line for line in filtered_text.splitlines() if line.strip()][1:]
        assert sha256_file(sold) != sha256_file(out2)
        D7_PINS["source"] = sha256_file(sold)
        D7_PINS["filter1_output"] = sha256_file(out1)
        D7_PINS["filter2_output"] = sha256_file(out2)
        D7_PINS["row_count"] = len(data_rows)
        B2_PINS["low_parcel_count"] = 1
        B2_PINS["house_sales"] = sha256_file(sales)
        payload = build(
            Namespace(
                house_sales=sales,
                plot_split=plots,
                crosswalk=crosswalk,
                sold_tfa=sold,
                access=access,
                bedrooms=bedrooms,
                filter1_script=script1,
                filter1_output=out1,
                filter2_script=script2,
                filter2_output=out2,
            )
        )
    finally:
        D7_PINS.clear()
        D7_PINS.update(saved_d7)
        B2_PINS.clear()
        B2_PINS.update(saved_b2)
    assert payload["fit_rows"]
    assert {row["f_m2"] for row in payload["fit_rows"]} == {"222"}
    assert all(int(row["year"]) < 2024 for row in payload["fit_rows"])
    assert all(row["sold_tfa_mean"] == "222" for row in payload["sold_tfa"])
    assert "999" not in {row["sold_tfa_mean"] for row in payload["sold_tfa"]}


def test_house_sales_pin_rejects_shared_eight_character_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. A digest that shares only 702c9ada's width is refused before adapt."""
    sales = tmp_path / "house_sales.csv"
    sales.write_text("# SYNTHETIC\nGeographyCode,DateCode,Value\nS01,2021,1\n", encoding="utf-8")
    actual = sha256_file(sales)
    forged = actual[:8] + ("0" * 56)
    if forged == actual:
        forged = actual[:8] + ("1" * 56)
    assert len(forged) == 64
    assert forged[:8] == actual[:8]
    assert forged != actual
    monkeypatch.setitem(B2_PINS, "house_sales", forged)
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_b2.adapt_house_sales",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    with pytest.raises(B2Error) as raised:
        build(Namespace(house_sales=sales))
    assert str(raised.value) == f"B2_HOUSE_SALES: ERROR: sha256: expected {forged}, got {actual}"
    assert calls["n"] == 0
