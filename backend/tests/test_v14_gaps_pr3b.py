"""PR 3b hedonic fit CLI, check sources, and the 2023 year flag.

SYNTHETIC fixtures only. No 2024 price cell is read.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from georgist.surface_v13 import capitalised_rent_land
from georgist.surface_v14_checks import _pass_at_ints, _plot
from georgist.v14_d7_chain import D7_FILTER2_OUTPUT_SHA256, D7_SOURCE_SHA256
from georgist.v14_score_report import PIN_TABLE as MERGE_PINS
from georgist.v14_score_report import (
    PR3_RECORDED_WHEN_PRESENT,
    RECORDED_FILES,
    frozen_set_lock_hash,
    frozen_set_members,
    mark_score_2024,
    sha256_file,
)
from scripts.build_v14_check_inputs import load_source
from scripts.build_v14_check_inputs import main as b6_main
from scripts.build_v14_check_sources import PIN_TABLE as SOURCE_PINS
from scripts.build_v14_check_sources import (
    CheckSourceError,
    build_check3,
    build_check4,
    build_dz2022_keys,
    build_ur6,
    copy_pin_table,
    save_check3,
    save_check4,
    save_dz2022,
    save_ur6,
)
from scripts.build_v14_check_sources import main as source_main
from scripts.build_v14_drc_components import PIN_TABLE as COMPONENT_PINS
from scripts.fit_v14_hedonic import FitError, fit_b2, project_records, _test_set_s_c3_maxiter
from scripts.fit_v14_hedonic import main as fit_main
from scripts.rerun_v14_score import main as score_main
from v14_dryrun.dryrun import run as dry_run

D7 = D7_FILTER2_OUTPUT_SHA256
RENT_PIN = "21190bfc70e1fee3a5b7e1804bba966b7777eb82e21b42ac43a35b77c5d63f11"
NRS_PIN = "b9bd3364ade0a843a3157fe7e33de5003144f18c54f87c9e410c4dd3fc04a9da"
GIS_PIN = "3320797696c876e7cb6b41163724f0346cbeb284f89d6792bf87a1e9c600735d"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v14_pr3b"
PLOT_HEADER = [
    "code",
    "pass_20",
    "pass_30",
    "pass_40",
    "all_20",
    "all_30",
    "all_40",
    "dz22_20",
    "dz22_30",
    "dz22_40",
    "detached_plot_m2",
    "measured_detached_pass",
]
RENT_HEADER = [
    "zone_id",
    "central",
    "low",
    "high",
    "status",
    "dwellings",
    "la_code",
    "ur6_class",
    "sales_n",
    "flags",
    "evidence_window",
    "evidence_oldest_year",
    "pooling_config_sha256",
]


def _row(zone: str, year: object, cell: str, price: object, ur3: str) -> dict:
    area = 40.0 if cell == "c" else 70.0
    return {
        "year": year,
        "zone": zone,
        "cell": cell,
        "price": price,
        "n_sales": 6,
        "a_m2": area,
        "f_m2": 50.0,
        "ratio_mean": 1.0,
        "iz": "IZ1",
        "ca": "CA1",
        "ur3": ur3,
    }


def _baseline_rows() -> list[dict]:
    rows = []
    for zone, cell, ur3 in (
        ("Z1", "c", "urban"),
        ("Z2", "c", "urban"),
        ("Z3", "d", "rural"),
        ("Z4", "d", "rural"),
    ):
        area = 40.0 if cell == "c" else 70.0
        price = math.exp(1.5 + 0.3 * math.log(area))
        for year in (2021, 2022):
            rows.append(_row(zone, year, cell, price, ur3))
    return rows


def _write_b2(path: Path, rows: list, d7: object | None = D7) -> None:
    payload: dict = {"label": "SYNTHETIC", "fit_rows": rows}
    if d7 is not None:
        payload["d7_sha256"] = d7
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _fit(path: Path, tmp_path: Path) -> dict:
    fit_out = tmp_path / "fitted_hedonic_2023.json"
    zone_out = tmp_path / "fitted_per_zone.json"
    assert fit_main(["--b2-out", str(path), "--fit-out", str(fit_out), "--per-zone-out", str(zone_out)]) == 0
    return {
        "fit": json.loads(fit_out.read_text(encoding="utf-8")),
        "zones": json.loads(zone_out.read_text(encoding="utf-8")),
        "fit_path": fit_out,
        "zone_path": zone_out,
    }


def _s_x2(payload: dict) -> dict:
    return next(item for item in payload["sensitivities"] if item["id"] == "S-x2")


def _csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    lines = ["# SYNTHETIC", ",".join(header)]
    lines.extend(",".join(cells) for cells in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _plot_row(code: str) -> list[str]:
    return [code, "1", "1", "1", "1", "1", "1", "1", "1", "1", "40", "1"]


def _pins_for(paths: dict[str, Path]) -> dict[str, str]:
    pins = copy_pin_table()
    for name, path in paths.items():
        if name in pins and path.is_file():
            pins[name] = sha256_file(path)
    return pins


def _rent_row(zone: str, central: str = "4", low: str = "1") -> list[str]:
    item = {name: "1" for name in RENT_HEADER}
    item["zone_id"] = zone
    item["central"] = central
    item["low"] = low
    return [item[name] for name in RENT_HEADER]


def _count_key(value: object, key: str) -> int:
    if isinstance(value, dict):
        return sum(1 if name == key else 0 for name in value) + sum(
            _count_key(item, key) for item in value.values()
        )
    if isinstance(value, list):
        return sum(_count_key(item, key) for item in value)
    return 0


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


def _frozen_flags(files: dict[str, Path]) -> list[str]:
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
        flags.extend([flag, str(files[name])])
    return flags


def test_pr3b_fixtures_are_labelled_synthetic() -> None:
    """SYNTHETIC. Every committed PR 3b fixture carries the label."""
    found = False
    for path in FIXTURES.rglob("*"):
        if not path.is_file():
            continue
        found = True
        text = path.read_text(encoding="utf-8")
        assert "SYNTHETIC" in text
        assert "\u00a3" not in text
    assert found


def test_fit_cli_baseline(tmp_path: Path) -> None:
    """SYNTHETIC. 2021-2022 rows write the fit and S-x2 fits."""
    path = tmp_path / "b2.json"
    _write_b2(path, _baseline_rows())
    built = _fit(path, tmp_path)
    assert built["fit_path"].is_file()
    assert _s_x2(built["fit"])["status"] == "fit"


def test_fit_cli_excludes_2023(tmp_path: Path) -> None:
    """SYNTHETIC. A 2023 row is left out, and its price does not move the fit."""
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    rows = _baseline_rows()
    _write_b2(first, [*rows, {"year": 2023, "zone": "Z1", "price": 1}])
    _write_b2(second, [*rows, {"year": 2023, "zone": "Z1", "price": 999}])
    left = _fit(first, tmp_path / "left")
    right = _fit(second, tmp_path / "right")
    assert left["fit"]["row_count"] == len(rows)
    assert left["fit"]["beta_by_cell"] == right["fit"]["beta_by_cell"]


def test_fit_cli_refuses_2024_before_price(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. Year 2024 refuses before the price field and the fit."""
    path = tmp_path / "b2.json"
    rows = [*_baseline_rows(), {"year": 2024, "zone": "Z9", "price": "SENTINEL"}]
    _write_b2(path, rows)
    calls = {"price": 0, "fit": 0}
    monkeypatch.setattr(
        "scripts.fit_v14_hedonic.read_price_field",
        lambda value: calls.__setitem__("price", calls["price"] + 1) or value,
    )
    monkeypatch.setattr(
        "scripts.fit_v14_hedonic.fit_headline",
        lambda *_args, **_kwargs: calls.__setitem__("fit", calls["fit"] + 1),
    )
    fit_out = tmp_path / "fitted_hedonic_2023.json"
    zone_out = tmp_path / "fitted_per_zone.json"
    with pytest.raises(FitError) as raised:
        fit_b2(path)
    assert str(raised.value) == "B3_FIT: REFUSED: year: expected <2024, got 2024"
    assert calls == {"price": 0, "fit": 0}
    assert not fit_out.exists()
    assert not zone_out.exists()


