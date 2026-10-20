"""V14-SPEC-A2a: AM-2 / CO-1 / DZ2011 filter / n_sales from Count / fit-year leak.

SYNTHETIC fixtures only. No 2024 prices. No real house_sales. £ flag stays off.
A2a scope: T1-T7, T9-T15, T21, T25(a/b via adapt + build_v14_b2.main), T3m/T11m/T12m.
"""

from __future__ import annotations

import csv
import io
from argparse import Namespace
from pathlib import Path

import pytest

from georgist.v14_b2 import (
    B2Error,
    HOUSE_SALES_HEADERS,
    HOUSE_SALES_MEASUREMENT_LABELS,
    adapt_house_sales,
    read_value_cell,
)
from georgist.v14_d7_chain import D7ChainResult
from scripts.build_v14_b2 import _fit_rows, assert_fit_years, build, main

SENTINEL = "SENTINEL_7Q"
INCOMPLETE = (
    "B2_HOUSE_SALES: ERROR: measurement: expected Count, Mean, Median, "
    "Lower Quartile, Upper Quartile, got incomplete"
)
ZONE = "S01006506"
ZONE_HI = "S01013481"
MEASURES = ("Count", "Mean", "Median", "Lower Quartile", "Upper Quartile")


def _header() -> list[str]:
    return list(HOUSE_SALES_HEADERS)


def _row(
    zone: str,
    year: int,
    label: str,
    value: str,
    *,
    geo: str = "2011 Data Zones",
    units: str | None = None,
    sales: str = "Number of sales",
) -> list[str]:
    if units is None:
        units = "Number of sales" if label == "Count" else "GBP"
    return [
        zone,
        "SYNTHETIC zone",
        geo,
        str(year),
        label,
        units,
        value,
        sales if label == "Count" else "Price - Mean",
    ]


def _complete(
    zone: str,
    year: int,
    *,
    count: str = "6",
    mean: str = "10",
    median: str = "9",
    geo: str = "2011 Data Zones",
) -> list[list[str]]:
    rows = []
    values = {
        "Count": count,
        "Mean": mean,
        "Median": median,
        "Lower Quartile": "8",
        "Upper Quartile": "12",
    }
    for label in MEASURES:
        rows.append(_row(zone, year, label, values[label], geo=geo))
    return rows


def _write(path: Path, rows: list[list[str]], header: list[str] | None = None) -> Path:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header if header is not None else _header())
    writer.writerows(rows)
    path.write_text("# SYNTHETIC\n" + buf.getvalue(), encoding="utf-8")
    return path


def _value_spy(monkeypatch: pytest.MonkeyPatch) -> dict:
    calls = {"n": 0, "values": []}

    def spy(value: str) -> str:
        calls["n"] += 1
        calls["values"].append(value)
        return value

    monkeypatch.setattr("georgist.v14_b2.read_value_cell", spy)
    return calls


def _fit_spy(monkeypatch: pytest.MonkeyPatch) -> dict:
    calls = {"n": 0, "rows": []}

    def spy(rows, d7_sha256=None):
        calls["n"] += 1
        calls["rows"] = list(rows)
        return {
            "sensitivities": [{"id": "S-x2", "status": "fit"}],
        }

    monkeypatch.setattr("scripts.build_v14_b2.fit_headline", spy)
    return calls


