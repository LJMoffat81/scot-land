"""HOLDOUT-UR6-1 header contract, n25i council join, and check 4 statuses.

SYNTHETIC labelled rows under the real header tuples. No 2024 price cell is read.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from openpyxl import Workbook

from georgist import surface_rent as sr
from georgist.rent_table_pooled import RENT_TABLE_COLUMNS
from georgist.v14_b2 import PIN_TABLE as B2_PINS
from georgist.v14_b2 import SCHEMA_HEADERS, parse_data_rows, read_value_cell, write_adapter
from georgist.v14_real_headers import REAL_HEADERS, REAL_SHA256, header_refusal, read_header_fields
from georgist.v14_score_report import PIN_TABLE as MERGE_PINS
from scripts.build_v14_check_sources import (
    CROSSWALK_FIELDS,
    EXPECTED_EXCLUDED,
    GIS_FIELDS,
    PIN_TABLE as SOURCE_PINS,
    PLOT_FIELDS,
    UR6_FIELDS,
    _csv_table,
    build_check4,
    build_dz2022_keys,
    build_ur6,
    save_check3,
    save_check4,
    save_dz2022,
    save_ur6,
)
from scripts.build_v14_check_sources import main as source_main
from scripts.build_v14_drc import main as b1_main
from scripts.build_v14_drc_components import (
    PIN_TABLE as COMPONENT_PINS,
    REQUIRED_COLUMNS,
    build_components,
    copy_pin_table,
    sha256_file,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v14_pr3a"
CONTRACT = (
    "epc",
    "nrs2017",
    "plot_bands",
    "ur6",
    "n25i",
    "house_sales",
    "plot_split",
    "crosswalk",
    "sold_tfa",
    "access",
    "bedrooms",
    "rent_table",
    "merge_map",
    "crosswalk_b5",
    "ur6_b5",
)
CHECK3 = (
    pytest.param(
        "plot_bands_check3",
        marks=pytest.mark.xfail(
            strict=True,
            raises=AssertionError,
            reason="D1: check 3 method O-P1 open (HOLDOUT-UR6-1 §3)",
        ),
    ),
    pytest.param(
        "gis_house_plot_check3",
        marks=pytest.mark.xfail(
            strict=True,
            raises=AssertionError,
            reason="D1: check 3 method O-P1 open (HOLDOUT-UR6-1 §3)",
        ),
    ),
)
CODE_COLUMN = {
    "epc": "code",
    "nrs2017": "code",
    "plot_bands": "code",
    "ur6": "code",
    "n25i": "Data Zone code",
    "house_sales": "GeographyCode",
    "plot_split": "dz2022_code",
    "crosswalk": "dz2011_code",
    "sold_tfa": "code",
    "access": "code",
    "bedrooms": "dz2022_code",
    "rent_table": "zone_id",
    "crosswalk_b5": "dz2011_code",
    "ur6_b5": "code",
}
HEADER_KEY = {
    "crosswalk_b5": "crosswalk",
    "ur6_b5": "ur6",
    "plot_bands_check3": "plot_bands",
    "gis_house_plot_check3": "gis_house_plot",
}
B2_READERS = ("house_sales", "plot_split", "crosswalk", "sold_tfa", "access", "bedrooms")
PIN_TABLES = (COMPONENT_PINS, SOURCE_PINS, B2_PINS, MERGE_PINS)


def _header_name(name: str) -> str:
    return HEADER_KEY.get(name, name)


def _required(name: str) -> set[str]:
    if name == "plot_bands":
        return set(sr.load_config()["estate"]["columns"].values()) | {"code"}
    if name == "plot_bands_check3":
        return set(PLOT_FIELDS)
    if name == "gis_house_plot_check3":
        return set(GIS_FIELDS)
    if name == "n25i":
        return {"Data Zone code", "Council area code"}
    if name in REQUIRED_COLUMNS:
        return set(REQUIRED_COLUMNS[name])
    if name in SCHEMA_HEADERS:
        return set(SCHEMA_HEADERS[name])
    if name == "rent_table":
        return set(RENT_TABLE_COLUMNS)
    if name == "merge_map":
        return set(REAL_HEADERS["merge_map"])
    if name == "crosswalk_b5":
        return set(CROSSWALK_FIELDS)
    if name == "ur6_b5":
        return set(UR6_FIELDS)
    raise AssertionError(name)


def _csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    lines = ["# SYNTHETIC", ",".join(header)]
    lines.extend(",".join(cells) for cells in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _row(name: str, values: dict[str, str]) -> list[str]:
    return [values.get(column, "") for column in REAL_HEADERS[name]]


def _rename(name: str) -> list[str]:
    header = list(REAL_HEADERS[_header_name(name)])
    column = CODE_COLUMN[name]
    header[header.index(column)] = "kode"
    return header


def _paths() -> dict[str, Path]:
    return {
        "epc": FIXTURES / "epc.csv",
        "nrs2017": FIXTURES / "nrs2017.csv",
        "plot_bands": FIXTURES / "plot_bands.csv",
        "ur6": FIXTURES / "ur6.csv",
        "n25i": FIXTURES / "n25i.xlsx",
    }


def _pins(paths: dict[str, Path]) -> dict[str, str]:
    pins = copy_pin_table()
    for name, path in paths.items():
        if name in pins and path.is_file():
            pins[name] = sha256_file(path)
    return pins


def _source_pins(paths: dict[str, Path]) -> dict[str, str]:
    pins = {key: str(SOURCE_PINS[key]) for key in SOURCE_PINS}
    for name, path in paths.items():
        if name in pins and path.is_file():
            pins[name] = sha256_file(path)
    return pins


def _write_n25i(
    path: Path,
    rows: list[dict[str, str]] | list[list[str]],
    header: list[str] | None = None,
    *,
    raw_rows: bool = False,
) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "2025"
    sheet.append(["SYNTHETIC"])
    sheet.append([None])
    sheet.append([None])
    sheet.append([None])
    used = list(REAL_HEADERS["n25i"] if header is None else header)
    sheet.append(used)
    for values in rows:
        if raw_rows:
            sheet.append(list(values))
        else:
            sheet.append([values.get(column, "") for column in used])
    workbook.save(path)


def _n25i_values(code: str, council: str) -> dict[str, str]:
    values = {column: "0" for column in REAL_HEADERS["n25i"]}
    values["Data Zone code"] = code
    values["Data zone name"] = "SYNTHETIC"
    values["Council area code"] = council
    values["Council area name"] = "SYNTHETIC"
    values["Total number of dwellings"] = "10"
    return values


def _ur6_values(code: str, ur6_class: str) -> dict[str, str]:
    values = {column: "" for column in REAL_HEADERS["ur6"]}
    values["code"] = code
    values["ur6_class"] = ur6_class
    values["ur6_name"] = "SYNTHETIC"
    values["source"] = "SYNTHETIC"
    values["licence"] = "OGL-3.0"
    return values


def _rent_values(zone: str, **overrides: str) -> dict[str, str]:
    values = {column: "1" for column in REAL_HEADERS["rent_table"]}
    values["zone_id"] = zone
    values["status"] = "observed_pooled"
    values.update(overrides)
    return values


@pytest.mark.parametrize("name", (*CONTRACT, *CHECK3))
def test_header_contract(name: str) -> None:
    """SYNTHETIC. Each reader may require only fields the real header has."""
    assert set(_required(name)) <= set(REAL_HEADERS[_header_name(name)])


@pytest.mark.parametrize("name", tuple(REAL_SHA256))
def test_real_sha_matches_prod_pins(name: str) -> None:
    """SYNTHETIC. Header digests match the production pin tables."""
    sha = REAL_SHA256[name]
    assert re.fullmatch(r"[0-9a-f]{64}", sha)
    matched = False
    for table in PIN_TABLES:
        if name in table:
            assert table[name] == sha
            matched = True
    assert matched


@pytest.mark.parametrize(
    "name",
    (
        "epc",
        "nrs2017",
        "plot_bands",
        "ur6",
        "n25i",
        *B2_READERS,
        "ur6_b5",
        "rent_table",
        "crosswalk_b5",
    ),
)
def test_runtime_header_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """SYNTHETIC. A renamed column is refused before any data row is parsed."""
    header = _rename(name)
    key = _header_name(name)
    expected = ",".join(REAL_HEADERS[key])
    got = ",".join(header)
    if name in B2_READERS:
        step = f"B2_{name.upper()}"
    elif name == "ur6_b5":
        step = "B5_UR6"
    elif name == "rent_table":
        step = "B5_CHECK4"
    elif name == "crosswalk_b5":
        step = "B5_CROSSWALK"
    else:
        step = "B1_COMPONENTS"
    message = f"{step}: REFUSED: header: expected {expected}, got {got}"
    calls = {"rows": 0, "down": 0}
    out = tmp_path / "out.json"

    def _rows(*_args, **_kwargs):
        calls["rows"] += 1
        return []

    def _down(*_args, **_kwargs):
        calls["down"] += 1

    if name in {"epc", "nrs2017", "plot_bands", "ur6", "n25i"}:
        paths = dict(_paths())
        if name == "n25i":
            path = tmp_path / "n25i.xlsx"
            _write_n25i(path, [_n25i_values("ZA1", "S12000001")], header)
            paths["n25i"] = path
        else:
            path = tmp_path / f"{name}.csv"
            _csv(path, header, [["SYNTHETIC"] * len(header)])
            paths[name] = path
        monkeypatch.setattr("scripts.build_v14_drc_components.parse_component_rows", _rows)
        monkeypatch.setattr("scripts.build_v14_drc_components.parse_n25i_rows", _rows)
        monkeypatch.setattr("scripts.build_v14_drc_components.borrow_plot_bands", _down)
        monkeypatch.setattr("scripts.build_v14_drc_components.write_components", _down)
        with pytest.raises(Exception) as raised:
            build_components(paths, pins=_pins(paths))
        assert str(raised.value) == message
    elif name in B2_READERS:
        path = tmp_path / f"{name}.csv"
        _csv(path, header, [["SYNTHETIC"] * len(header)])
        monkeypatch.setitem(B2_PINS, name, sha256_file(path))
        monkeypatch.setattr("georgist.v14_b2.parse_data_rows", _rows)
        monkeypatch.setattr("georgist.v14_b2.emit_output", _down)
        cross = tmp_path / "cross.csv"
        _csv(cross, list(SCHEMA_HEADERS["crosswalk"]), [["D1", "Z1", "1"]])
        with pytest.raises(Exception) as raised:
            write_adapter(name, path, out, crosswalk=cross, expected_count=0)
        assert str(raised.value) == message
    else:
        path = tmp_path / f"{name}.csv"
        _csv(path, header, [["SYNTHETIC"] * len(header)])
        monkeypatch.setattr("scripts.build_v14_check_sources._csv_table", _rows)
        monkeypatch.setattr("scripts.build_v14_check_sources.write_output", _down)
        monkeypatch.setattr("scripts.build_v14_check_sources.two_route_lands", _down)
        pins = _source_pins({})
        if name == "ur6_b5":
            pins["ur6"] = sha256_file(path)
            with pytest.raises(Exception) as raised:
                save_ur6(path, out, pins=pins)
        elif name == "rent_table":
            pins["rent_table"] = sha256_file(path)
            with pytest.raises(Exception) as raised:
                save_check4(path, out, pins=pins)
        else:
            primary = tmp_path / "primary.json"
            primary.write_text('{"label":"SYNTHETIC","zones":[]}\n', encoding="utf-8")
            pins["crosswalk"] = sha256_file(path)
            with pytest.raises(Exception) as raised:
                save_dz2022(path, primary, out, pins=pins)
        assert str(raised.value) == message
    assert calls == {"rows": 0, "down": 0}
    assert not out.exists()


@pytest.mark.parametrize(
    ("reader", "code_col", "class_col"),
    (
        ("ur6", "code", "ur6_class"),
        ("n25i", "Data Zone code", "Council area code"),
        ("ur6_b5", "code", "ur6_class"),
        ("check4", "zone_id", "status"),
    ),
)
@pytest.mark.parametrize("case", ("missing_code", "missing_class", "blank_class", "short_row"))
def test_reader_bad_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reader: str,
    code_col: str,
    class_col: str,
    case: str,
) -> None:
    """SYNTHETIC. A bad header or cell refuses before the downstream step."""
    key = {"ur6": "ur6", "n25i": "n25i", "ur6_b5": "ur6", "check4": "rent_table"}[reader]
    step = {"ur6": "B1_COMPONENTS", "n25i": "B1_COMPONENTS", "ur6_b5": "B5_UR6", "check4": "B5_CHECK4"}[reader]
    header = list(REAL_HEADERS[key])
    width = len(header)
    if case == "missing_code":
        header = [column for column in header if column != code_col]
    elif case == "missing_class":
        header = [column for column in header if column != class_col]
    values = {column: "1" for column in header}
    if reader in {"ur6", "ur6_b5"}:
        values = _ur6_values("S01000001", "1")
        values = {column: values.get(column, "") for column in header}
    elif reader == "n25i":
        values = _n25i_values("S01000001", "S12000001")
        values = {column: values.get(column, "") for column in header}
    elif reader == "check4":
        values = _rent_values("Z1")
        values = {column: values.get(column, "") for column in header}
    if case == "blank_class":
        values[class_col] = ""
    row = [values.get(column, "") for column in header]
    if case == "short_row":
        row = row[:1]
    calls = {"down": 0}
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.borrow_plot_bands",
        lambda *_a, **_k: calls.__setitem__("down", calls["down"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.two_route_lands",
        lambda *_a, **_k: calls.__setitem__("down", calls["down"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.write_output",
        lambda *_a, **_k: calls.__setitem__("down", calls["down"] + 1),
    )
    out = tmp_path / "out.json"
    if reader == "n25i":
        path = tmp_path / "n25i.xlsx"
        if case == "short_row":
            _write_n25i(path, [row], header, raw_rows=True)
        else:
            _write_n25i(path, [dict(zip(header, row))], header)
        paths = dict(_paths())
        paths["n25i"] = path
        with pytest.raises(Exception) as raised:
            build_components(paths, pins=_pins(paths))
    elif reader == "ur6":
        path = tmp_path / "ur6.csv"
        _csv(path, header, [row])
        paths = dict(_paths())
        paths["ur6"] = path
        with pytest.raises(Exception) as raised:
            build_components(paths, pins=_pins(paths))
    elif reader == "ur6_b5":
        path = tmp_path / "ur6.csv"
        _csv(path, header, [row])
        pins = _source_pins({})
        pins["ur6"] = sha256_file(path)
        with pytest.raises(Exception) as raised:
            save_ur6(path, out, pins=pins)
    else:
        path = tmp_path / "rent.csv"
        _csv(path, header, [row])
        pins = _source_pins({})
        pins["rent_table"] = sha256_file(path)
        with pytest.raises(Exception) as raised:
            save_check4(path, out, pins=pins)
    if case in {"missing_code", "missing_class"}:
        message = f"{step}: REFUSED: header: expected {','.join(REAL_HEADERS[key])}, got {','.join(header)}"
    elif case == "blank_class":
        if reader == "n25i":
            label = "Council area code"
        elif reader == "check4":
            label = "status"
        else:
            label = "ur6_class"
        message = f"{step}: ERROR: {label} row 1: expected value, got blank"
    else:
        message = f"{step}: ERROR: row 1: expected {width} fields, got 1"
    assert str(raised.value) == message
    assert calls["down"] == 0
    assert not out.exists()


@pytest.mark.parametrize("value", ("0", "7", "x"))
def test_ur6_class_range(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """SYNTHETIC. UR6 outside 1-6 refuses and writes nothing."""
    calls = {"down": 0}
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.borrow_plot_bands",
        lambda *_a, **_k: calls.__setitem__("down", calls["down"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.write_output",
        lambda *_a, **_k: calls.__setitem__("down", calls["down"] + 1),
    )
    header = list(REAL_HEADERS["ur6"])
    path = tmp_path / "ur6.csv"
    _csv(path, header, [_row("ur6", _ur6_values("S01000001", value))])
    paths = dict(_paths())
    paths["ur6"] = path
    out = tmp_path / "out.json"
    with pytest.raises(Exception) as b1:
        build_components(paths, pins=_pins(paths))
    assert str(b1.value) == f"B1_COMPONENTS: ERROR: ur6_class row 1: expected 1-6, got {value}"
    pins = _source_pins({})
    pins["ur6"] = sha256_file(path)
    with pytest.raises(Exception) as b5:
        save_ur6(path, out, pins=pins)
    assert str(b5.value) == f"B5_UR6: ERROR: ur6 row 1: expected 1-6, got {value}"
    assert calls["down"] == 0
    assert not out.exists()


def test_missing_council(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A UR6 code absent from n25i is refused before plot bands are borrowed."""
    calls = {"down": 0}
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.borrow_plot_bands",
        lambda *_a, **_k: calls.__setitem__("down", calls["down"] + 1),
    )
    path = tmp_path / "ur6.csv"
    _csv(path, list(REAL_HEADERS["ur6"]), [_row("ur6", _ur6_values("S01000009", "1"))])
    paths = dict(_paths())
    paths["ur6"] = path
    out = tmp_path / "components.json"
    with pytest.raises(Exception) as raised:
        build_components(paths, pins=_pins(paths))
    assert str(raised.value) == (
        f"B1_COMPONENTS: REFUSED: council_code: expected S01000009 in n25i {paths['n25i']}, got absent"
    )
    assert calls["down"] == 0
    assert not out.exists()


