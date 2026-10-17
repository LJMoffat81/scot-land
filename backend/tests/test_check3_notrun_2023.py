"""CHECK3-NOTRUN-2023. SYNTHETIC fixtures only. No 2024 price file is opened.

W12 mutations, recorded in the PR body: deleting rule f turns W3 red; skipping
the reason check turns W5 red; replacing the type check with ``== 2023`` turns
W9c and W9d red; removing rule 0 turns W13 red.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from georgist.check3_record import (
    Check3RecordError,
    not_run_record_text,
    validate_check3_record,
)
from georgist.surface_paths import REPO_ROOT
from georgist.surface_v14_checks import (
    AM1_FAILED_LABEL,
    AM1_PASSED_LABEL,
    AM1_REASON,
    gating_marks,
    score_both,
)
from georgist.v14_real_headers import REAL_HEADERS
from georgist.v14_score_report import PIN_TABLE as MERGE_PINS
from georgist.v14_score_report import b6_pins_sha256, frozen_set_members, sha256_file
from scripts.build_v14_check_inputs import CheckInputError, load_source
from scripts.build_v14_check_inputs import main as b6_main
from scripts.build_v14_check_inputs import sha256_file as file_sha
from scripts.build_v14_check_sources import PIN_TABLE as SOURCE_PINS
from scripts.build_v14_check_sources import main as source_main
from scripts.rerun_v14_score import HoldoutLockError, _frozen_paths, raise_missing_frozen
from scripts.rerun_v14_score import main as score_main
from test_am1_gate_1 import _passing_zones
from test_v14_gaps_pr2_lock import _args, _holdout, _layout

NOT_RUN_LINE = "B5_CHECK3: NOT_RUN: plot_bands header: expected pass_20, got absent"
PLOT_WITH_PASS = [
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
BACKEND = REPO_ROOT / "backend"
SOURCE_NAMES = (
    "builder_output",
    "primary_estimates",
    "fitted_hedonic",
    "check3_plot_passes",
    "check4_rent_route",
    "dz2022_keys",
    "ur6",
)


def _csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    buffer = io.StringIO()
    buffer.write("# SYNTHETIC\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8")


def _record_bytes(**overrides: object) -> bytes:
    record: dict[str, object] = {"reason": AM1_REASON, "status": "NOT_RUN", "year": 2023}
    record.update(overrides)
    return (json.dumps(record) + "\n").encode("utf-8")


def _expected_record_bytes() -> bytes:
    return (
        json.dumps({"reason": AM1_REASON, "status": "NOT_RUN", "year": 2023}, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _pin_plots(monkeypatch: pytest.MonkeyPatch, plots: Path, houses: Path) -> None:
    monkeypatch.setitem(SOURCE_PINS, "plot_bands", sha256_file(plots))
    monkeypatch.setitem(SOURCE_PINS, "gis_house_plot", sha256_file(houses))


def _sources(tmp_path: Path, check3: bytes) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    files = {name: tmp_path / f"{name}.json" for name in SOURCE_NAMES}
    for name, path in files.items():
        if name == "check3_plot_passes":
            path.write_bytes(check3)
        else:
            path.write_text('{"label": "SYNTHETIC"}\n', encoding="utf-8")
    return files


def _b6_argv(out: Path, files: dict[str, Path], year: str) -> list[str]:
    argv = ["--out", str(out), "--year", year]
    for name, path in files.items():
        argv.extend([f"--{name.replace('_', '-')}", str(path), "--pin", f"{name}={file_sha(path)}"])
    return argv


def _assert_b6_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: bytes,
    message: str,
    *,
    year: str,
) -> None:
    calls = {"join": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_inputs.join_sources",
        lambda *_args, **_kwargs: calls.__setitem__("join", calls["join"] + 1),
    )
    files = _sources(tmp_path, raw)
    with pytest.raises(Check3RecordError) as raised:
        load_source(files["check3_plot_passes"], "check3_plot_passes", mode=int(year))
    assert str(raised.value) == message
    out = tmp_path / "checks.json"
    assert b6_main(_b6_argv(out, files, year)) == 1
    assert calls["join"] == 0
    assert not out.exists()
    assert capsys.readouterr().err == message + "\n"


def _assert_holdout_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: bytes,
    message: str,
    *,
    score_2024: bool = False,
) -> None:
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.rerun_v14_score._score_holdout",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "check3.json"
    path.write_bytes(raw)
    step = "SCORE_2024" if score_2024 else "HOLDOUT_2023"
    year = 2024 if score_2024 else 2023
    with pytest.raises(Check3RecordError) as raised:
        validate_check3_record(path, year=year, step=step)
    assert str(raised.value) == message
    out = tmp_path / "report.json"
    lock = tmp_path / "holdout.lock"
    argv = [
        "--out",
        str(out),
        "--score-2024" if score_2024 else "--holdout-2023",
        "--lock-path",
        str(lock),
        "--check3-plot-passes",
        str(path),
    ]
    assert score_main(argv) == 1
    assert calls["n"] == 0
    assert not out.exists()
    assert not lock.exists()
    assert capsys.readouterr().err == message + "\n"


def _rule_message(step: str, kind: str, got: object | None = None) -> str:
    if kind == "a":
        return f"{step}: REFUSED: check3_plot_passes status: expected 'NOT_RUN', got {got!r}"
    if kind == "b":
        return f"{step}: REFUSED: check3_plot_passes: expected no passes with NOT_RUN, got passes"
    if kind == "c":
        return (
            f"{step}: REFUSED: check3_plot_passes fields: "
            f"expected ['reason', 'status', 'year'], got {got!r}"
        )
    if kind == "d":
        return f"{step}: REFUSED: check3_plot_passes reason: expected {AM1_REASON!r}, got {got!r}"
    if kind == "e":
        return f"{step}: REFUSED: check3_plot_passes year: expected 2023, got {got!r}"
    if kind == "f":
        return (
            f"{step}: REFUSED: check3_plot_passes: expected passes, got NOT_RUN record (AM-1 is 2023 only)"
        )
    if kind == "json":
        return f"{step}: REFUSED: check3_plot_passes: expected JSON object, got invalid JSON"
    if kind == "type":
        return f"{step}: REFUSED: check3_plot_passes: expected JSON object, got {got}"
    raise AssertionError(kind)


def test_w1_year_2023_writes_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. 2023 without pass_20 writes the exact NOT_RUN record and exits 0."""
    plots = tmp_path / "plots.csv"
    houses = tmp_path / "houses.csv"
    _csv(plots, list(REAL_HEADERS["plot_bands"]), [["SYNTHETIC"] * len(REAL_HEADERS["plot_bands"])])
    _csv(houses, ["code", "house_plot_m2"], [["Z1", "1"]])
    _pin_plots(monkeypatch, plots, houses)
    dest = tmp_path / "check3.json"
    assert source_main(
        ["--year", "2023", "--plot-bands", str(plots), "--gis-house-plot", str(houses), "--check3-out", str(dest)]
    ) == 0
    assert dest.read_bytes() == _expected_record_bytes()
    assert dest.read_bytes() == not_run_record_text().encode("utf-8")
    assert capsys.readouterr().out == NOT_RUN_LINE + "\n"


