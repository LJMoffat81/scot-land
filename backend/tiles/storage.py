"""Local tile storage config and publish helpers (ARCH-2a)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

STORAGE_YAML = Path(__file__).resolve().parents[1] / "layers" / "storage.yaml"
STORAGE_SCHEMA = Path(__file__).resolve().parents[1] / "layers" / "storage.schema.json"


class StorageError(Exception):
    """Raised when tile storage config or env is invalid (``STORAGE:`` prefix)."""


def _format_path(path: list[Any] | None) -> str:
    if not path:
        return "$"
    parts: list[str] = ["$"]
    for item in path:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            parts.append(f".{item}")
    return "".join(parts)


@dataclass(frozen=True)
class StorageConfig:
    storage: str
    root_env: str
    keep_versions: int
    root: Path


class LocalStorage:
    """Filesystem tile store under ``TILES_DIR`` (or configured ``root_env``)."""

    def __init__(self, config: StorageConfig):
        self.config = config

    def path_for(self, layer_id: str, version: str) -> Path:
        return self.config.root / f"{layer_id}.{version}.pmtiles"

    def publish(self, tmp: Path, layer_id: str, version: str) -> Path:
        dest = self.path_for(layer_id, version)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, dest)
        return dest

    def prune(self, layer_id: str, keep: int) -> None:
        root = self.config.root
        pattern = f"{layer_id}."
        files = sorted(
            (
                p
                for p in root.glob(f"{layer_id}.*.pmtiles")
                if p.name.startswith(pattern) and p.suffix == ".pmtiles"
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for stale in files[keep:]:
            stale.unlink(missing_ok=True)


def load_storage(path: Path | str | None = None) -> StorageConfig:
    """Load and validate ``storage.yaml``; resolve ``root_env`` to a directory."""
    cfg_path = Path(path) if path is not None else STORAGE_YAML
    if not cfg_path.is_file():
        raise StorageError(f"STORAGE: config missing: {cfg_path}")
    raw_text = cfg_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise StorageError(f"STORAGE: config empty: {cfg_path}")
    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise StorageError(f"STORAGE: config not YAML: {cfg_path}") from exc
    if not isinstance(data, dict):
        # Match jsonschema-style messaging used by S-4.
        raise StorageError(f"STORAGE: $: {data!r} is not of type 'object'")

    schema = json.loads(STORAGE_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    try:
        validator.validate(data)
    except ValidationError as exc:
        path_s = _format_path(list(exc.absolute_path))
        raise StorageError(f"STORAGE: {path_s}: {exc.message}") from exc

    root_env = str(data["root_env"])
    root_val = os.environ.get(root_env)
    if root_val is None or root_val == "":
        raise StorageError(f"STORAGE: {root_env} not set")
    root = Path(root_val)
    if not root.is_dir():
        raise StorageError(f"STORAGE: {root_env} not a directory: {root}")

    return StorageConfig(
        storage=str(data["storage"]),
        root_env=root_env,
        keep_versions=int(data["keep_versions"]),
        root=root,
    )