@pytest.mark.parametrize(
    "d7",
    [
        D7_SOURCE_SHA256,
        D7[:-1] + ("0" if D7[-1] != "0" else "1"),
        None,
    ],
)
def test_fit_cli_wrong_d7_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, d7: str | None) -> None:
    """SYNTHETIC. A wrong or absent D7 pin records NOT_RUN and still writes the fit."""
    path = tmp_path / "b2.json"
    _write_b2(path, _baseline_rows(), d7)
    calls = {"n": 0}

    def spy(*_args, **_kwargs):
        calls["n"] += 1
        raise AssertionError("S-x2 fit ran")

    monkeypatch.setattr("scripts.fit_v14_hedonic.fit_s_x2", spy)
    built = _fit(path, tmp_path)
    actual = "absent" if d7 is None else d7
    assert _s_x2(built["fit"])["status"] == "NOT_RUN"
    assert _s_x2(built["fit"])["reason"] == (
        "B3_FIT: NOT_RUN: d7_sha256: expected "
        f"{D7}, got {actual}"
    )
    assert calls["n"] == 0
    assert built["fit_path"].is_file()


def test_fit_cli_d7_shared_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. The first eight D7 characters do not count as a match."""
    forged = D7[:8] + ("a" * 56)
    path = tmp_path / "b2.json"
    _write_b2(path, _baseline_rows(), forged)
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.fit_v14_hedonic.fit_s_x2",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    built = _fit(path, tmp_path)
    assert _s_x2(built["fit"])["reason"] == (
        f"B3_FIT: NOT_RUN: d7_sha256: expected {D7}, got {forged}"
    )
    assert calls["n"] == 0


def test_fit_cli_missing_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A missing B2 file refuses before the fit."""
    missing = tmp_path / "absent.json"
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.fit_v14_hedonic.fit_headline",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    out = tmp_path / "fitted_hedonic_2023.json"
    with pytest.raises(FitError) as raised:
        fit_b2(missing)
    assert str(raised.value) == f"B3_FIT: ERROR: file: expected {missing}, got absent"
    assert calls["n"] == 0
    assert not out.exists()


