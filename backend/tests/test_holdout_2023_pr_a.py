"""HOLDOUT-2023-RUN PR-A. SYNTHETIC fixtures only: codes, no prices from any real file."""

from __future__ import annotations

import ast
import hashlib
from argparse import Namespace
from pathlib import Path

import pytest

from georgist import v14_fit_joins as joins_mod
from georgist.v14_b2 import B2Error, adapt_house_sales
from georgist.v14_fit_joins import (
    IZ_LOOKUP_SHA256,
    JOIN_FIELDS,
    JOIN_PINS,
    MERGE_MAP_SHA256,
    NO_CELL_LIST_SHA256,
    JoinError,
    _sha256,
    join_fit_rows,
    read_iz_lookup,
    read_merge_map,
    read_no_cell,
)
from v14_dryrun.join_fixture import write_join_files

BACKEND = Path(__file__).resolve().parents[1]
HEADER = "GeographyCode,GeographyName,GeographyType,DateCode,Measurement,Units,Value,Sales"
MEASURES = ("Count", "Lower Quartile", "Mean", "Median", "Upper Quartile")


def _sales_lines(zone: str, name: str, year: int) -> list[str]:
    return [f"{zone},{name},2011 Data Zones,{year},{m},Number,7,Label" for m in MEASURES]


def _pin(monkeypatch: pytest.MonkeyPatch, paths: dict[str, Path]) -> None:
    monkeypatch.setitem(JOIN_PINS, "merge_map", _sha256(paths["merge_map"]))
    monkeypatch.setitem(JOIN_PINS, "iz_lookup", _sha256(paths["iz_lookup"]))
    monkeypatch.setitem(JOIN_PINS, "no_cell", _sha256(paths["no_cell_list"]))


def _fit_row(zone: str, year: int = 2021) -> dict:
    return {"zone": zone, "year": year, "price": "1", "median_price": "1", "n_sales": 6, "f_m2": "50"}


# --- 1. header / row-36 parsing -------------------------------------------------


