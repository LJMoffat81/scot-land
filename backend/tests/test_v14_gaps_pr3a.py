"""PR 3a DRC components, 2023 primary estimates, and the full frozen set.

SYNTHETIC fixtures only. No 2024 price cell is read.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from georgist.v14_score_report import (
    FROZEN_SET_KEYS,
    PIN_TABLE as MERGE_PINS,
    PR3_RECORDED_WHEN_PRESENT,
    RECORDED_FILES,
    frozen_set_members,
    sha256_file,
)
from scripts.build_v14_check_inputs import load_source
from scripts.build_v14_drc import main as b1_main
from scripts.build_v14_drc_components import PIN_TABLE, build_components, copy_pin_table
from scripts.build_v14_primary_2023 import main as primary_main
from scripts.rerun_v14_score import main as score_main
from test_v14_pipeline_b import _zone
from v14_dryrun.dryrun import run as dry_run

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v14_pr3a"
SENTINEL = "SENTINEL_PRICE"
SUBSET_SHA = "f4e2d5a9e316dd556546b8c72e44d2dd96a38753a68145bf8409cfe30906c652"
LT = "all_ages_share_lt005"
MID = "all_ages_share_005_010"
GT = "all_ages_share_gt010"
HAND = {
    "ZA1": ("filled", 0.5, 0.25, 0.25),
    "ZA2": ("filled", 0.25, 0.25, 0.5),
    "ZA3": ("borrowed", 0.375, 0.25, 0.375),
    "ZB1": ("filled", 0.5, 0.5, 0.0),
    "ZB2": ("filled", 0.0, 0.5, 0.5),
    "ZA4": ("borrowed_national", 0.25, 0.5, 0.25),
}
PRIMARY_HAND = {
    "Z1": {"share": 0.6, "land_per_home": 60.0},
    "Z2": {"share": 0.75, "land_per_home": 60.0},
    "Z3": {"share": 0.8, "land_per_home": 40.0},
    "Z4": {"share": 0.5, "land_per_home": 45.0},
}


def _paths() -> dict[str, Path]:
    return {
        "epc": FIXTURES / "epc.csv",
        "nrs2017": FIXTURES / "nrs2017.csv",
        "plot_bands": FIXTURES / "plot_bands.csv",
        "ur6": FIXTURES / "ur6.csv",
    }


def _pins_for(paths: dict[str, Path]) -> dict[str, str]:
    pins = copy_pin_table()
    for name, path in paths.items():
        pins[name] = sha256_file(path)
    return pins


def _records(paths: dict[str, Path] | None = None, pins: dict[str, str] | None = None) -> list[dict]:
    used = _paths() if paths is None else paths
    return build_components(used, pins=_pins_for(used) if pins is None else pins)


def _component_error(paths: dict[str, Path], pins: dict[str, str]) -> str:
    with pytest.raises(Exception) as raised:
        build_components(paths, pins=pins)
    return str(raised.value)


def _sale(zone: str, year: object, price: object, count: object = "2") -> dict:
    return {
        "zone": zone,
        "year": year,
        "n_sales": count,
        "price": price,
        "median_price": price,
    }


def _baseline_sales() -> list[dict]:
    rows = []
    for zone, year, price in (
        ("Z1", 2021, "1"),
        ("Z1", 2022, "2"),
        ("Z1", 2023, "80"),
        ("Z1", 2023, "120"),
        ("Z2", 2021, "3"),
        ("Z2", 2023, "80"),
        ("Z3", 2022, "4"),
        ("Z3", 2023, "50"),
        ("Z4", 2021, "5"),
        ("Z4", 2023, "90"),
    ):
        count = "1" if zone == "Z1" and year == 2023 else "2"
        if zone == "Z2":
            count = "4"
        if zone == "Z3":
            count = "1"
        if zone == "Z4":
            count = "3"
        rows.append(_sale(zone, year, price, count))
    return rows


def _baseline_drc() -> dict[str, float]:
    return {"Z1": 40.0, "Z2": 20.0, "Z3": 10.0, "Z4": 45.0}


def _write_primary_inputs(tmp_path: Path, sales: list[dict], drc: dict[str, float]) -> tuple[Path, Path]:
    b2 = tmp_path / "b2.json"
    costs = tmp_path / "drc.json"
    b2.write_text(
        json.dumps({"label": "SYNTHETIC", "house_sales": sales}, indent=2) + "\n",
        encoding="utf-8",
    )
    costs.write_text(json.dumps(drc) + "\n", encoding="utf-8")
    return b2, costs


def _primary_outs(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "primary_estimates_2023.json", tmp_path / "builder_output_2023.json"


def _run_primary(b2: Path, drc: Path, primary: Path, builder: Path) -> int:
    return primary_main(
        [
            "--b2-out",
            str(b2),
            "--drc",
            str(drc),
            "--primary-out",
            str(primary),
            "--builder-out",
            str(builder),
        ]
    )


def _zones(year: int) -> list[dict]:
    zones = []
    for index in range(8):
        zones.append(
            _zone(
                f"Z{index}",
                year=year,
                ur6=1 if index < 4 else 2,
                share=0.2 + 0.01 * index,
                price=float(index + 1),
                land_per_home=5.0 if index < 4 else 2.0,
            )
        )
    return zones


def _frozen_files(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "frozen"
    root.mkdir()
    files = {
        "merge_map": root / "merge.csv",
        "hedonic_coefs_2021_22": root / "coefs.json",
        "code_sha8_block": root / "sha8.json",
        "check3_plot_passes": root / "check3.json",
        "check4_rent_route": root / "check4.json",
        "ur6": root / "ur6.json",
        "dz2022_keys": root / "dz.json",
    }
    files["merge_map"].write_text("# SYNTHETIC\ndz2011,cell\nS01,c\n", encoding="utf-8")
    for key, path in files.items():
        if key != "merge_map":
            path.write_text('{"label": "SYNTHETIC"}\n', encoding="utf-8")
    return files


def _frozen_flags(files: dict[str, Path], *, drop: str | None = None) -> list[str]:
    pairs = [
        ("merge_map", "--merge-map"),
        ("hedonic_coefs_2021_22", "--hedonic-coefs"),
        ("code_sha8_block", "--sha8-block"),
        ("check3_plot_passes", "--check3-plot-passes"),
        ("check4_rent_route", "--check4-rent-route"),
        ("ur6", "--ur6"),
        ("dz2022_keys", "--dz2022-keys"),
    ]
    flags: list[str] = []
    for name, flag in pairs:
        if name == drop:
            continue
        flags.extend([flag, str(files[name])])
    return flags


def test_drc_components_baseline() -> None:
    """SYNTHETIC. Blank zones borrow council x UR6, else the UR6 national share."""
    for path in FIXTURES.iterdir():
        if path.is_file():
            assert "SYNTHETIC" in path.read_text(encoding="utf-8")
    records = _records()
    assert [row["dz2011"] for row in records] == ["ZA1", "ZA2", "ZA3", "ZA4", "ZB1", "ZB2"]
    by_zone = {row["dz2011"]: row["estate_row"] for row in records}
    for zone, (source, lt, mid, gt) in HAND.items():
        estate = by_zone[zone]
        assert estate["_plot_bands_source"] == source
        assert float(estate[LT]) == lt
        assert float(estate[MID]) == mid
        assert float(estate[GT]) == gt


def test_drc_components_then_b1_runs(tmp_path: Path) -> None:
    """SYNTHETIC. B1 values the component file and does not raise PendingSourceError."""
    out = tmp_path / "components.json"
    out.write_text(json.dumps(_records()) + "\n", encoding="utf-8")
    drc = tmp_path / "drc.json"
    code = b1_main(["--drc-json", str(drc), "--components", str(out)])
    assert code == 0
    assert drc.is_file()
    payload = json.loads(drc.read_text(encoding="utf-8"))
    assert set(payload) == set(HAND)


@pytest.mark.parametrize("name", ("epc", "plot_bands", "ur6"))
def test_drc_components_pin_wrong(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """SYNTHETIC. One changed input byte refuses before plot bands are borrowed."""
    paths = dict(_paths())
    changed = tmp_path / paths[name].name
    changed.write_bytes(paths[name].read_bytes() + b"\n")
    paths[name] = changed
    pins = _pins_for(_paths())
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.borrow_plot_bands",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    out = tmp_path / "components.json"
    message = _component_error(paths, pins)
    assert message == (
        f"B1_COMPONENTS: REFUSED: {name} sha256: expected {pins[name]}, got {sha256_file(changed)}"
    )
    assert calls["n"] == 0
    assert not out.exists()


@pytest.mark.parametrize("name", ("epc", "plot_bands", "ur6", "nrs2017"))
def test_drc_components_pin_shared_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """SYNTHETIC. A shared 8-character prefix is a mismatch."""
    paths = _paths()
    actual = sha256_file(paths[name])
    forged = actual[:8] + ("0" * 56)
    if forged == actual:
        forged = actual[:8] + ("1" * 56)
    pins = _pins_for(paths)
    pins[name] = forged
    calls = {"borrow": 0, "reader": 0}
    reader = {
        "epc": "load_epc",
        "plot_bands": "load_plot_bands",
        "ur6": "load_ur6",
        "nrs2017": "load_nrs2017",
    }[name]
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.borrow_plot_bands",
        lambda *_args, **_kwargs: calls.__setitem__("borrow", calls["borrow"] + 1),
    )
    monkeypatch.setattr(
        f"scripts.build_v14_drc_components.{reader}",
        lambda *_args, **_kwargs: calls.__setitem__("reader", calls["reader"] + 1),
    )
    assert _component_error(paths, pins) == (
        f"B1_COMPONENTS: REFUSED: {name} sha256: expected {forged}, got {actual}"
    )
    assert calls == {"borrow": 0, "reader": 0}
    assert not (tmp_path / "components.json").exists()


def test_drc_components_pending_pin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SYNTHETIC. PENDING_FULL_SHA is refused from a copy and the production table stays."""
    original = copy_pin_table()
    pins = copy_pin_table()
    pins["nrs2017"] = "PENDING_FULL_SHA"
    calls = {"nrs": 0, "borrow": 0}
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.load_nrs2017",
        lambda *_args, **_kwargs: calls.__setitem__("nrs", calls["nrs"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.borrow_plot_bands",
        lambda *_args, **_kwargs: calls.__setitem__("borrow", calls["borrow"] + 1),
    )
    assert _component_error(_paths(), pins) == (
        "B1_COMPONENTS: REFUSED: pin: expected full sha256, got PENDING_FULL_SHA"
    )
    assert calls == {"nrs": 0, "borrow": 0}
    assert not (tmp_path / "components.json").exists()
    assert PIN_TABLE == original


@pytest.mark.parametrize("name", ("nrs2017",))
def test_prod_pins_full_sha(name: str) -> None:
    """SYNTHETIC. The production nrs2017 pin is the full NRS dwellings digest."""
    assert PIN_TABLE[name] == "b9bd3364ade0a843a3157fe7e33de5003144f18c54f87c9e410c4dd3fc04a9da"
    assert "PENDING_FULL_SHA" not in PIN_TABLE.values()
    for value in PIN_TABLE.values():
        assert re.fullmatch(r"[0-9a-f]{64}", str(value))


@pytest.mark.parametrize(
    "value",
    ("abcd1234", "a" * 63, "not-a-sha", ""),
)
def test_pin_not_full_sha(value: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SYNTHETIC. A short, non-hex, or blank pin is refused before the NRS reader."""
    pins = copy_pin_table()
    pins["nrs2017"] = value
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.load_nrs2017",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    shown = "blank" if value == "" else value
    assert _component_error(_paths(), pins) == (
        f"B1_COMPONENTS: REFUSED: pin: expected full sha256, got {shown}"
    )
    assert calls["n"] == 0
    assert not (tmp_path / "components.json").exists()


def test_nrs_pin_not_fixture_subset() -> None:
    """SYNTHETIC. The production pin is not the real-data subset digest."""
    assert PIN_TABLE["nrs2017"] != SUBSET_SHA
    needle = "/".join(
        [
            "fixtures",
            "surface_costs_dz2011_inputs",
            "nrs_dwelling_mix_2011_fallback.csv",
        ]
    )
    assert needle not in Path(__file__).read_text(encoding="utf-8")
    for path in FIXTURES.rglob("*"):
        if path.is_file():
            assert needle not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ("epc", "nrs2017", "plot_bands", "ur6"))
def test_drc_components_missing_file(tmp_path: Path, name: str) -> None:
    """SYNTHETIC. A missing input file is named and nothing is written."""
    paths = dict(_paths())
    missing = tmp_path / "absent.csv"
    paths[name] = missing
    pins = _pins_for(_paths())
    assert _component_error(paths, pins) == f"B1_COMPONENTS: ERROR: file: expected {missing}, got absent"
    assert not (tmp_path / "components.json").exists()


def test_drc_components_blank_and_short(tmp_path: Path) -> None:
    """SYNTHETIC. A blank code and a short row each refuse before the output exists."""
    blank = tmp_path / "blank.csv"
    lines = (FIXTURES / "epc.csv").read_text(encoding="utf-8").splitlines()
    header, first, rest = lines[1], lines[2], lines[3:]
    cells = first.split(",")
    cells[0] = ""
    blank.write_text("\n".join(["# SYNTHETIC", header, ",".join(cells), *rest]) + "\n", encoding="utf-8")
    paths = dict(_paths())
    paths["epc"] = blank
    pins = _pins_for(paths)
    assert _component_error(paths, pins) == "B1_COMPONENTS: ERROR: code row 1: expected value, got blank"
    assert not (tmp_path / "components.json").exists()

    short = tmp_path / "short.csv"
    short_cells = first.split(",")[:1]
    short.write_text("\n".join(["# SYNTHETIC", header, ",".join(short_cells), *rest]) + "\n", encoding="utf-8")
    paths["epc"] = short
    pins = _pins_for(paths)
    width = len(header.split(","))
    assert _component_error(paths, pins) == (
        f"B1_COMPONENTS: ERROR: row 1: expected {width} fields, got {len(short_cells)}"
    )
    assert not (tmp_path / "components.json").exists()


def test_drc_components_no_price_column_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A planted price column is not read."""
    planted = tmp_path / "epc.csv"
    lines = (FIXTURES / "epc.csv").read_text(encoding="utf-8").splitlines()
    header = lines[1] + ",price"
    body = [line + "," + SENTINEL for line in lines[2:]]
    planted.write_text("\n".join(["# SYNTHETIC", header, *body]) + "\n", encoding="utf-8")
    paths = dict(_paths())
    paths["epc"] = planted
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_drc_components.read_price_cell",
        lambda value: calls.__setitem__("n", calls["n"] + 1) or value,
    )
    records = build_components(paths, pins=_pins_for(paths))
    blob = json.dumps(records)
    assert SENTINEL not in blob
    assert calls["n"] == 0


def test_primary_2023_baseline(tmp_path: Path) -> None:
    """SYNTHETIC. Share and land per home use only the 2023 sales-weighted mean."""
    b2, drc = _write_primary_inputs(tmp_path, _baseline_sales(), _baseline_drc())
    primary, builder = _primary_outs(tmp_path)
    assert _run_primary(b2, drc, primary, builder) == 0
    estimates = {row["zone"]: row for row in json.loads(primary.read_text(encoding="utf-8"))["zones"]}
    assert set(estimates) == set(PRIMARY_HAND)
    for zone, hand in PRIMARY_HAND.items():
        assert estimates[zone]["share"] == hand["share"]
        assert estimates[zone]["land_per_home"] == hand["land_per_home"]


def test_primary_2023_skips_2004_2022_without_price(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. Years 2004, 2015 and 2022 do not read price."""
    sales = [
        _sale("Z1", 2004, SENTINEL),
        _sale("Z2", 2015, SENTINEL),
        _sale("Z3", 2022, SENTINEL),
        *_baseline_sales(),
    ]
    seen: list[object] = []

    def spy(value: object) -> object:
        seen.append(value)
        return value

    monkeypatch.setattr("scripts.build_v14_primary_2023.read_price_field", spy)
    b2, drc = _write_primary_inputs(tmp_path, sales, _baseline_drc())
    primary, builder = _primary_outs(tmp_path)
    base = tmp_path / "base"
    base.mkdir()
    base_b2, base_drc = _write_primary_inputs(base, _baseline_sales(), _baseline_drc())
    base_primary, base_builder = _primary_outs(tmp_path / "base")
    assert _run_primary(base_b2, base_drc, base_primary, base_builder) == 0
    assert _run_primary(b2, drc, primary, builder) == 0
    assert json.loads(primary.read_text(encoding="utf-8")) == json.loads(base_primary.read_text(encoding="utf-8"))
    assert json.loads(builder.read_text(encoding="utf-8")) == json.loads(base_builder.read_text(encoding="utf-8"))
    assert SENTINEL not in seen
    assert SENTINEL not in primary.read_text(encoding="utf-8")
    assert SENTINEL not in builder.read_text(encoding="utf-8")


def test_primary_2023_refuses_2024_before_price(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. Year 2024 refuses before that row's price is read."""
    sales = [_sale("Z1", 2024, SENTINEL), *_baseline_sales()]
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.read_price_field",
        lambda value: calls.__setitem__("n", calls["n"] + 1) or value,
    )
    b2, drc = _write_primary_inputs(tmp_path, sales, _baseline_drc())
    primary, builder = _primary_outs(tmp_path)
    assert _run_primary(b2, drc, primary, builder) == 1
    assert capsys.readouterr().err == "B4_PRIMARY_2023: REFUSED: year: expected <2024, got 2024\n"
    assert calls["n"] == 0
    assert not primary.exists()
    assert not builder.exists()


def test_primary_2023_year_blank_short_nonint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A blank, missing, or non-integer year does not read price."""
    cases = [
        ({"zone": "Z1", "year": "", "n_sales": "1", "price": SENTINEL}, "blank"),
        ({"zone": "Z1", "n_sales": "1", "price": SENTINEL}, "short"),
        ({"zone": "Z1", "year": "20x3", "n_sales": "1", "price": SENTINEL}, "20x3"),
    ]
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.read_price_field",
        lambda value: calls.__setitem__("n", calls["n"] + 1) or value,
    )
    for row, got in cases:
        case = tmp_path / got
        case.mkdir()
        b2, drc = _write_primary_inputs(case, [row], _baseline_drc())
        primary, builder = _primary_outs(case)
        assert _run_primary(b2, drc, primary, builder) == 1
        assert capsys.readouterr().err == (
            f"B4_PRIMARY_2023: ERROR: year row 1: expected integer, got {got}\n"
        )
        assert not primary.exists()
        assert not builder.exists()
    assert calls["n"] == 0


def test_primary_2023_dropped_no_price(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """SYNTHETIC. One zone with no 2023 sales stops and writes neither file."""
    sales = [row for row in _baseline_sales() if not (row["zone"] == "Z4" and row["year"] == 2023)]
    b2, drc = _write_primary_inputs(tmp_path, sales, _baseline_drc())
    primary, builder = _primary_outs(tmp_path)
    assert _run_primary(b2, drc, primary, builder) == 1
    captured = capsys.readouterr()
    assert captured.out == "dropped_no_price=1 dropped_no_cost=0\n"
    assert captured.err == ""
    assert not primary.exists()
    assert not builder.exists()


def test_primary_2023_dropped_no_cost(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """SYNTHETIC. One zone with no DRC row stops and writes neither file."""
    costs = _baseline_drc()
    del costs["Z4"]
    b2, drc = _write_primary_inputs(tmp_path, _baseline_sales(), costs)
    primary, builder = _primary_outs(tmp_path)
    assert _run_primary(b2, drc, primary, builder) == 1
    captured = capsys.readouterr()
    assert captured.out == "dropped_no_price=0 dropped_no_cost=1\n"
    assert captured.err == ""
    assert not primary.exists()
    assert not builder.exists()


def test_builder_output_2023_fields_exact(tmp_path: Path) -> None:
    """SYNTHETIC. Builder rows carry only the B6 builder fields."""
    b2, drc = _write_primary_inputs(tmp_path, _baseline_sales(), _baseline_drc())
    primary, builder = _primary_outs(tmp_path)
    assert _run_primary(b2, drc, primary, builder) == 0
    rows = json.loads(builder.read_text(encoding="utf-8"))["zones"]
    assert rows
    for row in rows:
        assert set(row) == {"zone", "price", "count_in_1d", "unavailable", "model_failure", "hla"}
    load_source(builder, "builder_output")


def test_primary_estimates_2023_fields_exact(tmp_path: Path) -> None:
    """SYNTHETIC. Primary rows carry only the 2023 estimate fields."""
    b2, drc = _write_primary_inputs(tmp_path, _baseline_sales(), _baseline_drc())
    primary, builder = _primary_outs(tmp_path)
    assert _run_primary(b2, drc, primary, builder) == 0
    rows = json.loads(primary.read_text(encoding="utf-8"))["zones"]
    assert rows
    for row in rows:
        assert set(row) == {"zone", "share", "land_per_home", "unavailable", "count_in_1d"}
    load_source(primary, "primary_estimates")


@pytest.mark.parametrize("kind", ("b2_out", "drc"))
def test_primary_2023_missing_input(tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str) -> None:
    """SYNTHETIC. A missing B2 or DRC file writes neither output."""
    b2, drc = _write_primary_inputs(tmp_path, _baseline_sales(), _baseline_drc())
    primary, builder = _primary_outs(tmp_path)
    missing = tmp_path / "absent.json"
    if kind == "b2_out":
        b2 = missing
    else:
        drc = missing
    assert _run_primary(b2, drc, primary, builder) == 1
    assert capsys.readouterr().err == f"B4_PRIMARY_2023: ERROR: file: expected {missing}, got absent\n"
    assert not primary.exists()
    assert not builder.exists()


@pytest.mark.parametrize("column", ("price", "count", "zone"))
def test_primary_2023_blank_short(tmp_path: Path, capsys: pytest.CaptureFixture[str], column: str) -> None:
    """SYNTHETIC. A blank cell and a short row each refuse before either output exists."""
    full = {"zone": "Z1", "year": 2023, "count": "2", "price": "100"}
    blank = dict(full)
    blank[column] = ""
    short = dict(full)
    if column == "price":
        del short["price"]
        got_fields = 3
    elif column == "count":
        del short["count"]
        got_fields = 2
    else:
        del short["zone"]
        got_fields = 0
    for label, row, message in (
        (
            "blank",
            blank,
            f"B4_PRIMARY_2023: ERROR: {column} row 1: expected value, got blank",
        ),
        (
            "short",
            short,
            f"B4_PRIMARY_2023: ERROR: row 1: expected 4 fields, got {got_fields}",
        ),
    ):
        case = tmp_path / f"{column}-{label}"
        case.mkdir()
        b2, drc = _write_primary_inputs(case, [row], {"Z1": 10.0})
        primary, builder = _primary_outs(case)
        assert _run_primary(b2, drc, primary, builder) == 1
        assert capsys.readouterr().err == message + "\n"
        assert not primary.exists()
        assert not builder.exists()


@pytest.mark.parametrize(
    "name",
    (
        "merge_map",
        "hedonic_coefs_2021_22",
        "code_sha8_block",
        "check3_plot_passes",
        "check4_rent_route",
        "ur6",
        "dz2022_keys",
    ),
)
def test_holdout_refuses_without_full_frozen_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    """SYNTHETIC. Holdout refuses when one frozen-set path is absent."""
    files = _frozen_files(tmp_path)
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps({"primary_zones": _zones(2023), "secondary_zones": _zones(2023)}),
        encoding="utf-8",
    )
    lock = tmp_path / "holdout.lock"
    report = tmp_path / "report.json"
    calls = {"n": 0}

    def spy(*_args, **_kwargs):
        calls["n"] += 1
        raise AssertionError("scored")

    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    assert score_main(
        [
            "--out",
            str(report),
            "--holdout-2023",
            "--check-inputs",
            str(checks),
            "--lock-path",
            str(lock),
            *_frozen_flags(files, drop=name),
        ]
    ) == 1
    assert capsys.readouterr().err == (
        f"HOLDOUT_2023: REFUSED: frozen_set {name}: expected path, got absent\n"
    )
    assert calls["n"] == 0
    assert not lock.exists()
    assert not report.exists()


def test_score_2024_refuses_legacy_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A lock without frozen_set does not score."""
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps({"primary_zones": _zones(2024), "secondary_zones": _zones(2024)}),
        encoding="utf-8",
    )
    lock = tmp_path / "legacy.lock"
    lock.write_text(
        json.dumps({"inputs_sha256": "abc", "commit": "abc123abc123", "label": "seen, not out-of-sample"}) + "\n",
        encoding="utf-8",
    )
    report = tmp_path / "report.json"
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.rerun_v14_score._score_holdout",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    assert score_main(
        [
            "--out",
            str(report),
            "--score-2024",
            "--check-inputs",
            str(checks),
            "--lock-path",
            str(lock),
        ]
    ) == 1
    assert capsys.readouterr().err == "SCORE_2024: REFUSED: lock frozen_set: expected present, got absent\n"
    assert calls["n"] == 0
    assert not report.exists()