@pytest.mark.parametrize(
    "name",
    ("epc", "nrs2017", "plot_bands", "ur6", "n25i", "rent_table", "ur6_b5", "crosswalk_b5"),
)
def test_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """SYNTHETIC. A missing input is named before its reader runs."""
    calls = {"reader": 0}
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.load_epc",
        lambda *_a, **_k: calls.__setitem__("reader", calls["reader"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.load_nrs2017",
        lambda *_a, **_k: calls.__setitem__("reader", calls["reader"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.load_plot_bands",
        lambda *_a, **_k: calls.__setitem__("reader", calls["reader"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.load_ur6",
        lambda *_a, **_k: calls.__setitem__("reader", calls["reader"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.load_n25i",
        lambda *_a, **_k: calls.__setitem__("reader", calls["reader"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.load_rent_table",
        lambda *_a, **_k: calls.__setitem__("reader", calls["reader"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.load_ur6_rows",
        lambda *_a, **_k: calls.__setitem__("reader", calls["reader"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.load_crosswalk",
        lambda *_a, **_k: calls.__setitem__("reader", calls["reader"] + 1),
    )
    missing = tmp_path / "absent.csv"
    out = tmp_path / "out.json"
    if name in {"epc", "nrs2017", "plot_bands", "ur6", "n25i"}:
        paths = dict(_paths())
        paths[name] = missing
        with pytest.raises(Exception) as raised:
            build_components(paths, pins=_pins(_paths()))
        step = "B1_COMPONENTS"
    elif name == "rent_table":
        with pytest.raises(Exception) as raised:
            build_check4(missing, pins=_source_pins({}))
        step = "B5_CHECK4"
    elif name == "ur6_b5":
        with pytest.raises(Exception) as raised:
            build_ur6(missing, pins=_source_pins({}))
        step = "B5_UR6"
    else:
        primary = tmp_path / "primary.json"
        primary.write_text('{"zones":[]}\n', encoding="utf-8")
        with pytest.raises(Exception) as raised:
            build_dz2022_keys(missing, primary, pins=_source_pins({}))
        step = "B5_CROSSWALK"
    assert str(raised.value) == f"{step}: ERROR: file: expected {missing}, got absent"
    assert calls["reader"] == 0
    assert not out.exists()


def _zone_inputs(code: str, council: str, ur6_class: str, bands: dict[str, str]) -> dict[str, dict[str, str]]:
    epc = {column: "" for column in REAL_HEADERS["epc"]}
    epc["code"] = code
    for column in REAL_HEADERS["epc"]:
        if column.startswith("age_") or column.startswith("recent10_age_"):
            epc[column] = "1" if column == "age_pre1919_share" else "0"
    nrs = {column: "" for column in REAL_HEADERS["nrs2017"]}
    nrs["code"] = code
    for column in REAL_HEADERS["nrs2017"]:
        if column.startswith("type_"):
            nrs[column] = "10" if column == "type_detached" else "0"
    plot = {column: "" for column in REAL_HEADERS["plot_bands"]}
    plot["code"] = code
    plot.update(bands)
    ur6 = _ur6_values(code, ur6_class)
    return {"epc": epc, "nrs2017": nrs, "plot_bands": plot, "ur6": ur6, "council": council}


def test_components_output_exact(tmp_path: Path) -> None:
    """SYNTHETIC. Council codes come from n25i and a blank band is borrowed."""
    spec = [
        ("S01000001", "S12000001", "1", {"all_ages_share_lt005": "0.5", "all_ages_share_005_010": "0.25", "all_ages_share_gt010": "0.25", "n_detached_all_ages_matched": "4"}),
        ("S01000002", "S12000002", "2", {"all_ages_share_lt005": "0", "all_ages_share_005_010": "0.5", "all_ages_share_gt010": "0.5", "n_detached_all_ages_matched": "2"}),
        ("S01000003", "S12000001", "1", {}),
    ]
    built = [_zone_inputs(*item) for item in spec]
    paths = {}
    for key in ("epc", "nrs2017", "plot_bands", "ur6"):
        path = tmp_path / f"{key}.csv"
        _csv(path, list(REAL_HEADERS[key]), [_row(key, item[key]) for item in built])
        paths[key] = path
    n25i = tmp_path / "n25i.xlsx"
    _write_n25i(n25i, [_n25i_values(item[0], item[1]) for item in spec])
    paths["n25i"] = n25i
    records = build_components(paths, pins=_pins(paths))
    expected = [
        {
            "dz2011": "S01000001",
            "council_code": "S12000001",
            "epc_row": built[0]["epc"],
            "nrs2017_row": built[0]["nrs2017"],
            "estate_row": {**built[0]["plot_bands"], "_plot_bands_source": "filled"},
        },
        {
            "dz2011": "S01000002",
            "council_code": "S12000002",
            "epc_row": built[1]["epc"],
            "nrs2017_row": built[1]["nrs2017"],
            "estate_row": {**built[1]["plot_bands"], "_plot_bands_source": "filled"},
        },
        {
            "dz2011": "S01000003",
            "council_code": "S12000001",
            "epc_row": built[2]["epc"],
            "nrs2017_row": built[2]["nrs2017"],
            "estate_row": {
                "code": "S01000003",
                "all_ages_share_lt005": 0.5,
                "all_ages_share_005_010": 0.25,
                "all_ages_share_gt010": 0.25,
                "_plot_bands_source": "borrowed",
                "_borrow_cell": "('S12000001', 1)",
                "_borrow_n_zones": 1,
            },
        },
    ]
    assert records == expected
    out = tmp_path / "components.json"
    drc = tmp_path / "drc.json"
    out.write_text(json.dumps(records) + "\n", encoding="utf-8")
    assert b1_main(["--drc-json", str(drc), "--components", str(out)]) == 0


@pytest.mark.parametrize("mode", ("one_byte", "prefix"))
def test_n25i_wrong_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """SYNTHETIC. n25i is refused on a full sha mismatch before the reader or the join."""
    calls = {"reader": 0, "join": 0}
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.load_n25i",
        lambda *_a, **_k: calls.__setitem__("reader", calls["reader"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.borrow_plot_bands",
        lambda *_a, **_k: calls.__setitem__("join", calls["join"] + 1),
    )
    paths = dict(_paths())
    changed = tmp_path / "n25i.xlsx"
    changed.write_bytes(paths["n25i"].read_bytes() + b"\n")
    paths["n25i"] = changed
    actual = sha256_file(changed)
    pins = _pins(_paths())
    if mode == "one_byte":
        pins["n25i"] = sha256_file(_paths()["n25i"])
        shown = pins["n25i"]
    else:
        shown = actual[:8] + ("0" * 56 if actual[8] != "0" else "1" * 56)
        pins["n25i"] = shown
    out = tmp_path / "components.json"
    with pytest.raises(Exception) as raised:
        build_components(paths, pins=pins)
    assert str(raised.value) == f"B1_COMPONENTS: REFUSED: n25i sha256: expected {shown}, got {actual}"
    assert calls == {"reader": 0, "join": 0}
    assert not out.exists()


@pytest.mark.parametrize("reader", ("n25i", "ur6", "ur6_b5"))
def test_duplicate_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reader: str) -> None:
    """SYNTHETIC. A repeated zone code is refused before the join."""
    calls = {"join": 0}
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.borrow_plot_bands",
        lambda *_a, **_k: calls.__setitem__("join", calls["join"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.write_output",
        lambda *_a, **_k: calls.__setitem__("join", calls["join"] + 1),
    )
    out = tmp_path / "out.json"
    if reader == "n25i":
        path = tmp_path / "n25i.xlsx"
        _write_n25i(path, [_n25i_values("S01000001", "S12000001"), _n25i_values("S01000001", "S12000002")])
        paths = dict(_paths())
        paths["n25i"] = path
        with pytest.raises(Exception) as raised:
            build_components(paths, pins=_pins(paths))
        assert str(raised.value) == "B1_COMPONENTS: REFUSED: n25i code: expected unique, got duplicate S01000001"
    elif reader == "ur6":
        path = tmp_path / "ur6.csv"
        _csv(
            path,
            list(REAL_HEADERS["ur6"]),
            [_row("ur6", _ur6_values("ZA1", "1")), _row("ur6", _ur6_values("ZA1", "2"))],
        )
        paths = dict(_paths())
        paths["ur6"] = path
        with pytest.raises(Exception) as raised:
            build_components(paths, pins=_pins(paths))
        assert str(raised.value) == "B1_COMPONENTS: REFUSED: ur6 code: expected unique, got duplicate ZA1"
    else:
        path = tmp_path / "ur6.csv"
        _csv(
            path,
            list(REAL_HEADERS["ur6"]),
            [_row("ur6", _ur6_values("ZA1", "1")), _row("ur6", _ur6_values("ZA1", "2"))],
        )
        pins = _source_pins({})
        pins["ur6"] = sha256_file(path)
        with pytest.raises(Exception) as raised:
            save_ur6(path, out, pins=pins)
        assert str(raised.value) == "B5_UR6: REFUSED: ur6 code: expected unique, got duplicate ZA1"
    assert calls["join"] == 0
    assert not out.exists()


def _rent_file(path: Path, rows: list[dict[str, str]]) -> None:
    header = list(REAL_HEADERS["rent_table"])
    _csv(path, header, [[item[column] for column in header] for item in rows])


def _excluded(pending: int, not_applicable: int) -> list[dict[str, str]]:
    rows = []
    for index in range(pending):
        rows.append(_rent_values(f"P{index}", status="model_fill_pending", central="", low="", high="", flags=""))
    for index in range(not_applicable):
        rows.append(_rent_values(f"N{index}", status="not_applicable"))
    return rows


@pytest.mark.parametrize(
    "case",
    (
        "blank_central",
        "blank_low",
        "pending_excluded",
        "not_applicable_excluded",
        "unknown_status",
        "blank_flags",
    ),
)
def test_check4_statuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], case: str) -> None:
    """SYNTHETIC. Check 4 keeps observed rows and refuses a blank or unknown status."""
    calls = {"down": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.two_route_lands",
        lambda row: calls.__setitem__("down", calls["down"] + 1) or (float(row["central"]), float(row["low"])),
    )
    path = tmp_path / "rent.csv"
    out = tmp_path / "check4.json"
    if case == "blank_central":
        _rent_file(path, [_rent_values("Z1", central="")])
    elif case == "blank_low":
        _rent_file(path, [_rent_values("Z1", low="")])
    elif case == "unknown_status":
        _rent_file(path, [_rent_values("Z1", status="other")])
    else:
        observed = _rent_values("Z1", central="4", low="1")
        if case == "blank_flags":
            observed["flags"] = ""
        _rent_file(path, [observed, *_excluded(129, 3)])
    pins = _source_pins({})
    pins["rent_table"] = sha256_file(path)
    monkeypatch.setitem(SOURCE_PINS, "rent_table", sha256_file(path))
    if case in {"blank_central", "blank_low", "unknown_status"}:
        with pytest.raises(Exception) as raised:
            build_check4(path, pins=pins)
        if case == "blank_central":
            message = "B5_CHECK4: ERROR: central row 1: expected value, got blank"
        elif case == "blank_low":
            message = "B5_CHECK4: ERROR: low row 1: expected value, got blank"
        else:
            message = "B5_CHECK4: REFUSED: status row 1: expected observed_pooled|model_fill_pending|not_applicable, got other"
        assert str(raised.value) == message
        assert calls["down"] == 0
        assert not out.exists()
        return
    assert source_main(["--rent-table", str(path), "--check4-out", str(out)]) == 0
    assert capsys.readouterr().out == "B5_CHECK4: excluded=132\n"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [row["zone"] for row in payload["zones"]] == ["Z1"]
    assert calls["down"] == 1


@pytest.mark.parametrize(
    "column",
    ("dwellings", "la_code", "ur6_class", "sales_n", "pooling_config_sha256", "zone_id"),
)
def test_check4_required_blank(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, column: str) -> None:
    """SYNTHETIC. A blank required check-4 cell refuses before the route."""
    calls = {"down": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.two_route_lands",
        lambda *_a, **_k: calls.__setitem__("down", calls["down"] + 1),
    )
    path = tmp_path / "rent.csv"
    _rent_file(path, [_rent_values("Z1", **{column: ""})])
    pins = _source_pins({})
    pins["rent_table"] = sha256_file(path)
    out = tmp_path / "check4.json"
    with pytest.raises(Exception) as raised:
        save_check4(path, out, pins=pins)
    assert str(raised.value) == f"B5_CHECK4: ERROR: {column} row 1: expected value, got blank"
    assert calls["down"] == 0
    assert not out.exists()


def test_check4_expected_excluded_constant() -> None:
    """SYNTHETIC. The excluded split is the preregistered constant, with no file read."""
    assert EXPECTED_EXCLUDED == {"model_fill_pending": 129, "not_applicable": 3}


@pytest.mark.parametrize(
    ("pending", "not_applicable", "message"),
    (
        (128, 3, "got model_fill_pending=128,not_applicable=3"),
        (130, 3, "got model_fill_pending=130,not_applicable=3"),
        (130, 2, "got model_fill_pending=130,not_applicable=2"),
    ),
)
def test_check4_excluded_split_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pending: int,
    not_applicable: int,
    message: str,
) -> None:
    """SYNTHETIC. A wrong excluded split refuses before the route is written."""
    calls = {"down": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.two_route_lands",
        lambda *_a, **_k: calls.__setitem__("down", calls["down"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.write_output",
        lambda *_a, **_k: calls.__setitem__("down", calls["down"] + 1),
    )
    path = tmp_path / "rent.csv"
    _rent_file(path, [_rent_values("Z1"), *_excluded(pending, not_applicable)])
    pins = _source_pins({})
    pins["rent_table"] = sha256_file(path)
    out = tmp_path / "check4.json"
    with pytest.raises(Exception) as raised:
        save_check4(path, out, pins=pins)
    assert str(raised.value) == (
        "B5_CHECK4: REFUSED: excluded: expected model_fill_pending=129,not_applicable=3, " + message
    )
    assert calls["down"] == 0
    assert not out.exists()


def test_check4_excluded_split_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. 129 pending and 3 not applicable are excluded and the route runs once."""
    calls = {"down": 0}

    def spy(row: dict[str, str]) -> tuple[float, float]:
        calls["down"] += 1
        return float(row["central"]), float(row["low"])

    monkeypatch.setattr("scripts.build_v14_check_sources.two_route_lands", spy)
    path = tmp_path / "rent.csv"
    _rent_file(path, [_rent_values("Z1", central="4", low="1"), *_excluded(129, 3)])
    monkeypatch.setitem(SOURCE_PINS, "rent_table", sha256_file(path))
    out = tmp_path / "check4.json"
    assert source_main(["--rent-table", str(path), "--check4-out", str(out)]) == 0
    assert capsys.readouterr().out == "B5_CHECK4: excluded=132\n"
    assert calls["down"] == 1
    assert out.is_file()


@pytest.mark.parametrize(
    ("step", "field", "writer"),
    (
        ("B5_UR6", "ur6_class", "save_ur6"),
        ("B5_CHECK4", "status", "save_check4"),
        ("B5_CROSSWALK", "uprn_count", "save_dz2022"),
    ),
)
def test_csv_table_names_missing_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, step: str, field: str, writer: str
) -> None:
    """SYNTHETIC. A direct table read names the missing field, and the writer does not run."""
    calls = {"writer": 0}
    monkeypatch.setattr(
        f"scripts.build_v14_check_sources.{writer}",
        lambda *_a, **_k: calls.__setitem__("writer", calls["writer"] + 1),
    )
    if step == "B5_UR6":
        fields = UR6_FIELDS
        header = ["code", "ur6_name"]
    elif step == "B5_CHECK4":
        fields = RENT_TABLE_COLUMNS
        header = [column for column in RENT_TABLE_COLUMNS if column != "status"]
    else:
        fields = CROSSWALK_FIELDS
        header = ["dz2011_code", "dz2022_code"]
    path = tmp_path / "table.csv"
    _csv(path, header, [["1"] * len(header)])
    out = tmp_path / "out.json"
    with pytest.raises(Exception) as raised:
        _csv_table(path, step, tuple(fields))
    assert str(raised.value) == f"{step}: ERROR: header: expected {field}, got absent"
    assert calls["writer"] == 0
    assert not out.exists()


def test_check3_not_run_until_d1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. Real plot-band headers do not invent a check 3 pass rule."""
    calls = {"writer": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.write_output",
        lambda *_a, **_k: calls.__setitem__("writer", calls["writer"] + 1),
    )
    plots = tmp_path / "plots.csv"
    _csv(plots, list(REAL_HEADERS["plot_bands"]), [["SYNTHETIC"] * len(REAL_HEADERS["plot_bands"])])
    houses = tmp_path / "houses.csv"
    _csv(houses, ["code", "house_plot_m2"], [["Z1", "1"]])
    pins = _source_pins({"plot_bands": plots, "gis_house_plot": houses})
    out = tmp_path / "check3.json"
    with pytest.raises(Exception) as raised:
        save_check3({"plot_bands": plots, "gis_house_plot": houses}, out, pins=pins)
    assert str(raised.value) == "B5_CHECK3: NOT_RUN: plot_bands header: expected pass_20, got absent"
    assert calls["writer"] == 0
    assert not out.exists()


def test_house_sales_header_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. The house-sales guard stops at the header line."""
    header = list(REAL_HEADERS["house_sales"])
    path = tmp_path / "sales.csv"
    _csv(path, header, [["S01", "SYNTHETIC", "DZ", "2021", "Mean", "GBP", "SENTINEL_VALUE", "1"]])
    seen: list[str] = []
    real_open = Path.open

    def tracking_open(self: Path, *args, **kwargs):
        handle = real_open(self, *args, **kwargs)

        class _Lines:
            def __iter__(self):
                return self

            def __next__(self):
                line = next(handle)
                seen.append(line)
                return line

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                handle.close()
                return False

        return _Lines()

    monkeypatch.setattr(Path, "open", tracking_open)
    calls = {"value": 0}
    monkeypatch.setattr(
        "georgist.v14_b2.read_value_cell",
        lambda value: calls.__setitem__("value", calls["value"] + 1) or value,
    )
    fields = read_header_fields(path)
    assert header_refusal("B2_HOUSE_SALES", "house_sales", fields or []) is None
    assert calls["value"] == 0
    assert "SENTINEL_VALUE" not in "".join(seen)
    assert read_value_cell("unread") == "unread"
