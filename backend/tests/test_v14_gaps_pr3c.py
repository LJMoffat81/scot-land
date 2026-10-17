"""PR 3c: the 2024 check-input path and the #219 cleanups.

SYNTHETIC fixtures only. No 2024 price cell is read.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

from georgist.v14_b2 import B2Error, adapt_house_sales, scan_measurement_labels
from georgist.v14_d7_chain import PIN_TABLE, run_d7_chain, sha256_file
from georgist.v14_score_report import PIN_TABLE as MERGE_PINS
from georgist.v14_score_report import input_years
from scripts.build_v14_check_inputs import sha256_file as file_sha
from scripts.build_v14_check_inputs import main as b6_main
from scripts.rerun_v14_score import main as score_main
from test_v14_gaps_pr2_chain import FILTER1, FILTER2, _baseline
from test_v14_gaps_pr2_lock import _args, _holdout, _layout, _score_stub
from v14_dryrun.dryrun import run as dry_run

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v14_pr3c"
HOUSE_HEADER = [
    "GeographyCode",
    "GeographyName",
    "GeographyType",
    "DateCode",
    "Measurement",
    "Units",
    "Value",
    "Sales",
]
SENTINEL = "SENTINEL_VALUE"


def test_pr3c_fixtures_are_labelled_synthetic() -> None:
    """SYNTHETIC. Every committed PR 3c fixture carries the label."""
    found = False
    for path in FIXTURES.rglob("*"):
        if not path.is_file():
            continue
        found = True
        text = path.read_text(encoding="utf-8")
        assert "SYNTHETIC" in text
        assert "\u00a3" not in text
    assert found


def _zone_sources(tmp_path: Path, *, builder_zones: list[dict], primary_zones: list[dict], fitted_zones: list[dict]) -> dict[str, Path]:
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
        json.dumps({"label": "SYNTHETIC", "zones": builder_zones}) + "\n",
        encoding="utf-8",
    )
    files["primary_estimates"].write_text(
        json.dumps({"label": "SYNTHETIC", "zones": primary_zones}) + "\n",
        encoding="utf-8",
    )
    files["fitted_hedonic"].write_text(
        json.dumps({"label": "SYNTHETIC", "zones": fitted_zones}) + "\n",
        encoding="utf-8",
    )
    files["check3_plot_passes"].write_text(
        json.dumps(
            {
                "label": "SYNTHETIC",
                "zones": [
                    {
                        "zone": "Z1",
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
            {"label": "SYNTHETIC", "zones": [{"zone": "Z1", "residual_land": 4, "capitalised_land": 4}]}
        )
        + "\n",
        encoding="utf-8",
    )
    files["dz2022_keys"].write_text(
        json.dumps(
            {
                "label": "SYNTHETIC",
                "zones": [
                    {"zone": "Z1", "dz2022": "Z1", "share_low": 0.1, "share_central": 0.2, "share_high": 0.3}
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    files["ur6"].write_text(
        json.dumps({"label": "SYNTHETIC", "zones": [{"zone": "Z1", "ur6": 1}]}) + "\n",
        encoding="utf-8",
    )
    return files


def _builder(year: object = 2024, **extra) -> dict:
    row = {
        "zone": "Z1",
        "year": year,
        "price": 10,
        "count_in_1d": True,
        "unavailable": False,
        "model_failure": False,
        "hla": False,
    }
    row.update(extra)
    return row


def _primary(year: object = 2024) -> dict:
    return {
        "zone": "Z1",
        "year": year,
        "share": 0.2,
        "land_per_home": 2,
        "unavailable": False,
        "count_in_1d": True,
    }


def _fitted(year: object = 2024) -> dict:
    return {
        "zone": "Z1",
        "year": year,
        "share": 0.2,
        "land_per_home": 2,
        "unavailable": False,
        "model_failure": False,
        "count_in_1d": True,
    }


def _fit_file(path: Path, coefficient: float = 0.2) -> Path:
    path.write_text(
        json.dumps(
            {
                "label": "SYNTHETIC",
                "coefficients": [coefficient],
                "beta_by_cell": {"c": coefficient},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _lock_for(path: Path, coefs: Path) -> None:
    path.write_text(
        json.dumps({"frozen_set": {"hedonic_coefs_2021_22": file_sha(coefs)}}) + "\n",
        encoding="utf-8",
    )


def _argv(out: Path, files: dict[str, Path], year: str, coefs: Path, lock: Path) -> list[str]:
    argv = ["--out", str(out), "--year", year, "--lock", str(lock), "--hedonic-coefs", str(coefs)]
    for name, path in files.items():
        argv.extend([f"--{name.replace('_', '-')}", str(path), "--pin", f"{name}={file_sha(path)}"])
    return argv


def _baseline_2024(tmp_path: Path) -> tuple[dict[str, Path], Path, Path, Path]:
    files = _zone_sources(
        tmp_path,
        builder_zones=[_builder()],
        primary_zones=[_primary()],
        fitted_zones=[_fitted()],
    )
    coefs = _fit_file(tmp_path / "coefs.json")
    lock = tmp_path / "holdout.lock"
    _lock_for(lock, coefs)
    out = tmp_path / "checks.json"
    return files, coefs, lock, out


def test_b6_2024_accepts_only_2024(tmp_path: Path) -> None:
    """SYNTHETIC. 2024 mode writes the check file and every row year is 2024."""
    files, coefs, lock, out = _baseline_2024(tmp_path)
    assert b6_main(_argv(out, files, "2024", coefs, lock)) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    rows = payload["primary_zones"] + payload["secondary_zones"]
    assert rows
    assert [row["year"] for row in rows] == [2024, 2024]


def test_b6_2024_refuses_other_year(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. One 2023 row refuses before the join."""
    files, coefs, lock, out = _baseline_2024(tmp_path)
    files["builder_output"].write_text(
        json.dumps({"label": "SYNTHETIC", "zones": [_builder(2023)]}) + "\n",
        encoding="utf-8",
    )
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_inputs.join_sources",
        lambda *_args, **_kwargs: calls.__setitem__("n", calls["n"] + 1),
    )
    assert b6_main(_argv(out, files, "2024", coefs, lock)) == 1
    assert calls["n"] == 0
    assert not out.exists()
    assert capsys.readouterr().err == "B6: REFUSED: year: expected 2024, got 2023\n"


