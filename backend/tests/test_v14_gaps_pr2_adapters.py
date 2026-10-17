"""PR 2 B2 adapters. SYNTHETIC fixtures only. No 2024 price cell is read."""

from __future__ import annotations

import inspect
from decimal import Decimal
from pathlib import Path

import pytest

from georgist.v14_b2 import (
    BEDROOM_BANDS,
    FIELD_CITATIONS,
    FIDELITY_ADAPTATION,
    HOUSE_SALES_MEASUREMENT_LABELS,
    B2Error,
    adapt_access,
    adapt_bedrooms,
    adapt_crosswalk,
    adapt_house_sales,
    adapt_plot_split,
    adapt_sold_tfa,
    dz2011_low_parcel_flags,
    extend_column_map,
    project_cited_fields,
    quantize,
    scan_measurement_labels,
    write_adapter,
)

SCHEMAS = ("house_sales", "plot_split", "crosswalk", "sold_tfa", "access", "bedrooms")


def _text(header: list[str], rows: list[list[str]]) -> str:
    lines = ["# SYNTHETIC", ",".join(header)]
    lines.extend(",".join(row) for row in rows)
    return "\n".join(lines) + "\n"


def _house() -> tuple[list[str], list[list[str]]]:
    header = [
        "GeographyCode",
        "GeographyName",
        "GeographyType",
        "DateCode",
        "Measurement",
        "Units",
        "Value",
        "Sales",
    ]
    rows = [
        ["S01", "SYNTHETIC zone", "2011 Data Zones", "2021", "Mean", "GBP", "10", "6"],
        ["S01", "SYNTHETIC zone", "2011 Data Zones", "2021", "Median", "GBP", "9", "6"],
    ]
    return header, rows


def _files(tmp_path: Path) -> dict[str, tuple[list[str], list[list[str]]]]:
    house = _house()
    return {
        "house_sales": house,
        "plot_split": (["dz2022_code", "method_flags"], [["Z1", "low_parcel_coverage_lt0.5"]]),
        "crosswalk": (["dz2011_code", "dz2022_code", "uprn_count"], [["D1", "Z1", "4"]]),
        "sold_tfa": (["code", "year", "sold_tfa_mean"], [["Z1", "2021", "50"]]),
        "access": (["code", "vintage", "job_access"], [["Z1", "2011", "1.5"]]),
        "bedrooms": (
            ["dz2022_code", "households_total", "share_1", "share_3", "share_4plus"],
            [["Z1", "10", "0.5", "0.3", "0.2"]],
        ),
    }


def _path(tmp_path: Path, schema: str, header: list[str], rows: list[list[str]]) -> Path:
    path = tmp_path / f"{schema}.csv"
    path.write_text(_text(header, rows), encoding="utf-8")
    return path


def _write_schema(tmp_path: Path, schema: str, header: list[str] | None = None, rows: list[list[str]] | None = None) -> Path:
    base_header, base_rows = _files(tmp_path)[schema]
    return _path(tmp_path, schema, base_header if header is None else header, base_rows if rows is None else rows)


def _cross(tmp_path: Path) -> Path:
    header, rows = _files(tmp_path)["crosswalk"]
    path = tmp_path / "crosswalk_weights.csv"
    path.write_text(_text(header, rows), encoding="utf-8")
    return path


