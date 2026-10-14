"""One-shot fill holdout: run-guard refusals, fixed split, metric output (exact)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from georgist import dz2022_fill as fill
from georgist import dz2022_fill_holdout as ho
from scripts import run_dz2022_fill_holdout_oneshot as oneshot

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dz2022_fill"
RENT = FIXTURES / "rent_2011.csv"
UR6 = FIXTURES / "ur6_dz2022.csv"

# Deterministic held set for DEFAULT_SEED on the CI rent fixture (k=8).
FIXED_HELD_CODES = [
    "S01013402",
    "S01013413",
    "S01013414",
    "S01013417",
    "S01013418",
    "S01013421",
    "S01013428",
    "S01013429",
]


@pytest.fixture
def measured():
    rows = fill.load_2011_rent_table(RENT)
    return [r for r in rows if fill._is_measured(r)]


@pytest.fixture
def log_path(tmp_path):
    return tmp_path / "run_log" / "dz2022_fill_runs.jsonl"


def test_fixed_split_is_seed_stable_and_k_equals_eight(measured):
    codes_a = oneshot.fixed_split_codes(measured, seed=ho.DEFAULT_SEED)
    codes_b = oneshot.fixed_split_codes(measured, seed=ho.DEFAULT_SEED)
    assert codes_a == codes_b
    assert codes_a == FIXED_HELD_CODES
    assert len(codes_a) == oneshot.EXPECTED_FIXTURE_HELD_N
    assert len(codes_a) == 8  # k=8 tested
    # Different seed must not silently reuse the same split.
    other = oneshot.fixed_split_codes(measured, seed=ho.DEFAULT_SEED + 1)
    assert other != FIXED_HELD_CODES


def test_refuse_run_when_not_pre_registered(log_path):
    with pytest.raises(oneshot.NotPreRegisteredError, match="not pre-registered"):
        oneshot.run_scored(
            rent_table=RENT,
            ur6_lookup=UR6,
            log_path=log_path,
            class_min=3,
        )
    assert not log_path.exists() or log_path.read_text().strip() == ""


def test_refuse_when_already_run(log_path):
    oneshot.preregister_run(rent_table=RENT, ur6_lookup=UR6, log_path=log_path)
    oneshot.run_scored(
        rent_table=RENT,
        ur6_lookup=UR6,
        log_path=log_path,
        class_min=3,
    )
    with pytest.raises(ho.RepeatScoredRunError, match="already recorded"):
        oneshot.run_scored(
            rent_table=RENT,
            ur6_lookup=UR6,
            log_path=log_path,
            class_min=3,
        )
    with pytest.raises(ho.RepeatScoredRunError):
        oneshot.preregister_run(rent_table=RENT, ur6_lookup=UR6, log_path=log_path)


def test_preregister_writes_hashes_seed_empty_metrics(log_path):
    out = oneshot.preregister_run(
        rent_table=RENT, ur6_lookup=UR6, log_path=log_path, seed=ho.DEFAULT_SEED
    )
    entry = out["preregister_entry"]
    assert entry["phase"] == "preregister"
    assert entry["metrics"] == {}
    assert entry["seed"] == ho.DEFAULT_SEED
    assert len(entry["spec_sha256"]) == 64
    assert entry["script_sha256"] == oneshot.oneshot_script_hash()
    assert "rent_table" in entry["input_sha256s"]
    assert "ur6_lookup" in entry["input_sha256s"]
    assert "neighbours" in entry["input_sha256s"]
    bands = entry["pass_bands"]
    # P10–P90 coverage pass band 75–85% (0.80 ± 0.05); low-sales bias under 0.10
    assert bands["coverage_target"] == 0.80
    assert bands["coverage_tol"] == 0.05
    assert bands["bias_abs_max"] == 0.10
    lines = [json.loads(x) for x in log_path.read_text().splitlines() if x.strip()]
    assert len(lines) == 1
    assert lines[0]["phase"] == "preregister"


def test_metric_output_exact_counts_coverage_bias_and_widen(log_path, measured):
    oneshot.preregister_run(rent_table=RENT, ur6_lookup=UR6, log_path=log_path)
    result = oneshot.run_scored(
        rent_table=RENT,
        ur6_lookup=UR6,
        log_path=log_path,
        class_min=3,
    )
    assert result["k"] == 8
    assert result["held_n"] == 8
    assert result["train_n"] == 18
    assert result["held_codes"] == FIXED_HELD_CODES

    c = result["c_metrics"]
    assert c["n"] == 6
    # Exact coverage: 2 of 6 held-with-model zones inside P10–P90
    assert c["coverage_p10_p90"] == 2 / 6

    # Sole lowest-sales-decile held zone with a model: S01013421 (sales_n=4)
    train, held = ho.stratified_mask(measured, seed=ho.DEFAULT_SEED)
    assert sorted(str(r["code"]) for r in held) == FIXED_HELD_CODES
    models = fill.fit_council_ur6_models(
        train, neighbours=fill.load_neighbouring_councils(), class_min=3
    )
    pred = fill.predict_group_rent(models[("S12000049", 2)], dwellings=10)[1]
    expected_bias = math.log(pred) - math.log(50.0)
    assert c["signed_median_log_bias_lowest_sales_decile"] == expected_bias
    assert abs(expected_bias) >= 0.10  # fails the <0.10 band on this fixture

    decision = result["decision"]
    assert decision["pass"] is False
    assert "c_coverage" in decision["fails"]
    assert "c_low_sales_bias" in decision["fails"]
    assert decision["pass_bands"]["coverage_target"] == 0.80
    assert decision["pass_bands"]["coverage_tol"] == 0.05
    assert decision["pass_bands"]["bias_abs_max"] == 0.10

    # Fail widens bands with no re-fit (central unchanged; errors recorded).
    assert fill.CLASS_C in result["widening"]
    assert fill.CLASS_B in result["widening"]
    assert result["widening"][fill.CLASS_C] == c["abs_log_errors"]
    low, central, high = fill.widen_bands_from_holdout_errors(
        90.0, 100.0, 110.0, abs_log_errors=result["widening"][fill.CLASS_C]
    )
    assert central == 100.0
    assert low < 90.0 or high > 110.0

    lines = [json.loads(x) for x in log_path.read_text().splitlines() if x.strip()]
    assert len(lines) == 2
    assert lines[0]["phase"] == "preregister"
    assert lines[0]["metrics"] == {}
    assert lines[1]["phase"] == "result"
    assert lines[1]["metrics"]["k"] == 8
    assert lines[1]["metrics"]["held_codes"] == FIXED_HELD_CODES
    assert lines[1]["widening"][fill.CLASS_C] == c["abs_log_errors"]


def test_cli_preregister_then_run_then_refuse(tmp_path):
    log = tmp_path / "runs.jsonl"
    rc = oneshot.main(
        [
            "preregister",
            "--rent",
            str(RENT),
            "--ur6",
            str(UR6),
            "--log",
            str(log),
        ]
    )
    assert rc == 0
    rc = oneshot.main(
        [
            "run",
            "--rent",
            str(RENT),
            "--ur6",
            str(UR6),
            "--log",
            str(log),
            "--class-min",
            "3",
        ]
    )
    assert rc == 0
    rc = oneshot.main(
        [
            "run",
            "--rent",
            str(RENT),
            "--ur6",
            str(UR6),
            "--log",
            str(log),
            "--class-min",
            "3",
        ]
    )
    assert rc == 2  # already run
    rc = oneshot.main(
        [
            "run",
            "--rent",
            str(RENT),
            "--ur6",
            str(UR6),
            "--log",
            str(tmp_path / "other.jsonl"),
            "--class-min",
            "3",
        ]
    )
    assert rc == 2  # not pre-registered
