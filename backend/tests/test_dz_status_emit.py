"""DZ-STATUS-EMIT. SYNTHETIC fixtures only. No scoring on real data, no step 10."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from georgist.v14_score_report import (
    DZ2011_KEYS_SHA256,
    DZ_STATUS_IDS,
    HoldoutLockError,
    build_dz_status_map,
    classify_scored_zone,
    emit_dz_status,
    load_dz2011_keys,
    sha256_file,
)
from scripts.rerun_v14_score import main as score_main
from test_lock_outputs import _args, _holdout, _layout, _score_stub
from test_v14_pipeline_b import _zone


KEYS = frozenset({"S01000001", "S01000002", "S01000003", "S01000004"})


def _write_keys(path: Path, codes: list[str] | None = None) -> str:
    payload = sorted(codes if codes is not None else KEYS)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_classify_precedence_no_cell_over_model_failure() -> None:
    assert classify_scored_zone({"zone": "S01000001", "no_cell": True, "model_failure": True}) == "no_cell"


def test_classify_precedence_model_failure_over_unavailable() -> None:
    assert (
        classify_scored_zone({"zone": "S01000001", "model_failure": True, "unavailable": True})
        == "model_failure"
    )


def test_classify_unavailable() -> None:
    assert classify_scored_zone({"zone": "S01000001", "unavailable": True}) == "unavailable"


def test_classify_estimated_default() -> None:
    assert classify_scored_zone({"zone": "S01000001"}) == "estimated"


def test_classify_non_bool_flag_refused() -> None:
    with pytest.raises(HoldoutLockError) as exc:
        classify_scored_zone({"zone": "S01000001", "unavailable": "yes"})
    assert str(exc.value) == (
        "DZ-STATUS-EMIT: REFUSED: zone S01000001: expected bool flag unavailable, got str"
    )


def test_build_scored_plus_not_scored_covers_keys_exactly() -> None:
    primary = [
        _zone("S01000001"),
        _zone("S01000002", unavailable=True),
        _zone("S01000003", model_failure=True),
    ]
    out = build_dz_status_map(KEYS, primary)
    assert out == {
        "S01000001": "estimated",
        "S01000002": "unavailable",
        "S01000003": "model_failure",
        "S01000004": "not_scored",
    }
    n_scored = sum(1 for s in out.values() if s != "not_scored")
    n_not = sum(1 for s in out.values() if s == "not_scored")
    assert n_scored + n_not == len(KEYS)
    assert set(out) == KEYS


def test_build_extra_zone_refused() -> None:
    with pytest.raises(HoldoutLockError) as exc:
        build_dz_status_map(KEYS, [_zone("S01000001"), _zone("S01999999")])
    assert str(exc.value) == (
        "DZ-STATUS-EMIT: REFUSED: coverage: extra zone S01999999 (1 extra)"
    )


def test_build_duplicate_zone_refused() -> None:
    with pytest.raises(HoldoutLockError) as exc:
        build_dz_status_map(KEYS, [_zone("S01000001"), _zone("S01000001")])
    assert str(exc.value) == (
        "DZ-STATUS-EMIT: REFUSED: zone S01000001: expected unique, got duplicate"
    )


def test_build_absent_primary_refused() -> None:
    with pytest.raises(HoldoutLockError) as exc:
        build_dz_status_map(KEYS, None)  # type: ignore[arg-type]
    assert str(exc.value) == (
        "DZ-STATUS-EMIT: REFUSED: check inputs: expected primary_zones, got absent"
    )


def test_emit_writes_pr_a_schema(tmp_path: Path) -> None:
    statuses = build_dz_status_map(
        KEYS,
        [_zone("S01000001"), _zone("S01000002", no_cell=True)],
    )
    out = tmp_path / "dz_status_2024.json"
    emit_dz_status(
        out,
        estimate_year=2024,
        data_zone_vintage="DZ2011",
        statuses=statuses,
        keys=KEYS,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert set(payload) == {"estimate_year", "data_zone_vintage", "zones"}
    assert payload["estimate_year"] == 2024
    assert payload["data_zone_vintage"] == "DZ2011"
    assert [row["zone"] for row in payload["zones"]] == sorted(KEYS)
    assert {row["zone"]: row["status"] for row in payload["zones"]} == statuses
    assert all(set(row) == {"zone", "status"} for row in payload["zones"])
    assert "\u00a3" not in out.read_text(encoding="utf-8")
    assert "gbp" not in out.read_text(encoding="utf-8").lower()


def test_emit_year_2023_refused(tmp_path: Path) -> None:
    statuses = {code: "not_scored" for code in KEYS}
    with pytest.raises(HoldoutLockError) as exc:
        emit_dz_status(
            tmp_path / "s.json",
            estimate_year=2023,
            data_zone_vintage="DZ2011",
            statuses=statuses,
            keys=KEYS,
        )
    assert str(exc.value) == "DZ-STATUS-EMIT: REFUSED: estimate_year: expected 2024, got 2023"
    assert not (tmp_path / "s.json").exists()


def test_emit_wrong_vintage_refused(tmp_path: Path) -> None:
    statuses = {code: "not_scored" for code in KEYS}
    with pytest.raises(HoldoutLockError) as exc:
        emit_dz_status(
            tmp_path / "s.json",
            estimate_year=2024,
            data_zone_vintage="DZ2022",
            statuses=statuses,
            keys=KEYS,
        )
    assert str(exc.value) == (
        "DZ-STATUS-EMIT: REFUSED: data_zone_vintage: expected DZ2011, got DZ2022"
    )


def test_emit_existing_path_refused(tmp_path: Path) -> None:
    statuses = {code: "not_scored" for code in KEYS}
    out = tmp_path / "s.json"
    out.write_text("{}\n", encoding="utf-8")
    before = out.read_bytes()
    with pytest.raises(HoldoutLockError) as exc:
        emit_dz_status(
            out,
            estimate_year=2024,
            data_zone_vintage="DZ2011",
            statuses=statuses,
            keys=KEYS,
        )
    assert str(exc.value) == "DZ-STATUS-EMIT: REFUSED: status out: expected absent, got present"
    assert out.read_bytes() == before


def test_emit_missing_coverage_refused(tmp_path: Path) -> None:
    statuses = {code: "not_scored" for code in list(KEYS)[:3]}
    with pytest.raises(HoldoutLockError) as exc:
        emit_dz_status(
            tmp_path / "s.json",
            estimate_year=2024,
            data_zone_vintage="DZ2011",
            statuses=statuses,
            keys=KEYS,
        )
    assert str(exc.value).startswith("DZ-STATUS-EMIT: REFUSED: coverage: missing zone ")
    assert not (tmp_path / "s.json").exists()


def test_emit_unknown_status_refused(tmp_path: Path) -> None:
    statuses = {code: "not_scored" for code in KEYS}
    statuses["S01000001"] = "pending"
    with pytest.raises(HoldoutLockError) as exc:
        emit_dz_status(
            tmp_path / "s.json",
            estimate_year=2024,
            data_zone_vintage="DZ2011",
            statuses=statuses,
            keys=KEYS,
        )
    assert str(exc.value) == (
        "DZ-STATUS-EMIT: REFUSED: zone S01000001: expected status enum, got 'pending'"
    )


def test_load_keys_pin_mismatch_refused(tmp_path: Path) -> None:
    keys_path = tmp_path / "keys.json"
    _write_keys(keys_path)
    with pytest.raises(HoldoutLockError) as exc:
        load_dz2011_keys(keys_path, expected_sha="0" * 64)
    assert str(exc.value).startswith("DZ-STATUS-EMIT: REFUSED: keys sha256: expected ")


def test_load_keys_missing_refused(tmp_path: Path) -> None:
    with pytest.raises(HoldoutLockError) as exc:
        load_dz2011_keys(tmp_path / "absent.json", expected_sha=None)
    assert str(exc.value) == "DZ-STATUS-EMIT: REFUSED: keys file: expected file, got absent"


def test_load_production_keys_pin() -> None:
    keys = load_dz2011_keys()
    assert len(keys) == 6976
    assert DZ2011_KEYS_SHA256.startswith("2611c9e7")
    assert all(code.startswith("S01") for code in list(keys)[:3])


def test_status_ids_match_heatmap_contract() -> None:
    from georgist.dz_heatmap import STATUS_IDS

    assert DZ_STATUS_IDS == STATUS_IDS


def test_emit_pound_in_serialised_body_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    statuses = {code: "not_scored" for code in KEYS}
    real = json.dumps

    def inject(obj, **kwargs):
        return real(obj, **kwargs).replace('"not_scored"', '"not_scored \u00a3"')

    monkeypatch.setattr("georgist.v14_score_report.json.dumps", inject)
    with pytest.raises(HoldoutLockError) as exc:
        emit_dz_status(
            tmp_path / "s.json",
            estimate_year=2024,
            data_zone_vintage="DZ2011",
            statuses=statuses,
            keys=KEYS,
        )
    assert str(exc.value) == "DZ-STATUS-EMIT: REFUSED: status file contains a pound sign"
    assert not (tmp_path / "s.json").exists()


def test_score_2024_dz_status_out_writes_and_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. Emit after report; sha listed in score_2024.lock outputs_sha256."""
    paths = _layout(tmp_path)
    _holdout(paths, monkeypatch)
    # Tiny synthetic key set matching the layout's Z0..Z7 primary zones.
    codes = [f"Z{index}" for index in range(8)]
    keys_path = tmp_path / "synth_keys.json"
    digest = _write_keys(keys_path, codes)
    monkeypatch.setattr(
        "scripts.rerun_v14_score.load_dz2011_keys",
        lambda path=None, expected_sha=None: load_dz2011_keys(keys_path, expected_sha=digest),
    )
    # Mark one zone unavailable so the file is not all-estimated.
    payload = json.loads(paths["checks"].read_text(encoding="utf-8"))
    payload["primary_zones"][0]["unavailable"] = True
    payload["primary_zones"][1]["model_failure"] = True
    payload["primary_zones"][2]["no_cell"] = True
    paths["checks"].write_text(json.dumps(payload), encoding="utf-8")

    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "score" / "report.json"
    status_out = tmp_path / "dz_heatmap" / "dz_status_2024.json"
    argv = _args(paths, out, holdout=False, score=True) + ["--dz-status-out", str(status_out)]
    assert score_main(argv) == 0
    assert calls["n"] == 1
    assert status_out.is_file()
    body = json.loads(status_out.read_text(encoding="utf-8"))
    assert body["estimate_year"] == 2024
    assert body["data_zone_vintage"] == "DZ2011"
    by_status = {row["zone"]: row["status"] for row in body["zones"]}
    assert by_status["Z0"] == "unavailable"
    assert by_status["Z1"] == "model_failure"
    assert by_status["Z2"] == "no_cell"
    assert by_status["Z3"] == "estimated"
    assert set(by_status) == set(codes)
    score_lock = paths["lock"].with_name("score_2024.lock")
    locked = json.loads(score_lock.read_text(encoding="utf-8"))
    assert locked["outputs_sha256"]["dz_status"] == sha256_file(status_out)
    assert locked["outputs_sha256"]["report"] == sha256_file(out)


