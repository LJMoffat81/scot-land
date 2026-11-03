"""CHECK4-S-NOTRUN: Check 4 secondary over estimated S zones only; NOT_RUN when none.

Synthetic fixtures only. No real inputs are read.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from georgist import surface_v14_checks as checks
from georgist.v14_check4_route import build_v15_check4_score_report, score_check4_non_gbp
from scripts import rerun_v14_score
from scripts.build_v14_check_inputs import (
    CheckInputError,
    build_v14_check_inputs,
    load_status_s,
)
from scripts.build_v14_check_inputs import main as check_inputs_main

ZONES = ("Z1", "Z2", "Z3", "Z4", "Z5", "Z6")
NOT_RUN = {"status": "NOT_RUN", "reason": "S NOT_CONVERGED"}
PINS = {"check4_f8": "a" * 64}


def _tables(fitted: dict[str, dict]) -> dict[str, dict[str, dict]]:
    builder, primary, check3, f8, dz, ur6 = {}, {}, {}, {}, {}, {}
    for i, z in enumerate(ZONES, start=1):
        builder[z] = {"price": 100000.0 + 9000.0 * i, "count_in_1d": True, "unavailable": False,
                      "model_failure": False, "hla": False}
        primary[z] = {"share": 0.10 + 0.03 * i, "land_per_home": 20000.0 + 3100.0 * i,
                      "unavailable": False, "count_in_1d": True}
        check3[z] = {"pass_at": {"20": True, "30": True, "40": True}}
        f8[z] = {"capitalised_land": 21000.0 + 2900.0 * i, "drc": 90000.0, "capitalised_property": 111000.0 + i}
        dz[z] = {"dz2022": f"D{i}", "share_low": 0.05, "share_central": 0.2, "share_high": 0.35}
        ur6[z] = {"ur6": 1 + (i % 3)}
    return {"builder_output": builder, "primary_estimates": primary, "fitted_hedonic": fitted,
            "check3_plot_passes": check3, "check4_f8": f8, "dz2022_keys": dz, "ur6": ur6}


def _est(i: int) -> dict:
    return {"share": 0.2 + 0.02 * i, "land_per_home": 30000.0 + 4100.0 * i, "unavailable": False,
            "model_failure": False, "count_in_1d": True}


def _all_estimated_fitted() -> dict[str, dict]:
    return {z: _est(i) for i, z in enumerate(ZONES, start=1)}


def _dump(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, default=str).encode()


# ---------------- T1: all model_failure + missing no_cell zones ----------------

def _t1_tables_and_status():
    # Z5, Z6 are no_cell and absent from fitted_hedonic (as in the r10 refusal); Z1-Z4 model_failure.
    fitted = {z: {"model_failure": True, "unavailable": False, "count_in_1d": True} for z in ZONES[:4]}
    status = {**{z: "model_failure" for z in ZONES[:4]}, "Z5": "no_cell", "Z6": "no_cell"}
    return _tables(fitted), status


def test_t1_all_model_failure_is_not_run_with_exact_reason() -> None:
    tables, status = _t1_tables_and_status()
    built = build_v14_check_inputs(tables, PINS, status_s=status)  # fails on builder refusal
    assert built["secondary_zones"] == []  # fails on any scored or P-copied secondary row
    assert built["check4_secondary"] == NOT_RUN  # fails on PASS or any other status/reason
    assert set(built) == {"primary_zones", "secondary_zones", "check4_secondary", "pins"}
    assert built["pins"] == {"check4_f8": "a" * 64}
    # Primary is untouched by status_S.
    legacy_tables = _tables(_all_estimated_fitted())
    assert _dump(built["primary_zones"]) == _dump(build_v14_check_inputs(legacy_tables)["primary_zones"])


def test_t1_route_report_not_run_never_scores_secondary(monkeypatch: pytest.MonkeyPatch) -> None:
    tables, status = _t1_tables_and_status()
    built = build_v14_check_inputs(tables, PINS, status_s=status)
    import georgist.v14_check4_route as route

    seen: list[int] = []
    real = route.score_check4_non_gbp
    monkeypatch.setattr(route, "score_check4_non_gbp", lambda z, **k: (seen.append(len(z)), real(z, **k))[1])
    monkeypatch.setattr(route, "check4_sensitivities", lambda *a, **k: pytest.fail("sensitivities scored"))
    report = build_v15_check4_score_report(
        primary_zones=built["primary_zones"], secondary_zones=built["secondary_zones"], pins=PINS,
        year=2023, lookup_zones=8, not_scored_zones=2, secondary_scored_zones=0, secondary_no_cell_zones=2,
        check4_secondary=built["check4_secondary"],
    )
    assert seen == [len(ZONES)]  # primary only; any secondary scoring fails
    assert report["secondary"] == {"status": "NOT_RUN", "reason": "S NOT_CONVERGED", "pass": None}
    assert report["publication"]["publish_secondary"] is False
    with pytest.raises(route.Check4RouteError) as exc:
        build_v15_check4_score_report(
            primary_zones=built["primary_zones"], secondary_zones=built["primary_zones"], pins=PINS,
            year=2023, lookup_zones=8, not_scored_zones=2, check4_secondary=NOT_RUN,
        )
    assert str(exc.value) == "V14_CHECK4: ERROR: secondary NOT_RUN: expected 0 secondary zones, got 6"


def test_t1_rerun_check4_summary_not_run(tmp_path: Path) -> None:
    tables, status = _t1_tables_and_status()
    built = build_v14_check_inputs(tables, PINS, status_s=status)
    path = tmp_path / "check_inputs.json"
    path.write_text(json.dumps(built))
    summary = rerun_v14_score._write_check4_summary(path, tmp_path / "summary.json")
    assert summary["secondary"] == {"status": "NOT_RUN", "reason": "S NOT_CONVERGED", "pass": None}
    bad = dict(built, secondary_zones=built["primary_zones"])
    path.write_text(json.dumps(bad))
    with pytest.raises(rerun_v14_score.ReportAbort):
        rerun_v14_score._write_check4_summary(path, tmp_path / "s2.json")


def test_t1_refusals_status_absent_and_no_model_failure() -> None:
    tables, status = _t1_tables_and_status()
    partial = {k: v for k, v in status.items() if k != "Z3"}
    with pytest.raises(CheckInputError) as exc:
        build_v14_check_inputs(tables, status_s=partial)
    assert str(exc.value) == "V14_CHECK_INPUTS: ERROR: zone_status Z3: expected status_S, got absent"
    with pytest.raises(CheckInputError) as exc2:
        build_v14_check_inputs(tables, status_s={z: "no_cell" for z in ZONES})
    assert str(exc2.value) == (
        "V14_CHECK_INPUTS: ERROR: check4 secondary: expected estimated or model_failure zones, got none"
    )


def test_t1_reason_from_status_counts_not_fit_values() -> None:
    tables, status = _t1_tables_and_status()
    poisoned = copy.deepcopy(tables)
    for row in poisoned["fitted_hedonic"].values():
        row.update({"share": 0.3, "land_per_home": 1.0, "model_failure": False})
    assert build_v14_check_inputs(poisoned, status_s=status)["check4_secondary"] == NOT_RUN


def test_t1_cli_pins_zone_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    zs = tmp_path / "zone_status_2023.json"
    zs.write_text(json.dumps({"zones": [{"zone": "Z1", "status_S": "model_failure"}]}))
    assert load_status_s(zs) == {"Z1": "model_failure"}
    zs.write_text(json.dumps({"zones": [{"zone": "Z1", "status_S": "PASS"}]}))
    with pytest.raises(CheckInputError):
        load_status_s(zs)
    capsys.readouterr()
    rc = check_inputs_main(["--out", str(tmp_path / "o.json"), "--year", "2024", "--zone-status-2023", str(zs)])
    assert rc == 1
    assert capsys.readouterr().err == "V14_CHECK_INPUTS: ERROR: zone_status: expected 2023 F8 route, got other\n"


# ---------------- T2: partial failure ----------------

def test_t2_partial_secondary_is_exactly_estimated_set() -> None:
    fitted = {
        "Z1": _est(1), "Z2": _est(2), "Z3": _est(3),
        "Z4": {"model_failure": True, "unavailable": False, "count_in_1d": True},
        "X9": _est(9),  # extra fit zone outside the builder set
    }
    status = {"Z1": "estimated", "Z2": "estimated", "Z3": "estimated", "Z4": "model_failure",
              "Z5": "no_cell", "Z6": "no_cell"}
    built = build_v14_check_inputs(_tables(fitted), status_s=status)
    assert [z["zone"] for z in built["secondary_zones"]] == ["Z1", "Z2", "Z3"]
    assert "check4_secondary" not in built
    legacy = build_v14_check_inputs(_tables(_all_estimated_fitted() | {z: fitted[z] for z in ("Z1", "Z2", "Z3")}))
    expect = [z for z in legacy["secondary_zones"] if z["zone"] in {"Z1", "Z2", "Z3"}]
    assert _dump(built["secondary_zones"]) == _dump(expect)
    assert score_check4_non_gbp(built["secondary_zones"]) == score_check4_non_gbp(expect)
    # Contains-guard: an estimated zone missing from the fit is still refused.
    del fitted["Z2"]
    with pytest.raises(CheckInputError) as exc:
        build_v14_check_inputs(_tables(fitted), status_s=status)
    assert str(exc.value) == "V14_CHECK_INPUTS: ERROR: check4 secondary Z2: expected residual_land, got absent"
    # Extra fit zone X9 and missing no_cell zones are accepted; legacy equality guard still holds without status_S.
    with pytest.raises(CheckInputError) as exc_legacy:
        build_v14_check_inputs(_tables(_all_estimated_fitted() | {"X9": _est(9)}))
    assert str(exc_legacy.value) == "fitted_hedonic zones do not match the builder output"


# ---------------- T3: S fully estimated, before vs after ----------------

def test_t3_fully_estimated_primary_and_hbu_byte_identical() -> None:
    tables = _tables(_all_estimated_fitted())
    before = build_v14_check_inputs(copy.deepcopy(tables))  # legacy (pre-change) path
    after = build_v14_check_inputs(copy.deepcopy(tables), status_s={z: "estimated" for z in ZONES})
    assert _dump(before["primary_zones"]) == _dump(after["primary_zones"])
    assert _dump(before["secondary_zones"]) == _dump(after["secondary_zones"])
    assert "check4_secondary" not in after
    s_before = checks.score_both(before["primary_zones"], before["secondary_zones"], year=2023)
    s_after = checks.score_both(after["primary_zones"], after["secondary_zones"], year=2023)
    assert _dump(s_before["primary"]) == _dump(s_after["primary"])
    assert _dump(s_before["hbu"]) == _dump(s_after["hbu"])
    assert _dump(s_before["agreement"]) == _dump(s_after["agreement"])
    assert score_check4_non_gbp(before["primary_zones"]) == score_check4_non_gbp(after["primary_zones"])


# ---------------- T4: score_both NOT_RUN (Auditor ruling a) ----------------

def _t1_built() -> dict:
    tables, status = _t1_tables_and_status()
    return build_v14_check_inputs(tables, PINS, status_s=status)


def test_t4_score_both_empty_secondary_not_run_without_raising() -> None:
    built = _t1_built()
    out = checks.score_both(built["primary_zones"], [], year=2023, secondary_not_run=built["check4_secondary"])
    sec = out["secondary"]
    assert sec["gating_pass"] is False
    items = [*sec["gating"].values(), *sec["information"].values()]
    assert items
    for item in items:
        assert item["status"] == "NOT_RUN" and item["reason"] == "S NOT_CONVERGED" and item["pass"] is None
    assert set(sec["gating"]) | {"3"} == set(out["primary"]["gating"]) | {"3"}
    assert out["secondary_status"] == {"status": "NOT_RUN", "reason": "S NOT_CONVERGED"}
    assert out["publication"]["publish_secondary"] is False
    assert out["hbu"] == checks.hbu_line(built["primary_zones"])
    hla_primary = [dict(z, hla=(z["zone"] == "Z1")) for z in built["primary_zones"]]
    out_hla = checks.score_both(hla_primary, [], year=2023, secondary_not_run=built["check4_secondary"])
    assert [h["zone"] for h in out_hla["hbu"]] == ["Z1"]  # primary HBU once; nothing added for S


def test_t4_agreement_never_pass_and_never_computed(monkeypatch: pytest.MonkeyPatch) -> None:
    built = _t1_built()
    monkeypatch.setattr(checks, "agreement", lambda *a, **k: pytest.fail("agreement computed"))
    out = checks.score_both(built["primary_zones"], [], year=2023, secondary_not_run=built["check4_secondary"])
    assert out["agreement"] == {"check": "agreement", "status": "NOT_RUN", "reason": "S NOT_CONVERGED", "pass": None}


def test_t4_primary_unchanged_by_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    built = _t1_built()
    calls: list[int] = []
    real = checks.score_estimator
    monkeypatch.setattr(checks, "score_estimator", lambda z: (calls.append(len(z)), real(z))[1])
    out = checks.score_both(built["primary_zones"], [], year=2023, secondary_not_run=built["check4_secondary"])
    assert calls == [len(ZONES)]  # secondary never scored, never filled from P
    monkeypatch.setattr(checks, "score_estimator", real)
    ref = checks.score_both(built["primary_zones"], built["primary_zones"], year=2023)
    assert _dump(out["primary"]) == _dump(ref["primary"])
    assert out["publication"]["publish_primary"] == ref["primary"]["gating_pass"]


def test_t4_refusals() -> None:
    built = _t1_built()
    p = built["primary_zones"]
    for rec, sec, msg in [
        ({"status": "PASS", "reason": "S NOT_CONVERGED"}, [], "expected NOT_RUN record"),
        ({"status": "NOT_RUN", "reason": "other"}, [], "expected 'S NOT_CONVERGED'"),
        ({"status": "NOT_RUN", "reason": "S NOT_CONVERGED"}, p, "expected 0 secondary zones, got 6"),
    ]:
        with pytest.raises(ValueError) as exc:
            checks.score_both(p, sec, year=2023, secondary_not_run=rec)
        assert msg in str(exc.value)


def test_t4_rerun_holdout_and_check_summary_paths(tmp_path: Path) -> None:
    built = _t1_built()
    path = tmp_path / "check_inputs.json"
    path.write_text(json.dumps(built))
    scored = rerun_v14_score._score_holdout(path, year=2023)
    assert scored["secondary_status"] == {"status": "NOT_RUN", "reason": "S NOT_CONVERGED"}
    assert scored["agreement"]["pass"] is None
    summary = rerun_v14_score._check_summary(path)
    assert summary["secondary_gating_pass"] is False


def test_t4_holdout_report_states_secondary_not_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from georgist.v14_score_report import PIN_TABLE as MERGE_PINS, sha256_file
    from scripts.rerun_v14_score import main as score_main
    from test_v14_gaps_pr2_lock import _layout

    built = _t1_built()
    paths = _layout(tmp_path)
    paths["checks"].write_text(json.dumps(built), encoding="utf-8")
    f8 = tmp_path / "check4_f8.json"
    f8.write_text(json.dumps({"schema": "v14_check4_f8_v1", "zones": [
        {"zone": z["zone"], "capitalised_property": 200.0, "drc": 100.0, "capitalised_land": 100.0}
        for z in built["primary_zones"]]}) + "\n", encoding="utf-8")
    monkeypatch.setitem(MERGE_PINS, "merge_map", sha256_file(paths["merge_map"]))
    out = tmp_path / "holdout" / "report.json"
    argv = ["--out", str(out), "--holdout-2023", "--check-inputs", str(paths["checks"]),
            "--lock-path", str(paths["lock"]), "--merge-map", str(paths["merge_map"]),
            "--hedonic-coefs", str(paths["coefs"]), "--sha8-block", str(paths["sha8"]),
            "--check3-plot-passes", str(paths["check3"]), "--check4-f8", str(f8),
            "--ur6", str(paths["ur6"]), "--dz2022-keys", str(paths["dz"])]
    assert score_main(argv) == 0
    checks_block = json.loads(out.read_text(encoding="utf-8"))["checks"]
    assert checks_block["secondary_status"] == {"status": "NOT_RUN", "reason": "S NOT_CONVERGED"}
    assert checks_block["scope"] == "internal_diagnostic_only"
    assert checks_block["gbp_display"] is False
    assert checks_block["secondary_gating_pass"] is False
    assert checks_block["effective_publication"] == {
        "status": "internal_diagnostic_only",
        "reason": "secondary NOT_RUN (S NOT_CONVERGED); AM-3 M5 precedent: NOT_RUN = NOT PASSED",
        "governs": True,
        "gbp_display": False,
    }


# ---------------- T5: effective_publication governs (Auditor ruling 2) ----------------

EFFECTIVE = {
    "status": "internal_diagnostic_only",
    "reason": "secondary NOT_RUN (S NOT_CONVERGED); AM-3 M5 precedent: NOT_RUN = NOT PASSED",
    "governs": True,
    "gbp_display": False,
}


def test_t5_effective_publication_beside_unchanged_no_switch_outcome() -> None:
    built = _t1_built()
    out = checks.score_both(built["primary_zones"], [], year=2023, secondary_not_run=built["check4_secondary"])
    ref = checks.score_both(built["primary_zones"], built["primary_zones"], year=2023)
    assert out["effective_publication"] == EFFECTIVE
    # Pre-registered no-switch outcome is computed exactly as before (secondary gate False).
    expect = v14_pub(bool(ref["primary"]["gating_pass"]), False)
    assert out["publication"] == {**expect, **({"am1_label": out["publication"]["am1_label"]})}
    assert "effective_publication" not in ref


def v14_pub(p: bool, s: bool) -> dict:
    from georgist import surface_v14 as v14
    return v14.apply_no_switch_publication(primary_gating_pass=p, secondary_gating_pass=s)


def test_t5_no_display_or_export_consumer_reads_publication_outcome() -> None:
    """'publish_primary_only' must never reach a display/export/bands path.

    Fails if any non-test backend/frontend source outside the scoring modules reads the
    no-switch outcome or publish flags (a new consumer must defer to effective_publication).
    """
    root = Path(__file__).resolve().parents[2]
    allowed = {
        "backend/georgist/surface_v14.py",
        "backend/georgist/surface_v14_checks.py",
        "backend/georgist/v14_score_report.py",
        "backend/scripts/rerun_v14_score.py",
        "backend/georgist/v14_check4_route.py",
    }
    needles = (
        "publish_primary_only", "publish_range_both", "publish_primary", "publish_secondary", "publish_as_range",
        "[\"publication\"]", "['publication']", "get(\"publication\")", "get('publication')",
    )
    offenders = []
    for base in ("backend", "frontend/src"):
        for path in (root / base).rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx", ".js"} or "test" in path.name or "node_modules" in path.parts:
                continue
            rel = path.relative_to(root).as_posix()
            if rel in allowed or "/tests/" in f"/{rel}":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(n in text for n in needles):
                offenders.append(rel)
    assert offenders == []


def test_t5_report_refuses_gbp_display_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from georgist import surface_v14_checks as c
    from georgist.v14_score_report import PIN_TABLE as MERGE_PINS, sha256_file
    from scripts.rerun_v14_score import main as score_main
    from test_v14_gaps_pr2_lock import _layout

    monkeypatch.setitem(c.EFFECTIVE_PUBLICATION_S_NOT_RUN, "gbp_display", True)
    built = _t1_built()
    paths = _layout(tmp_path)
    paths["checks"].write_text(json.dumps(built), encoding="utf-8")
    f8 = tmp_path / "check4_f8.json"
    f8.write_text(json.dumps({"schema": "v14_check4_f8_v1", "zones": [
        {"zone": z["zone"], "capitalised_property": 200.0, "drc": 100.0, "capitalised_land": 100.0}
        for z in built["primary_zones"]]}) + "\n", encoding="utf-8")
    monkeypatch.setitem(MERGE_PINS, "merge_map", sha256_file(paths["merge_map"]))
    out = tmp_path / "holdout" / "report.json"
    argv = ["--out", str(out), "--holdout-2023", "--check-inputs", str(paths["checks"]),
            "--lock-path", str(paths["lock"]), "--merge-map", str(paths["merge_map"]),
            "--hedonic-coefs", str(paths["coefs"]), "--sha8-block", str(paths["sha8"]),
            "--check3-plot-passes", str(paths["check3"]), "--check4-f8", str(f8),
            "--ur6", str(paths["ur6"]), "--dz2022-keys", str(paths["dz"])]
    capsys.readouterr()
    assert score_main(argv) == 1
    assert "CHECK4-S-NOTRUN: gbp_display: expected false, got other" in capsys.readouterr().err
    assert not paths["lock"].exists()