def _stub_build(monkeypatch: pytest.MonkeyPatch, sales: Path) -> Namespace:
    monkeypatch.setattr("scripts.build_v14_b2.assert_house_sales_pin", lambda _p: None)
    monkeypatch.setattr(
        "scripts.build_v14_b2.adapt_plot_split",
        lambda *_a, **_k: [{"code": "Z1", "low_parcel_coverage": 0, "method_flags": "x"}],
    )
    monkeypatch.setattr(
        "scripts.build_v14_b2.adapt_crosswalk",
        lambda *_a, **_k: [{"dz2011": "D1", "dz2022": "Z1", "uprn_count": "1"}],
    )
    monkeypatch.setattr(
        "scripts.build_v14_b2.adapt_access",
        lambda *_a, **_k: [{"zone": "Z1", "job_access": "1.5", "vintage": "2011"}],
    )
    monkeypatch.setattr(
        "scripts.build_v14_b2.adapt_bedrooms",
        lambda *_a, **_k: {"rows": []},
    )
    monkeypatch.setattr(
        "scripts.build_v14_b2.run_d7_chain",
        lambda **_k: D7ChainResult(
            status="passed",
            d7_sha256="a" * 64,
            message="",
            manifest={},
        ),
    )
    monkeypatch.setattr(
        "scripts.build_v14_b2.adapt_sold_tfa",
        lambda *_a, **_k: [
            {"zone": ZONE, "year": 2021, "sold_tfa_mean": "50"},
            {"zone": ZONE, "year": 2022, "sold_tfa_mean": "50"},
            {"zone": "ZB", "year": 2021, "sold_tfa_mean": "50"},
            {"zone": "ZB", "year": 2022, "sold_tfa_mean": "50"},
            {"zone": "Z1", "year": 2019, "sold_tfa_mean": "50"},
            {"zone": "Z1", "year": 2021, "sold_tfa_mean": "50"},
            {"zone": "Z1", "year": 2022, "sold_tfa_mean": "50"},
            {"zone": "Z1", "year": 2023, "sold_tfa_mean": "50"},
        ],
    )
    return Namespace(
        house_sales=sales,
        plot_split=Path("x"),
        crosswalk=Path("x"),
        sold_tfa=Path("x"),
        access=Path("x"),
        bedrooms=Path("x"),
        filter1_script=Path("x"),
        filter1_output=Path("x"),
        filter2_script=Path("x"),
        filter2_output=Path("x"),
    )


def _main_argv(out: Path, sales: Path) -> list[str]:
    return [
        "--out",
        str(out),
        "--house-sales",
        str(sales),
        "--plot-split",
        "x",
        "--crosswalk",
        "x",
        "--sold-tfa",
        "x",
        "--access",
        "x",
        "--bedrooms",
        "x",
        "--filter1-script",
        "x",
        "--filter1-output",
        "x",
        "--filter2-script",
        "x",
        "--filter2-output",
        "x",
    ]


def _run_main_refuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    rows: list[list[str]],
    message: str,
) -> None:
    sales = _write(tmp_path / "house_sales.csv", rows)
    out = tmp_path / "b2.json"
    monkeypatch.setattr("scripts.build_v14_b2.assert_house_sales_pin", lambda _p: None)
    rc = main(_main_argv(out, sales))
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err == message + "\n"
    assert not out.exists()


# --- T1 suppressed accepted ---


def test_t1_suppressed_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T1: Count 3 only -> excluded suppressed_price; spy 0."""
    path = _write(tmp_path / "h.csv", [_row(ZONE, 2023, "Count", "3")])
    calls = _value_spy(monkeypatch)
    am2: dict = {}
    rows = adapt_house_sales(path, am2=am2)
    assert rows == []
    assert am2["excluded"] == [
        {"zone": ZONE, "year": 2023, "reason": "suppressed_price", "count": 3}
    ]
    assert calls["n"] == 0


# --- T2 no_sales ---


def test_t2_no_sales(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T2: Count 0 only -> no_sales."""
    path = _write(tmp_path / "h.csv", [_row(ZONE, 2023, "Count", "0")])
    calls = _value_spy(monkeypatch)
    am2: dict = {}
    rows = adapt_house_sales(path, am2=am2)
    assert rows == []
    assert am2["excluded"] == [
        {"zone": ZONE, "year": 2023, "reason": "no_sales", "count": 0}
    ]
    assert calls["n"] == 0


# --- T3 Count >=5 no prices ---


def test_t3_count_ge5_no_prices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T3: Count 5 alone refuses; count value never printed; spy 0."""
    path = _write(tmp_path / "h.csv", [_row(ZONE, 2023, "Count", "5")])
    calls = _value_spy(monkeypatch)
    msg = (
        f"B2_HOUSE_SALES: ERROR: am2 {ZONE} 2023: expected Count 0-4 with no "
        "price measures, got Count >=5"
    )
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == msg
    assert "got Count >=5" in str(raised.value)
    assert calls["n"] == 0


def test_t3m_count_ge5_via_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T3m: T3 through build_v14_b2.main; rc 1; b2.json absent."""
    msg = (
        f"B2_HOUSE_SALES: ERROR: am2 {ZONE} 2023: expected Count 0-4 with no "
        "price measures, got Count >=5"
    )
    _run_main_refuse(tmp_path, monkeypatch, capsys, [_row(ZONE, 2023, "Count", "5")], msg)


# --- T4 partial measures ---