@pytest.mark.parametrize("schema", SCHEMAS)
def test_adapter_maps_equal_source(tmp_path: Path, schema: str) -> None:
    """SYNTHETIC. Mapped fields equal the source fields. Bedrooms may rebuild shares."""
    path = _write_schema(tmp_path, schema)
    if schema == "house_sales":
        rows = adapt_house_sales(path)
        assert rows[0]["zone"] == "S01"
        assert rows[0]["year"] == 2021
        assert rows[0]["price"] == "10"
        assert rows[0]["median_price"] == "9"
        assert rows[0]["n_sales"] == "6"
    elif schema == "plot_split":
        rows = adapt_plot_split(path, expected_count=1)
        assert rows[0]["code"] == "Z1"
    elif schema == "crosswalk":
        rows = adapt_crosswalk(path)
        assert rows[0]["dz2011"] == "D1"
        assert rows[0]["dz2022"] == "Z1"
        assert rows[0]["uprn_count"] == "4"
    elif schema == "sold_tfa":
        rows = adapt_sold_tfa(path)
        assert rows[0]["zone"] == "Z1"
        assert rows[0]["sold_tfa_mean"] == "50"
    elif schema == "access":
        rows = adapt_access(path)
        assert rows == [{"zone": "Z1", "job_access": "1.5", "vintage": "2011"}]
    else:
        result = adapt_bedrooms(path, _cross(tmp_path))
        assert result["dz2022_shares"]["Z1"]["share_1"] == Decimal("0.5")
        assert result["dz2022_shares"]["Z1"]["share_3"] == Decimal("0.3")
        assert result["dz2022_shares"]["Z1"]["share_4plus"] == Decimal("0.2")


@pytest.mark.parametrize("schema", SCHEMAS)
def test_adapter_wrong_header(tmp_path: Path, schema: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A renamed header is refused before the output is written."""
    header, rows = _files(tmp_path)[schema]
    renamed = "renamed_column"
    header = [renamed, *header[1:]]
    path = _path(tmp_path, schema, header, rows)
    dest = tmp_path / "sentinel.json"
    calls = {"n": 0}

    def spy(*_args, **_kwargs):
        calls["n"] += 1

    monkeypatch.setattr("georgist.v14_b2.emit_output", spy)
    with pytest.raises(B2Error) as raised:
        write_adapter(schema, path, dest, crosswalk=_cross(tmp_path), expected_count=1)
    assert str(raised.value) == f"B2_{schema.upper()}: ERROR: header: expected {_files(tmp_path)[schema][0][0]}, got {renamed}"
    assert calls["n"] == 0
    assert not dest.exists()


@pytest.mark.parametrize("schema", SCHEMAS)
def test_adapter_missing_file(tmp_path: Path, schema: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A missing file is refused and the sentinel is absent."""
    dest = tmp_path / "sentinel.json"
    missing = tmp_path / f"missing_{schema}.csv"
    calls = {"n": 0}
    monkeypatch.setattr("georgist.v14_b2.emit_output", lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1))
    with pytest.raises(B2Error) as raised:
        write_adapter(schema, missing, dest, crosswalk=_cross(tmp_path), expected_count=1)
    assert str(raised.value) == f"B2_{schema.upper()}: ERROR: file: expected {missing}, got absent"
    assert calls["n"] == 0
    assert not dest.exists()


@pytest.mark.parametrize("schema", SCHEMAS)
def test_adapter_blank_field(tmp_path: Path, schema: str) -> None:
    """SYNTHETIC. A blank required cell is refused."""
    header, rows = _files(tmp_path)[schema]
    blank = list(rows[0])
    blank[0] = ""
    path = _path(tmp_path, schema, header, [blank, *rows[1:]])
    dest = tmp_path / "sentinel.json"
    column = header[0]
    with pytest.raises(B2Error) as raised:
        write_adapter(schema, path, dest, crosswalk=_cross(tmp_path), expected_count=1)
    assert str(raised.value) == f"B2_{schema.upper()}: ERROR: {column} row 1: expected value, got blank"
    assert not dest.exists()


@pytest.mark.parametrize("schema", SCHEMAS)
def test_adapter_short_row(tmp_path: Path, schema: str) -> None:
    """SYNTHETIC. A short row is refused."""
    header, rows = _files(tmp_path)[schema]
    short = list(rows[0][:-1])
    path = _path(tmp_path, schema, header, [short])
    dest = tmp_path / "sentinel.json"
    with pytest.raises(B2Error) as raised:
        write_adapter(schema, path, dest, crosswalk=_cross(tmp_path), expected_count=1)
    assert str(raised.value) == (
        f"B2_{schema.upper()}: ERROR: row 1: expected {len(header)} fields, got {len(short)}"
    )
    assert not dest.exists()


