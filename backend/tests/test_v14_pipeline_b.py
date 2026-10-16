"""PR-B hedonic secondary, checks, 2023 holdout and run report.

Synthetic fixtures only. No 2024 price file is read.
"""

from __future__ import annotations

import inspect
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from georgist import surface_v13 as v13
from georgist import surface_v14 as v14
from georgist.surface_v14_checks import (
    check_1a,
    check_1b,
    check_4,
    check_6_zone_range,
    score_both,
    score_estimator,
)
from georgist.v14_hedonic import (
    BOOTSTRAP_REPS,
    BOOTSTRAP_SEED,
    HedonicError,
    PriceYearError,
    apply_frozen_coefficients,
    fit_headline,
    land_share_for_zone,
    refuse_2024_price_file,
)
from georgist.v14_primary_inputs import (
    check_1d_shares_for_scored,
    dropped_scored_counts,
)
from georgist.v14_score_report import (
    HoldoutLockError,
    MergeMapError,
    ReportAbort,
    assert_2024_allowed,
    assert_expected_sha8,
    assert_merge_map,
    build_report,
    code_text_disagreements,
    prepare_holdout_2023,
    write_holdout_lock,
    write_report,
)
from scripts.build_v14_primary_inputs import main as build_main
from scripts.rerun_v14_score import main as score_main
from test_v14_pipeline_a import _paths, _row

BACKEND = Path(__file__).resolve().parents[1]
LEGACY_SCORER = BACKEND / "tests" / "fixtures" / "v14" / "rerun_v14_score_fe026b76.py"
SENTINEL = "SENTINEL_TV_9f3a"


def _rows(sign: float = 1.0) -> list[dict]:
    specs = [
        ("Z1", "IZ1", "CA1", 100.0, 50.0),
        ("Z2", "IZ1", "CA1", 200.0, 55.0),
        ("Z3", "IZ2", "CA2", 150.0, 70.0),
        ("Z4", "IZ2", "CA2", 250.0, 75.0),
    ]
    rows = []
    for zone, iz, ca, area, floor in specs:
        for year in (2021, 2022):
            log_price = 1.5 + sign * 0.3 * math.log(area) + 0.05 * math.log(floor)
            rows.append(
                {
                    "zone": zone,
                    "year": year,
                    "cell": "c",
                    "iz": iz,
                    "ca": ca,
                    "a_m2": area,
                    "f_m2": floor,
                    "n_sales": 6,
                    "price": math.exp(log_price),
                }
            )
    return rows


def _zone(code: str, **overrides) -> dict:
    row = {
        "zone": code,
        "dz2022": code,
        "share": 0.20,
        "price": 10.0,
        "ur6": 1,
        "land_per_home": 2.0,
        "residual_land": 4.0,
        "capitalised_land": 4.0,
        "pass_at": {30: True, 20: True, 40: True},
        "pass_at_all_homes": {30: True, 20: True, 40: True},
        "pass_at_dz22": {30: True, 20: True, 40: True},
        "share_low": 0.10,
        "share_central": 0.20,
        "share_high": 0.30,
        "dwellings": 1,
        "detached_plot_m2": 40.0,
        "house_plot_m2": 20.0,
        "hla": False,
    }
    row.update(overrides)
    return row