@pytest.mark.parametrize(
    "labels",
    [
        ("Count", "Mean"),
        ("Count", "Mean", "Median"),
        ("Mean",),
        ("Count", "Mean", "Median", "Lower Quartile"),
    ],
)
def test_t4_partial_measures(tmp_path: Path, labels: tuple[str, ...]) -> None:
    """T4: partial measure sets refuse incomplete (Mean+Median alone is red on fix)."""
    rows = []
    for label in labels:
        rows.append(_row(ZONE, 2023, label, "6" if label == "Count" else "10"))
    path = _write(tmp_path / "h.csv", rows)
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == INCOMPLETE


# --- T5 non-integer Count ---


@pytest.mark.parametrize("bad", ["4.0", "-1", "x", "1e3", "True", "٣"])
def test_t5_non_integer_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    """T5: non-integer Count refuses; cell text never printed; spy 0."""
    path = _write(tmp_path / "h.csv", [_row(ZONE, 2023, "Count", bad)])
    calls = _value_spy(monkeypatch)
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == (
        "B2_HOUSE_SALES: ERROR: count row 1: expected integer >=0, got non-integer"
    )
    # Cell text must not appear as the refused value (fixed words only).
    assert str(raised.value).endswith("got non-integer")
    assert f"got {bad}" not in str(raised.value)
    assert calls["n"] == 0


def test_t5b_blank_count(tmp_path: Path) -> None:
    """T5b: blank Count uses existing _require_value blank message."""
    path = _write(tmp_path / "h.csv", [_row(ZONE, 2023, "Count", "")])
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == (
        "B2_HOUSE_SALES: ERROR: Value row 1: expected value, got blank"
    )


# --- T6 duplicate measure (TE gap: red-first) ---


def test_t6_duplicate_measure(tmp_path: Path) -> None:
    """T6: two Count rows refuse duplicate."""
    path = _write(
        tmp_path / "h.csv",
        [
            _row(ZONE, 2023, "Count", "3"),
            _row(ZONE, 2023, "Count", "2"),
        ],
    )
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == (
        "B2_HOUSE_SALES: ERROR: measurement row 2: expected one Count "
        "per zone-year, got duplicate"
    )


# --- T7 weights/shrinkage ignore Count-only ---


def test_t7_fit_ignores_count_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T7: Count-only Z-B never reaches fit_headline; n_sales from Count Value."""
    rows = []
    rows.extend(_complete(ZONE, 2021, count="7"))
    rows.extend(_complete(ZONE, 2022, count="8"))
    rows.append(_row("ZB", 2021, "Count", "3"))
    rows.append(_row("ZB", 2022, "Count", "2"))
    sales = _write(tmp_path / "h.csv", rows)
    args = _stub_build(monkeypatch, sales)
    fit = _fit_spy(monkeypatch)
    payload = build(args)
    assert fit["n"] == 1
    zones = {row["zone"] for row in fit["rows"]}
    assert ZONE in zones
    assert "ZB" not in zones
    for row in fit["rows"]:
        assert "price" in row
        assert "median_price" in row
        assert "n_sales" in row
    by_year = {int(row["year"]): row["n_sales"] for row in fit["rows"] if row["zone"] == ZONE}
    assert by_year[2021] == "7"
    assert by_year[2022] == "8"
    assert "am2" in payload
    assert any(item["zone"] == "ZB" for item in payload["am2"]["excluded"])


# --- T9 fit-window exclusion (TE gap: red-first) ---


def test_t9_fit_window_exclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T9: Count-only 2021-22 + complete 2019 -> no fit row; zone in fit_window list."""
    rows = []
    rows.extend(_complete("Z1", 2019, count="6"))
    rows.append(_row("Z1", 2021, "Count", "3"))
    rows.append(_row("Z1", 2022, "Count", "2"))
    sales = _write(tmp_path / "h.csv", rows)
    args = _stub_build(monkeypatch, sales)
    fit = _fit_spy(monkeypatch)
    payload = build(args)
    assert all(row["zone"] != "Z1" or int(row["year"]) not in (2021, 2022) for row in fit["rows"])
    assert "Z1" not in {row["zone"] for row in fit["rows"]}
    assert "Z1" in payload["am2"]["fit_window_no_complete_row"]


# --- T10 IZ filter ---