def test_b6_2023_still_refuses_2024(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. 2023 mode refuses year 2024 before the price cell."""
    files, coefs, lock, out = _baseline_2024(tmp_path)
    poisoned = _builder(2024)
    poisoned["price"] = SENTINEL
    files["builder_output"].write_text(
        json.dumps({"label": "SYNTHETIC", "zones": [poisoned]}) + "\n",
        encoding="utf-8",
    )
    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_inputs.read_price_cell",
        lambda value: calls.__setitem__("n", calls["n"] + 1) or value,
    )
    argv = ["--out", str(out), "--year", "2023"]
    for name, path in files.items():
        argv.extend([f"--{name.replace('_', '-')}", str(path), "--pin", f"{name}={file_sha(path)}"])
    assert b6_main(argv) == 1
    assert calls["n"] == 0
    assert not out.exists()
    err = capsys.readouterr().err
    assert err == "B6: REFUSED: year: expected <2024, got 2024\n"
    assert SENTINEL not in err


def test_b6_2024_uses_frozen_coefficients(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. Frozen coefficients are applied once and are not refit."""
    files, coefs, lock, out = _baseline_2024(tmp_path)
    before = json.loads(coefs.read_text(encoding="utf-8"))["coefficients"]
    calls = {"apply": 0, "fit": 0}
    real = __import__("scripts.build_v14_check_inputs", fromlist=["apply_frozen_coefficients"]).apply_frozen_coefficients

    def apply_spy(fit, rows):
        calls["apply"] += 1
        return real(fit, rows)

    def fit_spy(*_args, **_kwargs):
        calls["fit"] += 1
        raise AssertionError("refit")

    monkeypatch.setattr("scripts.build_v14_check_inputs.apply_frozen_coefficients", apply_spy)
    monkeypatch.setattr("scripts.build_v14_check_inputs.fit_headline", fit_spy)
    assert b6_main(_argv(out, files, "2024", coefs, lock)) == 0
    after = json.loads(coefs.read_text(encoding="utf-8"))["coefficients"]
    assert calls == {"apply": 1, "fit": 0}
    assert before == after
    assert out.is_file()


def test_b6_2024_refuses_non_frozen_coefficients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A changed coefficient refuses before apply_frozen_coefficients."""
    files, coefs, lock, out = _baseline_2024(tmp_path)
    locked = file_sha(coefs)
    changed = _fit_file(tmp_path / "changed.json", coefficient=0.3)
    calls = {"apply": 0, "fit": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_inputs.apply_frozen_coefficients",
        lambda *_args, **_kwargs: calls.__setitem__("apply", calls["apply"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_inputs.fit_headline",
        lambda *_args, **_kwargs: calls.__setitem__("fit", calls["fit"] + 1),
    )
    assert b6_main(_argv(out, files, "2024", changed, lock)) == 1
    actual = file_sha(changed)
    assert calls == {"apply": 0, "fit": 0}
    assert not out.exists()
    assert capsys.readouterr().err == (
        "B6: REFUSED: frozen_set hedonic_coefs_2021_22 sha256: "
        f"expected {locked}, got {actual}\n"
    )


def test_score_2024_end_to_end_synthetic(tmp_path: Path) -> None:
    """SYNTHETIC. S4 then S5. Year-file shas are in the report and not in the lock."""
    source = Path(__file__).resolve().parents[1] / "v14_dryrun" / "dryrun.py"
    text = source.read_text(encoding="utf-8")
    assert "def stub" not in text
    result = dry_run(tmp_path)
    assert result["status"] == "passed"
    report_path = Path(result["score_2024"])
    lock_path = Path(result["lock"])
    checks = Path(result["checks_2024"])
    assert report_path.is_file()
    years = input_years(checks)
    assert years
    assert set(years) == {2024}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert report["score_2024"]
    locked_values = set(lock["frozen_set"].values())
    for name, path in result["year_files"].items():
        digest = sha256_file(Path(path))
        assert report["input_paths"][name]["sha256"] == digest
        assert digest not in locked_values
        assert name not in lock["frozen_set"]


def _forge(actual: str) -> str:
    tail = "ab" * 28
    if actual[8:] == tail:
        tail = "cd" * 28
    forged = actual[:8] + tail
    assert len(forged) == 64
    assert forged[:8] == actual[:8]
    assert forged != actual
    return forged


@pytest.mark.parametrize(
    ("step", "check", "pin", "spy_name"),
    [
        ("D7_SOURCE", "sha256", "source", "execute_filter1"),
        ("D7_FILTER1", "script sha256", "filter1_script", "execute_filter1"),
        ("D7_FILTER1_OUT", "sha256", "filter1_output", "execute_filter2"),
        ("D7_FILTER2", "script sha256", "filter2_script", "execute_filter2"),
        ("D7_FILTER2_OUT", "sha256", "filter2_output", "fit_headline"),
    ],
)
def test_d7_chain_shared_prefix_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    step: str,
    check: str,
    pin: str,
    spy_name: str,
) -> None:
    """SYNTHETIC. An 8-character prefix match is NOT_RUN and the next step does not run."""
    paths = _baseline(tmp_path, monkeypatch)
    actuals = {
        "source": sha256_file(paths["source"]),
        "filter1_script": sha256_file(FILTER1),
        "filter1_output": sha256_file(paths["out1"]),
        "filter2_script": sha256_file(FILTER2),
        "filter2_output": sha256_file(paths["out2"]),
    }
    actual = actuals[pin]
    forged = _forge(actual)
    monkeypatch.setitem(PIN_TABLE, pin, forged)
    calls = {"n": 0}

    def spy(*_args, **_kwargs):
        calls["n"] += 1

    monkeypatch.setattr(f"georgist.v14_d7_chain.{spy_name}", spy)
    result = run_d7_chain(
        source=paths["source"],
        filter1_script=FILTER1,
        filter1_output=paths["out1"],
        filter2_script=FILTER2,
        filter2_output=paths["out2"],
    )
    assert result.message == f"{step}: NOT_RUN: {check}: expected {forged}, got {actual}"
    assert calls["n"] == 0


def test_missing_lock_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A missing lock is one SCORE_2024 line and scoring does not run."""
    paths = _layout(tmp_path)
    monkeypatch.setitem(MERGE_PINS, "merge_map", sha256_file(paths["merge_map"]))
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 1
    err = capsys.readouterr().err
    assert [line for line in err.splitlines() if line.startswith("SCORE_2024:")] == [
        f"SCORE_2024: REFUSED: lock: expected {paths['lock']}, got absent"
    ]
    assert err == f"SCORE_2024: REFUSED: lock: expected {paths['lock']}, got absent\n"
    assert "2024 run refused unless the holdout lock exists" not in err
    assert calls["n"] == 0
    assert not out.exists()


def test_holdout_lock_exists_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. A second holdout is one line and leaves the lock untouched."""
    paths = _layout(tmp_path)
    _holdout(paths, monkeypatch)
    before = paths["lock"].read_bytes()
    mtime = paths["lock"].stat().st_mtime_ns
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "again" / "report.json"
    assert score_main(_args(paths, out, holdout=True, score=False)) == 1
    err = capsys.readouterr().err
    assert err == f"HOLDOUT_2023: REFUSED: lock: expected absent, got {paths['lock']}\n"
    assert "second 2023 holdout run refused" not in err
    assert calls["n"] == 0
    assert paths["lock"].read_bytes() == before
    assert paths["lock"].stat().st_mtime_ns == mtime


class _ByteTracker:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.pos = 0
        self.high = 0
        self.seen = bytearray()

    def read(self, n: int = 1) -> bytes:
        if n is None or n < 0:
            n = len(self.payload) - self.pos
        chunk = self.payload[self.pos : self.pos + n]
        self.pos += len(chunk)
        self.high = max(self.high, self.pos)
        self.seen += chunk
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> bool:
        return False


def _house_bytes(rows: list[list[str]]) -> bytes:
    lines = ["# SYNTHETIC", ",".join(HOUSE_HEADER)]
    lines.extend(",".join(row) for row in rows)
    return ("\n".join(lines) + "\n").encode("ascii")


def _track(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> dict[str, _ByteTracker]:
    box: dict[str, _ByteTracker] = {}

    def _open(self, *_args, **_kwargs):
        box["tracker"] = _ByteTracker(payload)
        return box["tracker"]

    monkeypatch.setattr(Path, "open", _open)
    return box


def test_house_sales_streaming_2024(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. DateCode 2024 stops at the end of that field."""
    row = ["S01", "SYNTHETIC zone", "2011 Data Zones", "2024", "Mean", "GBP", SENTINEL, "6"]
    payload = _house_bytes([row])
    path = tmp_path / "house_sales.csv"
    path.write_bytes(payload)
    calls = {"n": 0}
    monkeypatch.setattr(
        "georgist.v14_b2.read_value_cell",
        lambda value: calls.__setitem__("n", calls["n"] + 1) or value,
    )
    box = _track(monkeypatch, payload)
    end = payload.index(b"2024") + len(b"2024")
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == "B2_HOUSE_SALES: ERROR: year row 1: expected <2024, got 2024"
    assert calls["n"] == 0
    assert box["tracker"].high <= end
    assert SENTINEL.encode("ascii") not in box["tracker"].seen
    box = _track(monkeypatch, payload)
    with pytest.raises(B2Error) as scanned:
        scan_measurement_labels(path)
    assert str(scanned.value) == "B2_HOUSE_SALES: ERROR: year row 1: expected <2024, got 2024"
    assert box["tracker"].high <= end
    assert SENTINEL.encode("ascii") not in box["tracker"].seen


@pytest.mark.parametrize(
    ("row", "got"),
    [
        (["S01", "SYNTHETIC zone", "2011 Data Zones", "", "Mean", "GBP", SENTINEL, "6"], "blank"),
        (["S01", "SYNTHETIC zone", "2011 Data Zones"], "short"),
        (["S01", "SYNTHETIC zone", "2011 Data Zones", "20x3", "Mean", "GBP", SENTINEL, "6"], "20x3"),
    ],
)
def test_house_sales_streaming_blank_short_nonint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, row: list[str], got: str
) -> None:
    """SYNTHETIC. A blank, short, or non-integer DateCode does not read a later sentinel."""
    payload = _house_bytes([row, ["S02", "SYNTHETIC zone", "2011 Data Zones", "2021", "Mean", "GBP", SENTINEL, "6"]])
    path = tmp_path / "house_sales.csv"
    path.write_bytes(payload)
    box = _track(monkeypatch, payload)
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == f"B2_HOUSE_SALES: ERROR: year row 1: expected integer, got {got}"
    assert SENTINEL.encode("ascii") not in box["tracker"].seen


