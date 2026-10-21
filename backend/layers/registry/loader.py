"""Load and validate YAML layer registry entries against schema.json."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import json
import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

REGISTRY_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = REGISTRY_DIR / "schema.json"

_CACHE: dict[str, "LayerEntry"] | None = None


class RegistryError(Exception):
    """Raised when a registry file fails schema or cross-reference checks."""


@dataclass(frozen=True)
class LayerEntry:
    """One validated registry row."""

    id: str
    raw: dict[str, Any]

    def __getattr__(self, name: str) -> Any:
        try:
            return self.raw[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


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


def _schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RegistryError(f"REGISTRY: {path.stem}: $: expected object")
    return data


def _validate_entry(
    entry_id: str, data: dict[str, Any], validator: Draft202012Validator
) -> None:
    if data.get("id") != entry_id:
        raise RegistryError(
            f"REGISTRY: {entry_id}: $.id: must equal file name {entry_id!r}"
        )
    # clip:none is only allowed with serve.mode raster — raise before schema so
    # the message names $.clip (not the if/then serve.mode const failure).
    if data.get("clip") == "none" and (data.get("serve") or {}).get("mode") != "raster":
        raise RegistryError(
            f"REGISTRY: {entry_id}: $.clip: 'none' is only allowed with serve.mode raster"
        )
    try:
        validator.validate(data)
    except ValidationError as exc:
        path = _format_path(list(exc.absolute_path))
        raise RegistryError(f"REGISTRY: {entry_id}: {path}: {exc.message}") from exc


def _check_lineage_refs(entries: dict[str, LayerEntry]) -> None:
    for entry_id, entry in entries.items():
        lineage = entry.raw.get("lineage") or {}
        for dep in lineage.get("derived_from") or []:
            if dep not in entries:
                raise RegistryError(
                    f"REGISTRY: {entry_id}: lineage.derived_from: unknown layer {dep}"
                )


def _check_lineage_cycles(entries: dict[str, LayerEntry]) -> None:
    graph = {
        eid: list((e.raw.get("lineage") or {}).get("derived_from") or [])
        for eid, e in entries.items()
    }

    def walk(node: str, stack: list[str]) -> None:
        if node in stack:
            cycle = stack[stack.index(node) :] + [node]
            raise RegistryError("REGISTRY: lineage cycle: " + " -> ".join(cycle))
        if node not in graph:
            return
        for nxt in graph[node]:
            walk(nxt, stack + [node])

    for start in graph:
        walk(start, [])


def load_registry(dir: Path | str | None = None) -> dict[str, LayerEntry]:
    """Validate every ``*.yaml`` in ``dir`` and return id → entry.

    Raises ``RegistryError`` with ``REGISTRY: …`` messages on failure.
    """
    root = Path(dir) if dir is not None else REGISTRY_DIR
    validator = _schema_validator()
    entries: dict[str, LayerEntry] = {}
    for path in sorted(root.glob("*.yaml")):
        entry_id = path.stem
        data = _load_yaml(path)
        _validate_entry(entry_id, data, validator)
        if entry_id in entries or any(e.id == data["id"] for e in entries.values()):
            raise RegistryError(f"REGISTRY: duplicate id {entry_id}")
        entries[entry_id] = LayerEntry(id=entry_id, raw=data)
    _check_lineage_refs(entries)
    _check_lineage_cycles(entries)
    return entries


def registry() -> dict[str, LayerEntry]:
    """Cached registry loaded once from the package directory."""
    global _CACHE
    if _CACHE is None:
        _CACHE = load_registry()
    return _CACHE


# Load at import so a bad committed registry fails at process start.
registry()