def _run_scorer(script: Path, out: Path, extra: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    command = [sys.executable, str(script), "--out", str(out), *(extra or [])]
    return subprocess.run(command, cwd=BACKEND, env=env, capture_output=True, text=True, check=False)


def test_bootstrap_is_reproducible_with_the_fixed_seed():
    first = fit_headline(_rows())
    second = fit_headline(_rows())
    assert first["iz_ci"]["seed"] == BOOTSTRAP_SEED
    assert first["iz_ci"]["reps"] == BOOTSTRAP_REPS == 1999
    assert first["iz_ci"]["ci_by_cell"] == second["iz_ci"]["ci_by_cell"]
    assert first["wild_cluster"]["ci_by_cell"] == second["wild_cluster"]["ci_by_cell"]


def test_merge_map_sha_mismatch_aborts(tmp_path: Path):
    path = tmp_path / "merge.csv"
    path.write_bytes(b"dz2011\nS01007001\n")
    with pytest.raises(MergeMapError):
        assert_merge_map(path)


def test_model_failure_is_unavailable_and_counted_in_g1():
    fit = fit_headline(_rows(sign=-1.0))
    assert fit["model_failure_by_cell"]["c"] is True
    share = land_share_for_zone(fit, {"zone": "Z1", "cell": "c", "price": 8.0})
    assert share["unavailable"] is True
    assert share["model_failure"] is True
    assert share["share"] == 0.0
    assert share["land_per_home"] == 0.0
    zones = [
        _zone("Z1", share=-0.2, unavailable=True, model_failure=True, land_per_home=-1.0, residual_land=-1.0, ur6=1),
        _zone("Z2", share=-0.1, unavailable=True, model_failure=True, land_per_home=-1.0, residual_land=-1.0, ur6=1, price=12.0),
    ]
    scored = score_estimator(zones)
    assert scored["gating"]["1"]["median"] == 0.0
    assert scored["gating"]["1d"]["n"] == 2
    assert scored["gating"]["1d"]["n_at_0"] == 2
    assert scored["gating"]["1a"]["medians"][1] == 0.0
    assert scored["gating"]["4"]["pass"] is False
    assert scored["gating"]["4"]["reason"] == "residual_route_median_non_positive"


def test_gating_checks_pass_and_fail_at_the_frozen_marks():
    passing = [
        _zone(f"P{index}", price=float(index + 1), share=0.15 + 0.01 * index, ur6=1 if index < 5 else 2,
              land_per_home=5.0 if index < 5 else 2.0)
        for index in range(10)
    ]
    assert score_estimator(passing)["gating"]["1"]["pass"] is True
    assert check_1a([_zone("A", ur6=1, land_per_home=5.0), _zone("B", ur6=2, land_per_home=2.0)])["pass"] is True
    assert check_1b(passing)["pass"] is True
    one_zero = [0.0] + [0.2] * 9
    assert v13.check_1d_zero_mass(one_zero, max_share=0.10)["pass"] is True
    assert v13.check_3_plot_comparison(
        [{"pass_at": {30: True, 20: True, 40: True}}] * 4
        + [{"pass_at": {30: False, 20: False, 40: False}}]
    )["pass"] is True
    assert check_4([_zone("A"), _zone("B", ur6=2)])["pass"] is True
    assert check_6_zone_range([_zone("A")])["pass"] is True

    failing_share = [_zone("F", share=0.05)]
    assert score_estimator(failing_share)["gating"]["1"]["pass"] is False
    assert check_1a([_zone("A", ur6=1, land_per_home=1.0), _zone("B", ur6=2, land_per_home=4.0)])["pass"] is False
    reversed_decile = [
        _zone(f"D{index}", price=float(index + 1), share=0.40 - 0.02 * index) for index in range(10)
    ]
    assert check_1b(reversed_decile)["pass"] is False
    two_zeros = [0.0, 0.0] + [0.2] * 8
    assert v13.check_1d_zero_mass(two_zeros, max_share=0.10)["pass"] is False
    assert v13.check_3_plot_comparison(
        [{"pass_at": {30: True, 20: True, 40: True}}] * 3
        + [{"pass_at": {30: False, 20: False, 40: False}}] * 2
    )["pass"] is False
    zero_residual = [_zone("A", residual_land=0.0), _zone("B", ur6=2, residual_land=0.0)]
    failed = check_4(zero_residual)
    assert failed["pass"] is False
    assert failed["reason"] == "residual_route_median_non_positive"
    assert check_6_zone_range([_zone("A", share_low=0.4, share_central=0.2, share_high=0.3)])["pass"] is False


def test_no_switch_table_has_four_outcomes():
    rule = v14.NO_SWITCH_PUBLICATION_RULE
    for sentence in (
        "Primary passes + secondary passes",
        "Primary passes + secondary fails",
        "Primary fails + secondary passes",
        "Both fail",
    ):
        assert sentence in rule
    expected = (
        (True, True, "publish_range_both", True, True),
        (True, False, "publish_primary_only", True, False),
        (False, True, "primary_fail_secondary_pass_publish_neither_until_v15", False, False),
        (False, False, "both_fail_publish_neither", False, False),
    )
    for primary, secondary, outcome, publish_primary, publish_secondary in expected:
        got = v14.apply_no_switch_publication(
            primary_gating_pass=primary,
            secondary_gating_pass=secondary,
        )
        assert got["outcome"] == outcome
        assert got["publish_primary"] is publish_primary
        assert got["publish_secondary"] is publish_secondary
        assert got["never_switch_to_passing"] is True


def test_holdout_lock_blocks_a_second_run_and_2024_needs_the_lock(tmp_path: Path):
    score_dir = tmp_path / "v14_score"
    first = prepare_holdout_2023(score_dir, inputs_sha256="abc", commit="commit-1")
    assert first["label"] == "seen, not out-of-sample"
    assert Path(first["disagreement_table"]).is_file()
    assert "pending" in Path(first["disagreement_table"]).read_text(encoding="utf-8")
    write_holdout_lock(score_dir, inputs_sha256="abc", commit="commit-1")
    with pytest.raises(HoldoutLockError):
        prepare_holdout_2023(score_dir, inputs_sha256="abc", commit="commit-1")
    allowed = prepare_holdout_2023(
        score_dir,
        inputs_sha256="abc",
        commit="commit-1",
        allow_incident="INC-7",
    )
    assert allowed["allow_incident"] == "INC-7"
    assert "INC-7" in (score_dir / "fidelity_bug.log").read_text(encoding="utf-8")
    bare = tmp_path / "bare"
    bare.mkdir()
    with pytest.raises(HoldoutLockError):
        assert_2024_allowed(bare)
    assert_2024_allowed(score_dir)
    names = inspect.signature(prepare_holdout_2023).parameters
    assert not any("outcome" in name for name in names)


def test_report_missing_method_or_sha8_aborts(tmp_path: Path):
    missing = tmp_path / "report.json"
    with pytest.raises(ReportAbort):
        write_report(missing, {"depreciation": {"method": ""}, "sha8": {"backend/georgist/surface_rent.py": "dc07f4fe"}})
    assert not missing.exists()
    with pytest.raises(ReportAbort):
        write_report(missing, {"depreciation": {"method": "straight_line_v14"}, "sha8": {}})
    assert not missing.exists()
    root = tmp_path / "tree"
    target = root / "backend" / "georgist"
    target.mkdir(parents=True)
    (target / "surface_rent.py").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ReportAbort):
        assert_expected_sha8({"backend/georgist/surface_rent.py": "dc07f4fe"}, root)
    report = build_report(commit="abc123")
    assert report["depreciation"]["method"] == "straight_line_v14"
    assert report["sha8"]["backend/georgist/surface_rent.py"] == "dc07f4fe"
    assert report["sha8"]["backend/georgist/surface_v14.py"] == "cdb69a4f"
    assert report["sha8"]["data/config/surface.yaml"] == "0ad64260"
    assert report["seed"] == BOOTSTRAP_SEED
    assert report["code_text_disagreements"] == code_text_disagreements()
    assert report["disclosures"]["scored_zones"] == 5489
    assert all(value is False for value in report["price_columns_read"].values()) or report["price_columns_read"] == {}