@pytest.mark.parametrize(
    ("year", "got"),
    [("", "blank"), (None, "short"), ("20x3", "20x3")],
)
def test_fit_cli_year_blank_short_nonint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, year: object, got: str
) -> None:
    """SYNTHETIC. A blank, short, or non-integer year refuses before the price."""
    row: dict = {"zone": "Z1", "price": "SENTINEL"}
    if year is not None:
        row["year"] = year
    path = tmp_path / "b2.json"
    _write_b2(path, [row])
    calls = {"price": 0, "fit": 0}
    monkeypatch.setattr(
        "scripts.fit_v14_hedonic.read_price_field",
        lambda value: calls.__setitem__("price", calls["price"] + 1) or value,
    )
    monkeypatch.setattr(
        "scripts.fit_v14_hedonic.fit_headline",
        lambda *_args, **_kwargs: calls.__setitem__("fit", calls["fit"] + 1),
    )
    out = tmp_path / "fitted_hedonic_2023.json"
    with pytest.raises(FitError) as raised:
        fit_b2(path)
    assert str(raised.value) == f"B3_FIT: ERROR: year row 1: expected integer, got {got}"
    assert calls == {"price": 0, "fit": 0}
    assert not out.exists()


@pytest.mark.parametrize("mode", ["nonconverge", "one_group"])
def test_fit_cli_nonconverging(tmp_path: Path, mode: str) -> None:
    """SYNTHETIC. A failed MixedLM marks the zone unavailable and does not escape."""
    if mode == "nonconverge":
        rows = []
        for zone, ur3, area in (
            ("Z1", "urban", 40.0),
            ("Z2", "urban", 55.0),
            ("Z3", "rural", 70.0),
            ("Z4", "rural", 90.0),
        ):
            # Price rises with area, so a converged fit would have β > 0.
            price = math.exp(1.5 + 0.4 * math.log(area))
            for year in (2021, 2022):
                item = _row(zone, year, "c", price, ur3)
                item["a_m2"] = area
                rows.append(item)
        _test_set_s_c3_maxiter(1)
    else:
        rows = []
        for zone in ("Z1", "Z2"):
            for year in (2021, 2022):
                rows.append(_row(zone, year, "c", math.exp(1.2 + 0.2 * math.log(40.0)), "urban"))
        _test_set_s_c3_maxiter(None)
    path = tmp_path / "b2.json"
    _write_b2(path, rows)
    try:
        built = _fit(path, tmp_path)
    finally:
        _test_set_s_c3_maxiter(None)
    status = built["fit"]["s_c3_status"]
    if mode == "nonconverge":
        assert status == "NOT_CONVERGED"
        assert built["fit"]["s_c3_reason"]
        assert built["fit"]["beta_by_cell"]["c"] > 0
    else:
        assert status == "NOT_RUN"
        assert built["fit"]["s_c3_reason"] == "MixedLM needs two or more groups"
    assert built["zones"]["zones"]
    for record in built["zones"]["zones"]:
        assert record["model_failure"] is True
        assert record["unavailable"] is True


@pytest.mark.parametrize("column", ["price", "zone", "cell"])
def test_fit_cli_blank_short(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, column: str) -> None:
    """SYNTHETIC. A blank cell and a short row each refuse before the fit."""
    order = ["year", "zone", "cell", "price", "n_sales", "a_m2", "f_m2"]
    full = _row("Z1", 2021, "c", 10.0, "urban")
    full["zone"] = "Z2"
    partner = _row("Z2", 2022, "c", 10.0, "urban")
    blank = dict(full)
    blank[column] = ""
    short = {name: full[name] for name in order[: order.index(column)]}
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.fit_v14_hedonic.fit_headline",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    for kind, row, message in (
        (
            "blank",
            blank,
            f"B3_FIT: ERROR: {column} row 1: expected value, got blank",
        ),
        (
            "short",
            short,
            f"B3_FIT: ERROR: row 1: expected 7 fields, got {order.index(column)}",
        ),
    ):
        path = tmp_path / f"{kind}.json"
        _write_b2(path, [row, partner])
        out = tmp_path / f"{kind}-out.json"
        with pytest.raises(FitError) as raised:
            fit_b2(path)
        assert str(raised.value) == message
        assert not out.exists()
    assert calls["n"] == 0


def test_per_zone_writer_fields_exact(tmp_path: Path) -> None:
    """SYNTHETIC. Per-zone keys are exact and the limitation is file-level once."""
    path = tmp_path / "b2.json"
    _write_b2(path, _baseline_rows())
    built = _fit(path, tmp_path)
    allowed = {"zone", "share", "land_per_home", "unavailable", "model_failure", "count_in_1d"}
    loaded = load_source(built["zone_path"], "fitted_hedonic")
    assert loaded
    for record in built["zones"]["zones"]:
        assert set(record) == allowed
    assert _count_key(built["zones"], "fidelity_limitation") == 1


@pytest.mark.parametrize(("name", "beta"), [("beta_zero", 0.0), ("beta_negative", -0.1)])
def test_per_zone_writer_nonpositive_beta(name: str, beta: float) -> None:
    """SYNTHETIC. A non-positive elasticity publishes share 0 and unavailable."""
    fitted = {
        "beta_by_cell": {"c": beta},
        "model_failure_by_cell": {"c": True},
        "informative_by_cell": {"c": True},
        "sensitivities": [{"id": "S-c3", "status": "fit", "reason": "converged"}],
    }
    records = project_records(fitted, [{"zone": "Z1", "cell": "c", "year": 2022}])
    assert records[0]["share"] == 0
    assert records[0]["unavailable"] is True
    assert records[0]["model_failure"] is True
    assert records[0]["land_per_home"] == 0
    assert name


