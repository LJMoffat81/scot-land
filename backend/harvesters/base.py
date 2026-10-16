"""Shared harvester helpers for LAYERS-ADD-1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_ROOT = REPO_ROOT / "data" / "external"

# Substrings that must never appear in manual_drop harvester source.
MANUAL_DROP_FORBIDDEN = (
    "spatialhub.scot",
    "authkey",
    "/login",
    "accept",
    "terms",
)


@dataclass(frozen=True)
class HarvesterResult:
    layer_id: str
    ok: bool
    skipped: bool
    reason: str
    rows: int = 0


def external_dir(layer_id: str) -> Path:
    return EXTERNAL_ROOT / layer_id


def load_manual_drop(layer_id: str) -> HarvesterResult:
    """Read a local extract only. No network. Skip when absent."""
    root = external_dir(layer_id)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return HarvesterResult(
            layer_id=layer_id,
            ok=True,
            skipped=True,
            reason="extract absent — skip Improvement Service layer",
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return HarvesterResult(
            layer_id=layer_id,
            ok=False,
            skipped=False,
            reason=f"manifest unreadable: {exc}",
        )
    files = manifest.get("files") or []
    return HarvesterResult(
        layer_id=layer_id,
        ok=True,
        skipped=False,
        reason="manifest ok",
        rows=len(files),
    )


def run_harvester(layer_id: str, *, acquisition: str) -> HarvesterResult:
    if acquisition == "manual_drop":
        return load_manual_drop(layer_id)
    # Auto harvesters are invoked by dedicated modules; absent data → skip.
    return HarvesterResult(
        layer_id=layer_id,
        ok=True,
        skipped=True,
        reason="auto harvest not run in this process",
    )


def assert_no_currency_fields(properties: dict[str, Any]) -> None:
    banned = ("£", "gbp", "value", "rent")
    for key in properties:
        lower = key.lower()
        if any(token in lower for token in banned):
            raise ValueError(f"currency-like property forbidden: {key}")


def filter_tile_properties(
    layer_id: str, properties: dict[str, Any], allowlist: frozenset[str]
) -> dict[str, Any]:
    assert_no_currency_fields(properties)
    return {k: v for k, v in properties.items() if k in allowlist}