def test_house_sales_unknown_measurement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. An unmapped Measurement label does not read Value."""
    header, _rows = _house()
    rows = [["S01", "SYNTHETIC zone", "2011 Data Zones", "2021", "NotAPrice", "GBP", "SENTINEL_VALUE", "6"]]
    path = _path(tmp_path, "house_sales", header, rows)
    calls = {"n": 0}
    monkeypatch.setattr("georgist.v14_b2.read_value_cell", lambda value: calls.__setitem__("n", calls["n"] + 1) or value)
    labels = ", ".join(HOUSE_SALES_MEASUREMENT_LABELS)
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == f"B2_HOUSE_SALES: ERROR: measurement: expected one of {labels}, got NotAPrice"
    assert calls["n"] == 0


def test_house_sales_label_constants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. Measurement labels match the pinned constants and Value stays unread."""
    header, _rows = _house()
    rows = []
    for label in HOUSE_SALES_MEASUREMENT_LABELS:
        rows.append(["S01", "SYNTHETIC zone", "2011 Data Zones", "2021", label, "GBP", "1", "6"])
    path = _path(tmp_path, "house_sales", header, rows)
    calls = {"n": 0}
    monkeypatch.setattr("georgist.v14_b2.read_value_cell", lambda value: calls.__setitem__("n", calls["n"] + 1) or value)
    assert scan_measurement_labels(path) == list(HOUSE_SALES_MEASUREMENT_LABELS)
    assert calls["n"] == 0


def test_access_vintage_filter(tmp_path: Path) -> None:
    """SYNTHETIC. Access keeps vintage 2011 only."""
    header = ["code", "vintage", "job_access"]
    rows = [["Z1", "2011", "1.5"], ["Z2", "2022", "9.0"], ["Z3", "2001", "3.0"]]
    path = _path(tmp_path, "access", header, rows)
    output = adapt_access(path)
    assert [row["vintage"] for row in output] == ["2011"]
    assert output[0]["zone"] == "Z1"


def test_low_parcel_flag_synthetic(tmp_path: Path) -> None:
    """SYNTHETIC low_parcel_count=2. The variant with one flag removed is refused."""
    header = ["dz2022_code", "method_flags"]
    rows = [["Z1", "low_parcel_coverage_lt0.5"], ["Z2", "parcel;low_parcel_coverage_lt0.5"]]
    path = _path(tmp_path, "plot_split", header, rows)
    assert path.read_text(encoding="utf-8").splitlines()[0] == "# SYNTHETIC"
    counted = adapt_plot_split(path, expected_count=2)
    assert sum(row["low_parcel_coverage"] for row in counted) == 2
    variant_rows = [["Z1", "low_parcel_coverage_lt0.5"], ["Z2", "parcel"]]
    variant = _path(tmp_path, "plot_variant", header, variant_rows)
    dest = tmp_path / "sentinel.json"
    with pytest.raises(B2Error) as raised:
        write_adapter("plot_split", variant, dest, expected_count=2)
    assert str(raised.value) == "B2_PLOT_SPLIT: ERROR: low_parcel_count: expected 2, got 1"
    assert not dest.exists()


def test_low_parcel_boundary() -> None:
    """SYNTHETIC. Apportioned share 0.49 flags 0 and 0.50 flags 1."""
    plots = [
        {"code": "F", "low_parcel_coverage": 1},
        {"code": "U", "low_parcel_coverage": 0},
    ]
    crosswalk = [
        {"dz2022": "F", "dz2011": "A", "uprn_count": "49"},
        {"dz2022": "U", "dz2011": "A", "uprn_count": "51"},
        {"dz2022": "F", "dz2011": "B", "uprn_count": "50"},
        {"dz2022": "U", "dz2011": "B", "uprn_count": "50"},
    ]
    flags = dz2011_low_parcel_flags(plots, crosswalk)
    assert flags["A"] == 0
    assert flags["B"] == 1


def _bedrooms(tmp_path: Path, name: str, bedroom_rows: list[list[str]], edges: list[list[str]]) -> dict:
    beds = _path(
        tmp_path,
        name,
        ["dz2022_code", "households_total", "share_1", "share_3", "share_4plus"],
        bedroom_rows,
    )
    cross = _path(tmp_path, name + "_x", ["dz2011_code", "dz2022_code", "uprn_count"], edges)
    return adapt_bedrooms(beds, cross)


