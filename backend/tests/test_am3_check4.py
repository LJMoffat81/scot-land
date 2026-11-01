"""AM-3 (Check 4 reporting-only, 2024 run) synthetic tests A1-A12. No real 2024 data, no money levels."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from georgist.surface_paths import REPO_ROOT
from georgist.v14_check4_route import (
    AM3_SHA256,
    AM3_SIGNATURES_SHA256,
    PIN_TABLE,
    Check4RouteError,
    build_v15_check4_score_report,
    check4_sensitivities,
    check_2024_inputs,
    score_check4_non_gbp,
)

COMMITTED_REPORT = REPO_ROOT / "data" / "processed" / "methods_code_1" / "v15_check4_score" / "report.json"
GATE_KEYS = (
    "check", "status", "pass", "reason", "national_max_abs", "class_max_abs", "n_zones",
    "n_unavailable", "n_positive_residual", "n_positive_capitalised", "residual_median_positive",
    "class_residual_median_positive", "national_median_gap", "national_within_band", "by_ur6",
)


def _zone(idx: int, ur6: int, res: float, cap: float, **flags) -> dict:
    z = {"zone": f"S0100{idx:04d}", "ur6": ur6, "residual_land": res, "capitalised_land": cap,
         "unavailable": False, "model_failure": False}
    z.update(flags)
    return z


def _fail_246() -> list[dict]:
    """3 zones per UR6 class; classes 6, 4, 2 (listed in that order) have 2 of 3 zero-filled."""
    zones: list[dict] = []
    idx = 0
    for ur6 in (6, 5, 4, 3, 2, 1):
        for j in range(3):
            bad = ur6 in (2, 4, 6) and j < 2
            flags = {}
            if bad:
                flags = [{"unavailable": True}, {"unavailable": True, "model_failure": True}][j]
                if ur6 == 4 and j == 0:
                    flags = {"unavailable": True, "no_cell": True}
            zones.append(_zone(idx, ur6, 0.0 if bad else 90.0 + j, 100.0 + j, **flags))
            idx += 1
    return zones


def _passing() -> list[dict]:
    return [_zone(i, (i % 6) + 1, 105.0 + i, 100.0 + i,
                  capitalised_land_no_plus4=95.0 + i, drc_gt_price=(i % 4 == 0),
                  drc_gt_capitalised_property=(i % 3 == 0)) for i in range(12)]


def _write(tmp_path: Path, name: str, body: bytes) -> tuple[Path, str]:
    p = tmp_path / f"{name}.bin"
    p.write_bytes(body)
    return p, hashlib.sha256(body).hexdigest()


def _inputs(tmp_path: Path) -> tuple[dict, dict]:
    paths, pins = {}, {}
    for name in ("rents", "drc", "prices"):
        paths[name], pins[name] = _write(tmp_path, name, f"synthetic {name}\n".encode())
    return paths, pins


def _report(zp, zs, **kw):
    n = len(zp)
    return build_v15_check4_score_report(
        primary_zones=zp, secondary_zones=zs, pins=PIN_TABLE, lookup_zones=n + 1, not_scored_zones=1,
        secondary_scored_zones=n, secondary_no_cell_zones=0, cancellation_zones_checked=n, **kw)


def test_a1_failing_classes_lists_all_sorted_and_reason_unchanged() -> None:
    out = score_check4_non_gbp(_fail_246(), am3_reporting=True)
    assert out["failing_classes"] == [2, 4, 6]
    assert out["reason"] == "residual_route_median_non_positive_ur6_6"
    assert out["pass"] is False


def test_a2_failing_classes_empty_on_pass_and_single_class() -> None:
    assert score_check4_non_gbp(_passing(), am3_reporting=True)["failing_classes"] == []
    zones = _passing()
    for z in zones:
        if z["ur6"] == 3:
            z["unavailable"] = True
    assert score_check4_non_gbp(zones, am3_reporting=True)["failing_classes"] == [3]


def test_a3_unavailable_split_sums_and_precedence() -> None:
    out = score_check4_non_gbp(_fail_246(), am3_reporting=True)
    split = out["unavailable_split"]
    assert split == {"negative_residual": 2, "model_failure": 3, "no_cell": 1, "zero_filled": 6}
    assert split["negative_residual"] + split["model_failure"] + split["no_cell"] == out["n_unavailable"] == 6
    by = out["unavailable_split_by_ur6"]
    assert by["4"] == {"negative_residual": 0, "model_failure": 1, "no_cell": 1}
    assert by["1"] == {"negative_residual": 0, "model_failure": 0, "no_cell": 0}
    assert sum(sum(v.values()) for v in by.values()) == 6


def test_a4_no_cell_without_unavailable_is_counted_not_zero_filled() -> None:
    zones = _passing()
    zones[0]["no_cell"] = True
    out = score_check4_non_gbp(zones, am3_reporting=True)
    assert out["unavailable_split"]["no_cell"] == 0
    assert out["no_cell_not_zero_filled"] == 1
    assert out["n_unavailable"] == 0


@pytest.mark.parametrize("flag", ["unavailable", "model_failure", "no_cell"])
@pytest.mark.parametrize("bad", ["", "true", 1, None])
def test_a5_non_bool_flag_refused_exact_message(flag: str, bad) -> None:
    zones = _passing()
    zones[0][flag] = bad
    with pytest.raises(Check4RouteError) as exc:
        score_check4_non_gbp(zones, am3_reporting=True)
    assert str(exc.value) == f"V14_CHECK4: ERROR: score zone flag {flag}: expected bool, got {type(bad).__name__}"


def test_a6_am3_off_output_identical_to_v15_shape() -> None:
    for zones in (_fail_246(), _passing()):
        off = score_check4_non_gbp(copy.deepcopy(zones))
        on = score_check4_non_gbp(copy.deepcopy(zones), am3_reporting=True)
        assert set(off) == set(GATE_KEYS)
        assert json.dumps({k: on[k] for k in GATE_KEYS}, sort_keys=True) == json.dumps(off, sort_keys=True)


def test_a7_sensitivities_never_gate_and_do_not_mutate() -> None:
    for zones in (_fail_246(), _passing()):
        before = copy.deepcopy(zones)
        gate_off = score_check4_non_gbp(copy.deepcopy(zones))
        sens = check4_sensitivities(zones, estimator="secondary")
        gate_after = score_check4_non_gbp(zones)
        assert zones == before
        assert gate_after == gate_off
        assert sens["gating"] is False
        assert all(sens[k]["gating"] is False for k in sens if k != "gating")


def test_a8_sensitivity_values() -> None:
    sens = check4_sensitivities(_fail_246(), estimator="secondary")
    s1 = sens["S1_exclude_zero_filled"]
    assert s1["n_zones"] == 12 and s1["pass"] is True
    s3 = sens["S3_secondary_no_cell_excluded"]
    assert s3["n_zones"] == 17
    assert sens["S2_no_plus4_uplift"] == {"gating": False, "status": "not_computable",
                                          "detail": "input absent: capitalised_land_no_plus4"}
    assert sens["S4_drc_exceeds_counts"]["status"] == "not_computable"
    prim = check4_sensitivities(_passing(), estimator="primary")
    assert prim["S3_secondary_no_cell_excluded"]["status"] == "not_applicable"
    assert prim["S2_no_plus4_uplift"]["n_zones"] == 12
    assert prim["S2_no_plus4_uplift"]["national_median_gap"] != score_check4_non_gbp(_passing())["national_median_gap"]
    s4 = prim["S4_drc_exceeds_counts"]["by_ur6"]
    assert sum(v["drc_gt_price"] for v in s4.values()) == 3
    assert sum(v["drc_gt_capitalised_property"] for v in s4.values()) == 4
    with pytest.raises(Check4RouteError) as exc:
        check4_sensitivities(_passing(), estimator="tertiary")
    assert str(exc.value) == "V14_CHECK4: ERROR: sensitivity estimator: expected primary or secondary, got 'tertiary'"


def test_a9_s1_all_zero_filled_not_computable() -> None:
    zones = [_zone(i, (i % 6) + 1, 0.0, 100.0, unavailable=True) for i in range(6)]
    s1 = check4_sensitivities(zones, estimator="primary")["S1_exclude_zero_filled"]
    assert s1 == {"gating": False, "status": "not_computable", "detail": "no zones after exclusion"}


def test_a10_2024_report_gate_identical_with_block_and_writes_am3(tmp_path: Path) -> None:
    paths, pins = _inputs(tmp_path)
    zp, zs = _passing(), _fail_246()[:12]
    r24 = _report(zp, zs, year=2024, inputs_2024=paths, pins_2024=pins)
    r23 = _report(copy.deepcopy(zp), copy.deepcopy(zs), year=2023)
    for est in ("primary", "secondary"):
        assert {k: r24[est][k] for k in GATE_KEYS} == r23[est]
    assert r24["publication"] == r23["publication"]
    assert r24["status"] == "scored" and r24["gbp_display"] is False
    assert r24["method_authority"]["am3_sha256"] == AM3_SHA256
    assert r24["method_authority"]["am3_signatures_sha256"] == AM3_SIGNATURES_SHA256
    assert r24["sensitivities"]["gating"] is False
    assert r24["pins_2024"] == pins
    assert "sensitivities" not in r23 and "failing_classes" not in r23["primary"]


@pytest.mark.parametrize(
    "mutate,inp,detail",
    [
        (lambda p, s, t: p.pop("rents"), "rents", "file absent"),
        (lambda p, s, t: p["drc"].unlink(), "drc", "file absent"),
        (lambda p, s, t: p.__setitem__("prices", t / "nope.bin"), "prices", "file absent"),
        (lambda p, s, t: p.__setitem__("prices", t), "prices", "file absent"),
        (lambda p, s, t: s.pop("drc"), "drc", "pin absent"),
        (lambda p, s, t: s.__setitem__("rents", ""), "rents", "pin absent"),
        (lambda p, s, t: s.__setitem__("drc", s["drc"][:63]), "drc", "pin absent"),
        (lambda p, s, t: s.__setitem__("drc", s["drc"].upper()), "drc", "pin absent"),
        (lambda p, s, t: s.__setitem__("prices", None), "prices", "pin absent"),
        (lambda p, s, t: s.__setitem__("prices", "0" * 64), "prices", "pin mismatch"),
        (lambda p, s, t: p["rents"].write_bytes(b"altered\n"), "rents", "pin mismatch"),
        (lambda p, s, t: p.__setitem__("drc", str(p["drc"])), "drc", "file absent"),
    ],
)
def test_a11_2024_missing_or_altered_pin_is_not_run_never_pass(tmp_path: Path, mutate, inp, detail) -> None:
    paths, pins = _inputs(tmp_path)
    assert check_2024_inputs(paths, pins) is None
    mutate(paths, pins, tmp_path)
    assert check_2024_inputs(paths, pins) == {"input": inp, "detail": detail}
    rep = _report(_passing(), _passing(), year=2024, inputs_2024=paths, pins_2024=pins)
    assert rep["status"] == "NOT_RUN"
    assert rep["reason"] == f"source unavailable: {inp}"
    for est in ("primary", "secondary"):
        assert rep[est]["status"] == "NOT_RUN" and rep[est]["pass"] is False
        assert rep[est]["reason"] == f"source unavailable: {inp}" and rep[est]["detail"] == detail
    assert rep["publication"]["outcome"] == "both_fail_publish_neither"
    assert rep["publication"]["publish_primary"] is False and rep["publication"]["publish_secondary"] is False
    assert "sensitivities" not in rep and rep["gbp_display"] is False


def test_a11b_2024_without_inputs_is_not_run_first_input() -> None:
    for inputs, pins in ((None, None), ({}, {})):
        rep = _report(_passing(), _passing(), year=2024, inputs_2024=inputs, pins_2024=pins)
        assert rep["status"] == "NOT_RUN" and rep["reason"] == "source unavailable: rents"
        assert rep["primary"]["pass"] is False


def test_a12_committed_2023_gate_fields_reproduce_from_counts() -> None:
    """Regression: committed #280 report keeps its sha and its exact key set (no AM-3 keys on 2023)."""
    raw = COMMITTED_REPORT.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "ff6e07a62dffb7c6455754298e8712bb300053ed96f233c147ce36ce2d91d59f"
    payload = json.loads(raw)
    for est in ("primary", "secondary"):
        assert set(payload[est]) == set(GATE_KEYS)
    assert "sensitivities" not in payload