def test_holdout_with_full_frozen_set_writes_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. All seven paths write frozen_set and its digest."""
    files = _frozen_files(tmp_path)
    monkeypatch.setitem(MERGE_PINS, "merge_map", sha256_file(files["merge_map"]))
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps({"primary_zones": _zones(2023), "secondary_zones": _zones(2023)}),
        encoding="utf-8",
    )
    lock = tmp_path / "holdout.lock"
    report = tmp_path / "holdout" / "report.json"
    assert score_main(
        [
            "--out",
            str(report),
            "--holdout-2023",
            "--check-inputs",
            str(checks),
            "--lock-path",
            str(lock),
            *_frozen_flags(files),
        ]
    ) == 0
    payload = json.loads(lock.read_text(encoding="utf-8"))
    assert set(payload["frozen_set"]) == set(FROZEN_SET_KEYS)
    assert len(payload["frozen_set_sha256"]) == 64


def test_dryrun_3a_steps_no_stub(tmp_path: Path) -> None:
    """SYNTHETIC. B1 and the 2023 primary step run through the driver."""
    source = Path(__file__).resolve().parents[1] / "v14_dryrun" / "dryrun.py"
    text = source.read_text(encoding="utf-8")
    assert "def stub" not in text
    result = dry_run(tmp_path)
    assert result["status"] == "passed"
    assert Path(result["components"]).is_file()
    assert Path(result["drc"]).is_file()
    assert Path(result["primary"]).is_file()
    assert Path(result["builder"]).is_file()
    assert json.loads(Path(result["drc"]).read_text(encoding="utf-8"))


def test_recorded_files_include_pr3a_scripts() -> None:
    """SYNTHETIC. The two new scripts are recorded and no longer optional."""
    for rel in (
        "backend/scripts/build_v14_drc_components.py",
        "backend/scripts/build_v14_primary_2023.py",
    ):
        assert rel in RECORDED_FILES
        assert rel not in PR3_RECORDED_WHEN_PRESENT


def test_holdout_lists_every_missing_frozen_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A holdout names every absent frozen-set member."""
    files = _frozen_files(tmp_path)
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps({"primary_zones": _zones(2023), "secondary_zones": _zones(2023)}),
        encoding="utf-8",
    )
    lock = tmp_path / "holdout.lock"
    report = tmp_path / "report.json"
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.rerun_v14_score._score_holdout",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    flags: list[str] = []
    for name, flag in (
        ("merge_map", "--merge-map"),
        ("hedonic_coefs_2021_22", "--hedonic-coefs"),
        ("code_sha8_block", "--sha8-block"),
        ("check3_plot_passes", "--check3-plot-passes"),
        ("check4_rent_route", "--check4-rent-route"),
        ("ur6", "--ur6"),
        ("dz2022_keys", "--dz2022-keys"),
    ):
        if name in {"merge_map", "ur6"}:
            continue
        flags.extend([flag, str(files[name])])
    assert score_main(
        [
            "--out",
            str(report),
            "--holdout-2023",
            "--check-inputs",
            str(checks),
            "--lock-path",
            str(lock),
            *flags,
        ]
    ) == 1
    assert capsys.readouterr().err == (
        "HOLDOUT_2023: REFUSED: frozen_set merge_map: expected path, got absent\n"
        "HOLDOUT_2023: REFUSED: frozen_set ur6: expected path, got absent\n"
    )
    assert calls["n"] == 0
    assert not lock.exists()
    assert not report.exists()


