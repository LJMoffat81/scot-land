"""Holdout run guard, widen-on-fail, and publishability (no £ leak) for DZ2022 fill."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from georgist import dz2022_fill as fill
from georgist import dz2022_fill_holdout as ho

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dz2022_fill"
RENT = FIXTURES / "rent_2011.csv"
GUARD = Path(__file__).resolve().parents[3] / "scripts" / "check_publishable.py"


@pytest.fixture
def measured():
    rows = fill.load_2011_rent_table(RENT)
    return [r for r in rows if fill._is_measured(r)]


@pytest.fixture
def neighbours():
    return fill.load_neighbouring_councils()


def test_run_guard_refuses_second_scored_run(tmp_path, measured, neighbours):
    log = tmp_path / "run_log" / "dz2022_fill_runs.jsonl"
    r1 = ho.run_holdout(
        measured,
        neighbours=neighbours,
        log_path=log,
        scored=True,
        input_hashes={"rent": "abc"},
        require_preconditions={"ready": True},
    )
    assert r1["run_log_entry"]["scored"] is True
    assert log.exists()
    with pytest.raises(ho.RepeatScoredRunError):
        ho.run_holdout(
            measured,
            neighbours=neighbours,
            log_path=log,
            scored=True,
            require_preconditions={"ready": True},
        )
    # Override with reason is allowed and logged.
    r3 = ho.run_holdout(
        measured,
        neighbours=neighbours,
        log_path=log,
        scored=True,
        override=True,
        reason="fixture re-run for CI",
        require_preconditions={"ready": True},
    )
    assert r3["run_log_entry"]["override"] is True
    assert len(log.read_text().splitlines()) == 2


def test_scored_holdout_refuses_missing_preconditions(tmp_path, measured, neighbours):
    pre = ho.check_scored_preconditions(
        rent_table=None, ur6_lookup="/tmp/missing-ur6.csv"
    )
    assert pre["ready"] is False
    with pytest.raises(ho.HoldoutPreconditionError, match="TODO"):
        ho.run_holdout(
            measured,
            neighbours=neighbours,
            log_path=tmp_path / "run_log" / "dz2022_fill_runs.jsonl",
            require_preconditions=pre,
        )


def test_fail_path_widens_bands_without_refit(measured, neighbours, tmp_path):
    # Force a fail by using empty held set metrics path via evaluate_pass with bad coverage.
    c_metrics = {
        "coverage_p10_p90": 0.50,  # outside 80% ±5
        "signed_median_log_bias_lowest_sales_decile": 0.0,
        "abs_log_errors": [0.1, 0.2, 0.5],
        "n": 3,
    }
    a_metrics = {
        "coverage_p10_p90": 0.80,
        "abs_log_errors": [0.01],
        "n": 1,
    }
    decision = ho.evaluate_pass(c_metrics, a_metrics)
    assert decision["pass"] is False
    assert "c_coverage" in decision["fails"]
    widening = ho.widen_on_fail(decision["fails"], c_metrics, a_metrics)
    assert fill.CLASS_C in widening
    assert widening[fill.CLASS_C] == [0.1, 0.2, 0.5]
    # Apply widen — central unchanged (no re-fit).
    low, c, high = fill.widen_bands_from_holdout_errors(
        90.0, 100.0, 110.0, abs_log_errors=widening[fill.CLASS_C]
    )
    assert c == 100.0
    assert low < 90.0 or high > 110.0

    # Record widening in run log via register.
    g = ho.FillRunGuard(tmp_path / "dz2022_fill_runs.jsonl")
    entry = g.register(
        spec_sha256="x",
        script_sha256="y",
        input_hashes={},
        seed=1,
        metrics={"decision": decision},
        pass_bands=decision["pass_bands"],
        widening=widening,
        scored=False,
    )
    assert entry["widening"][fill.CLASS_C]


def test_method_a_bias_path_exact(measured):
    # With noise-free synthetic mask, pred == actual; coverage should be high.
    m = ho.score_method_a_synthetic(measured, empty_share=0.25, seed=1)
    assert m["n"] == len(measured)
    assert m["median_abs_log_error"] == pytest.approx(0.0)
    assert m["coverage_p10_p90"] == pytest.approx(1.0)


def test_publishability_guard_no_pound_leak_from_fill_outputs(tmp_path):
    """Tracked public JSON must not ship model_fill_dz2022 £ payloads."""
    import importlib.util
    import os
    import subprocess

    spec = importlib.util.spec_from_file_location("check_publishable", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert "model_fill_dz2022" in mod.FORBIDDEN_PUBLIC_FILL_TOKENS

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    leak = tmp_path / "frontend" / "public" / "zones.geojson"
    leak.parent.mkdir(parents=True)
    leak.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature",'
        '"properties":{"code":"S01020870","model_fill_dz2022":1000},'
        '"geometry":null}]}',
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", "."], check=True)
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        problems = mod.check(mod.tracked())
    finally:
        os.chdir(cwd)
    assert any("model_fill_dz2022" in p for p in problems), problems