def test_row36_quoted_comma_name_parses(tmp_path: Path) -> None:
    """The holdout stopped at row 36: a quoted GeographyName holding a comma."""
    lines = []
    for index in range(7):
        lines += _sales_lines(f"S0100{6506 + index}", f"Zone {index}", 2021)
    lines += _sales_lines("S01006599", '"Cults, Bieldside and Milltimber West - 01"', 2021)
    assert lines[35].startswith('S01006599,"Cults, Bieldside')
    path = tmp_path / "house_sales.SYNTHETIC.csv"
    path.write_text(HEADER + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    rows = adapt_house_sales(path)
    assert {row["zone"] for row in rows} == {f"S0100{6506 + i}" for i in range(7)} | {"S01006599"}


def test_repeated_header_row_refused_exact(tmp_path: Path) -> None:
    lines = _sales_lines("S01006506", "Zone 1", 2021) + [HEADER]
    path = tmp_path / "house_sales.SYNTHETIC.csv"
    path.write_text(HEADER + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == "B2_HOUSE_SALES: ERROR: year row 6: expected integer, got DateCode"


# --- 2. pin mismatch ------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "reader", "token"),
    [
        ("merge_map", read_merge_map, "B2_MERGE_MAP"),
        ("iz_lookup", read_iz_lookup, "B2_IZ_LOOKUP"),
        ("no_cell_list", read_no_cell, "B2_NO_CELL"),
    ],
)
def test_join_pin_mismatch_refused_exact(tmp_path: Path, name, reader, token) -> None:
    paths = write_join_files(tmp_path, ["Z1"])
    actual = _sha256(paths[name])
    with pytest.raises(JoinError) as raised:
        reader(paths[name])
    pin_key = "no_cell" if name == "no_cell_list" else name
    assert str(raised.value) == f"{token}: REFUSED: sha256: expected {JOIN_PINS[pin_key]}, got {actual}"


def test_production_join_pins_are_the_frozen_shas() -> None:
    assert JOIN_PINS == {
        "merge_map": "581b0aa1647c5af7ce5b9617e35fcfa73982bc8712a42eb63242243ee6a95947",
        "iz_lookup": "a13d2853e9737ccd6d499eea0ca29e417f5c9ac132828c2c24fce9b48bf004f4",
        "no_cell": "f4a0bead7d9e8264b7bcd3c4881edbf0cee3b13853f4402fc7396421be27aaa6",
    }
    assert (MERGE_MAP_SHA256, IZ_LOOKUP_SHA256, NO_CELL_LIST_SHA256) == tuple(JOIN_PINS.values())


def test_join_header_mismatch_refused_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "iz.SYNTHETIC.csv"
    path.write_text("DZ2011,IZ,CA\nZ1,IZ1,CA1\n", encoding="utf-8")
    monkeypatch.setitem(JOIN_PINS, "iz_lookup", _sha256(path))
    with pytest.raises(JoinError) as raised:
        read_iz_lookup(path)
    assert str(raised.value) == "B2_IZ_LOOKUP: REFUSED: header: expected DZ2011,IZ2011,CA, got DZ2011,IZ,CA"


# --- 3. iz ----------------------------------------------------------------------


def test_join_adds_every_fit_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_join_files(tmp_path, ["Z1"])
    _pin(monkeypatch, paths)
    rows, dropped = join_fit_rows(
        [_fit_row("Z1")], read_merge_map(paths["merge_map"]), read_iz_lookup(paths["iz_lookup"]),
        read_no_cell(paths["no_cell_list"]),
    )
    assert dropped == []
    assert set(JOIN_FIELDS) <= set(rows[0])
    assert (rows[0]["iz"], rows[0]["cell"], rows[0]["a_m2"], rows[0]["ur6"]) == ("IZ1", "c", 40.0, 1)


def test_missing_iz_refused_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_join_files(tmp_path, ["Z1"])
    _pin(monkeypatch, paths)
    with pytest.raises(JoinError) as raised:
        join_fit_rows(
            [_fit_row("Z1")], read_merge_map(paths["merge_map"]), {}, frozenset()
        )
    assert str(raised.value) == "B2_FIT_ROWS: REFUSED: iz row 1: expected IZ2011 code, got absent"


def test_missing_iz_argument_refused_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.build_v14_b2 as b2

    monkeypatch.setattr(b2, "assert_house_sales_pin", lambda _p: None)
    monkeypatch.setattr(b2, "adapt_house_sales", lambda *_a, **_k: [])
    for name in ("adapt_plot_split", "adapt_crosswalk", "adapt_access", "adapt_sold_tfa"):
        monkeypatch.setattr(b2, name, lambda *_a, **_k: [])
    monkeypatch.setattr(b2, "adapt_bedrooms", lambda *_a, **_k: {"rows": []})
    monkeypatch.setattr(
        b2, "run_d7_chain",
        lambda **_k: b2.D7ChainResult(status="passed", d7_sha256="a" * 64, message="", manifest={}),
    )
    fit_calls = []
    monkeypatch.setattr(b2, "fit_headline", lambda *a, **k: fit_calls.append(1))
    args = Namespace(**{k: Path("x") for k in (
        "house_sales", "plot_split", "crosswalk", "sold_tfa", "access", "bedrooms",
        "filter1_script", "filter1_output", "filter2_script", "filter2_output",
        "merge_map", "no_cell_list")}, iz_lookup=None)
    with pytest.raises(B2Error) as raised:
        b2.build(args)
    assert str(raised.value) == "B2_FIT_ROWS: REFUSED: iz_lookup: expected path, got absent"
    assert fit_calls == []


def test_ca_disagreement_refused_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_join_files(tmp_path, ["Z1"])
    _pin(monkeypatch, paths)
    lookup = {"Z1": {"DZ2011": "Z1", "IZ2011": "IZ1", "CA": "CA9"}}
    with pytest.raises(JoinError) as raised:
        join_fit_rows([_fit_row("Z1")], read_merge_map(paths["merge_map"]), lookup, frozenset())
    assert str(raised.value) == "B2_FIT_ROWS: REFUSED: ca row 1: expected CA1, got CA9"


# --- 4. no_cell (fit side) ------------------------------------------------------


def test_no_cell_zone_dropped_and_disclosed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_join_files(tmp_path, ["Z1", "Z2"], no_cell=["Z2"])
    _pin(monkeypatch, paths)
    rows, dropped = join_fit_rows(
        [_fit_row("Z1"), _fit_row("Z2")], read_merge_map(paths["merge_map"]),
        read_iz_lookup(paths["iz_lookup"]), read_no_cell(paths["no_cell_list"]),
    )
    assert [row["zone"] for row in rows] == ["Z1"]
    assert dropped == ["Z2"]


def test_unlisted_zone_missing_from_merge_map_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_join_files(tmp_path, ["Z1"])
    _pin(monkeypatch, paths)
    with pytest.raises(JoinError) as raised:
        join_fit_rows(
            [_fit_row("Z1"), _fit_row("Z7")], read_merge_map(paths["merge_map"]),
            read_iz_lookup(paths["iz_lookup"]), frozenset(),
        )
    assert str(raised.value) == "B2_FIT_ROWS: REFUSED: cell row 2: expected merge-map zone, got absent"


def test_listed_no_cell_zone_present_in_merge_map_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = write_join_files(tmp_path, ["Z1"])
    _pin(monkeypatch, paths)
    with pytest.raises(JoinError) as raised:
        join_fit_rows(
            [_fit_row("Z1")], read_merge_map(paths["merge_map"]),
            read_iz_lookup(paths["iz_lookup"]), frozenset({"Z1"}),
        )
    assert str(raised.value) == (
        "B2_FIT_ROWS: REFUSED: cell row 1: expected no_cell zone absent from merge map, got present"
    )


# --- 5. no stub reachable -------------------------------------------------------

ENTRY_POINTS = (
    "scripts/build_v14_b2.py", "scripts/build_v14_drc_components.py", "scripts/build_v14_drc.py",
    "scripts/build_v14_primary_2023.py", "scripts/fit_v14_hedonic.py",
    "scripts/build_v14_check_sources.py", "scripts/build_v14_check_inputs.py",
    "scripts/rerun_v14_score.py",
)


def _local_imports(path: Path) -> set[Path]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names = []
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        for name in names:
            candidate = BACKEND / (name.replace(".", "/") + ".py")
            if candidate.is_file():
                found.add(candidate)
    return found


def reachable_modules() -> set[Path]:
    seen: set[Path] = set()
    todo = [BACKEND / entry for entry in ENTRY_POINTS]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        todo.extend(_local_imports(path) - seen)
    return seen


def test_no_stub_reachable_from_holdout_entry_points() -> None:
    modules = reachable_modules()
    assert BACKEND / "georgist/v14_fit_joins.py" in modules
    offenders = sorted(
        str(path.relative_to(BACKEND)) for path in modules
        if "stub" in path.stem.lower() or "dryrun" in str(path) or "TEMP_STUB" in path.read_text(encoding="utf-8")
    )
    assert offenders == []


# --- 6. synthetic fixtures only -------------------------------------------------


def test_fixture_files_are_synthetic_and_never_match_production(tmp_path: Path) -> None:
    paths = write_join_files(tmp_path, ["Z1", "Z2"], no_cell=["Z2"])
    production = {MERGE_MAP_SHA256, IZ_LOOKUP_SHA256, NO_CELL_LIST_SHA256}
    for path in paths.values():
        assert ".SYNTHETIC." in path.name
        assert hashlib.sha256(path.read_bytes()).hexdigest() not in production


def test_fixture_module_reads_no_real_input() -> None:
    source = (BACKEND / "v14_dryrun" / "join_fixture.py").read_text(encoding="utf-8")
    for marker in ("/workspace", "/tmp/", "merge_map_v14", "dz2011_iz2011_ca_lookup", "AM2_s3_fit_no_cell"):
        assert marker not in source


def test_duplicate_join_zone_refused_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "iz.SYNTHETIC.csv"
    path.write_text("DZ2011,IZ2011,CA\nZ1,IZ1,CA1\nZ1,IZ2,CA1\n", encoding="utf-8")
    monkeypatch.setitem(JOIN_PINS, "iz_lookup", _sha256(path))
    with pytest.raises(JoinError) as raised:
        read_iz_lookup(path)
    assert str(raised.value) == "B2_IZ_LOOKUP: REFUSED: DZ2011 row 2: expected unique, got duplicate Z1"


def test_build_fits_joined_rows_and_discloses_no_cell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.build_v14_b2 as b2

    paths = write_join_files(tmp_path, ["Z1", "Z2"], no_cell=["Z2"])
    _pin(monkeypatch, paths)
    sales = [
        {"zone": z, "year": 2021, "price": "1", "median_price": "1", "n_sales": 6} for z in ("Z1", "Z2")
    ]
    monkeypatch.setattr(b2, "assert_house_sales_pin", lambda _p: None)
    monkeypatch.setattr(b2, "adapt_house_sales", lambda *_a, **_k: sales)
    for name in ("adapt_plot_split", "adapt_crosswalk", "adapt_access"):
        monkeypatch.setattr(b2, name, lambda *_a, **_k: [])
    monkeypatch.setattr(
        b2, "adapt_sold_tfa",
        lambda *_a, **_k: [{"zone": z, "year": 2021, "sold_tfa_mean": "50"} for z in ("Z1", "Z2")],
    )
    monkeypatch.setattr(b2, "adapt_bedrooms", lambda *_a, **_k: {"rows": []})
    monkeypatch.setattr(b2, "_am2_payload", lambda *_a, **_k: {})
    monkeypatch.setattr(
        b2, "run_d7_chain",
        lambda **_k: b2.D7ChainResult(status="passed", d7_sha256="a" * 64, message="", manifest={}),
    )
    seen: list[list[dict]] = []
    monkeypatch.setattr(b2, "fit_headline", lambda rows, d7_sha256=None: seen.append(rows))
    args = Namespace(**{k: Path("x") for k in (
        "house_sales", "plot_split", "crosswalk", "sold_tfa", "access", "bedrooms",
        "filter1_script", "filter1_output", "filter2_script", "filter2_output")}, **paths)
    payload = b2.build(args)
    assert [row["zone"] for row in seen[0]] == ["Z1"]
    assert seen[0][0]["iz"] == "IZ1" and seen[0][0]["cell"] == "c"
    assert [row["zone"] for row in payload["fit_rows"]] == ["Z1"]
    assert payload["no_cell_fit"] == {"count": 1, "zones": ["Z2"]}
