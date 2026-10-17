"""PR 1 fail-closed year screen and fidelity fixes.

SYNTHETIC fixtures only. No 2024 price file is opened.
"""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import pytest
import scipy
import statsmodels

from georgist import v14_hedonic as hedonic
from georgist.surface_v14_checks import score_estimator
from georgist.v14_hedonic import D7_SHA256, S_C3_GTOL
from georgist.v14_score_report import (
    PIN_TABLE,
    S_C3_GTOL_MAPPING,
    S_C3_OPTIMIZER,
    build_report,
    disagreement_markdown,
    frozen_set_members,
    sha256_file,
)
from scripts.build_v14_check_inputs import CheckInputError, load_source
from scripts.build_v14_hedonic_rows import HedonicRowError, _load_sold_tfa, screen_year_column
from scripts.rerun_v14_score import _inputs_sha256
from scripts.rerun_v14_score import main as score_main
from test_v14_pipeline_b import _rows, _zone
from test_v14_pipeline_c2 import _ByteTracker

BACKEND = Path(__file__).resolve().parents[1]
SENTINEL = "SENTINEL_TV_9f3a"


def _raise_before_later_cell(payload: bytes, match: str) -> None:
    tracker = _ByteTracker(payload)
    with pytest.raises(HedonicRowError, match=match) as raised:
        screen_year_column(tracker, "year", "synthetic.csv")
    assert SENTINEL.encode("ascii") not in tracker.seen
    assert SENTINEL not in str(raised.value)


def test_blank_short_and_non_integer_years_raise_before_later_cells() -> None:
    """SYNTHETIC. The year screen fails closed and does not read a later cell."""
    _raise_before_later_cell(
        b"zone,year,price\nS01000001,," + SENTINEL.encode("ascii") + b"\n",
        "blank",
    )
    _raise_before_later_cell(
        b"zone,year,price\nS01000001\nS01000002,2021," + SENTINEL.encode("ascii") + b"\n",
        "short",
    )
    _raise_before_later_cell(
        b"zone,year,price\nS01000001,20x," + SENTINEL.encode("ascii") + b"\n",
        "not an integer",
    )


def test_sold_tfa_and_check_input_year_screen_fail_closed(tmp_path: Path) -> None:
    """SYNTHETIC. The same year rule raises in sold-TFA and B6 load_source."""
    blank = tmp_path / "sold_blank.csv"
    blank.write_text(
        f"zone,year,sold_tfa_mean\nS01000001,,{SENTINEL}\n",
        encoding="utf-8",
    )
    with pytest.raises(HedonicRowError, match="blank") as raised:
        _load_sold_tfa(blank)
    assert SENTINEL not in str(raised.value)

    short = tmp_path / "sold_short.csv"
    short.write_text(
        f"zone,year,sold_tfa_mean\nS01000001\nS01000002,2021,{SENTINEL}\n",
        encoding="utf-8",
    )
    with pytest.raises(HedonicRowError, match="short") as raised_short:
        _load_sold_tfa(short)
    assert SENTINEL not in str(raised_short.value)

    odd = tmp_path / "sold_text.csv"
    odd.write_text(
        f"zone,year,sold_tfa_mean\nS01000001,yy,{SENTINEL}\n",
        encoding="utf-8",
    )
    with pytest.raises(HedonicRowError, match="not an integer") as raised_odd:
        _load_sold_tfa(odd)
    assert SENTINEL not in str(raised_odd.value)

    kept = tmp_path / "sold_ok.csv"
    kept.write_text("zone,year,sold_tfa_mean\nS01000001,2021,80\n", encoding="utf-8")
    assert _load_sold_tfa(kept)[("S01000001", 2021)]["f_m2"] == 80.0

    source = tmp_path / "builder.json"
    source.write_text(
        json.dumps({"zones": [{"zone": "S01000001", "year": "", "price": SENTINEL}]}),
        encoding="utf-8",
    )
    with pytest.raises(CheckInputError, match="blank") as raised_json:
        load_source(source, "builder_output")
    assert SENTINEL not in str(raised_json.value)
    source.write_text(
        json.dumps({"zones": [{"zone": "S01000001", "year": "20x", "price": SENTINEL}]}),
        encoding="utf-8",
    )
    with pytest.raises(CheckInputError, match="not an integer") as raised_text:
        load_source(source, "builder_output")
    assert SENTINEL not in str(raised_text.value)