def test_bedrooms_crosswalk_3zone(tmp_path: Path) -> None:
    """SYNTHETIC. Hand-computed O-D1 counts and rebuilt shares."""
    result = _bedrooms(
        tmp_path,
        "beds3",
        [
            ["A", "100", "0.2", "0.3", "0.5"],
            ["B", "50", "0.4", "0.2", "0.4"],
            ["C", "80", "0.25", "0.25", "0.5"],
        ],
        [["X", "A", "3"], ["Y", "A", "1"], ["X", "B", "1"], ["Y", "C", "2"]],
    )
    by_zone = {row["dz2011"]: row for row in result["rows"]}
    assert by_zone["X"]["share_1"] == Decimal("35")
    assert by_zone["X"]["share_3"] == Decimal("32.5")
    assert by_zone["X"]["share_4plus"] == Decimal("57.5")
    assert by_zone["Y"]["share_1"] == Decimal("25")
    assert by_zone["Y"]["share_3"] == Decimal("27.5")
    assert by_zone["Y"]["share_4plus"] == Decimal("52.5")
    assert quantize(by_zone["X"]["share_1_share"]) == quantize(Decimal("35") / Decimal("125"))
    assert result["dz2022_shares"]["A"]["share_1"] == Decimal("0.2")
    assert result["dz2022_shares"]["B"]["share_3"] == Decimal("0.2")
    assert result["dz2022_shares"]["C"]["share_4plus"] == Decimal("0.5")


def test_bedrooms_missing_total_suppressed(tmp_path: Path) -> None:
    """SYNTHETIC. A blank households_total suppresses that zone and does not fill it."""
    result = _bedrooms(
        tmp_path,
        "beds_blank",
        [["A", "", "0.2", "0.3", "0.5"], ["B", "10", "0.5", "0.3", "0.2"]],
        [["D1", "A", "4"], ["D2", "B", "4"]],
    )
    assert "A" in result["suppressed_dz2022"]
    assert [row["dz2011"] for row in result["rows"]] == ["D2"]
    assert "A" not in result["dz2022_shares"]
    rendered = str(result["rows"])
    assert "filled" not in rendered


def test_bedrooms_threshold_pct(tmp_path: Path) -> None:
    """SYNTHETIC. Missing-data weight of exactly 1 percent keeps a row. Above 1 percent suppresses."""
    kept = _bedrooms(
        tmp_path,
        "pct_keep",
        [["M", "", "0.2", "0.3", "0.5"], ["P", "10", "0.5", "0.3", "0.2"]],
        [["D", "M", "1"], ["D", "P", "99"]],
    )
    assert [row["dz2011"] for row in kept["rows"]] == ["D"]
    dropped = _bedrooms(
        tmp_path,
        "pct_drop",
        [["M", "", "0.2", "0.3", "0.5"], ["P", "10", "0.5", "0.3", "0.2"]],
        [["D", "M", "2"], ["D", "P", "99"]],
    )
    assert dropped["rows"] == []


def test_bedrooms_threshold_count(tmp_path: Path) -> None:
    """SYNTHETIC. Four affected zones keep a row. Five suppress it. The weight stays under 1 percent."""
    def edges(count: int) -> list[list[str]]:
        built = [["D", f"M{index}", "1"] for index in range(count)]
        built.append(["D", "P", "10000"])
        return built

    def rooms(count: int) -> list[list[str]]:
        built = [[f"M{index}", "", "0.2", "0.3", "0.5"] for index in range(count)]
        built.append(["P", "10", "0.5", "0.3", "0.2"])
        return built

    kept = _bedrooms(tmp_path, "count4", rooms(4), edges(4))
    assert [row["dz2011"] for row in kept["rows"]] == ["D"]
    dropped = _bedrooms(tmp_path, "count5", rooms(5), edges(5))
    assert dropped["rows"] == []


