"""SHARE-FIX — ingest receipt writes are non-fatal when /app/data is read-only."""

from __future__ import annotations

import json
from pathlib import Path

from etl.ingest_builtup_mask import write_stamp
from etl.ingest_hla_sites import write_local_stamp
from etl.receipt_write import write_receipt


def test_write_receipt_preferred_path(tmp_path: Path):
    preferred = tmp_path / "builtup_mask.ingest.json"
    out = write_receipt(preferred, {"layer": "map_builtup_mask", "ok": True})
    assert out == preferred
    payload = json.loads(preferred.read_text(encoding="utf-8"))
    assert payload["layer"] == "map_builtup_mask"


def test_write_receipt_falls_back_when_preferred_readonly(
    tmp_path: Path, monkeypatch
):
    preferred = tmp_path / "ro" / "builtup_mask.ingest.json"
    preferred.parent.mkdir()
    fallback_root = tmp_path / "fallback"
    monkeypatch.setenv("INGEST_RECEIPT_DIR", str(fallback_root))

    real_write = Path.write_text

    def selective(self: Path, data, encoding=None, errors=None, newline=None):
        if self == preferred:
            raise PermissionError("Read-only file system")
        return real_write(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", selective)

    out = write_receipt(
        preferred,
        {"layer": "map_builtup_mask", "ok": True},
        fallback_name="builtup_mask.ingest.json",
    )
    assert out is not None
    assert out.parent == fallback_root
    assert json.loads(out.read_text(encoding="utf-8"))["ok"] is True


def test_write_receipt_returns_none_when_all_paths_fail(
    tmp_path: Path, monkeypatch
):
    preferred = tmp_path / "nope.ingest.json"
    monkeypatch.setenv("INGEST_RECEIPT_DIR", str(tmp_path / "also-ro"))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp-ro"))

    def always_fail(self: Path, *args, **kwargs):
        raise PermissionError("Read-only file system")

    monkeypatch.setattr(Path, "write_text", always_fail)

    out = write_receipt(preferred, {"layer": "x"})
    assert out is None


def test_builtup_mask_write_stamp_uses_fallback(tmp_path: Path, monkeypatch):
    preferred = tmp_path / "ro" / "builtup_mask.ingest.json"
    preferred.parent.mkdir()
    fallback = tmp_path / "fallback"
    monkeypatch.setenv("INGEST_RECEIPT_DIR", str(fallback))

    real_write = Path.write_text

    def selective(self: Path, data, encoding=None, errors=None, newline=None):
        if self.parent == preferred.parent:
            raise PermissionError("Read-only file system")
        return real_write(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", selective)
    out = write_stamp(preferred, mask_parts=3, dz_rows=10)
    assert out is not None
    assert out.parent == fallback
    assert json.loads(out.read_text(encoding="utf-8"))["map_builtup_mask_parts"] == 3


def test_hla_write_local_stamp_uses_fallback(tmp_path: Path, monkeypatch):
    input_path = tmp_path / "ro" / "hla.geojson"
    input_path.parent.mkdir()
    input_path.write_text("{}", encoding="utf-8")
    fallback = tmp_path / "fallback"
    monkeypatch.setenv("INGEST_RECEIPT_DIR", str(fallback))

    stamp_name = input_path.with_suffix(input_path.suffix + ".ingest.json").name
    real_write = Path.write_text

    def selective(self: Path, data, encoding=None, errors=None, newline=None):
        if self.parent == input_path.parent and self.name.endswith(".ingest.json"):
            raise PermissionError("Read-only file system")
        return real_write(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", selective)
    out = write_local_stamp(input_path, count=4, vintage="2026-01-01")
    assert out is not None
    assert out.parent == fallback
    assert out.name == stamp_name
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["layer"] == "hla"
    assert payload["row_count"] == 4
