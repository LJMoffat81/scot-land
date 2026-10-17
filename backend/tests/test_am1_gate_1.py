"""AM-1: check 3 is outside the 2023 gate and still gates 2024.

Synthetic fixtures only. No 2024 price cell is read. No scored public run.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from georgist.surface_paths import REPO_ROOT
from georgist.surface_v14_checks import (
    AM1_FAILED_LABEL,
    AM1_NONGATING_2023,
    AM1_PASSED_LABEL,
    AM1_REASON,
    apply_year_gate,
    gating_marks,
    score_both,
    score_estimator,
)
from georgist.v14_score_report import PIN_TABLE, RECORDED_FILES, sha256_file
from scripts.rerun_v14_score import main as score_main
from test_v14_gaps_pr2_lock import _args, _holdout, _layout
from test_v14_pipeline_b import _zone

BACKEND = Path(__file__).resolve().parents[1]
AMENDMENT = REPO_ROOT / "docs" / "methods" / "v14_prereg_AM1.md"
SIGNOFF = REPO_ROOT / "docs" / "methods" / "v14_prereg_AM1_SIGNOFF.md"
AMENDMENT_SHA256 = "22df5e66740c847eac673d6328cf7ddfd8d56493f4f700745b8ed7691725e04e"
SIGNOFF_TEXT = (
    "Methods Auditor/Statistician (ff0d3261): SIGNED 17 Oct 2026 at "
    "22df5e66740c847eac673d6328cf7ddfd8d56493f4f700745b8ed7691725e04e\n"
)
PRE_AM1_FIXTURE = BACKEND / "tests" / "fixtures" / "v14" / "surface_v14_checks_pre_am1.bytes"
PRE_AM1_SHA256 = "725a7325a1f47776c196d97e3c82ed4938a7df9c4ce46d7ca87218b9f0563fef"
_BARE = "GATING" + "_MARKS"
BARE_MARKS = re.compile(rf"(?<![A-Za-z0-9_]){_BARE}(?![A-Za-z0-9_])")
UPSTREAM = "B5_CHECK3: NOT_RUN: plot_bands header: expected pass_20, got absent"
UPSTREAM_DETAIL = "plot_bands header: expected pass_20, got absent"


def _passing_zones() -> list[dict]:
    return [
        _zone(
            f"P{index}",
            price=float(index + 1),
            share=0.15 + 0.01 * index,
            ur6=1 if index < 5 else 2,
            land_per_home=5.0 if index < 5 else 2.0,
            year=2024,
        )
        for index in range(10)
    ]


def _fail(block: dict, name: str) -> None:
    block["gating"][name] = {**block["gating"][name], "pass": False, "status": "fail"}


def test_t1_gating_marks_are_exact() -> None:
    assert gating_marks(2023) == ("1", "1a", "1b", "1d", "4", "6")
    assert gating_marks(2024) == ("1", "1a", "1b", "1d", "3", "4", "6")
    assert "3" not in gating_marks(2023)
    assert "3" in gating_marks(2024)
    assert AM1_NONGATING_2023 == ("3",)


@pytest.mark.parametrize(
    ("year", "message"),
    [
        (2022, "AM-1: no gating set for year 2022"),
        (2025, "AM-1: no gating set for year 2025"),
        (None, "AM-1: no gating set for year None"),
        ("2023", "AM-1: no gating set for year '2023'"),
        (0, "AM-1: no gating set for year 0"),
    ],
)
def test_t2_unknown_year_is_refused(year: object, message: str) -> None:
    with pytest.raises(ValueError) as exc:
        gating_marks(year)
    assert str(exc.value) == message


@pytest.mark.parametrize("status", ["NOT_RUN", "pending"])
def test_t3_2023_ignores_check3_when_the_gates_pass(status: str) -> None:
    zones = _passing_zones()
    scored = score_both(zones, zones, year=2023, check3_status=status)
    assert scored["publish"] is True
    assert scored["publication"]["am1_label"] == AM1_PASSED_LABEL
    assert scored["publication"]["outcome"] == "publish_range_both"
    assert scored["diagnostics (non-gating)"]["3"] == {
        "status": status,
        "reason": AM1_REASON,
        "detail": None,
    }
    for block in (scored["primary"], scored["secondary"]):
        assert "3" not in block["gating"]
    assert "v1.4 pass" not in json.dumps(scored)


@pytest.mark.parametrize("status", ["NOT_RUN", "FAIL", "pending"])
def test_t4_2024_check3_still_fails_closed(status: str) -> None:
    zones = _passing_zones()
    scored = score_both(zones, zones, year=2024, check3_status=status)
    assert scored["primary"]["gating_pass"] is False
    assert scored["secondary"]["gating_pass"] is False
    assert scored["publication"]["outcome"] == "both_fail_publish_neither"
    assert scored["publication"]["publish_primary"] is False
    assert "am1_label" not in scored["publication"]
    for name in gating_marks(2024):
        if name == "3":
            continue
        assert scored["primary"]["gating"][name]["pass"] is True
        assert scored["secondary"]["gating"][name]["pass"] is True


@pytest.mark.parametrize("name", ["1", "1a", "1b", "1d", "4", "6"])
def test_t5_each_2023_gate_still_fails_the_publish(name: str) -> None:
    zones = _passing_zones()
    primary = score_estimator(zones)
    secondary = score_estimator(zones)
    _fail(primary, name)
    _fail(secondary, name)
    scored = apply_year_gate(primary, secondary, 2023, check3_status="NOT_RUN")
    assert scored["publish"] is False
    assert scored["publication"]["am1_label"] == AM1_FAILED_LABEL
    assert scored["diagnostics (non-gating)"]["3"]["status"] == "NOT_RUN"
    assert name in scored["primary"]["gating"]
    assert "3" not in scored["primary"]["gating"]


def test_t6_2023_check3_fail_does_not_decide_publish() -> None:
    zones = _passing_zones()
    scored = score_both(zones, zones, year=2023, check3_status="FAIL")
    assert scored["publish"] is True
    assert scored["publication"]["am1_label"] == AM1_PASSED_LABEL
    assert scored["diagnostics (non-gating)"]["3"] == {
        "status": "FAIL",
        "reason": AM1_REASON,
        "detail": None,
    }
    assert "3" not in scored["primary"]["gating"]
    assert "3" not in scored["secondary"]["gating"]


def test_t7_bare_name_is_gone_and_2023_output_has_no_full_pass_string() -> None:
    offenders = []
    for path in BACKEND.rglob("*.py"):
        if BARE_MARKS.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(BACKEND)))
    assert offenders == []
    zones = _passing_zones()
    scored = score_both(zones, zones, year=2023, check3_status="NOT_RUN")
    assert "v1.4 pass" not in json.dumps(scored)


def test_t11_upstream_b5_detail_stays_out_of_the_gate() -> None:
    zones = _passing_zones()
    scored = score_both(zones, zones, year=2023, check3_upstream=UPSTREAM)
    assert scored["diagnostics (non-gating)"]["3"] == {
        "status": "NOT_RUN",
        "reason": AM1_REASON,
        "detail": UPSTREAM_DETAIL,
    }
    assert scored["publish"] is True
    assert "3" not in scored["primary"]["gating"]
    primary = score_estimator(zones)
    secondary = score_estimator(zones)
    _fail(primary, "4")
    _fail(secondary, "4")
    refused = apply_year_gate(primary, secondary, 2023, check3_upstream=UPSTREAM)
    assert refused["publish"] is False
    assert refused["publication"]["am1_label"] == AM1_FAILED_LABEL
    assert refused["diagnostics (non-gating)"]["3"]["detail"] == UPSTREAM_DETAIL


def test_t12_pre_am1_module_bytes_refuse_the_2024_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "backend/georgist/surface_v14_checks.py" in RECORDED_FILES
    pre = PRE_AM1_FIXTURE.read_bytes()
    assert hashlib.sha256(pre).hexdigest() == PRE_AM1_SHA256
    current = (BACKEND / "georgist" / "surface_v14_checks.py").read_bytes()
    assert pre != current
    paths = _layout(tmp_path)
    paths["sha8"].write_bytes(pre)
    _holdout(paths, monkeypatch)
    paths["sha8"].write_bytes(current)
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 1
    locked = json.loads(paths["lock"].read_text(encoding="utf-8"))["frozen_set"]["code_sha8_block"]
    message = (
        "SCORE_2024: REFUSED: frozen_set code_sha8_block sha256: "
        f"expected {locked}, got {sha256_file(paths['sha8'])}"
    )
    assert message in capsys.readouterr().err
    assert locked == hashlib.sha256(pre).hexdigest()
    assert not out.exists()


def test_t13_amendment_bytes_and_signoff_line() -> None:
    assert hashlib.sha256(AMENDMENT.read_bytes()).hexdigest() == AMENDMENT_SHA256
    assert SIGNOFF.read_bytes() == SIGNOFF_TEXT.encode("utf-8")


def _not_run_plot(_zones: list, _field: str) -> dict:
    return {"check": "3", "pass": None, "status": "NOT_RUN"}


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    original = gating_marks
    seen: list[object] = []

    def spy(year: object) -> tuple[str, ...]:
        seen.append(year)
        return original(year)

    monkeypatch.setattr("georgist.surface_v14_checks.gating_marks", spy)
    return seen


def _ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    paths = _layout(tmp_path)
    zones = _passing_zones()
    paths["checks"].write_text(
        json.dumps({"primary_zones": zones, "secondary_zones": zones}),
        encoding="utf-8",
    )
    _holdout(paths, monkeypatch)
    return paths


def test_t9_score_2024_calls_only_2024_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _ready(tmp_path, monkeypatch)
    seen = _spy(monkeypatch)
    monkeypatch.setattr("georgist.surface_v14_checks._plot", _not_run_plot)
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 0
    assert seen == [2024]
    scored = json.loads(out.read_text(encoding="utf-8"))["score_2024"]
    assert scored["primary"]["gating_pass"] is False
    assert scored["secondary"]["gating_pass"] is False
    assert scored["publication"]["outcome"] == "both_fail_publish_neither"
    assert scored["publication"]["publish_primary"] is False
    assert "am1_label" not in scored["publication"]
    for block in (scored["primary"], scored["secondary"]):
        assert block["gating"]["3"]["status"] == "NOT_RUN"
        for name in gating_marks(2024):
            if name != "3":
                assert block["gating"][name]["pass"] is True


def test_t9b_holdout_2023_calls_only_2023(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _layout(tmp_path)
    zones = _passing_zones()
    paths["checks"].write_text(
        json.dumps({"primary_zones": zones, "secondary_zones": zones}),
        encoding="utf-8",
    )
    monkeypatch.setitem(PIN_TABLE, "merge_map", sha256_file(paths["merge_map"]))
    seen = _spy(monkeypatch)
    out = tmp_path / "holdout" / "report.json"
    assert score_main(_args(paths, out, holdout=True, score=False)) == 0
    assert seen == [2023]
    report = json.loads(out.read_text(encoding="utf-8"))
    assert "v1.4 pass" not in json.dumps(report)
    assert report["holdout_scores"]["publication"]["am1_label"] == AM1_PASSED_LABEL


def _reject_year_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    flag: str,
    year: str,
) -> None:
    seen = _spy(monkeypatch)
    score_calls: list[int] = []

    def score_spy(*_args, **_kwargs):
        score_calls.append(1)
        raise AssertionError("scoring ran")

    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", score_spy)
    out = tmp_path / "report.json"
    with pytest.raises(SystemExit) as exc:
        score_main(["--out", str(out), flag, "--year", year])
    assert exc.value.code == 2
    assert f"unrecognized arguments: --year {year}" in capsys.readouterr().err
    assert seen == []
    assert score_calls == []
    assert not out.exists()


def test_t10a_score_2024_rejects_a_year_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _reject_year_flag(monkeypatch, capsys, tmp_path, "--score-2024", "2023")


def test_t10b_holdout_2023_rejects_a_year_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _reject_year_flag(monkeypatch, capsys, tmp_path, "--holdout-2023", "2024")


def _report_of(paths: dict[str, Path], out: Path, *, holdout: bool, score: bool) -> dict:
    assert score_main(_args(paths, out, holdout=holdout, score=score)) == 0
    return json.loads(out.read_text(encoding="utf-8"))


def test_t10c_env_year_does_not_change_the_2024_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    left_root = tmp_path / "left"
    right_root = tmp_path / "right"
    left_root.mkdir()
    right_root.mkdir()
    left = _ready(left_root, monkeypatch)
    right = _ready(right_root, monkeypatch)
    seen = _spy(monkeypatch)
    monkeypatch.delenv("SCOTLAND_YEAR", raising=False)
    plain = _report_of(left, left_root / "score" / "report.json", holdout=False, score=True)
    assert seen == [2024]
    seen.clear()
    monkeypatch.setenv("SCOTLAND_YEAR", "2023")
    overridden = _report_of(right, right_root / "score" / "report.json", holdout=False, score=True)
    assert seen == [2024]
    assert overridden == plain
    assert os.environ["SCOTLAND_YEAR"] == "2023"


def test_t10d_env_year_does_not_change_the_2023_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def prepared(root: Path) -> dict[str, Path]:
        paths = _layout(root)
        zones = _passing_zones()
        paths["checks"].write_text(
            json.dumps({"primary_zones": zones, "secondary_zones": zones}),
            encoding="utf-8",
        )
        monkeypatch.setitem(PIN_TABLE, "merge_map", sha256_file(paths["merge_map"]))
        return paths

    left_root = tmp_path / "left"
    right_root = tmp_path / "right"
    left_root.mkdir()
    right_root.mkdir()
    left = prepared(left_root)
    right = prepared(right_root)
    seen = _spy(monkeypatch)
    monkeypatch.delenv("SCOTLAND_YEAR", raising=False)
    plain = _report_of(left, left["out"], holdout=True, score=False)
    assert seen == [2023]
    seen.clear()
    monkeypatch.setenv("SCOTLAND_YEAR", "2024")
    overridden = _report_of(right, right["out"], holdout=True, score=False)
    assert seen == [2023]
    assert overridden == plain


def test_t10e_entry_points_do_not_read_year_from_env_or_config() -> None:
    modules = [
        BACKEND / "georgist" / "surface_v14_checks.py",
        BACKEND / "scripts" / "rerun_v14_score.py",
    ]
    for path in modules:
        text = path.read_text(encoding="utf-8")
        assert "os.environ" not in text
        assert "os.getenv" not in text
        assert "SCOTLAND_YEAR" not in text
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
                raise AssertionError(f"{path.name} reads {node.attr}")
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                if node.slice.value in {"year", "SCOTLAND_YEAR"}:
                    raise AssertionError(f"{path.name} reads config key {node.slice.value}")
    script = ast.parse((BACKEND / "scripts" / "rerun_v14_score.py").read_text(encoding="utf-8"))
    years = []
    for node in ast.walk(script):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            called = func.id == "_score_holdout"
        elif isinstance(func, ast.Attribute):
            called = func.attr == "_score_holdout"
        else:
            called = False
        if not called:
            continue
        year = next(item.value for item in node.keywords if item.arg == "year")
        assert isinstance(year, ast.Constant)
        years.append(year.value)
    assert years == [2023, 2024]