def test_score_2024_lists_every_missing_frozen_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A partial 2024 frozen set names every absent member."""
    files = _frozen_files(tmp_path)
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps({"primary_zones": _zones(2023), "secondary_zones": _zones(2023)}),
        encoding="utf-8",
    )
    lock = tmp_path / "holdout.lock"
    report = tmp_path / "report.json"
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.rerun_v14_score._score_holdout",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    assert score_main(
        [
            "--out",
            str(report),
            "--score-2024",
            "--check-inputs",
            str(checks),
            "--lock-path",
            str(lock),
            "--merge-map",
            str(files["merge_map"]),
        ]
    ) == 1
    assert capsys.readouterr().err == (
        "SCORE_2024: REFUSED: frozen_set: expected complete, got partial\n"
        "SCORE_2024: REFUSED: frozen_set hedonic_coefs_2021_22: expected path, got absent\n"
        "SCORE_2024: REFUSED: frozen_set code_sha8_block: expected path, got absent\n"
        "SCORE_2024: REFUSED: frozen_set check3_plot_passes: expected path, got absent\n"
        "SCORE_2024: REFUSED: frozen_set check4_rent_route: expected path, got absent\n"
        "SCORE_2024: REFUSED: frozen_set ur6: expected path, got absent\n"
        "SCORE_2024: REFUSED: frozen_set dz2022_keys: expected path, got absent\n"
    )
    assert calls["n"] == 0
    assert not report.exists()


def test_score_2024_different_check_inputs_scores_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A 2023 holdout then one 2024 score on different check inputs."""
    files = _frozen_files(tmp_path)
    monkeypatch.setitem(MERGE_PINS, "merge_map", sha256_file(files["merge_map"]))
    holdout_checks = tmp_path / "holdout_checks.json"
    holdout_checks.write_text(
        json.dumps({"primary_zones": _zones(2023), "secondary_zones": _zones(2023)}),
        encoding="utf-8",
    )
    score_rows = [{"zone": f"Z{index}", "year": 2024} for index in range(8)]
    score_checks = tmp_path / "score_checks.json"
    score_checks.write_text(
        json.dumps(
            {"primary_zones": score_rows, "secondary_zones": [dict(row) for row in score_rows]}
        ),
        encoding="utf-8",
    )
    year_file = tmp_path / "year.csv"
    year_file.write_text("# SYNTHETIC\nyear\n2024\n", encoding="utf-8")
    lock = tmp_path / "holdout.lock"
    assert score_main(
        [
            "--out",
            str(tmp_path / "holdout" / "report.json"),
            "--holdout-2023",
            "--check-inputs",
            str(holdout_checks),
            "--lock-path",
            str(lock),
            *_frozen_flags(files),
        ]
    ) == 0
    calls = {"n": 0}

    def spy(*_args, **_kwargs):
        calls["n"] += 1
        return {
            "primary": {"gating_pass": False},
            "secondary": {"gating_pass": False},
            "publication": {"outcome": "both_fail_publish_neither"},
            "checks_include_hbu": False,
        }

    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    score_report = tmp_path / "score" / "report.json"
    command = [
        "--out",
        str(score_report),
        "--score-2024",
        "--check-inputs",
        str(score_checks),
        "--lock-path",
        str(lock),
        "--year-file",
        str(year_file),
        *_frozen_flags(files),
    ]
    rc = score_main(command)
    err = capsys.readouterr().err
    assert rc == 0, err
    assert calls["n"] == 1
    assert score_report.is_file()
    assert json.loads(lock.read_text(encoding="utf-8"))["score_2024"] is True
    assert score_main(
        [
            "--out",
            str(tmp_path / "again" / "report.json"),
            "--score-2024",
            "--check-inputs",
            str(score_checks),
            "--lock-path",
            str(lock),
            "--year-file",
            str(year_file),
            *_frozen_flags(files),
        ]
    ) == 1
    assert "second 2024 run refused" in capsys.readouterr().err
    assert calls["n"] == 1