def test_default_mode_does_not_emit_a_price_sentinel(tmp_path: Path, capsys):
    sentinel_file = tmp_path / "prices_2024.csv"
    sentinel_file.write_text(SENTINEL + "\n", encoding="utf-8")
    out = tmp_path / "out"
    assert build_main(["--out-dir", str(out)]) == 0
    report = tmp_path / "report.json"
    assert score_main(["--out", str(report)]) == 0
    captured = capsys.readouterr()
    blob = captured.out + captured.err
    for path in out.rglob("*"):
        if path.is_file():
            blob += path.read_text(encoding="utf-8")
    blob += report.read_text(encoding="utf-8")
    assert SENTINEL not in blob
    with pytest.raises(PriceYearError) as refused:
        refuse_2024_price_file(sentinel_file.name)
    assert SENTINEL not in str(refused.value)
    with pytest.raises(PriceYearError) as refused_year:
        fit_headline(
            [
                {
                    "zone": "Z1",
                    "year": 2024,
                    "cell": "c",
                    "iz": "IZ1",
                    "ca": "CA1",
                    "a_m2": 10,
                    "f_m2": 10,
                    "n_sales": 6,
                    "price": SENTINEL,
                }
            ]
        )
    assert SENTINEL not in str(refused_year.value)


def test_legacy_scorer_output_is_byte_identical(tmp_path: Path):
    shares = tmp_path / "shares.json"
    shares.write_text("[0.2, 0.25, 0.3]\n", encoding="utf-8")
    cases = [[], ["--primary-shares-json", str(shares), "--secondary-shares-json", str(shares)]]
    for extra in cases:
        legacy_out = tmp_path / "legacy.json"
        new_out = tmp_path / "new.json"
        legacy = _run_scorer(LEGACY_SCORER, legacy_out, extra)
        new = _run_scorer(BACKEND / "scripts" / "rerun_v14_score.py", new_out, extra)
        assert legacy.returncode == 0, legacy.stderr
        assert new.returncode == 0, new.stderr
        assert legacy_out.read_bytes() == new_out.read_bytes()
        assert legacy.stdout.replace(str(legacy_out), "OUT") == new.stdout.replace(str(new_out), "OUT")
        assert legacy.stderr == new.stderr


