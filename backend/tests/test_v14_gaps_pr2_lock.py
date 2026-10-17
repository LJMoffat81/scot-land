"""PR 2 corrected R4 lock. SYNTHETIC fixtures only. No 2024 price cell is read."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from georgist.v14_score_report import PIN_TABLE, HoldoutLockError, sha256_file
from scripts.rerun_v14_score import main as score_main
from test_v14_pipeline_b import _zone


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


def _score_stub():
    calls = {"n": 0}

    def spy(*_args, **_kwargs):
        calls["n"] += 1
        return {
            "primary": {"gating_pass": False},
            "secondary": {"gating_pass": False},
            "publication": {"outcome": "both_fail_publish_neither"},
            "checks_include_hbu": False,
        }

    return calls, spy


def _line(err: str, prefix: str) -> str:
    matches = [line for line in err.splitlines() if line.startswith(prefix)]
    assert matches, err
    return matches[0]


def _layout(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "merge_map": tmp_path / "merge.csv",
        "coefs": tmp_path / "coefs.json",
        "sha8": tmp_path / "sha8.json",
        "check3": tmp_path / "check3.json",
        "check4": tmp_path / "check4.json",
        "ur6": tmp_path / "ur6.json",
        "dz": tmp_path / "dz.json",
        "builder": tmp_path / "builder.json",
        "primary": tmp_path / "primary.json",
        "fitted": tmp_path / "fitted.json",
        "year": tmp_path / "years.csv",
        "checks": tmp_path / "checks.json",
        "lock": tmp_path / "holdout.lock",
        "out": tmp_path / "holdout" / "report.json",
    }
    paths["merge_map"].write_text("dz2011,cell\nS01,c\n", encoding="utf-8")
    paths["coefs"].write_text('{"beta": 0.2}\n', encoding="utf-8")
    paths["sha8"].write_text('{"backend/georgist/surface_rent.py": "dc07f4fe"}\n', encoding="utf-8")
    paths["check3"].write_text('{"pass_at": {"20": true}}\n', encoding="utf-8")
    paths["check4"].write_text('{"residual_land": 1}\n', encoding="utf-8")
    paths["ur6"].write_text('{"ur6": 1}\n', encoding="utf-8")
    paths["dz"].write_text('{"dz2022": "S01"}\n', encoding="utf-8")
    paths["builder"].write_text('{"year": 2024, "label": "SYNTHETIC"}\n', encoding="utf-8")
    paths["primary"].write_text('{"year": 2024, "label": "SYNTHETIC"}\n', encoding="utf-8")
    paths["fitted"].write_text('{"year": 2024, "label": "SYNTHETIC"}\n', encoding="utf-8")
    paths["year"].write_text("# SYNTHETIC\nyear,price\n2024,SYNTHETIC\n", encoding="utf-8")
    paths["checks"].write_text(
        json.dumps({"primary_zones": _zones(2023), "secondary_zones": _zones(2023)}),
        encoding="utf-8",
    )
    return paths


def _args(paths: dict[str, Path], out: Path, *, holdout: bool, score: bool, year_files: list[Path] | None = None) -> list[str]:
    files = [paths["year"]] if year_files is None else year_files
    command = [
        "--out",
        str(out),
        "--lock-path",
        str(paths["lock"]),
        "--check-inputs",
        str(paths["checks"]),
        "--merge-map",
        str(paths["merge_map"]),
        "--hedonic-coefs",
        str(paths["coefs"]),
        "--sha8-block",
        str(paths["sha8"]),
        "--check3-plot-passes",
        str(paths["check3"]),
        "--check4-rent-route",
        str(paths["check4"]),
        "--ur6",
        str(paths["ur6"]),
        "--dz2022-keys",
        str(paths["dz"]),
        "--builder-output",
        str(paths["builder"]),
        "--primary-estimates",
        str(paths["primary"]),
        "--fitted-per-zone",
        str(paths["fitted"]),
    ]
    for path in files:
        command.extend(["--year-file", str(path)])
    if holdout:
        command.append("--holdout-2023")
    if score:
        command.append("--score-2024")
    return command


def _holdout(paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setitem(PIN_TABLE, "merge_map", sha256_file(paths["merge_map"]))
    assert score_main(_args(paths, paths["out"], holdout=True, score=False)) == 0
    payload = json.loads(paths["lock"].read_text(encoding="utf-8"))
    return payload["frozen_set_sha256"]


def _hash(path: Path) -> str:
    return json.loads(path.read_text(encoding="utf-8"))["frozen_set_sha256"]


def test_r4_valid_synthetic_2024_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A locked frozen set and input_years [2024] score once."""
    paths = _layout(tmp_path)
    baseline = _holdout(paths, monkeypatch)
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 0
    assert calls["n"] == 1
    assert out.is_file()
    assert _hash(paths["lock"]) == baseline