def test_t10_iz_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T10: IZ rows skipped; only DZ Value cells read."""
    rows = []
    rows.append(_row("IZ01", 2023, "Count", "3", geo="2011 Intermediate Zones"))
    rows.extend(_complete("IZ02", 2023, geo="2011 Intermediate Zones"))
    rows.extend(_complete(ZONE, 2023))
    path = _write(tmp_path / "h.csv", rows)
    calls = _value_spy(monkeypatch)
    am2: dict = {}
    out = adapt_house_sales(path, am2=am2)
    assert len(out) == 1
    assert out[0]["zone"] == ZONE
    assert all(item["zone"] != "IZ01" and item["zone"] != "IZ02" for item in am2["excluded"])
    assert "IZ01" not in am2["zones_present"]
    assert "IZ02" not in am2["zones_present"]
    assert am2["skipped_geography"]["2011 Intermediate Zones"] == 6
    # Mean + Median for the one DZ complete row
    assert calls["n"] == 2
    assert SENTINEL not in "".join(calls["values"])


# --- T11 unknown geography (TE gap: red-first) ---


def test_t11_unknown_geography(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T11: 2022 Data Zones refuse geography; spy 0."""
    path = _write(
        tmp_path / "h.csv",
        [_row(ZONE, 2023, "Count", "6", geo="2022 Data Zones")],
    )
    calls = _value_spy(monkeypatch)
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == (
        "B2_HOUSE_SALES: ERROR: geography row 1: expected 2011 Data Zones, got other type"
    )
    assert calls["n"] == 0


def test_t11m_unknown_geography_via_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T11m: T11 through build_v14_b2.main."""
    msg = "B2_HOUSE_SALES: ERROR: geography row 1: expected 2011 Data Zones, got other type"
    _run_main_refuse(
        tmp_path,
        monkeypatch,
        capsys,
        [_row(ZONE, 2023, "Count", "6", geo="2022 Data Zones")],
        msg,
    )


# --- T12 code range (TE gap: red-first) ---


def test_t12_code_range_edges(tmp_path: Path) -> None:
    """T12: S01013482 / S01006505 refuse; edges and short SYNTHETIC accepted."""
    for code, expect_got in (("S01013482", "S01013482"), ("S01006505", "S01006505")):
        path = _write(tmp_path / f"{code}.csv", _complete(code, 2023))
        with pytest.raises(B2Error) as raised:
            adapt_house_sales(path)
        assert str(raised.value) == (
            f"B2_HOUSE_SALES: ERROR: vintage row 1: expected S01006506-S01013481, "
            f"got {expect_got}"
        )
    for code in (ZONE, ZONE_HI, "Z1"):
        path = _write(tmp_path / f"ok_{code}.csv", _complete(code, 2023))
        am2: dict = {}
        rows = adapt_house_sales(path, am2=am2)
        assert len(rows) == 1
        assert rows[0]["zone"] == code


def test_t12m_code_range_via_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T12m: out-of-range via build_v14_b2.main."""
    msg = (
        "B2_HOUSE_SALES: ERROR: vintage row 1: expected S01006506-S01013481, "
        "got S01013482"
    )
    _run_main_refuse(
        tmp_path, monkeypatch, capsys, _complete("S01013482", 2023), msg
    )


# --- T13 n_sales from Count Value ---


def test_t13_n_sales_from_count_value(tmp_path: Path) -> None:
    """T13: Count Value 7, Sales label -> n_sales == '7'."""
    rows = _complete(ZONE, 2021, count="7")
    # Ensure Sales column is the unit label, not the count.
    for row in rows:
        if row[4] == "Count":
            row[7] = "Number of sales"
        else:
            row[7] = "Price - Mean"
    path = _write(tmp_path / "h.csv", rows)
    out = adapt_house_sales(path)
    assert out[0]["n_sales"] == "7"


# --- T14 leak guard ---


def test_t14_fit_rows_only_2021_2022() -> None:
    """T14: _fit_rows drops years outside FIT_YEARS."""
    sales = [
        {"zone": "Z1", "year": 2019, "price": "1", "median_price": "1", "n_sales": "6"},
        {"zone": "Z1", "year": 2021, "price": "1", "median_price": "1", "n_sales": "6"},
        {"zone": "Z1", "year": 2022, "price": "1", "median_price": "1", "n_sales": "6"},
        {"zone": "Z1", "year": 2023, "price": "1", "median_price": "1", "n_sales": "6"},
    ]
    floors = [
        {"zone": "Z1", "year": y, "sold_tfa_mean": "50"}
        for y in (2019, 2021, 2022, 2023)
    ]
    built = _fit_rows(sales, floors)
    assert {int(row["year"]) for row in built} == {2021, 2022}


