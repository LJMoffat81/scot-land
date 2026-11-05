"""LOCK-OUTPUTS. SYNTHETIC fixtures only. No scoring on real data, no step 10."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.rerun_v14_score as rerun
from georgist.v14_score_report import (
    HoldoutLockError,
    assert_2024_allowed,
    emit_dz_status,
    score_2024_lock_path,
    score_2024_tombstone_path,
    sha256_file,
    write_holdout_lock,
    write_score_2024_tombstone,
)
from scripts.rerun_v14_score import main as score_main
from test_v14_gaps_pr2_lock import _args, _holdout, _layout, _score_stub


COMMIT = "0" * 40


def _out(tmp_path: Path, name: str = "report.json", body: str = '{"r": 1}\n') -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_lock_writes_outputs_sha256_in_same_write(tmp_path: Path) -> None:
    rep = _out(tmp_path)
    extra = _out(tmp_path, "t.md", "x\n")
    lock = write_holdout_lock(
        tmp_path,
        inputs_sha256="i",
        commit=COMMIT,
        report_sha256=sha256_file(rep),
        lock_path=tmp_path / "h.lock",
        outputs={"report": rep, "table": extra},
    )
    payload = json.loads(lock.read_text(encoding="utf-8"))
    assert payload["outputs_sha256"] == {"report": sha256_file(rep), "table": sha256_file(extra)}
    assert payload["report_sha256"] == sha256_file(rep)


def test_refuses_empty_outputs(tmp_path: Path) -> None:
    with pytest.raises(HoldoutLockError) as exc:
        write_holdout_lock(
            tmp_path, inputs_sha256="i", commit=COMMIT, lock_path=tmp_path / "h.lock", outputs={}
        )
    assert str(exc.value) == "LOCK-OUTPUTS: REFUSED: outputs: expected non-empty, got empty"
    assert not (tmp_path / "h.lock").exists()


def test_refuses_missing_output_file(tmp_path: Path) -> None:
    with pytest.raises(HoldoutLockError) as exc:
        write_holdout_lock(
            tmp_path,
            inputs_sha256="i",
            commit=COMMIT,
            lock_path=tmp_path / "h.lock",
            outputs={"report": tmp_path / "absent.json"},
        )
    assert str(exc.value) == "LOCK-OUTPUTS: REFUSED: output report: expected file, got absent"
    assert not (tmp_path / "h.lock").exists()


def test_refuses_outputs_without_report(tmp_path: Path) -> None:
    rep = _out(tmp_path)
    other = _out(tmp_path, "t.md", "x\n")
    with pytest.raises(HoldoutLockError) as exc:
        write_holdout_lock(
            tmp_path,
            inputs_sha256="i",
            commit=COMMIT,
            report_sha256=sha256_file(rep),
            lock_path=tmp_path / "h.lock",
            outputs={"table": other},
        )
    assert str(exc.value) == "LOCK-OUTPUTS: REFUSED: outputs: expected report, got absent"
    assert not (tmp_path / "h.lock").exists()


def test_byte_identity_before_after(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC holdout run, before (no outputs) and after: report bytes equal; lock equal bar the new key."""
    paths = _layout(tmp_path)
    real = rerun._run_outputs
    monkeypatch.setattr(rerun, "_run_outputs", lambda *_a, **_k: None)
    _holdout(paths, monkeypatch)
    report_before = paths["out"].read_bytes()
    lock_before = paths["lock"].read_bytes()
    table = paths["out"].parent / "code_text_disagreements.md"
    table_before = table.read_bytes()
    paths["lock"].unlink()
    paths["out"].unlink()
    table.unlink()
    monkeypatch.setattr(rerun, "_run_outputs", real)
    _holdout(paths, monkeypatch)
    assert paths["out"].read_bytes() == report_before
    assert table.read_bytes() == table_before
    after = json.loads(paths["lock"].read_text(encoding="utf-8"))
    outputs = after.pop("outputs_sha256")
    assert (json.dumps(after, sort_keys=True) + "\n").encode("utf-8") == lock_before
    assert outputs == {
        "code_text_disagreements": sha256_file(table),
        "report": sha256_file(paths["out"]),
    }