@pytest.mark.parametrize("year", [None, "2024"])
def test_w1b_other_years_write_no_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    year: str | None,
) -> None:
    """SYNTHETIC. 2024 and no --year leave no file and exit 1."""
    plots = tmp_path / "plots.csv"
    houses = tmp_path / "houses.csv"
    _csv(plots, list(REAL_HEADERS["plot_bands"]), [["SYNTHETIC"] * len(REAL_HEADERS["plot_bands"])])
    _csv(houses, ["code", "house_plot_m2"], [["Z1", "1"]])
    _pin_plots(monkeypatch, plots, houses)
    dest = tmp_path / "check3.json"
    argv = ["--plot-bands", str(plots), "--gis-house-plot", str(houses), "--check3-out", str(dest)]
    if year is not None:
        argv = ["--year", year, *argv]
    assert source_main(argv) == 1
    assert not dest.exists()
    assert NOT_RUN_LINE in capsys.readouterr().err


def test_w1c_2023_without_check3_out_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. 2023 without --check3-out prints the NOT_RUN line and adds no file."""
    plots = tmp_path / "plots.csv"
    houses = tmp_path / "houses.csv"
    _csv(plots, list(REAL_HEADERS["plot_bands"]), [["SYNTHETIC"] * len(REAL_HEADERS["plot_bands"])])
    _csv(houses, ["code", "house_plot_m2"], [["Z1", "1"]])
    _pin_plots(monkeypatch, plots, houses)
    monkeypatch.chdir(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())
    assert source_main(["--year", "2023", "--plot-bands", str(plots), "--gis-house-plot", str(houses)]) == 0
    after = sorted(path.name for path in tmp_path.iterdir())
    assert before == after
    assert capsys.readouterr().out == NOT_RUN_LINE + "\n"


def test_w1d_2023_with_pass_20_matches_the_no_year_passes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. A 2023 passes file matches the no---year run and has no status."""
    def bands(root: Path) -> tuple[Path, Path]:
        plots = root / "plots.csv"
        houses = root / "houses.csv"
        _csv(plots, PLOT_WITH_PASS, [["Z1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "40", "1"]])
        _csv(houses, ["code", "house_plot_m2"], [["Z1", "20"]])
        return plots, houses

    first = tmp_path / "year"
    second = tmp_path / "plain"
    first.mkdir()
    second.mkdir()
    plots_a, houses_a = bands(first)
    plots_b, houses_b = bands(second)
    _pin_plots(monkeypatch, plots_a, houses_a)
    out_a = first / "check3.json"
    assert source_main(
        ["--year", "2023", "--plot-bands", str(plots_a), "--gis-house-plot", str(houses_a), "--check3-out", str(out_a)]
    ) == 0
    _pin_plots(monkeypatch, plots_b, houses_b)
    out_b = second / "check3.json"
    assert source_main(
        ["--plot-bands", str(plots_b), "--gis-house-plot", str(houses_b), "--check3-out", str(out_b)]
    ) == 0
    assert out_a.read_bytes() == out_b.read_bytes()
    loaded = json.loads(out_a.read_bytes())
    assert set(loaded) == {"label", "zones"}
    assert "status" not in loaded


def _join_row(zone: str) -> dict[str, dict]:
    return {
        "builder_output": {
            "zone": zone,
            "price": 10,
            "count_in_1d": True,
            "unavailable": False,
            "model_failure": False,
            "hla": False,
        },
        "primary_estimates": {
            "zone": zone,
            "share": 0.2,
            "land_per_home": 2,
            "unavailable": False,
            "count_in_1d": True,
        },
        "fitted_hedonic": {
            "zone": zone,
            "share": 0.2,
            "land_per_home": 2,
            "unavailable": False,
            "model_failure": False,
            "count_in_1d": True,
        },
        "check4_rent_route": {"zone": zone, "residual_land": 4, "capitalised_land": 4},
        "dz2022_keys": {
            "zone": zone,
            "dz2022": zone,
            "share_low": 0.1,
            "share_central": 0.2,
            "share_high": 0.3,
        },
        "ur6": {"zone": zone, "ur6": 1 if zone < "Z4" else 2},
    }


def _write_join_sources(tmp_path: Path, check3: bytes) -> dict[str, Path]:
    rows = [_join_row(f"Z{index}") for index in range(8)]
    files = {name: tmp_path / f"{name}.json" for name in SOURCE_NAMES}
    for name in SOURCE_NAMES:
        if name == "check3_plot_passes":
            files[name].write_bytes(check3)
            continue
        zones = [item[name] for item in rows]
        files[name].write_text(
            json.dumps({"label": "SYNTHETIC", "zones": zones}) + "\n",
            encoding="utf-8",
        )
    return files


def test_w2_record_is_not_run_downstream(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. The record joins with no check-3 fields and the holdout keeps its sha256."""
    files = _write_join_sources(tmp_path, not_run_record_text().encode("utf-8"))
    out = tmp_path / "checks.json"
    assert b6_main(_b6_argv(out, files, "2023")) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["primary_zones"]
    for zone in payload["primary_zones"] + payload["secondary_zones"]:
        assert "pass_at" not in zone
    scored = score_both(payload["primary_zones"], payload["secondary_zones"], year=2023)
    assert scored["diagnostics (non-gating)"]["3"]["status"] == "NOT_RUN"
    assert scored["diagnostics (non-gating)"]["3"]["reason"] == AM1_REASON
    assert scored["publication"]["am1_label"] in {AM1_PASSED_LABEL, AM1_FAILED_LABEL}

    hold_root = tmp_path / "hold"
    hold_root.mkdir()
    paths = _layout(hold_root)
    paths["check3"].write_bytes(not_run_record_text().encode("utf-8"))
    monkeypatch.setitem(MERGE_PINS, "merge_map", sha256_file(paths["merge_map"]))
    assert score_main(_args(paths, paths["out"], holdout=True, score=False)) == 0
    report = json.loads(paths["out"].read_text(encoding="utf-8"))
    diagnostic = report["holdout_scores"]["diagnostics (non-gating)"]["3"]
    assert diagnostic["status"] == "NOT_RUN"
    assert diagnostic["reason"] == AM1_REASON
    assert "AM-1" in report["holdout_scores"]["publication"]["am1_label"]
    locked = json.loads(paths["lock"].read_text(encoding="utf-8"))["frozen_set"]
    frozen_paths = {
        "merge_map": paths["merge_map"],
        "hedonic_coefs_2021_22": paths["coefs"],
        "code_sha8_block": paths["sha8"],
        "check3_plot_passes": paths["check3"],
        "check4_rent_route": paths["check4"],
        "ur6": paths["ur6"],
        "dz2022_keys": paths["dz"],
    }
    assert locked == frozen_set_members(frozen_paths)
    file_sha256 = hashlib.sha256(paths["check3"].read_bytes()).hexdigest()
    assert file_sha256 == sha256_file(paths["check3"])
    assert locked["b6_pins"] == b6_pins_sha256(frozen_paths)


def test_w3_record_under_2024_is_rule_f(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A 2023 NOT_RUN record is refused on both 2024 entry points."""
    raw = not_run_record_text().encode("utf-8")
    b6 = _rule_message("B6", "f")
    score = _rule_message("SCORE_2024", "f")
    _assert_b6_refused(tmp_path / "b6", monkeypatch, capsys, raw, b6, year="2024")
    _assert_holdout_refused(tmp_path / "score", monkeypatch, capsys, raw, score, score_2024=True)


def test_w4_absent_file_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. Absent check 3 keeps the four existing messages."""
    missing = tmp_path / "missing-check3.json"
    b6_message = f"B6: ERROR: file: expected {missing}, got absent"
    calls = {"join": 0, "score": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_inputs.join_sources",
        lambda *_args, **_kwargs: calls.__setitem__("join", calls["join"] + 1),
    )
    monkeypatch.setattr(
        "scripts.rerun_v14_score._score_holdout",
        lambda *_args, **_kwargs: calls.__setitem__("score", calls["score"] + 1),
    )
    for year in ("2023", "2024"):
        files = _sources(tmp_path / year, b"{}")
        files["check3_plot_passes"].unlink()
        out = tmp_path / year / "checks.json"
        argv = ["--out", str(out), "--year", year, "--check3-plot-passes", str(missing)]
        for name, path in files.items():
            if name == "check3_plot_passes":
                continue
            argv.extend([f"--{name.replace('_', '-')}", str(path), "--pin", f"{name}={file_sha(path)}"])
        with pytest.raises(CheckInputError) as raised:
            load_source(missing, "check3_plot_passes", mode=int(year))
        assert str(raised.value) == b6_message
        assert b6_main(argv) == 1
        assert not out.exists()
        assert capsys.readouterr().err == b6_message + "\n"

    rerun_root = tmp_path / "rerun"
    rerun_root.mkdir()
    paths = _layout(rerun_root)
    paths["check3"].unlink()
    out = tmp_path / "rerun-report.json"
    holdout_argv = [arg for arg in _args(paths, out, holdout=True, score=False) if arg != str(paths["check3"])]
    holdout_argv = [arg for arg in holdout_argv if arg != "--check3-plot-passes"]
    assert score_main(holdout_argv) == 1
    holdout_message = "HOLDOUT_2023: REFUSED: frozen_set check3_plot_passes: expected path, got absent"
    assert capsys.readouterr().err == holdout_message + "\n"
    score_message = (
        "SCORE_2024: REFUSED: frozen_set: expected complete, got partial\n"
        "SCORE_2024: REFUSED: frozen_set check3_plot_passes: expected path, got absent"
    )
    holdout_args = argparse.Namespace(
        merge_map=paths["merge_map"],
        hedonic_coefs=paths["coefs"],
        sha8_block=paths["sha8"],
        check3_plot_passes=None,
        check4_rent_route=paths["check4"],
        ur6=paths["ur6"],
        dz2022_keys=paths["dz"],
    )
    with pytest.raises(HoldoutLockError) as holdout_raised:
        raise_missing_frozen(holdout_args, "HOLDOUT_2023")
    assert str(holdout_raised.value) == holdout_message
    with pytest.raises(HoldoutLockError) as score_raised:
        _frozen_paths(holdout_args)
    assert str(score_raised.value) == score_message

    score_out = tmp_path / "score-report.json"
    score_argv = [arg for arg in _args(paths, score_out, holdout=False, score=True) if arg != str(paths["check3"])]
    score_argv = [arg for arg in score_argv if arg != "--check3-plot-passes"]
    assert score_main(score_argv) == 1
    assert capsys.readouterr().err == score_message + "\n"
    assert calls == {"join": 0, "score": 0}
    assert not out.exists()
    assert not score_out.exists()
    assert not paths["lock"].exists()


@pytest.mark.parametrize("step_mode", ["b6", "holdout"])
def test_w5_wrong_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    step_mode: str,
) -> None:
    """SYNTHETIC. A shortened reason is rule d on both 2023 entry points."""
    got = "C_council: not pinned"
    raw = _record_bytes(reason=got)
    if step_mode == "b6":
        _assert_b6_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("B6", "d", got), year="2023")
    else:
        _assert_holdout_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("HOLDOUT_2023", "d", got))


@pytest.mark.parametrize("status", ["FAIL", "not_run"])
@pytest.mark.parametrize("step_mode", ["b6", "holdout"])
def test_w6_bad_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    step_mode: str,
) -> None:
    """SYNTHETIC. A status other than NOT_RUN is rule a on both 2023 entry points."""
    raw = _record_bytes(status=status)
    if step_mode == "b6":
        _assert_b6_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("B6", "a", status), year="2023")
    else:
        _assert_holdout_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("HOLDOUT_2023", "a", status))


@pytest.mark.parametrize("step_mode", ["b6", "holdout"])
def test_w7_passes_key_with_not_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    step_mode: str,
) -> None:
    """SYNTHETIC. passes beside NOT_RUN is rule b on both 2023 entry points."""
    raw = _record_bytes(passes=[{"zone": "Z1"}])
    if step_mode == "b6":
        _assert_b6_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("B6", "b"), year="2023")
    else:
        _assert_holdout_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("HOLDOUT_2023", "b"))


@pytest.mark.parametrize("step_mode", ["b6", "holdout"])
def test_w8_extra_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    step_mode: str,
) -> None:
    """SYNTHETIC. An extra detail field is rule c on both 2023 entry points."""
    raw = _record_bytes(detail="SYNTHETIC")
    got = ["detail", "reason", "status", "year"]
    if step_mode == "b6":
        _assert_b6_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("B6", "c", got), year="2023")
    else:
        _assert_holdout_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("HOLDOUT_2023", "c", got))


@pytest.mark.parametrize(("value", "shown"), [("2023", "2023"), (2024, 2024)])
@pytest.mark.parametrize("step_mode", ["b6", "holdout"])
def test_w9_record_year_must_be_int_2023(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: object,
    shown: object,
    step_mode: str,
) -> None:
    """SYNTHETIC. A string year and a 2024 year are rule e on both 2023 entry points."""
    raw = _record_bytes(year=value)
    if step_mode == "b6":
        _assert_b6_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("B6", "e", shown), year="2023")
    else:
        _assert_holdout_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("HOLDOUT_2023", "e", shown))


@pytest.mark.parametrize(("value", "shown"), [(2023.0, 2023.0), (True, True)])
@pytest.mark.parametrize("step_mode", ["b6", "holdout"])
def test_w9c_w9d_bool_and_float_year(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: object,
    shown: object,
    step_mode: str,
) -> None:
    """SYNTHETIC. A float year and a bool year are rule e on both 2023 entry points."""
    raw = _record_bytes(year=value)
    if step_mode == "b6":
        _assert_b6_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("B6", "e", shown), year="2023")
    else:
        _assert_holdout_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("HOLDOUT_2023", "e", shown))


def test_w10_2024_passes_file_still_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. A passes file is accepted in 2024 and check 3 still gates."""
    passes = {
        "label": "SYNTHETIC",
        "zones": [
            {
                "zone": "Z1",
                "pass_at": {"20": True, "30": True, "40": True},
            }
        ],
    }
    raw = (json.dumps(passes) + "\n").encode("utf-8")
    assert validate_check3_record(raw, year=2024, step="SCORE_2024") == "passes"
    assert "status" not in json.loads(raw)
    zones = _passing_zones()
    accepted = score_both(zones, zones, year=2024)
    assert accepted["primary"]["gating"]["3"]["pass"] is True
    assert "3" in gating_marks(2024)
    failed_zones = []
    for zone in zones:
        row = dict(zone)
        row["pass_at"] = {20: False, 30: False, 40: False}
        failed_zones.append(row)
    failed = score_both(failed_zones, failed_zones, year=2024)
    assert failed["publish"] is False
    assert failed["publication"]["publish_primary"] is False
    assert failed["publication"]["outcome"] == "both_fail_publish_neither"
    assert failed["primary"]["gating"]["3"]["pass"] is False

    paths = _layout(tmp_path)
    paths["check3"].write_bytes(raw)
    paths["checks"].write_text(
        json.dumps({"label": "SYNTHETIC", "primary_zones": failed_zones, "secondary_zones": failed_zones}) + "\n",
        encoding="utf-8",
    )
    _holdout(paths, monkeypatch)
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 0
    scored = json.loads(out.read_text(encoding="utf-8"))["score_2024"]
    assert scored["publish"] is False
    assert scored["publication"]["outcome"] == "both_fail_publish_neither"
    assert scored["primary"]["gating"]["3"]["pass"] is False


def test_w11_validator_is_defined_once() -> None:
    """SYNTHETIC. The validator is imported by both entry points. The reason literal stays put."""
    defined: list[Path] = []
    importers: list[Path] = []
    needle = AM1_REASON
    literal_hits: list[Path] = []
    for path in BACKEND.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if needle in text:
            literal_hits.append(path)
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "validate_check3_record":
                defined.append(path)
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "validate_check3_record":
                        importers.append(path)
    assert defined == [BACKEND / "georgist" / "check3_record.py"]
    imported = {path.name for path in importers}
    assert "build_v14_check_inputs.py" in imported
    assert "rerun_v14_score.py" in imported
    assert literal_hits == [BACKEND / "georgist" / "surface_v14_checks.py"]


@pytest.mark.parametrize(
    ("raw", "kind", "got"),
    [
        (b"", "json", None),
        (b"{not json", "json", None),
        (b"[]", "type", "list"),
        (b"null", "type", "NoneType"),
        (b"\xff", "json", None),
    ],
)
@pytest.mark.parametrize("step_mode", ["b6", "holdout"])
def test_w13_invalid_json_and_non_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: bytes,
    kind: str,
    got: str | None,
    step_mode: str,
) -> None:
    """SYNTHETIC. Empty, broken, non-object, and invalid UTF-8 bytes refuse on both entry points."""
    if step_mode == "b6":
        _assert_b6_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("B6", kind, got), year="2023")
    else:
        _assert_holdout_refused(tmp_path, monkeypatch, capsys, raw, _rule_message("HOLDOUT_2023", kind, got))
