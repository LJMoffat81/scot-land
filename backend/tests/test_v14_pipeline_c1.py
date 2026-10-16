"""PR-C1: G1, G2, V1–V8, V10–V12, V15, V16.

Synthetic fixtures only. No 2024 price file is read. V9, V13 and V14 stay open.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

import pandas as pd
import pytest
import statsmodels

from georgist import surface_v14 as v14
from georgist.surface_v14_checks import (
    HBU_NOT_RUN,
    agreement,
    check_1a,
    check_6_zone_range,
    gis_plot_median_ratio,
    hbu_cost_side,
    hbu_line,
    score_estimator,
)
from georgist.v14_hedonic import FIDELITY_LIMITATION, land_share_for_zone
from georgist.v14_primary_inputs import DepreciationMethodError
from georgist.v14_score_report import (
    PriceColumnReadLog,
    ReportAbort,
    apply_price_reader,
    build_report,
    code_text_disagreements,
    predeclared_not_run,
    prepare_holdout_2023,
    require_commit_sha,
)
from scripts.build_v14_drc import assert_straight_line_v14, drc_for_zone, remaining_factors
from scripts.build_v14_primary_inputs import assert_exclusion_list, main as build_main
from scripts.rerun_v14_score import main as score_main
from test_v14_pipeline_a import COST_INPUTS
from test_v14_pipeline_b import _zone

BACKEND = Path(__file__).resolve().parents[1]
FIXTURE = BACKEND / "tests" / "fixtures" / "v14" / "surface_v14_a81d627c.py"
SURFACE = BACKEND / "georgist" / "surface_v14.py"
GATING = ("1", "1a", "1b", "1d", "3", "4", "6")
INFORMATION = ("1c", "1e", "2", "3-all", "3-dz22", "5", "7", "agreement", "gis_plot_median_ratio")
OPEN_ROWS = ("V9", "V13", "V14")


def _names(tree: ast.AST) -> dict[str, ast.AST]:
    found: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            found[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node
    return found


def _string_constants(node: ast.AST) -> list[str]:
    found: list[str] = []

    def visit(item: ast.AST) -> None:
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            found.append(item.value)
        for child in ast.iter_child_nodes(item):
            visit(child)

    visit(node)
    return found


def test_surface_v14_untouched_functions():
    current = _names(ast.parse(SURFACE.read_text(encoding="utf-8")))
    pinned = _names(ast.parse(FIXTURE.read_text(encoding="utf-8")))
    assert set(current) == set(pinned)
    allowed = {"score_estimators", "apply_no_switch_publication"}
    for name, node in pinned.items():
        if name in allowed:
            continue
        assert ast.dump(current[name]) == ast.dump(node)
    old_strings = _string_constants(pinned["apply_no_switch_publication"])
    new_strings = _string_constants(current["apply_no_switch_publication"])
    assert old_strings != new_strings
    changed = [
        (old, new)
        for old, new in zip(old_strings, new_strings, strict=True)
        if old != new
    ]
    assert changed == [
        ("publish_neither_report_both", "primary_fail_secondary_pass_publish_neither_until_v15"),
        ("publish_neither_report_both", "both_fail_publish_neither"),
    ]


def test_share_only_pass_of_checks_1_and_1d_does_not_publish():
    shares = [0.2, 0.25, 0.3]
    scored = v14.score_estimators(primary_shares=shares, secondary_shares=list(shares))
    for block in (scored["primary"], scored["secondary"]):
        assert block["gating"]["1"]["pass"] is True
        assert block["gating"]["1d"]["pass"] is True
        for name in ("1a", "1b", "3", "4", "6"):
            assert block["gating"][name]["status"] == "pending"
        assert block["gating_pass"] is False
    publication = scored["publication"]
    assert publication["publish_primary"] is False
    assert publication["publish_secondary"] is False
    assert publication["publish_as_range"] is False
    assert publication["outcome"] == "both_fail_publish_neither"


def test_g1_reports_every_check_and_pending_when_inputs_are_missing():
    scored = v14.score_estimators(primary_shares=[0.2, 0.25], secondary_shares=[0.2, 0.25])
    for block in (scored["primary"], scored["secondary"]):
        for name in GATING:
            assert name in block["gating"]
        for name in INFORMATION:
            assert name in block["information"]
        assert block["gating"]["1a"]["status"] == "pending"
        assert block["gating"]["6"]["status"] == "pending"
    assert scored["agreement"]["status"] == "pending"


def test_g2_four_outcomes_are_distinct():
    outcomes = [
        v14.apply_no_switch_publication(primary_gating_pass=left, secondary_gating_pass=right)["outcome"]
        for left, right in ((True, True), (True, False), (False, True), (False, False))
    ]
    assert len(set(outcomes)) == 4
    assert outcomes[2] == "primary_fail_secondary_pass_publish_neither_until_v15"
    assert outcomes[3] == "both_fail_publish_neither"


def test_v1_land_per_home_uses_the_fitted_price():
    fit = {
        "beta_by_cell": {"c": 0.25},
        "model_failure_by_cell": {"c": False},
        "informative_by_cell": {"c": True},
        "coefficient_names": ["alpha[c]", "beta[c]"],
        "coefficients": [math.log(80.0), 0.25],
    }
    row = {"zone": "Z1", "cell": "c", "price": 10.0, "a_m2": math.e, "year": 2021}
    share = land_share_for_zone(fit, row)
    assert share["fitted_price"] != row["price"]
    assert share["land_per_home"] == share["beta"] * share["fitted_price"]
    assert share["land_per_home"] != share["beta"] * row["price"]


def test_v2_uninformative_cell_stays_in_the_denominator_only():
    zones = [
        _zone("Z1", share=0.0, count_in_1d=False),
        _zone("Z2", share=0.2),
        _zone("Z3", share=1.0),
    ]
    result = score_estimator(zones)["gating"]["1d"]
    assert result["n"] == 3
    assert result["numerator_n"] == 2
    assert result["n_at_0"] == 0
    assert result["n_at_100"] == 1
    assert result["uninformative_excluded_from_numerator"] == ["Z1"]


def test_v3_limitation_is_disclosed_and_there_is_no_premium_test():
    report = build_report(commit="abc123")
    assert report["fidelity_limitation"] == FIDELITY_LIMITATION
    assert "negative location premium" in FIDELITY_LIMITATION
    source = (BACKEND / "georgist" / "v14_hedonic.py").read_text(encoding="utf-8")
    assert "def location_premium" not in source
    assert "def negative_location_premium" not in source


def test_v4_tie_fails_check_1a():
    tied = check_1a(
        [
            _zone("A", ur6=1, land_per_home=4.0),
            _zone("B", ur6=2, land_per_home=4.0),
        ]
    )
    assert tied["pass"] is False
    assert tied["status"] == "fail"


def test_v5_missing_dz2022_raises():
    with pytest.raises(ValueError, match="dz2022"):
        check_6_zone_range([_zone("A", dz2022="")])
    with pytest.raises(ValueError, match="dz2022"):
        check_6_zone_range([{key: value for key, value in _zone("A").items() if key != "dz2022"}])


def test_v6_agreement_has_every_ur6_class():
    zones = [_zone(f"Z{index}", ur6=(index % 6) + 1, share=0.1 * ((index % 5) + 1)) for index in range(12)]
    result = agreement(zones, zones)
    assert set(result["by_ur6"]) == {str(klass) for klass in range(1, 7)}
    for klass in range(1, 7):
        assert "spearman" in result["by_ur6"][str(klass)]
        assert "median_difference" in result["by_ur6"][str(klass)]
        assert "bland_altman" in result["by_ur6"][str(klass)]
    assert result["national"]["n"] == 12


def test_v7_pooled_and_zone_median_ratios_differ():
    zones = [
        _zone("A", ur6=3, detached_plot_m2=40.0, house_plot_m2=10.0),
        _zone("B", ur6=3, detached_plot_m2=40.0, house_plot_m2=20.0),
        _zone("C", ur6=3, detached_plot_m2=40.0, house_plot_m2=90.0),
    ]
    ratios = gis_plot_median_ratio(zones)["ratio_by_ur6"]["3"]
    assert ratios["ratio_pooled_denominator"] != ratios["ratio_zone_median_denominator"]


def test_v8_hbu_does_not_gate_and_is_not_run():
    with_hla = [_zone(f"P{index}", share=0.2, ur6=1 if index < 5 else 2, hla=index == 0) for index in range(10)]
    without = [{**zone, "hla": False} for zone in with_hla]
    left = score_estimator(with_hla)
    right = score_estimator(without)
    assert left["gating"] == right["gating"]
    assert left["gating_pass"] == right["gating_pass"]
    line = hbu_line(with_hla)
    assert line[0]["gates"] is False
    assert line[0]["status"] == HBU_NOT_RUN
    assert line[0]["in_checks_1_to_7"] is False
    assert hbu_line(without) == []
    assert hbu_cost_side(100.0, 1.425) == 100.0 * 1.425 + 0.15 * 100.0


def _passing_zones() -> list[dict]:
    return [
        _zone(
            f"P{index}",
            price=float(index + 1),
            share=0.15 + 0.01 * index,
            ur6=1 if index < 5 else 2,
            land_per_home=5.0 if index < 5 else 2.0,
        )
        for index in range(10)
    ]


def test_v10_error_leaves_no_lock_and_success_writes_it_after_the_report(tmp_path: Path):
    broken = tmp_path / "broken"
    broken.mkdir()
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert score_main(
        ["--out", str(broken / "report.json"), "--holdout-2023", "--check-inputs", str(bad)]
    ) == 1
    assert not (broken / "holdout_2023.lock").exists()

    good_dir = tmp_path / "good"
    zones = _passing_zones()
    payload = good_dir / "checks.json"
    good_dir.mkdir()
    payload.write_text(
        json.dumps({"primary_zones": zones, "secondary_zones": zones}),
        encoding="utf-8",
    )
    report_path = good_dir / "report.json"
    assert score_main(
        ["--out", str(report_path), "--holdout-2023", "--check-inputs", str(payload), "--record-sha8s"]
    ) == 0
    lock = json.loads((good_dir / "holdout_2023.lock").read_text(encoding="utf-8"))
    digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
    assert lock["report_sha256"] == digest
    assert lock["commit"] != "pending"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["holdout_estimated"] is True
    assert report["holdout_scores"]["primary"]["gating"]["1"]["check"] == "1"


def test_v11_pending_commit_is_refused(tmp_path: Path):
    with pytest.raises(ReportAbort):
        require_commit_sha("pending")
    with pytest.raises(ReportAbort):
        require_commit_sha("  ")
    with pytest.raises(ReportAbort):
        prepare_holdout_2023(tmp_path / "score", inputs_sha256="abc", commit="pending")
    assert not (tmp_path / "score" / "holdout_2023.lock").exists()


def test_v12_price_flag_is_true_only_after_the_reader_runs():
    log = PriceColumnReadLog()
    assert log.snapshot()["primary_inputs"] is False
    assert log.snapshot()["hedonic_fit"] is False

    def reader() -> str:
        return "ran"

    assert apply_price_reader(log, "hedonic_fit", reader) == "ran"
    assert log.snapshot()["hedonic_fit"] is True
    assert log.snapshot()["primary_inputs"] is False
    script = (BACKEND / "scripts" / "rerun_v14_score.py").read_text(encoding="utf-8")
    assert '"primary_inputs": False' not in script


def test_v15_factors_and_wrong_method(tmp_path: Path):
    factors = remaining_factors()
    assert factors["0"] == 1.0
    assert f"{factors['20']:.3f}" == "0.930"
    assert f"{factors['68']:.3f}" == "0.762"
    assert f"{factors['100']:.3f}" == "0.762"
    with pytest.raises(DepreciationMethodError):
        assert_straight_line_v14({"method": "compounding_v13"})
    code = "S01006524"
    epc = pd.read_csv(COST_INPUTS / "epc_dz_rollup.csv").set_index("code")
    nrs = pd.read_csv(COST_INPUTS / "nrs_dwelling_mix_2011_fallback.csv").set_index("code")
    estate_rows = {
        str(item["code"]): item
        for item in json.loads((COST_INPUTS / "estate_rows.json").read_text(encoding="utf-8"))
    }
    row = epc.loc[code].to_dict()
    for key in list(row):
        if "age_" in key and key.endswith("_share"):
            row[key] = 0
    valued = drc_for_zone(
        code=code,
        epc_row=row,
        nrs2017_row=nrs.loc[code].to_dict() if code in nrs.index else None,
        estate_row=estate_rows.get(code),
    )
    assert f"{valued['remaining_factor']:.3f}" == "0.762"
    out = tmp_path / "drc.json"
    out.write_text(json.dumps({code: valued["drc"]}) + "\n", encoding="utf-8")
    assert "£" not in out.read_text(encoding="utf-8")


def test_v16_missing_exclusion_list_errors_and_wrong_sha_aborts(tmp_path: Path, capsys):
    assert build_main(["--scored-run", "--out-dir", str(tmp_path / "missing")]) == 1
    wrong = tmp_path / "exclusion.csv"
    wrong.write_text("dz2011_code,cause,in_scored_set\n", encoding="utf-8")
    with pytest.raises(Exception, match="sha256"):
        assert_exclusion_list(wrong)
    rc = build_main(
        [
            "--scored-run",
            "--out-dir",
            str(tmp_path / "bad"),
            "--c14",
            str(wrong),
            "--lookup",
            str(wrong),
            "--crosswalk",
            str(wrong),
            "--merge-map",
            str(wrong),
            "--ur",
            str(wrong),
            "--drc-json",
            str(wrong),
            "--exclusion-list",
            str(wrong),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert "sha256" in captured.err


def test_c1_disagreement_table_leaves_only_v9_v13_v14_open():
    rows = {row["id"]: row["status"] for row in code_text_disagreements()}
    assert set(rows) == {
        "G1",
        "G2",
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
        "V7",
        "V8",
        "V9",
        "V10",
        "V11",
        "V12",
        "V13",
        "V14",
        "V15",
        "V16",
    }
    open_rows = [row_id for row_id, status in rows.items() if status in {"open", "pending"}]
    assert tuple(open_rows) == OPEN_ROWS
    assert rows["V3"] == "limitation_disclosed"
    assert rows["V8"] == "NOT_RUN"
    for row_id, status in rows.items():
        if row_id in OPEN_ROWS or row_id in {"V3", "V8"}:
            continue
        assert status == "fixed"
    assert predeclared_not_run()[0]["status"] == "NOT_RUN"
    report = build_report(commit="abc123")
    assert report["s_c3_statsmodels_version"] == statsmodels.__version__


def test_new_files_have_no_currency_symbol():
    path = BACKEND / "scripts" / "build_v14_drc.py"
    assert "£" not in path.read_text(encoding="utf-8")