def test_2024_lock_written_holdout_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. 2024 writes its own lock; the 2023 holdout lock stays byte-identical."""
    paths = _layout(tmp_path)
    _holdout(paths, monkeypatch)
    before = paths["lock"].read_bytes()
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "score" / "report.json"
    assert score_main(_args(paths, out, holdout=False, score=True)) == 0
    assert calls["n"] == 1
    assert paths["lock"].read_bytes() == before
    score_lock = paths["lock"].with_name("score_2024.lock")
    assert score_lock.is_file()
    payload = json.loads(score_lock.read_text(encoding="utf-8"))
    assert payload["score_2024"] is True
    assert payload["report_sha256"] == sha256_file(out)
    assert isinstance(payload["outputs_sha256"], dict)
    assert payload["outputs_sha256"]["report"] == sha256_file(out)
    assert "score_2024" not in json.loads(before)
    assert paths["lock"].with_name("score_2024.tombstone").is_file()


def test_dz_status_out_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    paths = _layout(tmp_path)
    _holdout(paths, monkeypatch)
    before = paths["lock"].read_bytes()
    status_out = tmp_path / "dz_status.json"
    calls, spy = _score_stub()
    monkeypatch.setattr("scripts.rerun_v14_score._score_holdout", spy)
    out = tmp_path / "score" / "report.json"
    argv = _args(paths, out, holdout=False, score=True) + ["--dz-status-out", str(status_out)]
    assert score_main(argv) == 1
    err = capsys.readouterr().err
    assert (
        err.strip()
        == "LOCK-OUTPUTS: REFUSED: --dz-status-out: DZ-STATUS-EMIT not in this PR"
    )
    assert calls["n"] == 0
    assert not status_out.exists()
    assert paths["lock"].read_bytes() == before
    assert not paths["lock"].with_name("score_2024.lock").exists()


def test_emit_dz_status_hook_refuses(tmp_path: Path) -> None:
    target = tmp_path / "half.json"
    with pytest.raises(HoldoutLockError) as exc:
        emit_dz_status(target)
    assert str(exc.value) == (
        "LOCK-OUTPUTS: REFUSED: --dz-status-out: DZ-STATUS-EMIT not in this PR"
    )
    assert not target.exists()



def test_write_holdout_lock_refuses_existing(tmp_path: Path) -> None:
    """SYNTHETIC. Existence guard: never edits an existing lock."""
    lock = tmp_path / "h.lock"
    first = write_holdout_lock(
        tmp_path, inputs_sha256="i", commit=COMMIT, lock_path=lock
    )
    before = first.read_bytes()
    with pytest.raises(HoldoutLockError) as exc:
        write_holdout_lock(
            tmp_path, inputs_sha256="j", commit=COMMIT, lock_path=lock
        )
    assert str(exc.value) == "LOCK-OUTPUTS: REFUSED: lock: expected absent, got present"
    assert lock.read_bytes() == before


def test_assert_2024_allowed_refuses_when_lock_exists(tmp_path: Path) -> None:
    """SYNTHETIC. Direct unit: final score_2024.lock alone refuses."""
    holdout = tmp_path / "holdout.lock"
    holdout.write_text(
        '{"inputs_sha256": "synthetic", "commit": "'
        + COMMIT
        + '", "label": "seen, not out-of-sample"}\n',
        encoding="utf-8",
    )
    score_lock = score_2024_lock_path(holdout)
    score_lock.write_text('{"score_2024": true}\n', encoding="utf-8")
    assert not score_2024_tombstone_path(holdout).exists()
    with pytest.raises(HoldoutLockError) as exc:
        assert_2024_allowed(lock_path=holdout)
    assert str(exc.value) == "second 2024 run refused"


def test_assert_2024_allowed_refuses_when_tombstone_exists(tmp_path: Path) -> None:
    """SYNTHETIC. Direct unit: tombstone alone refuses (crash-after-start)."""
    holdout = tmp_path / "holdout.lock"
    holdout.write_text(
        '{"inputs_sha256": "synthetic", "commit": "'
        + COMMIT
        + '", "label": "seen, not out-of-sample"}\n',
        encoding="utf-8",
    )
    tombstone = score_2024_tombstone_path(holdout)
    write_score_2024_tombstone(tombstone)
    assert not score_2024_lock_path(holdout).exists()
    with pytest.raises(HoldoutLockError) as exc:
        assert_2024_allowed(lock_path=holdout)
    assert str(exc.value) == "second 2024 run refused"


def test_write_score_2024_tombstone_is_o_excl(tmp_path: Path) -> None:
    """SYNTHETIC. Second tombstone write refuses; first bytes unchanged."""
    path = tmp_path / "score_2024.tombstone"
    write_score_2024_tombstone(path)
    before = path.read_bytes()
    with pytest.raises(HoldoutLockError) as exc:
        write_score_2024_tombstone(path)
    assert str(exc.value) == "second 2024 run refused"
    assert path.read_bytes() == before


def test_tombstone_path_distinct_from_lock_and_holdout(tmp_path: Path) -> None:
    """SYNTHETIC. Tombstone is neither the holdout nor the final lock."""
    holdout = tmp_path / "holdout.lock"
    score_lock = score_2024_lock_path(holdout)
    tombstone = score_2024_tombstone_path(holdout)
    assert tombstone != holdout
    assert tombstone != score_lock
    assert tombstone.name == "score_2024.tombstone"
    assert score_lock.name == "score_2024.lock"