def test_r4_frozen_merge_map_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. One changed merge-map byte refuses before scoring."""
    paths = _layout(tmp_path)
    _holdout(paths, monkeypatch)
    paths["merge_map"].write_bytes(paths["merge_map"].read_bytes() + b"\n")
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 1
    locked = json.loads(paths["lock"].read_text(encoding="utf-8"))["frozen_set"]["merge_map"]
    assert _line(capsys.readouterr().err, "SCORE_2024:") == (
        f"SCORE_2024: REFUSED: frozen_set merge_map sha256: expected {locked}, got {sha256_file(paths['merge_map'])}"
    )
    assert calls["n"] == 0
    assert not out.exists()


def test_r4_frozen_coefs_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. One changed 2021-22 coefficient refuses before scoring."""
    paths = _layout(tmp_path)
    _holdout(paths, monkeypatch)
    paths["coefs"].write_text('{"beta": 0.3}\n', encoding="utf-8")
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 1
    locked = json.loads(paths["lock"].read_text(encoding="utf-8"))["frozen_set"]["hedonic_coefs_2021_22"]
    assert _line(capsys.readouterr().err, "SCORE_2024:") == (
        "SCORE_2024: REFUSED: frozen_set hedonic_coefs_2021_22 sha256: "
        f"expected {locked}, got {sha256_file(paths['coefs'])}"
    )
    assert calls["n"] == 0
    assert not out.exists()


def test_r4_frozen_sha8_block_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. One changed sha8 entry refuses before scoring."""
    paths = _layout(tmp_path)
    _holdout(paths, monkeypatch)
    paths["sha8"].write_text('{"backend/georgist/surface_rent.py": "00000000"}\n', encoding="utf-8")
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 1
    locked = json.loads(paths["lock"].read_text(encoding="utf-8"))["frozen_set"]["code_sha8_block"]
    assert _line(capsys.readouterr().err, "SCORE_2024:") == (
        "SCORE_2024: REFUSED: frozen_set code_sha8_block sha256: "
        f"expected {locked}, got {sha256_file(paths['sha8'])}"
    )
    assert calls["n"] == 0
    assert not out.exists()


@pytest.mark.parametrize(
    "key",
    ("check3", "check4", "ur6", "dz"),
)
def test_r4_frozen_b6_pins_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], key: str
) -> None:
    """SYNTHETIC. Each year-invariant B6 pin refuses as frozen_set b6_pins."""
    paths = _layout(tmp_path)
    _holdout(paths, monkeypatch)
    paths[key].write_bytes(paths[key].read_bytes() + b"\n")
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 1
    locked = json.loads(paths["lock"].read_text(encoding="utf-8"))["frozen_set"]["b6_pins"]
    from georgist.v14_score_report import b6_pins_sha256

    current = b6_pins_sha256(
        {
            "check3_plot_passes": paths["check3"],
            "check4_rent_route": paths["check4"],
            "ur6": paths["ur6"],
            "dz2022_keys": paths["dz"],
        }
    )
    assert _line(capsys.readouterr().err, "SCORE_2024:") == (
        f"SCORE_2024: REFUSED: frozen_set b6_pins sha256: expected {locked}, got {current}"
    )
    assert calls["n"] == 0
    assert not out.exists()


def test_r4_year_file_not_in_input_years(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. An extra year, or a missing 2024 file, refuses input_years."""
    paths = _layout(tmp_path)
    _holdout(paths, monkeypatch)
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    extra = tmp_path / "extra.csv"
    extra.write_text("# SYNTHETIC\nyear,price\n2025,SYNTHETIC\n", encoding="utf-8")
    out = tmp_path / "extra-out" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True, year_files=[paths["year"], extra])) == 1
    assert _line(capsys.readouterr().err, "SCORE_2024:") == "SCORE_2024: REFUSED: input_years: expected [2024], got [2024, 2025]"
    assert calls["n"] == 0
    assert not out.exists()
    out_missing = tmp_path / "missing-out" / "report.json"
    assert score_main(_args(paths, out_missing, holdout=False, score=True, year_files=[])) == 1
    assert _line(capsys.readouterr().err, "SCORE_2024:") == "SCORE_2024: REFUSED: input_years: expected [2024], got []"
    assert calls["n"] == 0
    assert not out_missing.exists()