def test_check3_int_radii(tmp_path: Path) -> None:
    """SYNTHETIC. JSON radii come back as ints 20, 30 and 40, and every zone passes."""
    plots = tmp_path / "plots.csv"
    houses = tmp_path / "houses.csv"
    _csv(plots, PLOT_HEADER, [_plot_row("Z1"), _plot_row("Z2")])
    _csv(houses, ["code", "house_plot_m2"], [["Z1", "20"], ["Z2", "20"]])
    pins = _pins_for({"plot_bands": plots, "gis_house_plot": houses})
    payload = build_check3({"plot_bands": plots, "gis_house_plot": houses}, pins=pins)
    path = tmp_path / "check3.json"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    loaded = load_source(path, "check3_plot_passes")
    zones = [{"zone": code, **fields} for code, fields in loaded.items()]
    for zone in zones:
        assert set(_pass_at_ints(zone["pass_at"])) == {20, 30, 40}
    assert _plot(zones, "pass_at")["n_pass"] == len(zones)


def test_check3_pending_pin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. PENDING_FULL_SHA is refused on a copy and the production table stays."""
    before = dict(SOURCE_PINS)
    pins = copy_pin_table()
    pins["gis_house_plot"] = "PENDING_FULL_SHA"
    plots = tmp_path / "plots.csv"
    houses = tmp_path / "houses.csv"
    _csv(plots, PLOT_HEADER, [_plot_row("Z1")])
    _csv(houses, ["code", "house_plot_m2"], [["Z1", "20"]])
    calls = {"gis": 0, "plots": 0, "b6": 0, "h": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.load_gis_house_plot",
        lambda *_args, **_kwargs: calls.__setitem__("gis", calls["gis"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.load_plot_bands",
        lambda *_args, **_kwargs: calls.__setitem__("plots", calls["plots"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_inputs.load_source",
        lambda *_args, **_kwargs: calls.__setitem__("b6", calls["b6"] + 1),
    )
    monkeypatch.setattr(
        "scripts.rerun_v14_score._score_holdout",
        lambda *_args, **_kwargs: calls.__setitem__("h", calls["h"] + 1),
    )
    out = tmp_path / "check3.json"
    with pytest.raises(CheckSourceError) as raised:
        build_check3({"plot_bands": plots, "gis_house_plot": houses}, pins=pins)
    assert str(raised.value) == "B5_CHECK3: REFUSED: pin: expected full sha256, got PENDING_FULL_SHA"
    assert calls == {"gis": 0, "plots": 0, "b6": 0, "h": 0}
    assert not out.exists()
    assert SOURCE_PINS == before


@pytest.mark.parametrize("name", ["nrs2017", "gis_house_plot"])
def test_prod_pins_full_sha(name: str) -> None:
    """SYNTHETIC. Production pins are full sha256 digests and none are pending."""
    if name == "nrs2017":
        assert COMPONENT_PINS["nrs2017"] == NRS_PIN
        table = COMPONENT_PINS
    else:
        assert SOURCE_PINS["gis_house_plot"] == GIS_PIN
        table = SOURCE_PINS
    assert "PENDING_FULL_SHA" not in table.values()
    for value in table.values():
        assert re.fullmatch(r"[0-9a-f]{64}", str(value))


@pytest.mark.parametrize(
    "value",
    ["33207976", "3320797696c876e7cb6b41163724f0346cbeb284f89d6792bf87a1e9c600735", "zz", ""],
)
def test_check3_pin_not_full_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """SYNTHETIC. A short, non-hex, or blank gis pin refuses before the reader."""
    pins = copy_pin_table()
    pins["gis_house_plot"] = value
    houses = tmp_path / "houses.csv"
    plots = tmp_path / "plots.csv"
    _csv(houses, ["code", "house_plot_m2"], [["Z1", "20"]])
    _csv(plots, PLOT_HEADER, [_plot_row("Z1")])
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.load_gis_house_plot",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    out = tmp_path / "check3.json"
    shown = "blank" if value == "" else value
    with pytest.raises(CheckSourceError) as raised:
        build_check3({"plot_bands": plots, "gis_house_plot": houses}, pins=pins)
    assert str(raised.value) == f"B5_CHECK3: REFUSED: pin: expected full sha256, got {shown}"
    assert calls["n"] == 0
    assert not out.exists()


@pytest.mark.parametrize("mode", ["shaped", "byte"])
def test_check4_wrong_rent_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """SYNTHETIC. A rent table whose sha is not the pin is refused before the route."""
    path = tmp_path / "rent.csv"
    _csv(path, RENT_HEADER, [_rent_row("Z1")])
    if mode == "byte":
        path.write_bytes(path.read_bytes() + b"\n")
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.two_route_lands",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    out = tmp_path / "check4.json"
    with pytest.raises(CheckSourceError) as raised:
        build_check4(path)
    actual = sha256_file(path)
    assert str(raised.value) == (
        f"B5_CHECK4: REFUSED: rent_table sha256: expected {RENT_PIN}, got {actual}"
    )
    assert calls["n"] == 0
    assert not out.exists()


def test_check4_shared_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. An eight-character rent-table prefix is a mismatch."""
    path = tmp_path / "rent.csv"
    _csv(path, RENT_HEADER, [_rent_row("Z1")])
    forged = RENT_PIN[:8] + ("b" * 56)
    pins = copy_pin_table()
    pins["rent_table"] = forged
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.two_route_lands",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    out = tmp_path / "check4.json"
    with pytest.raises(CheckSourceError) as raised:
        build_check4(path, pins=pins)
    actual = sha256_file(path)
    assert str(raised.value) == (
        f"B5_CHECK4: REFUSED: rent_table sha256: expected {forged}, got {actual}"
    )
    assert calls["n"] == 0
    assert not out.exists()