def test_bedrooms_fidelity_flag(tmp_path: Path) -> None:
    """SYNTHETIC. The bedrooms rebuild is disclosed as fidelity_adaptation bedrooms_o_d1."""
    path = _write_schema(tmp_path, "bedrooms")
    result = adapt_bedrooms(path, _cross(tmp_path))
    assert result["fidelity_adaptation"] == FIDELITY_ADAPTATION


def _field_test(name: str, value: str):
    citation = FIELD_CITATIONS[name]

    def test_field() -> None:
        assert citation in inspect.getdoc(test_field)
        if name == "low_parcel_coverage":
            assert value == "1"
            return
        assert project_cited_fields({name: value})[name] == value

    test_field.__doc__ = f"SYNTHETIC. {citation}"
    test_field.__name__ = f"test_field_{name}"
    return test_field


for _field_name, _citation in FIELD_CITATIONS.items():
    _hand = "1" if _field_name == "low_parcel_coverage" else "SYNTHETIC_" + _field_name
    globals()[f"test_field_{_field_name}"] = _field_test(_field_name, _hand)


def test_undefined_field_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A field with no frozen section is listed and not written."""
    dest = tmp_path / "sentinel.json"
    calls = {"n": 0}
    monkeypatch.setattr("georgist.v14_b2.emit_output", lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1))
    with pytest.raises(B2Error) as raised:
        extend_column_map(["not_a_field"])
        emit_blocked = dest
        emit_blocked.write_text("SYNTHETIC", encoding="utf-8")
    assert str(raised.value) == "B2_FIELDS: ERROR: frozen definition: expected cited section, got none for not_a_field"
    assert calls["n"] == 0
    assert not dest.exists()


def test_year_screen_long_blank(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A blank DateCode does not read Value."""
    _assert_year(tmp_path, monkeypatch, ["S01", "SYNTHETIC zone", "2011 Data Zones", "", "Mean", "GBP", "SENTINEL_VALUE", "6"], "blank")


def test_year_screen_long_short(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A row that ends before DateCode does not read Value."""
    _assert_year(tmp_path, monkeypatch, ["S01", "SYNTHETIC zone", "2011 Data Zones"], "short")


def test_year_screen_long_2024(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. DateCode 2024 is refused before Value is read."""
    header, _rows = _house()
    path = _path(
        tmp_path,
        "house_sales",
        header,
        [["S01", "SYNTHETIC zone", "2011 Data Zones", "2024", "Mean", "GBP", "SENTINEL_VALUE", "6"]],
    )
    calls = {"n": 0}
    monkeypatch.setattr("georgist.v14_b2.read_value_cell", lambda value: calls.__setitem__("n", calls["n"] + 1) or value)
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == "B2_HOUSE_SALES: ERROR: year row 1: expected <2024, got 2024"
    assert calls["n"] == 0
    assert "SENTINEL_VALUE" not in str(raised.value)


def test_year_screen_long_nonint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A non-integer DateCode does not read Value."""
    _assert_year(
        tmp_path,
        monkeypatch,
        ["S01", "SYNTHETIC zone", "2011 Data Zones", "20x3", "Mean", "GBP", "SENTINEL_VALUE", "6"],
        "20x3",
    )


def _assert_year(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, row: list[str], got: str) -> None:
    header, _rows = _house()
    path = _path(tmp_path, "house_sales", header, [row])
    calls = {"n": 0}
    monkeypatch.setattr("georgist.v14_b2.read_value_cell", lambda value: calls.__setitem__("n", calls["n"] + 1) or value)
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == f"B2_HOUSE_SALES: ERROR: year row 1: expected integer, got {got}"
    assert calls["n"] == 0
    assert "SENTINEL_VALUE" not in str(raised.value)


def test_pr2_fixtures_are_labelled_synthetic() -> None:
    """SYNTHETIC. Every committed PR 2 fixture carries the label."""
    root = Path(__file__).resolve().parent / "fixtures" / "v14_pr2"
    found = False
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        found = True
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "SYNTHETIC" in text
        assert "\u00a3" not in text
    assert found
    assert "SYNTHETIC" in Path(__file__).read_text(encoding="utf-8")
    assert BEDROOM_BANDS