def test_dz_status_out_with_holdout_2023_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    paths = _layout(tmp_path)
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    status_out = tmp_path / "dz_status.json"
    argv = _args(paths, paths["out"], holdout=True, score=False) + [
        "--dz-status-out",
        str(status_out),
    ]
    assert score_main(argv) == 1
    assert (
        capsys.readouterr().err.strip()
        == "DZ-STATUS-EMIT: REFUSED: --dz-status-out: 2023 is never emitted"
    )
    assert calls["n"] == 0
    assert not status_out.exists()
    assert not paths["lock"].exists()


def test_dz_status_out_without_score_2024_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    paths = _layout(tmp_path)
    _holdout(paths, monkeypatch)
    before = paths["lock"].read_bytes()
    status_out = tmp_path / "dz_status.json"
    # Extended path without score/holdout flags: --check-inputs alone.
    argv = [
        "--out",
        str(tmp_path / "other" / "report.json"),
        "--check-inputs",
        str(paths["checks"]),
        "--dz-status-out",
        str(status_out),
    ]
    assert score_main(argv) == 1
    assert (
        capsys.readouterr().err.strip()
        == "DZ-STATUS-EMIT: REFUSED: --dz-status-out: requires --score-2024"
    )
    assert not status_out.exists()
    assert paths["lock"].read_bytes() == before