def _banned_file_reads(function) -> list[str]:
    tree = ast.parse(inspect.getsource(function))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"read", "read_text", "read_bytes", "readlines"}:
            found.append(node.attr)
        if isinstance(node, ast.Name) and node.id in {"read_text", "read_bytes", "readlines", "read_csv"}:
            found.append(node.id)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            found.append(type(node).__name__)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "list":
            found.append("list")
    return found


def test_house_sales_no_whole_file_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. The house-sales readers do not load the file in one call."""
    assert _banned_file_reads(adapt_house_sales) == []
    assert _banned_file_reads(scan_measurement_labels) == []
    row = ["S01", "SYNTHETIC zone", "2011 Data Zones", "2024", "Mean", "GBP", SENTINEL, "6"]
    payload = _house_bytes([row])
    path = tmp_path / "house_sales.csv"
    path.write_bytes(payload)
    box = _track(monkeypatch, payload)
    end = payload.index(b"2024") + len(b"2024")
    with pytest.raises(B2Error):
        adapt_house_sales(path)
    assert box["tracker"].high <= end
    assert SENTINEL.encode("ascii") not in box["tracker"].seen


@pytest.mark.parametrize(
    ("year", "got"),
    [
        ("", "blank"),
        ("20x4", "20x4"),
        (None, "short"),
    ],
)
def test_b6_2024_year_nonint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    year: object,
    got: str,
) -> None:
    """SYNTHETIC. A blank, non-integer, or missing year refuses before the join and the price."""
    row = _builder()
    if year is None:
        del row["year"]
    else:
        row["year"] = year
    row["price"] = SENTINEL
    files, coefs, lock, out = _baseline_2024(tmp_path)
    files["builder_output"].write_text(
        json.dumps({"label": "SYNTHETIC", "zones": [row]}) + "\n",
        encoding="utf-8",
    )
    calls = {"join": 0, "price": 0}
    monkeypatch.setattr(
        "scripts.build_v14_check_inputs.join_sources",
        lambda *_args, **_kwargs: calls.__setitem__("join", calls["join"] + 1),
    )
    monkeypatch.setattr(
        "scripts.build_v14_check_inputs.read_price_cell",
        lambda value: calls.__setitem__("price", calls["price"] + 1) or value,
    )
    assert b6_main(_argv(out, files, "2024", coefs, lock)) == 1
    assert calls == {"join": 0, "price": 0}
    assert not out.exists()
    assert capsys.readouterr().err == f"B6: ERROR: year row 1: expected integer, got {got}\n"


def test_b6_missing_blank_short_2024(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC. Missing, blank, and short 2024 inputs leave no output."""
    files, coefs, lock, out = _baseline_2024(tmp_path)
    missing = tmp_path / "missing.json"
    argv = _argv(out, files, "2024", coefs, lock)
    argv[argv.index(str(files["builder_output"]))] = str(missing)
    assert b6_main(argv) == 1
    assert capsys.readouterr().err == f"B6: ERROR: file: expected {missing}, got absent\n"
    assert not out.exists()
    blank = _builder()
    blank["price"] = ""
    files["builder_output"].write_text(
        json.dumps({"label": "SYNTHETIC", "zones": [blank]}) + "\n",
        encoding="utf-8",
    )
    assert b6_main(_argv(out, files, "2024", coefs, lock)) == 1
    assert capsys.readouterr().err == "B6: ERROR: price row 1: expected value, got blank\n"
    assert not out.exists()
    short = _builder()
    del short["hla"]
    files["builder_output"].write_text(
        json.dumps({"label": "SYNTHETIC", "zones": [short]}) + "\n",
        encoding="utf-8",
    )
    assert b6_main(_argv(out, files, "2024", coefs, lock)) == 1
    assert capsys.readouterr().err == "B6: ERROR: row 1: expected 7 fields, got 6\n"
    assert not out.exists()
