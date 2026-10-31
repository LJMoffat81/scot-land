"""ARCH-6: Tests for weekly refresh runner + offline receipt/cron guard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from etl.refresh_registry import (
    RECEIPT_DIR,
    RefreshGuardError,
    check_receipt_dir,
    main,
    run_weekly_refresh,
    validate_cron_5field,
    validate_receipt_payload,
    validate_refresh_schedules,
)
from layers.registry.loader import REGISTRY_DIR, load_registry

_EXTENT_SHA = "e" * 64


def _valid_receipt(layer_id: str = "oil-fields") -> dict[str, Any]:
    return {
        "id": layer_id,
        "before": 12,
        "after": 10,
        "outside": 0,
        "repaired": 1,
        "url": "https://example.test/wfs?token=***",
        "as_of": "2026-10-23",
        "dataset_version": f"{layer_id}@2026-10-23-deadbeef",
        "extent_sha256": _EXTENT_SHA,
    }


def _valid_entry(
    layer_id: str = "oil-fields",
    *,
    cron: str = "0 4 * * 1",
    max_mb: float | int = 50,
    max_s: float | int = 120,
    clip_keep_all: bool = False,
    tiles: bool = False,
    gated_by: str | None = None,
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": layer_id,
        "refresh": {"cron": cron, "max_mb": max_mb, "max_s": max_s},
    }
    if clip_keep_all:
        raw["clip_keep_all"] = True
    if tiles:
        raw["serve"] = {"mode": "pmtiles"}
        raw["tiles"] = {"minzoom": 0, "maxzoom": 10}
    if gated_by:
        raw["gated_by"] = gated_by
    return raw


def test_real_registry_and_committed_receipts_pass() -> None:
    entries = load_registry(REGISTRY_DIR)
    ordered = validate_refresh_schedules(entries)
    assert ordered[0] == "scotland-extent"
    assert "settlements-2022" in ordered
    checked = check_receipt_dir(
        RECEIPT_DIR,
        entries=entries,
        require_layers=["settlements-2022"],
    )
    assert checked["settlements-2022"]["outside"] == 0
    assert checked["settlements-2022"]["after"] == 503


def test_cli_check_passes(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--check"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert "settlements-2022" in out["checked"]


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--check", "--run"],
    ],
)
def test_cli_requires_exact_mode(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(argv)
    assert rc == 2
    assert "REFRESH: specify exactly one of --check or --run" in (
        capsys.readouterr().err
    )


def test_cli_check_returns_1_on_guard_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["--check", "--receipt-dir", str(tmp_path)])
    assert rc == 1
    assert "REFRESH: no receipts found" in capsys.readouterr().err


@pytest.mark.parametrize(
    "cron",
    [
        "0 3 * * 1",
        "*/15 0-6 1,15 1-12 0-7",
        "30 4 1 * *",
    ],
)
def test_validate_cron_5field_accepts_valid_expressions(cron: str) -> None:
    assert validate_cron_5field("oil-fields", cron) == cron


@pytest.mark.parametrize(
    ("bad_cron", "msg"),
    [
        (None, r"^REFRESH: oil-fields: cron must be a 5-field string$"),
        (True, r"^REFRESH: oil-fields: cron must be a 5-field string$"),
        (123, r"^REFRESH: oil-fields: cron must be a 5-field string$"),
        (1.5, r"^REFRESH: oil-fields: cron must be a 5-field string$"),
        ([], r"^REFRESH: oil-fields: cron must be a 5-field string$"),
        ({}, r"^REFRESH: oil-fields: cron must be a 5-field string$"),
        ("", r"^REFRESH: oil-fields: cron must be a 5-field string$"),
        ("   ", r"^REFRESH: oil-fields: cron must be a 5-field string$"),
        ("0 3 * *", r"^REFRESH: oil-fields: cron must have 5 fields, got 4$"),
        ("0 3 * * * *", r"^REFRESH: oil-fields: cron must have 5 fields, got 6$"),
        ("60 3 * * 1", r"^REFRESH: oil-fields: invalid cron field '60'$"),
        ("0 24 * * 1", r"^REFRESH: oil-fields: invalid cron field '24'$"),
        ("0 3 0 * 1", r"^REFRESH: oil-fields: invalid cron field '0'$"),
        ("0 3 32 * 1", r"^REFRESH: oil-fields: invalid cron field '32'$"),
        ("0 3 * 13 1", r"^REFRESH: oil-fields: invalid cron field '13'$"),
        ("0 3 * * 8", r"^REFRESH: oil-fields: invalid cron field '8'$"),
        ("*/0 3 * * 1", r"^REFRESH: oil-fields: invalid cron field '\*/0'$"),
        ("*/x 3 * * 1", r"^REFRESH: oil-fields: invalid cron field '\*/x'$"),
        ("5-2 3 * * 1", r"^REFRESH: oil-fields: invalid cron field '5-2'$"),
        ("a-b 3 * * 1", r"^REFRESH: oil-fields: invalid cron field 'a-b'$"),
        ("foo 3 * * 1", r"^REFRESH: oil-fields: invalid cron field 'foo'$"),
    ],
)
def test_validate_cron_5field_rejects_bad_inputs(
    bad_cron: Any, msg: str
) -> None:
    with pytest.raises(RefreshGuardError, match=msg):
        validate_cron_5field("oil-fields", bad_cron)


@pytest.mark.parametrize(
    "bad_entries",
    [None, True, 1, 1.5, "x", [], {}],
)
def test_validate_refresh_schedules_rejects_non_mapping_entries(
    bad_entries: Any,
) -> None:
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: entries must be a non-empty mapping$",
    ):
        validate_refresh_schedules(bad_entries)


@pytest.mark.parametrize("bad_entry", [None, True, 1, "x", []])
def test_validate_refresh_schedules_rejects_non_mapping_entry(
    bad_entry: Any,
) -> None:
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: oil-fields: entry must be a mapping$",
    ):
        validate_refresh_schedules({"oil-fields": bad_entry})


@pytest.mark.parametrize("bad_ref", [None, True, 1, "x", []])
def test_validate_refresh_schedules_rejects_non_mapping_refresh(
    bad_ref: Any,
) -> None:
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: oil-fields: refresh must be a mapping$",
    ):
        validate_refresh_schedules({"oil-fields": {"refresh": bad_ref}})


@pytest.mark.parametrize("bad_val", [None, True, False, 0, -5, "50", [], {}])
def test_validate_refresh_schedules_rejects_bad_max_mb(bad_val: Any) -> None:
    entry = _valid_entry(max_mb=bad_val)
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: oil-fields: max_mb must be a positive number$",
    ):
        validate_refresh_schedules({"oil-fields": entry})


@pytest.mark.parametrize("bad_val", [None, True, False, 0, -1, "120", [], {}])
def test_validate_refresh_schedules_rejects_bad_max_s(bad_val: Any) -> None:
    entry = _valid_entry(max_s=bad_val)
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: oil-fields: max_s must be a positive number$",
    ):
        validate_refresh_schedules({"oil-fields": entry})


@pytest.mark.parametrize("bad_payload", [None, True, 1, 1.5, "x", []])
def test_validate_receipt_payload_rejects_non_dict(bad_payload: Any) -> None:
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt oil-fields: expected JSON object$",
    ):
        validate_receipt_payload("oil-fields", bad_payload)


@pytest.mark.parametrize(
    "missing_key",
    [
        "id",
        "before",
        "after",
        "outside",
        "repaired",
        "url",
        "as_of",
        "dataset_version",
        "extent_sha256",
    ],
)
def test_validate_receipt_payload_rejects_missing_key(missing_key: str) -> None:
    rec = _valid_receipt()
    rec.pop(missing_key)
    with pytest.raises(
        RefreshGuardError,
        match=rf"^REFRESH: receipt oil-fields: missing key '{missing_key}'$",
    ):
        validate_receipt_payload("oil-fields", rec)


def test_validate_receipt_payload_rejects_id_mismatch() -> None:
    rec = _valid_receipt()
    rec["id"] = "councils"
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt oil-fields: id mismatch 'councils'$",
    ):
        validate_receipt_payload("oil-fields", rec)


@pytest.mark.parametrize("field", ["before", "after", "outside", "repaired"])
@pytest.mark.parametrize("bad_val", [None, True, False, -1, 1.5, "10", [], {}])
def test_validate_receipt_payload_rejects_non_int_counts(
    field: str, bad_val: Any
) -> None:
    rec = _valid_receipt()
    rec[field] = bad_val
    with pytest.raises(
        RefreshGuardError,
        match=rf"^REFRESH: receipt oil-fields: {field} must be a non-negative integer$",
    ):
        validate_receipt_payload("oil-fields", rec)


def test_validate_receipt_payload_rejects_zero_after() -> None:
    rec = _valid_receipt()
    rec["after"] = 0
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt oil-fields: after must be > 0$",
    ):
        validate_receipt_payload("oil-fields", rec)


def test_validate_receipt_payload_rejects_nonzero_outside() -> None:
    rec = _valid_receipt()
    rec["outside"] = 2
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt oil-fields: outside=2 != 0$",
    ):
        validate_receipt_payload("oil-fields", rec)


def test_validate_receipt_payload_rejects_clip_keep_all_drop() -> None:
    rec = _valid_receipt("councils")
    rec["before"] = 32
    rec["after"] = 31
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt councils: clip kept 31 of 32 \(clip_keep_all\)$",
    ):
        validate_receipt_payload("councils", rec, clip_keep_all=True)


@pytest.mark.parametrize(
    "bad_url",
    [None, True, 1, "", "   ", [], {}],
)
def test_validate_receipt_payload_rejects_empty_or_non_str_url(
    bad_url: Any,
) -> None:
    rec = _valid_receipt()
    rec["url"] = bad_url
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt oil-fields: url must be a non-empty string$",
    ):
        validate_receipt_payload("oil-fields", rec)


@pytest.mark.parametrize(
    "leaked_url",
    [
        "https://example.test/wfs?service=WFS&token=supersecret123",
        "https://example.test/wfs?apikey=abc987&request=GetFeature",
        "https://example.test/wfs?password=hunter2",
    ],
)
def test_validate_receipt_payload_rejects_unredacted_secret_in_url(
    leaked_url: str,
) -> None:
    rec = _valid_receipt()
    rec["url"] = leaked_url
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt oil-fields: unredacted secret in url$",
    ):
        validate_receipt_payload("oil-fields", rec)


@pytest.mark.parametrize("bad_as_of", [None, True, 20261023, "2026-13-40", "not-a-date", []])
def test_validate_receipt_payload_rejects_bad_as_of(bad_as_of: Any) -> None:
    rec = _valid_receipt()
    rec["as_of"] = bad_as_of
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt oil-fields: bad as_of ",
    ):
        validate_receipt_payload("oil-fields", rec)


@pytest.mark.parametrize(
    "bad_dv",
    [
        None,
        True,
        123,
        "oil-fields@2026-10-23-UPPERCAS",
        "councils@2026-10-23-deadbeef",
        "oil-fields@2026-10-22-deadbeef",
    ],
)
def test_validate_receipt_payload_rejects_bad_dataset_version(
    bad_dv: Any,
) -> None:
    rec = _valid_receipt()
    rec["dataset_version"] = bad_dv
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt oil-fields: bad dataset_version ",
    ):
        validate_receipt_payload("oil-fields", rec)


@pytest.mark.parametrize("bad_sha", [None, True, 123, "short", "Z" * 64])
def test_validate_receipt_payload_rejects_bad_extent_sha256(
    bad_sha: Any,
) -> None:
    rec = _valid_receipt()
    rec["extent_sha256"] = bad_sha
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt oil-fields: bad extent_sha256$",
    ):
        validate_receipt_payload("oil-fields", rec)


def test_check_receipt_dir_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt dir not found: ",
    ):
        check_receipt_dir(missing, entries={"oil-fields": _valid_entry()})


def test_check_receipt_dir_empty_file_and_invalid_json_and_unknown_layer(
    tmp_path: Path,
) -> None:
    entries = {"oil-fields": _valid_entry("oil-fields")}
    p = tmp_path / "oil-fields.receipt.json"
    p.write_text("", encoding="utf-8")
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt oil-fields: empty file$",
    ):
        check_receipt_dir(tmp_path, entries=entries)

    p.write_text("{not-json", encoding="utf-8")
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt oil-fields: invalid JSON$",
    ):
        check_receipt_dir(tmp_path, entries=entries)

    p.unlink()
    unk = tmp_path / "mystery.json"
    unk.write_text(json.dumps(_valid_receipt("mystery")), encoding="utf-8")
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: receipt mystery\.json: unknown registry layer 'mystery'$",
    ):
        check_receipt_dir(tmp_path, entries=entries)


def test_check_receipt_dir_missing_required_layer(tmp_path: Path) -> None:
    entries = {
        "oil-fields": _valid_entry("oil-fields"),
        "councils": _valid_entry("councils"),
    }
    (tmp_path / "oil-fields.json").write_text(
        json.dumps(_valid_receipt("oil-fields")), encoding="utf-8"
    )
    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: missing required receipt for 'councils'$",
    ):
        check_receipt_dir(
            tmp_path, entries=entries, require_layers=["councils"]
        )


def test_run_weekly_refresh_orders_scotland_extent_first_and_skips_gated() -> None:
    entries = {
        "oil-fields": _valid_entry("oil-fields", tiles=True),
        "scotland-extent": _valid_entry(
            "scotland-extent", clip_keep_all=True, tiles=True
        ),
        "nmpi": _valid_entry("nmpi", gated_by="NMPI_LICENCE"),
    }
    calls: list[str] = []
    tiled: list[str] = []

    def fake_runner(lid: str) -> dict[str, Any]:
        calls.append(lid)
        rec = _valid_receipt(lid)
        if lid == "scotland-extent":
            rec["before"] = 1
            rec["after"] = 1
        return rec

    def fake_tiler(lid: str) -> dict[str, Any]:
        tiled.append(lid)
        return {"id": lid}

    summary = run_weekly_refresh(
        entries=entries, runner=fake_runner, tile_builder=fake_tiler
    )
    assert calls == ["scotland-extent", "oil-fields"]
    assert summary == {
        "refreshed": ["scotland-extent", "oil-fields"],
        "tiles_built": ["scotland-extent", "oil-fields"],
    }


def test_run_weekly_refresh_wraps_runner_and_tile_failures() -> None:
    entries = {"oil-fields": _valid_entry("oil-fields", tiles=True)}

    def bad_runner(lid: str) -> dict[str, Any]:
        raise RuntimeError(f"boom {lid}")

    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: oil-fields: ingest failed: boom oil-fields$",
    ):
        run_weekly_refresh(entries=entries, runner=bad_runner)

    def bad_tiler(lid: str) -> dict[str, Any]:
        raise RuntimeError(f"pmtiles {lid}")

    with pytest.raises(
        RefreshGuardError,
        match=r"^REFRESH: oil-fields: tile build failed: pmtiles oil-fields$",
    ):
        run_weekly_refresh(
            entries=entries,
            runner=lambda lid: _valid_receipt(lid),
            tile_builder=bad_tiler,
        )
