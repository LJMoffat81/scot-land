"""ARCH-2a-1 storage config tests S-1..S-12."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tiles.storage import StorageError, load_storage


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _raises(path: Path, msg: str, monkeypatch=None, **env) -> None:
    if monkeypatch is not None:
        for key, value in env.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
    with pytest.raises(StorageError, match=re.escape(msg) + "$"):
        load_storage(path)


def test_s1_missing_file(tmp_path):
    path = tmp_path / "missing.yaml"
    _raises(path, f"STORAGE: config missing: {path}")


def test_s2_empty_file(tmp_path):
    path = _write(tmp_path / "storage.yaml", "")
    _raises(path, f"STORAGE: config empty: {path}")


def test_s3_invalid_yaml(tmp_path):
    path = _write(tmp_path / "storage.yaml", "storage: [\n")
    _raises(path, f"STORAGE: config not YAML: {path}")


def test_s4_yaml_list(tmp_path):
    path = _write(tmp_path / "storage.yaml", "- local\n")
    _raises(path, "STORAGE: $: ['local'] is not of type 'object'")


def test_s5_storage_r2(tmp_path, monkeypatch):
    # TILES_DIR set so M9 (enum gains r2) yields DID NOT RAISE, not env failure.
    monkeypatch.setenv("TILES_DIR", str(tmp_path))
    path = _write(
        tmp_path / "storage.yaml",
        "storage: r2\nroot_env: TILES_DIR\nkeep_versions: 3\n",
    )
    _raises(path, "STORAGE: $.storage: 'r2' is not one of ['local']")


def test_s6_keep_versions_bool(tmp_path):
    path = _write(
        tmp_path / "storage.yaml",
        "storage: local\nroot_env: TILES_DIR\nkeep_versions: true\n",
    )
    _raises(path, "STORAGE: $.keep_versions: True is not of type 'integer'")


def test_s7_keep_versions_float(tmp_path):
    path = _write(
        tmp_path / "storage.yaml",
        "storage: local\nroot_env: TILES_DIR\nkeep_versions: 2.5\n",
    )
    _raises(path, "STORAGE: $.keep_versions: 2.5 is not of type 'integer'")


def test_s8_keep_versions_zero(tmp_path):
    path = _write(
        tmp_path / "storage.yaml",
        "storage: local\nroot_env: TILES_DIR\nkeep_versions: 0\n",
    )
    _raises(path, "STORAGE: $.keep_versions: 0 is less than the minimum of 1")


def test_s9_unknown_key(tmp_path):
    path = _write(
        tmp_path / "storage.yaml",
        "storage: local\nroot_env: TILES_DIR\nkeep_versions: 3\nbucket: x\n",
    )
    _raises(
        path,
        "STORAGE: $: Additional properties are not allowed "
        "('bucket' was unexpected)",
    )


def test_s10_env_unset(tmp_path, monkeypatch):
    path = _write(
        tmp_path / "storage.yaml",
        "storage: local\nroot_env: TILES_DIR\nkeep_versions: 3\n",
    )
    monkeypatch.delenv("TILES_DIR", raising=False)
    _raises(path, "STORAGE: TILES_DIR not set")


def test_s11_env_missing_path(tmp_path, monkeypatch):
    path = _write(
        tmp_path / "storage.yaml",
        "storage: local\nroot_env: TILES_DIR\nkeep_versions: 3\n",
    )
    missing = tmp_path / "no_such_dir"
    monkeypatch.setenv("TILES_DIR", str(missing))
    _raises(path, f"STORAGE: TILES_DIR not a directory: {missing}")


def test_s12_env_is_file(tmp_path, monkeypatch):
    path = _write(
        tmp_path / "storage.yaml",
        "storage: local\nroot_env: TILES_DIR\nkeep_versions: 3\n",
    )
    file_path = tmp_path / "not_a_dir"
    file_path.write_text("x", encoding="utf-8")
    monkeypatch.setenv("TILES_DIR", str(file_path))
    _raises(path, f"STORAGE: TILES_DIR not a directory: {file_path}")