# --- T15 leak refusal ---


def test_t15_assert_fit_years_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T15: 2023 row past _fit_rows refuses; fit_headline spy 0."""
    rows = _complete(ZONE, 2021)
    sales = _write(tmp_path / "h.csv", rows)
    args = _stub_build(monkeypatch, sales)
    fit = _fit_spy(monkeypatch)

    def leak(_sales, _floors):
        return [
            {
                "zone": ZONE,
                "year": 2023,
                "price": "1",
                "median_price": "1",
                "n_sales": "6",
                "f_m2": "50",
            }
        ]

    monkeypatch.setattr("scripts.build_v14_b2._fit_rows", leak)
    with pytest.raises(B2Error) as raised:
        build(args)
    assert str(raised.value) == (
        "B2_FIT_ROWS: REFUSED: year: expected 2021-2022, got 2023"
    )
    assert fit["n"] == 0


def test_assert_fit_years_helper_direct() -> None:
    """assert_fit_years reads only year."""
    assert_fit_years([{"year": 2021}, {"year": 2022}])
    with pytest.raises(B2Error) as raised:
        assert_fit_years([{"year": 2023}])
    assert str(raised.value) == (
        "B2_FIT_ROWS: REFUSED: year: expected 2021-2022, got 2023"
    )


# --- T21 entry points ---


def test_t21_entry_points_adapt_and_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T21: T1/T3/T11 via adapt and main share outcomes."""
    # T1 via adapt already covered; via main: pin stub + adapt success path needs full build.
    path = _write(tmp_path / "t1.csv", [_row(ZONE, 2023, "Count", "3")])
    am2: dict = {}
    assert adapt_house_sales(path, am2=am2) == []
    assert am2["excluded"][0]["reason"] == "suppressed_price"

    msg = (
        f"B2_HOUSE_SALES: ERROR: am2 {ZONE} 2023: expected Count 0-4 with no "
        "price measures, got Count >=5"
    )
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(_write(tmp_path / "t3.csv", [_row(ZONE, 2023, "Count", "5")]))
    assert str(raised.value) == msg
    _run_main_refuse(tmp_path, monkeypatch, capsys, [_row(ZONE, 2023, "Count", "5")], msg)


# --- T25 SENTINEL (TE gap: red-first) ---


def test_t25a_sentinel_in_count_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T25(a): SENTINEL_7Q in Count Value never appears in streams or exception."""
    rows = [_row(ZONE, 2023, "Count", SENTINEL)]
    path = _write(tmp_path / "h.csv", rows)
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert SENTINEL not in str(raised.value)
    assert str(raised.value) == (
        "B2_HOUSE_SALES: ERROR: count row 1: expected integer >=0, got non-integer"
    )
    out = tmp_path / "b2.json"
    monkeypatch.setattr("scripts.build_v14_b2.assert_house_sales_pin", lambda _p: None)
    rc = main(_main_argv(out, path))
    captured = capsys.readouterr()
    assert rc == 1
    assert SENTINEL not in captured.out
    assert SENTINEL not in captured.err
    assert not out.exists()


def test_t25b_sentinel_in_mean_of_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T25(b): SENTINEL in Mean of complete set with duplicate Mean; absent from streams."""
    rows = _complete(ZONE, 2023, mean=SENTINEL)
    # Force duplicate Mean refusal (second Mean row).
    rows.append(_row(ZONE, 2023, "Mean", SENTINEL))
    path = _write(tmp_path / "h.csv", rows)
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert SENTINEL not in str(raised.value)
    assert "got duplicate" in str(raised.value)
    out = tmp_path / "b2.json"
    monkeypatch.setattr("scripts.build_v14_b2.assert_house_sales_pin", lambda _p: None)
    rc = main(_main_argv(out, path))
    captured = capsys.readouterr()
    assert rc == 1
    assert SENTINEL not in captured.out
    assert SENTINEL not in captured.err
    assert not out.exists()


def test_labels_constant_unchanged() -> None:
    """House sales measurement labels stay the five AM-2 measures."""
    assert HOUSE_SALES_MEASUREMENT_LABELS == MEASURES