def test_s_c3_too_few_groups_is_not_run_and_pgtol_reaches_lbfgs(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. Too few groups is NOT_RUN. pgtol is 1e-8 and gtol is not passed."""
    one_group = [
        {"price": 10.0, "a_m2": 20.0, "ur3": "urban"},
        {"price": 11.0, "a_m2": 21.0, "ur3": "urban"},
    ]
    blocked = hedonic._fit_s_c3(one_group)
    assert blocked["status"] == "NOT_RUN"
    assert blocked["reason"] == "MixedLM needs two or more groups"

    seen: dict = {}
    import statsmodels.base.optimizer as opt

    original = opt._fit_lbfgs

    def spy(*args, **kwargs):
        seen["solver_kwargs"] = dict(args[4])
        return original(*args, **kwargs)

    monkeypatch.setattr(opt, "_fit_lbfgs", spy)
    two_groups = [
        {"price": 10.0, "a_m2": 20.0, "ur3": "urban"},
        {"price": 12.0, "a_m2": 22.0, "ur3": "urban"},
        {"price": 20.0, "a_m2": 40.0, "ur3": "rural"},
        {"price": 22.0, "a_m2": 42.0, "ur3": "rural"},
    ]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fitted = hedonic._fit_s_c3(two_groups)
    messages = " ".join(str(item.message) for item in caught)
    assert "unsupported keyword" not in messages
    assert seen["solver_kwargs"]["pgtol"] == S_C3_GTOL
    assert "gtol" not in seen["solver_kwargs"]
    assert "factr" not in seen["solver_kwargs"]
    assert fitted["status"] == "fit"

    class _Unconverged:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def fit(self, *args, **kwargs):
            class _Result:
                converged = False
                fe_params = [0.0, 0.1]

            return _Result()

    monkeypatch.setattr(hedonic, "MixedLM", _Unconverged)
    unconverged = hedonic._fit_s_c3(two_groups)
    assert unconverged["status"] == "NOT_CONVERGED"
    assert unconverged["reason"] == "MixedLM did not converge"
    assert unconverged["status"] != "NOT_RUN"
    assert unconverged["status"] != "ERROR"
    source = Path(hedonic.__file__).read_text(encoding="utf-8")
    assert 'kwargs["pgtol"] = S_C3_GTOL' in source
    assert "gtol=S_C3_GTOL" not in source
    assert "gtol=1e-8 maps to L-BFGS-B pgtol=1e-8" in source


def test_fit_headline_passes_the_d7_sha() -> None:
    """SYNTHETIC. A matching D7 sha runs S-x2. A wrong or missing sha is NOT_RUN."""
    rows = []
    for row in _rows():
        item = dict(row)
        item["ratio_mean"] = 1.0
        rows.append(item)
    matched = hedonic.fit_headline(rows, d7_sha256=D7_SHA256)
    by_id = {item["id"]: item for item in matched["sensitivities"]}
    assert by_id["S-x2"]["status"] == "fit"
    missing = hedonic.fit_headline(rows)
    missed = {item["id"]: item for item in missing["sensitivities"]}
    assert missed["S-x2"]["status"] == "NOT_RUN"
    wrong = hedonic.fit_headline(rows, d7_sha256="not-the-pin")
    refused = {item["id"]: item for item in wrong["sensitivities"]}
    assert refused["S-x2"]["status"] == "NOT_RUN"
    assert "D7" in refused["S-x2"]["reason"]


def test_check3_json_round_trip_counts_passes_at_30m() -> None:
    """SYNTHETIC. String radii from JSON become int radii 20, 30 and 40."""
    zones = []
    for index in range(4):
        zone = _zone(f"Z{index}", ur6=1 if index < 2 else 2, share=0.2 + 0.01 * index)
        encoded = json.loads(
            json.dumps(
                {
                    "pass_at": zone["pass_at"],
                    "pass_at_all_homes": zone["pass_at_all_homes"],
                    "pass_at_dz22": zone["pass_at_dz22"],
                }
            )
        )
        assert all(isinstance(key, str) for key in encoded["pass_at"])
        zone.update(encoded)
        zones.append(zone)
    scored = score_estimator(zones)
    assert scored["gating"]["3"]["n_pass"] == scored["gating"]["3"]["n"] == 4
    assert scored["gating"]["3"]["decide_radius_m"] == 30
    assert scored["information"]["3-all"]["n_pass"] == 4
    assert scored["information"]["3-dz22"]["n_pass"] == 4
    with pytest.raises(ValueError, match="not an integer"):
        score_estimator([{**zones[0], "pass_at": {"30m": True}}])


def test_predeclared_hbu_line_prints_not_run_once() -> None:
    text = disagreement_markdown()
    assert "NOT_RUN: NOT_RUN" not in text
    assert "HBU: NOT_RUN: frozen HBU" in text


def test_report_records_optimizer_inputs_and_secondary(tmp_path: Path) -> None:
    """SYNTHETIC. The report fixture carries every PR 1 field."""
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps({"pins": {"builder_output": "abc123"}, "primary_zones": [], "secondary_zones": []}),
        encoding="utf-8",
    )
    fitted = tmp_path / "fitted.json"
    table = [{"id": "S-c3", "converged": True, "status": "fit"}]
    fitted.write_text(json.dumps({"sensitivities": table}), encoding="utf-8")
    report = build_report(
        commit="abc123",
        input_paths={"check_inputs": checks, "fitted_hedonic": fitted},
        secondary_estimator={
            "sha256": sha256_file(fitted),
            "sensitivity_table": table,
            "s_c3_converged": True,
        },
    )
    assert report["s_c3_optimizer"] == S_C3_OPTIMIZER
    assert report["s_c3_optimizer"]["pgtol"] == 1e-8
    assert report["s_c3_optimizer"]["factr"] == "default"
    assert report["s_c3_gtol_mapping"] == S_C3_GTOL_MAPPING
    assert report["scipy_version"] == scipy.__version__
    assert report["s_c3_statsmodels_version"] == statsmodels.__version__
    assert report["input_sha256"]["merge_map"]["present"] is False
    assert report["input_sha256"]["merge_map"]["sha256"] is None
    assert report["input_sha256"]["check_inputs"]["present"] is True
    assert report["input_sha256"]["check_inputs"]["sha256"] == sha256_file(checks)
    assert report["input_sha256"]["fitted_hedonic"]["present"] is True
    assert report["input_sha256"]["fitted_hedonic"]["sha256"] == sha256_file(fitted)
    assert report["input_sha256"]["builder_output"] == {"present": True, "sha256": "abc123"}
    assert report["secondary_estimator_sha256"] == sha256_file(fitted)
    assert report["sensitivity_table"] == table
    assert report["s_c3_converged"] is True
    for rel in (
        "backend/scripts/build_v14_drc.py",
        "backend/scripts/build_v14_hedonic_rows.py",
        "backend/scripts/build_v14_check_inputs.py",
        "backend/scripts/build_v14_primary_inputs.py",
        "backend/scripts/build_ros_c14_v14_inputs.py",
        "backend/scripts/build_v14_drc_components.py",
        "backend/scripts/build_v14_primary_2023.py",
        "backend/scripts/fit_v14_hedonic.py",
        "backend/scripts/build_v14_check_sources.py",
    ):
        assert rel in report["sha8"]
        assert report["sha8"][rel] == sha256_file(BACKEND / rel.removeprefix("backend/"))[:8]
    assert "\u00a3" not in json.dumps(report)


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


class _ShaArgs:
    def __init__(self, path: Path, merge_map: Path | None = None) -> None:
        self.check_inputs = path
        self.secondary_estimator_json = None
        self.merge_map = merge_map


def _frozen_flags(tmp_path: Path) -> tuple[list[str], dict[str, Path]]:
    root = tmp_path / "frozen-set"
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
    files["merge_map"].write_text("dz2011,cell\nS01,c\n", encoding="utf-8")
    files["hedonic_coefs_2021_22"].write_text('{"beta": 0.2}\n', encoding="utf-8")
    files["code_sha8_block"].write_text("{}\n", encoding="utf-8")
    files["check3_plot_passes"].write_text("{}\n", encoding="utf-8")
    files["check4_rent_route"].write_text("{}\n", encoding="utf-8")
    files["ur6"].write_text("{}\n", encoding="utf-8")
    files["dz2022_keys"].write_text("{}\n", encoding="utf-8")
    flags = [
        "--merge-map",
        str(files["merge_map"]),
        "--hedonic-coefs",
        str(files["hedonic_coefs_2021_22"]),
        "--sha8-block",
        str(files["code_sha8_block"]),
        "--check3-plot-passes",
        str(files["check3_plot_passes"]),
        "--check4-rent-route",
        str(files["check4_rent_route"]),
        "--ur6",
        str(files["ur6"]),
        "--dz2022-keys",
        str(files["dz2022_keys"]),
    ]
    return flags, files


def _year_only(year: int) -> dict:
    rows = [{"zone": f"Z{index}", "year": year} for index in range(2)]
    return {"primary_zones": rows, "secondary_zones": [dict(row) for row in rows]}


def _refuse(capsys: pytest.CaptureFixture[str], message: str, calls: dict[str, int]) -> None:
    err = capsys.readouterr().err
    assert message in err
    assert calls["n"] == 0


def test_lock_path_is_shared_and_2024_refuses_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SYNTHETIC. One lock path. Holdout and 2024 do not follow --out."""
    payload = tmp_path / "checks.json"
    payload.write_text(
        json.dumps({"primary_zones": _zones(2024), "secondary_zones": _zones(2024)}),
        encoding="utf-8",
    )
    frozen_flags, frozen_files = _frozen_flags(tmp_path)
    monkeypatch.setitem(PIN_TABLE, "merge_map", sha256_file(frozen_files["merge_map"]))
    lock = tmp_path / "shared" / "holdout_2023.lock"
    out_a = tmp_path / "a" / "report.json"
    out_b = tmp_path / "b" / "report.json"
    assert score_main(
        [
            "--out",
            str(out_a),
            "--holdout-2023",
            "--check-inputs",
            str(payload),
            "--lock-path",
            str(lock),
            "--record-sha8s",
            *frozen_flags,
        ]
    ) == 0
    assert lock.is_file()
    capsys.readouterr()
    calls = {"n": 0}

    def spy(*_args, **_kwargs):
        calls["n"] += 1
        raise AssertionError("scored")

    monkeypatch.setattr("scripts.rerun_v14_score.score_both", spy)
    assert score_main(
        [
            "--out",
            str(tmp_path / "again" / "report.json"),
            "--holdout-2023",
            "--check-inputs",
            str(payload),
            "--lock-path",
            str(lock),
            *frozen_flags,
        ]
    ) == 1
    _refuse(capsys, "second 2023 holdout run refused", calls)
    assert score_main(
        ["--out", str(out_b), "--score-2024", "--check-inputs", str(payload)]
    ) == 1
    _refuse(capsys, "--lock-path is required", calls)
    missing_lock = tmp_path / "absent" / "holdout_2023.lock"
    assert not missing_lock.exists()
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps(_year_only(2024)), encoding="utf-8")
    assert score_main(
        [
            "--out",
            str(tmp_path / "missing" / "report.json"),
            "--score-2024",
            "--check-inputs",
            str(bare),
            "--lock-path",
            str(missing_lock),
        ]
    ) == 1
    _refuse(capsys, "2024 run refused unless the holdout lock exists", calls)
    other = tmp_path / "other.json"
    other.write_text(json.dumps(_year_only(2024)), encoding="utf-8")
    sha_lock = tmp_path / "sha.lock"
    sha_lock.write_text(lock.read_text(encoding="utf-8"), encoding="utf-8")
    year_ok = tmp_path / "year-ok.csv"
    year_ok.write_text("# SYNTHETIC\nyear\n2024\n", encoding="utf-8")
    scored = {"n": 0}

    def allow_score(*_args, **_kwargs):
        scored["n"] += 1
        return {
            "primary": {"gating_pass": False},
            "secondary": {"gating_pass": False},
            "publication": {"outcome": "both_fail_publish_neither"},
            "checks_include_hbu": False,
        }

    monkeypatch.setattr("scripts.rerun_v14_score.score_both", allow_score)
    assert score_main(
        [
            "--out",
            str(tmp_path / "mismatch" / "report.json"),
            "--score-2024",
            "--check-inputs",
            str(other),
            "--lock-path",
            str(sha_lock),
            "--year-file",
            str(year_ok),
            *frozen_flags,
        ]
    ) == 0
    mismatch_err = capsys.readouterr().err
    assert "inputs sha differs" not in mismatch_err
    assert scored["n"] == 1
    assert json.loads(lock.read_text(encoding="utf-8")).get("score_2024") is not True
    assert score_main(
        [
            "--out",
            str(tmp_path / "mismatch-again" / "report.json"),
            "--score-2024",
            "--check-inputs",
            str(other),
            "--lock-path",
            str(sha_lock),
            "--year-file",
            str(year_ok),
            *frozen_flags,
        ]
    ) == 1
    assert "second 2024 run refused" in capsys.readouterr().err
    assert scored["n"] == 1
    monkeypatch.setattr("scripts.rerun_v14_score.score_both", spy)
    early = tmp_path / "early.json"
    early.write_text(json.dumps(_year_only(2023)), encoding="utf-8")
    year_lock = tmp_path / "year.lock"
    year_lock.write_text(
        json.dumps(
            {
                "inputs_sha256": _inputs_sha256(_ShaArgs(early, frozen_files["merge_map"])),
                "commit": "abc123abc123",
                "label": "seen, not out-of-sample",
                "frozen_set": frozen_set_members(frozen_files),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert score_main(
        [
            "--out",
            str(tmp_path / "year" / "report.json"),
            "--score-2024",
            "--check-inputs",
            str(early),
            "--lock-path",
            str(year_lock),
            *frozen_flags,
        ]
    ) == 1
    err = capsys.readouterr().err
    assert "SCORE_2024: REFUSED: input_years: expected [2024], got [2023]" in err
    assert "2024 run refused: input year is not 2024" in err
    assert "inputs sha differs" not in err
    assert calls["n"] == 0
    monkeypatch.undo()
    assert score_main(
        [
            "--out",
            str(out_b),
            "--score-2024",
            "--check-inputs",
            str(payload),
            "--lock-path",
            str(lock),
            *frozen_flags,
        ]
    ) == 0
    second = json.loads(out_b.read_text(encoding="utf-8"))
    assert second["checks"]["full"] is True
    assert "agreement" in second["score_2024"]
    assert "gating" in second["score_2024"]["primary"]
    assert "sha8" not in second
    capsys.readouterr()
    assert score_main(
        [
            "--out",
            str(tmp_path / "c" / "report.json"),
            "--score-2024",
            "--check-inputs",
            str(payload),
            "--lock-path",
            str(lock),
        ]
    ) == 1
    assert "second 2024 run refused" in capsys.readouterr().err
    recorded = tmp_path / "d" / "report.json"
    assert score_main(
        [
            "--out",
            str(recorded),
            "--check-inputs",
            str(payload),
            "--record-sha8s",
        ]
    ) == 0
    with_sha = json.loads(recorded.read_text(encoding="utf-8"))
    assert "backend/scripts/build_v14_check_inputs.py" in with_sha["sha8"]
    assert math.isfinite(second["score_2024"]["primary"]["gating"]["1"]["median"])