def test_wild_cluster_is_information_only_and_leaves_the_iz_interval():
    fit = fit_headline(_rows())
    wild = fit["wild_cluster"]
    assert wild["seed"] == BOOTSTRAP_SEED
    assert wild["reps"] == 1999
    assert wild["weights"] == "rademacher"
    assert wild["information_only"] is True
    assert wild["gates"] is False
    assert wild["replaces_iz_ci"] is False
    assert fit["iz_ci"]["ci_by_cell"] == fit["iz_ci_before_wild"]["ci_by_cell"]
    assert fit["headline_form"] == "log"
    assert fit["levels_swapped_in"] is False
    assert fit["gates_use"] == "iz_point_beta"
    internal = [item for item in fit["sensitivities"] if item["id"] == "S-x4"]
    assert internal[0]["internal_only"] is True
    assert internal[0]["publish"] is False
    assert all(item["gates"] is False and item["swapped_in"] is False for item in fit["sensitivities"])
    before = list(fit["coefficients"])
    applied = apply_frozen_coefficients(fit, [{"zone": "Z9", "cell": "c", "year": 2024}])
    assert applied["refit"] is False
    assert list(fit["coefficients"]) == before
    uninformative = land_share_for_zone(
        {
            "beta_by_cell": {"c": 0.2},
            "model_failure_by_cell": {"c": False},
            "informative_by_cell": {"c": False},
            "coefficient_names": ["alpha[c]", "beta[c]"],
            "coefficients": [0.0, 0.2],
        },
        {"zone": "Z1", "cell": "c", "price": 8.0, "a_m2": 1.0, "year": 2021},
    )
    assert uninformative["count_in_1d"] is False
    narrowed = score_estimator(
        [
            _zone("Z1", count_in_1d=False, share=0.0),
            _zone("Z2", share=0.2),
        ]
    )
    assert narrowed["gating"]["1d"]["n"] == 2
    assert narrowed["gating"]["1d"]["n_at_0"] == 0
    assert narrowed["gating"]["1d"]["uninformative_excluded_from_numerator"] == ["Z1"]


def test_dropped_zones_are_printed_stop_scoring_and_stay_in_the_denominator(tmp_path: Path, capsys):
    counts = dropped_scored_counts(
        ["A", "B", "C"],
        {"A": 10.0, "B": 10.0},
        {"A": 4.0},
    )
    assert counts == {"no_price": 1, "no_cost": 2}
    shares = check_1d_shares_for_scored(
        ["A", "B", "C"],
        {"A": 10.0, "B": 10.0},
        {"A": 4.0},
        {"A": 0.25},
    )
    assert shares == [0.25, 0.0, 0.0]
    check = v13.check_1d_zero_mass(shares, max_share=0.10)
    assert check["n"] == 3
    assert check["n_at_0"] == 2

    body = [
        _row("S01013482", "Left", 10, 1000),
        _row("S01013483", "Right", 10, 500),
    ]
    paths = _paths(
        tmp_path,
        body,
        ["S01013482", "S01013483"],
        [
            ("S01007001", "S01013482", 20),
            ("S01007002", "S01013483", 20),
        ],
        ["S01007001", "S01007002", "S01007003"],
    )
    drc = tmp_path / "drc.json"
    drc.write_text(json.dumps({"S01007001": 40.0}), encoding="utf-8")
    out = tmp_path / "scored"
    rc = build_main(
        [
            "--scored-run",
            "--synthetic-fixtures",
            "--out-dir",
            str(out),
            "--c14",
            str(paths["c14"]),
            "--lookup",
            str(paths["lookup"]),
            "--crosswalk",
            str(paths["crosswalk"]),
            "--merge-map",
            str(paths["merge"]),
            "--ur",
            str(paths["ur"]),
            "--drc-json",
            str(drc),
            "--exclusion-list",
            str(BACKEND / "tests" / "fixtures" / "v14" / "synthetic_exclusion.csv"),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert "dropped_no_price=1" in captured.out
    assert "dropped_no_cost=2" in captured.out
    assert "stop_before_scoring=true" in captured.out
    assert SENTINEL not in captured.out
    assert not (out / "cost_availability.json").exists()
    assert not (out / "primary_estimates.json").exists()


def test_both_estimators_keep_hbu_outside_checks_1_to_7():
    zones = [
        _zone(
            f"P{index}",
            price=float(index + 1),
            share=0.15 + 0.01 * index,
            ur6=1 if index < 5 else 2,
            land_per_home=5.0 if index < 5 else 2.0,
            hla=index == 0,
        )
        for index in range(10)
    ]
    scored = score_both(zones, zones)
    assert scored["primary"]["gating_pass"] is True
    assert scored["secondary"]["gating_pass"] is True
    assert scored["publication"]["outcome"] == "publish_range_both"
    assert scored["checks_include_hbu"] is False
    assert "hbu" not in scored["primary"]["gating"]
    assert scored["hbu"][0]["in_checks_1_to_7"] is False
    for name in ("1c", "1e", "2", "3-all", "3-dz22", "5", "7", "gis_plot_median_ratio"):
        assert scored["primary"]["information"][name]["pass"] is None
    assert scored["agreement"]["pass"] is None


def test_unknown_cell_is_rejected():
    fit = fit_headline(_rows())
    with pytest.raises(HedonicError):
        apply_frozen_coefficients(fit, [{"zone": "Z9", "cell": "missing", "year": 2021}])