def test_check4_two_routes(tmp_path: Path) -> None:
    """SYNTHETIC. Residual and capitalised routes match the v1.3 check-4 method."""
    path = tmp_path / "rent.csv"
    _csv(path, RENT_HEADER, [_rent_row("Z1", "4", "1")])
    pins = copy_pin_table()
    pins["rent_table"] = sha256_file(path)
    payload = build_check4(path, pins=pins)
    zone = payload["zones"][0]
    assert zone["residual_land"] == 4.0
    assert zone["capitalised_land"] == capitalised_rent_land(1.0, yield_rate=0.045)
    text = Path(build_check4.__code__.co_filename).read_text(encoding="utf-8")
    assert "ce940445" in text
    assert "check 4" in text


def test_dz2022_keys_crosswalk(tmp_path: Path) -> None:
    """SYNTHETIC. O-D1 weights rebuild share low, central and high."""
    walk = tmp_path / "walk.csv"
    primary = tmp_path / "primary.json"
    _csv(
        walk,
        ["dz2011_code", "dz2022_code", "uprn_count"],
        [["P1", "A", "1"], ["P2", "A", "3"], ["P1", "B", "2"]],
    )
    primary.write_text(
        json.dumps(
            {
                "label": "SYNTHETIC",
                "zones": [
                    {"zone": "P1", "share_low": 1.0, "share_central": 1.0, "share_high": 1.0},
                    {"zone": "P2", "share_low": 2.0, "share_central": 4.0, "share_high": 6.0},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pins = copy_pin_table()
    pins["crosswalk"] = sha256_file(walk)
    payload, suppressed = build_dz2022_keys(walk, primary, pins=pins)
    assert suppressed == 0
    by_zone = {row["zone"]: row for row in payload["zones"]}
    assert by_zone["A"]["share_low"] == 1.75
    assert by_zone["A"]["share_central"] == 3.25
    assert by_zone["A"]["share_high"] == 4.75
    assert by_zone["B"]["share_low"] == 1.0
    assert by_zone["B"]["share_central"] == 1.0
    assert by_zone["B"]["share_high"] == 1.0


def test_dz2022_keys_no_primary_suppressed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A DZ2022 zone with no primary estimate is omitted, not filled."""
    walk = tmp_path / "walk.csv"
    primary = tmp_path / "primary.json"
    _csv(
        walk,
        ["dz2011_code", "dz2022_code", "uprn_count"],
        [["P1", "A", "1"], ["P2", "A", "3"], ["P9", "C", "4"]],
    )
    primary.write_text(
        json.dumps(
            {
                "label": "SYNTHETIC",
                "zones": [
                    {"zone": "P1", "share_low": 1.0, "share_central": 1.0, "share_high": 1.0},
                    {"zone": "P2", "share_low": 2.0, "share_central": 4.0, "share_high": 6.0},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(SOURCE_PINS, "crosswalk", sha256_file(walk))
    out = tmp_path / "dz.json"
    assert source_main(
        ["--crosswalk", str(walk), "--primary-estimates", str(primary), "--dz2022-out", str(out)]
    ) == 0
    assert capsys.readouterr().out == "B5_DZ2022_KEYS: suppressed=1\n"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "C" not in {row["zone"] for row in payload["zones"]}
    kept = next(row for row in payload["zones"] if row["zone"] == "A")
    assert kept["share_low"] == 1.75
    assert kept["share_central"] == 3.25
    assert kept["share_high"] == 4.75


@pytest.mark.parametrize(("bad", "shown"), [("7", "7"), ("0", "0")])
def test_ur6_vintage(tmp_path: Path, bad: str, shown: str) -> None:
    """SYNTHETIC. UR6 outside 1-6 refuses and leaves no output."""
    good = tmp_path / "good.csv"
    _csv(good, ["code", "ur6"], [["Z1", "1"], ["Z2", "6"]])
    pins = copy_pin_table()
    pins["ur6"] = sha256_file(good)
    payload = build_ur6(good, pins=pins)
    assert [row["ur6"] for row in payload["zones"]] == [1, 6]
    bad_path = tmp_path / "bad.csv"
    _csv(bad_path, ["code", "ur6"], [["Z1", bad]])
    pins["ur6"] = sha256_file(bad_path)
    out = tmp_path / "ur6.json"
    with pytest.raises(CheckSourceError) as raised:
        save_ur6(bad_path, out, pins=pins)
    assert str(raised.value) == f"B5_UR6: ERROR: ur6 row 1: expected 1-6, got {shown}"
    assert not out.exists()


@pytest.mark.parametrize("source", ["plot_bands", "crosswalk", "ur6", "gis_house_plot"])
def test_check_sources_pin_wrong(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    """SYNTHETIC. One changed input byte refuses before the writer."""
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.write_output",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    out = tmp_path / "out.json"
    if source == "plot_bands":
        path = tmp_path / "plots.csv"
        _csv(path, PLOT_HEADER, [_plot_row("Z1")])
        with pytest.raises(CheckSourceError) as raised:
            save_check3({"plot_bands": path, "gis_house_plot": path}, out)
        step, name = "B5_PLOT_BANDS", "plot_bands"
    elif source == "gis_house_plot":
        plots = tmp_path / "plots.csv"
        houses = tmp_path / "houses.csv"
        _csv(plots, PLOT_HEADER, [_plot_row("Z1")])
        _csv(houses, ["code", "house_plot_m2"], [["Z1", "20"]])
        pins = copy_pin_table()
        pins["plot_bands"] = sha256_file(plots)
        with pytest.raises(CheckSourceError) as raised:
            save_check3({"plot_bands": plots, "gis_house_plot": houses}, out, pins=pins)
        path = houses
        step, name = "B5_GIS_HOUSE_PLOT", "gis_house_plot"
    elif source == "crosswalk":
        path = tmp_path / "walk.csv"
        _csv(path, ["dz2011_code", "dz2022_code", "uprn_count"], [["P1", "A", "1"]])
        primary = tmp_path / "primary.json"
        primary.write_text('{"label": "SYNTHETIC", "zones": []}\n', encoding="utf-8")
        with pytest.raises(CheckSourceError) as raised:
            save_dz2022(path, primary, out)
        step, name = "B5_CROSSWALK", "crosswalk"
    else:
        path = tmp_path / "ur6.csv"
        _csv(path, ["code", "ur6"], [["Z1", "1"]])
        with pytest.raises(CheckSourceError) as raised:
            save_ur6(path, out)
        step, name = "B5_UR6", "ur6"
    actual = sha256_file(path)
    expected = SOURCE_PINS[name] if source != "gis_house_plot" else SOURCE_PINS["gis_house_plot"]
    if source == "gis_house_plot":
        expected = SOURCE_PINS["gis_house_plot"]
    else:
        expected = SOURCE_PINS[source]
    assert str(raised.value) == f"{step}: REFUSED: {name} sha256: expected {expected}, got {actual}"
    assert calls["n"] == 0
    assert not out.exists()


@pytest.mark.parametrize("source", ["plot_bands", "crosswalk", "ur6", "gis_house_plot"])
def test_check_sources_shared_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    """SYNTHETIC. A pin that shares eight characters is still a mismatch."""
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_sources.write_output",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    forged = SOURCE_PINS[source][:8] + ("c" * 56)
    pins = copy_pin_table()
    pins[source] = forged
    out = tmp_path / "out.json"
    if source in {"plot_bands", "gis_house_plot"}:
        plots = tmp_path / "plots.csv"
        houses = tmp_path / "houses.csv"
        _csv(plots, PLOT_HEADER, [_plot_row("Z1")])
        _csv(houses, ["code", "house_plot_m2"], [["Z1", "20"]])
        pins["plot_bands"] = sha256_file(plots) if source != "plot_bands" else forged
        pins["gis_house_plot"] = sha256_file(houses) if source != "gis_house_plot" else forged
        with pytest.raises(CheckSourceError) as raised:
            save_check3({"plot_bands": plots, "gis_house_plot": houses}, out, pins=pins)
        path = plots if source == "plot_bands" else houses
        step = "B5_PLOT_BANDS" if source == "plot_bands" else "B5_GIS_HOUSE_PLOT"
    elif source == "crosswalk":
        path = tmp_path / "walk.csv"
        _csv(path, ["dz2011_code", "dz2022_code", "uprn_count"], [["P1", "A", "1"]])
        primary = tmp_path / "primary.json"
        primary.write_text(
            json.dumps({"label": "SYNTHETIC", "zones": [{"zone": "P1", "share_low": 1, "share_central": 1, "share_high": 1}]})
            + "\n",
            encoding="utf-8",
        )
        with pytest.raises(CheckSourceError) as raised:
            save_dz2022(path, primary, out, pins=pins)
        step = "B5_CROSSWALK"
    else:
        path = tmp_path / "ur6.csv"
        _csv(path, ["code", "ur6"], [["Z1", "1"]])
        with pytest.raises(CheckSourceError) as raised:
            save_ur6(path, out, pins=pins)
        step = "B5_UR6"
    actual = sha256_file(path)
    assert str(raised.value) == f"{step}: REFUSED: {source} sha256: expected {forged}, got {actual}"
    assert calls["n"] == 0
    assert not out.exists()


@pytest.mark.parametrize(
    "source",
    ["plot_bands", "gis_house_plot", "rent_table", "crosswalk", "ur6", "primary_estimates"],
)
def test_check_sources_missing_blank_short(tmp_path: Path, source: str) -> None:
    """SYNTHETIC. Missing, blank, and short inputs leave no output."""
    out = tmp_path / "out.json"
    if source == "plot_bands":
        step, column, width = "B5_PLOT_BANDS", "code", len(PLOT_HEADER)
        header, sample = PLOT_HEADER, _plot_row("Z1")
    elif source == "gis_house_plot":
        step, column, width = "B5_GIS_HOUSE_PLOT", "code", 2
        header, sample = ["code", "house_plot_m2"], ["Z1", "20"]
    elif source == "rent_table":
        step, column, width = "B5_CHECK4", "zone_id", len(RENT_HEADER)
        header, sample = RENT_HEADER, _rent_row("Z1")
    elif source == "crosswalk":
        step, column, width = "B5_CROSSWALK", "dz2011_code", 3
        header, sample = ["dz2011_code", "dz2022_code", "uprn_count"], ["P1", "A", "1"]
    elif source == "ur6":
        step, column, width = "B5_UR6", "code", 2
        header, sample = ["code", "ur6"], ["Z1", "1"]
    else:
        step, column, width = "B5_PRIMARY", "zone", 4
        header, sample = [], []
    missing = tmp_path / "missing.csv"
    with pytest.raises(CheckSourceError) as raised:
        _run_source_case(source, missing, out, None)
    assert str(raised.value) == f"{step}: ERROR: file: expected {missing}, got absent"
    assert not out.exists()
    if source == "primary_estimates":
        blank = tmp_path / "blank.json"
        blank.write_text(
            json.dumps(
                {
                    "label": "SYNTHETIC",
                    "zones": [{"zone": "", "share_low": 1, "share_central": 1, "share_high": 1}],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        short = tmp_path / "short.json"
        short.write_text(
            json.dumps({"label": "SYNTHETIC", "zones": [{"zone": "Z1"}]}) + "\n",
            encoding="utf-8",
        )
        short_got = 1
    else:
        blank_cells = list(sample)
        blank_cells[header.index(column)] = ""
        blank = tmp_path / "blank.csv"
        short = tmp_path / "short.csv"
        _csv(blank, header, [blank_cells])
        _csv(short, header, [sample[:1]])
        short_got = 1
    with pytest.raises(CheckSourceError) as raised_blank:
        _run_source_case(source, blank, out, sha256_file(blank) if source != "primary_estimates" else None)
    assert str(raised_blank.value) == f"{step}: ERROR: {column} row 1: expected value, got blank"
    assert not out.exists()
    with pytest.raises(CheckSourceError) as raised_short:
        _run_source_case(source, short, out, sha256_file(short) if source != "primary_estimates" else None)
    assert str(raised_short.value) == f"{step}: ERROR: row 1: expected {width} fields, got {short_got}"
    assert not out.exists()


def _run_source_case(source: str, path: Path, out: Path, digest: str | None) -> None:
    pins = copy_pin_table()
    if source == "plot_bands":
        houses = path.parent / "houses.csv"
        if not houses.exists():
            _csv(houses, ["code", "house_plot_m2"], [["Z1", "20"]])
        pins["gis_house_plot"] = sha256_file(houses)
        if digest is not None:
            pins["plot_bands"] = digest
        save_check3({"plot_bands": path, "gis_house_plot": houses}, out, pins=pins)
        return
    if source == "gis_house_plot":
        plots = path.parent / "plots.csv"
        if not plots.exists():
            _csv(plots, PLOT_HEADER, [_plot_row("Z1")])
        pins["plot_bands"] = sha256_file(plots)
        if digest is not None:
            pins["gis_house_plot"] = digest
        save_check3({"plot_bands": plots, "gis_house_plot": path}, out, pins=pins)
        return
    if source == "rent_table":
        if digest is not None:
            pins["rent_table"] = digest
        save_check4(path, out, pins=pins)
        return
    if source == "crosswalk":
        primary = path.parent / "primary.json"
        if not primary.exists():
            primary.write_text(
                json.dumps(
                    {
                        "label": "SYNTHETIC",
                        "zones": [{"zone": "P1", "share_low": 1, "share_central": 1, "share_high": 1}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        if digest is not None:
            pins["crosswalk"] = digest
        save_dz2022(path, primary, out, pins=pins)
        return
    if source == "ur6":
        if digest is not None:
            pins["ur6"] = digest
        save_ur6(path, out, pins=pins)
        return
    walk = path.parent / "walk.csv"
    if not walk.exists():
        _csv(walk, ["dz2011_code", "dz2022_code", "uprn_count"], [["P1", "A", "1"]])
    pins["crosswalk"] = sha256_file(walk)
    save_dz2022(walk, path, out, pins=pins)


def test_check_sources_feed_b6_2023(tmp_path: Path) -> None:
    """SYNTHETIC. The 2023 check-input build accepts the four B6 sources."""
    zone = "Z1"
    files = {
        "builder_output": tmp_path / "builder.json",
        "primary_estimates": tmp_path / "primary.json",
        "fitted_hedonic": tmp_path / "fitted.json",
        "check3_plot_passes": tmp_path / "check3.json",
        "check4_rent_route": tmp_path / "check4.json",
        "dz2022_keys": tmp_path / "dz.json",
        "ur6": tmp_path / "ur6.json",
    }
    files["builder_output"].write_text(
        json.dumps(
            {
                "label": "SYNTHETIC",
                "zones": [
                    {
                        "zone": zone,
                        "price": 10,
                        "count_in_1d": True,
                        "unavailable": False,
                        "model_failure": False,
                        "hla": False,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    files["primary_estimates"].write_text(
        json.dumps(
            {
                "label": "SYNTHETIC",
                "zones": [
                    {
                        "zone": zone,
                        "share": 0.2,
                        "land_per_home": 2,
                        "unavailable": False,
                        "count_in_1d": True,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    files["fitted_hedonic"].write_text(
        json.dumps(
            {
                "label": "SYNTHETIC",
                "fidelity_limitation": "kept once",
                "zones": [
                    {
                        "zone": zone,
                        "share": 0.2,
                        "land_per_home": 2,
                        "unavailable": False,
                        "model_failure": False,
                        "count_in_1d": True,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    files["check3_plot_passes"].write_text(
        json.dumps(
            {
                "label": "SYNTHETIC",
                "zones": [
                    {
                        "zone": zone,
                        "pass_at": {"20": True, "30": True, "40": True},
                        "pass_at_all_homes": {"20": True, "30": True, "40": True},
                        "pass_at_dz22": {"20": True, "30": True, "40": True},
                        "measured_detached_pass": True,
                        "detached_plot_m2": 40,
                        "house_plot_m2": 20,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    files["check4_rent_route"].write_text(
        json.dumps(
            {"label": "SYNTHETIC", "zones": [{"zone": zone, "residual_land": 4, "capitalised_land": 4}]}
        )
        + "\n",
        encoding="utf-8",
    )
    files["dz2022_keys"].write_text(
        json.dumps(
            {
                "label": "SYNTHETIC",
                "zones": [
                    {"zone": zone, "dz2022": zone, "share_low": 0.1, "share_central": 0.2, "share_high": 0.3}
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    files["ur6"].write_text(
        json.dumps({"label": "SYNTHETIC", "zones": [{"zone": zone, "ur6": 1}]}) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "checks.json"
    argv = ["--out", str(out), "--year", "2023"]
    for name, path in files.items():
        argv.extend([f"--{name.replace('_', '-')}", str(path), "--pin", f"{name}={sha256_file(path)}"])
    assert b6_main(argv) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    for name in ("check3_plot_passes", "check4_rent_route", "ur6", "dz2022_keys"):
        assert re.fullmatch(r"[0-9a-f]{64}", payload["pins"][name])


def test_dryrun_holdout_end_to_end(tmp_path: Path) -> None:
    """SYNTHETIC. B1 through H run with no stub, and the lock carries frozen_set."""
    source = Path(__file__).resolve().parents[1] / "v14_dryrun" / "dryrun.py"
    text = source.read_text(encoding="utf-8")
    assert "def stub" not in text
    assert text.index("fit_main") < text.index("score_main")
    result = dry_run(tmp_path)
    assert result["status"] == "passed"
    report = Path(result["report"])
    lock = Path(result["lock"])
    assert report.is_file()
    assert lock.is_file()
    assert report.stat().st_mtime_ns <= lock.stat().st_mtime_ns
    assert "frozen_set" in json.loads(lock.read_text(encoding="utf-8"))


def test_recorded_files_include_pr3b_scripts() -> None:
    """SYNTHETIC. The two new scripts are recorded and no longer optional."""
    for rel in (
        "backend/scripts/fit_v14_hedonic.py",
        "backend/scripts/build_v14_check_sources.py",
    ):
        assert rel in RECORDED_FILES
        assert rel not in PR3_RECORDED_WHEN_PRESENT


@pytest.mark.parametrize(("flag", "shown"), [(None, "absent"), ("2024", "2024"), ("2022", "2022"), ("x", "x")])
def test_b6_year_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flag: str | None,
    shown: str,
) -> None:
    """SYNTHETIC. A missing or disallowed year refuses before S2, S3, or the join."""
    calls = {"read": 0, "join": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_inputs.read_s2_s3",
        lambda *_args, **_kwargs: calls.__setitem__("read", calls["read"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_inputs.join_sources",
        lambda *_args, **_kwargs: calls.__setitem__("join", calls["join"] + 1),
    )
    out = tmp_path / "checks.json"
    argv = ["--out", str(out)]
    if flag is not None:
        argv.extend(["--year", flag])
    assert b6_main(argv) == 1
    assert calls == {"read": 0, "join": 0}
    assert not out.exists()
    assert capsys.readouterr().err == f"B6: ERROR: year: expected one of 2023, got {shown}\n"


def test_score_2024_crash_still_refuses_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A crash during scoring still blocks a second --score-2024 run."""
    files = _frozen_files(tmp_path)
    monkeypatch.setitem(MERGE_PINS, "merge_map", sha256_file(files["merge_map"]))
    members = frozen_set_members(files)
    lock = tmp_path / "holdout.lock"
    lock.write_text(
        json.dumps(
            {
                "inputs_sha256": "synthetic",
                "commit": "a6cd2165eff8da13e174276c6e7c731c74c3c1cd",
                "label": "seen, not out-of-sample",
                "frozen_set": members,
                "frozen_set_sha256": frozen_set_lock_hash(members),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    checks = tmp_path / "checks.json"
    checks.write_text('{"label": "SYNTHETIC", "primary_zones": [], "secondary_zones": []}\n', encoding="utf-8")
    year_file = tmp_path / "year.csv"
    year_file.write_text("# SYNTHETIC\nyear\n2024\n", encoding="utf-8")
    calls = {"n": 0}

    def boom(*_args, **_kwargs):
        calls["n"] += 1
        raise RuntimeError("scoring crashed")

    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", boom)
    command = [
        "--out",
        str(tmp_path / "score" / "report.json"),
        "--score-2024",
        "--check-inputs",
        str(checks),
        "--lock-path",
        str(lock),
        "--year-file",
        str(year_file),
        *_frozen_flags(files),
    ]
    assert score_main(command) == 1
    assert calls["n"] == 1
    assert json.loads(lock.read_text(encoding="utf-8")).get("score_2024") is True
    assert score_main(command) == 1
    assert "second 2024 run refused" in capsys.readouterr().err
    assert calls["n"] == 1


def test_mark_score_2024_removes_tmp_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. A failed atomic replace does not leave the temporary lock."""
    lock = tmp_path / "holdout.lock"
    lock.write_text('{"score_2024": false}\n', encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr("georgist.v14_score_report.os.replace", boom)
    with pytest.raises(OSError, match="replace failed"):
        mark_score_2024(lock)
    assert not (tmp_path / ".holdout.lock.tmp").exists()
    assert json.loads(lock.read_text(encoding="utf-8"))["score_2024"] is False