def test_r4_year_file_change_not_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A 2024 year-file edit does not move the lock hash."""
    paths = _layout(tmp_path)
    baseline = _holdout(paths, monkeypatch)
    paths["year"].write_text("# SYNTHETIC\nyear,price\n2024,OTHER\n", encoding="utf-8")
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 0
    err = capsys.readouterr().err
    assert "SCORE_2024: REFUSED: frozen_set" not in err
    assert _hash(paths["lock"]) == baseline
    assert calls["n"] == 1


def test_r4_lock_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """SYNTHETIC. A missing lock refuses before scoring."""
    paths = _layout(tmp_path)
    monkeypatch.setitem(PIN_TABLE, "merge_map", sha256_file(paths["merge_map"]))
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 1
    assert _line(capsys.readouterr().err, "SCORE_2024:") == f"SCORE_2024: REFUSED: lock: expected {paths['lock']}, got absent"
    assert calls["n"] == 0


def test_r4_holdout_lock_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A second holdout leaves the lock bytes and mtime unchanged."""
    paths = _layout(tmp_path)
    _holdout(paths, monkeypatch)
    before = paths["lock"].read_bytes()
    mtime = paths["lock"].stat().st_mtime_ns
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "again" / "report.json"
    assert score_main(_args(paths, out, holdout=True, score=False)) == 1
    assert _line(capsys.readouterr().err, "HOLDOUT_2023:") == (
        f"HOLDOUT_2023: REFUSED: lock: expected absent, got {paths['lock']}"
    )
    assert calls["n"] == 0
    assert paths["lock"].read_bytes() == before
    assert paths["lock"].stat().st_mtime_ns == mtime


def test_r4_input_year_ne_2024(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. Year 2023 refuses before any price cell is read."""
    paths = _layout(tmp_path)
    _holdout(paths, monkeypatch)
    paths["year"].write_text("# SYNTHETIC\nyear,price\n2023,SENTINEL_PRICE\n", encoding="utf-8")
    calls, spy = _score_stub()
    prices = {"n": 0}
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    monkeypatch.setattr(
        "georgist.v14_score_report.read_price_cell",
        lambda value: prices.__setitem__("n", prices["n"] + 1) or value,
    )
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 1
    assert _line(capsys.readouterr().err, "SCORE_2024:") == "SCORE_2024: REFUSED: input_year: expected 2024, got 2023"
    assert calls["n"] == 0
    assert prices["n"] == 0
    assert not out.exists()


def test_r4_year_b6_source_change_not_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. Year-specific B6 sources stay out of the lock hash."""
    paths = _layout(tmp_path)
    baseline = _holdout(paths, monkeypatch)
    base_report = json.loads(paths["out"].read_text(encoding="utf-8"))
    original_lock = paths["lock"].read_bytes()
    names = {
        "builder_output": "builder",
        "primary_estimates": "primary",
        "fitted_per_zone": "fitted",
    }
    refusals = {"n": 0}
    real = __import__("georgist.v14_score_report", fromlist=["assert_frozen_set"]).assert_frozen_set

    def wrapped(locked, current):
        try:
            real(locked, current)
        except HoldoutLockError:
            refusals["n"] += 1
            raise

    monkeypatch.setattr("scripts.rerun_v14_score.assert_frozen_set", wrapped)
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    for name, key in names.items():
        target = paths[key]
        original = target.read_text(encoding="utf-8")
        target.write_text(original.replace("SYNTHETIC", "SYNTHETIC_CHANGED"), encoding="utf-8")
        lock_copy = tmp_path / f"lock_{key}"
        lock_copy.write_bytes(original_lock)
        paths["lock"] = lock_copy
        out = tmp_path / f"score_{key}" / "report.json"
        assert score_main(_args(paths, out, holdout=False, score=True)) == 0
        err = capsys.readouterr().err
        assert "SCORE_2024: REFUSED: frozen_set" not in err
        assert _hash(lock_copy) == baseline
        report = json.loads(out.read_text(encoding="utf-8"))
        assert report["input_paths"][name]["sha256"] == sha256_file(target)
        assert report["input_paths"][name]["sha256"] != base_report["input_paths"][name]["sha256"]
        target.write_text(original, encoding="utf-8")
    assert refusals["n"] == 0
    assert calls["n"] == 3
