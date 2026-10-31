"""ARCH-6: One weekly refresh runner + offline receipt/cron guard for registry layers.

Usage::

    python -m etl.refresh_registry --check
    python -m etl.refresh_registry --run

``ARCH-6-SCHEDULES`` (per-layer supercronic schedules) and the guard dashboard
are parked per Project Lead (23 Oct 01:28 BST).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

from etl.run_layer import LayerPipelineError, run_layer
from layers.registry.loader import REGISTRY_DIR, LayerEntry, RegistryError, load_registry
from tiles.build import TilesError, build_tileset, is_tiled

REPO_ROOT = Path(__file__).resolve().parents[2]
RECEIPT_DIR = REPO_ROOT / "data" / "processed" / "layers"

_SECRET_URL_RE = re.compile(
    r"(?i)(?:token|key|secret|password|apikey|authkey)=(?!\*{3})(?:[^&\s]+)"
)
_REQ_RECEIPT_KEYS = (
    "id",
    "before",
    "after",
    "outside",
    "repaired",
    "url",
    "as_of",
    "dataset_version",
    "extent_sha256",
)


class RefreshGuardError(Exception):
    """Raised when a registry refresh schedule or receipt check fails (``REFRESH:`` prefix)."""


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_cron_5field(layer_id: str, cron: Any) -> str:
    """Validate a standard 5-field cron expression ``min hour dom mon dow``."""
    if not isinstance(cron, str) or not cron.strip():
        raise RefreshGuardError(
            f"REFRESH: {layer_id}: cron must be a 5-field string"
        )
    fields = cron.strip().split()
    if len(fields) != 5:
        raise RefreshGuardError(
            f"REFRESH: {layer_id}: cron must have 5 fields, got {len(fields)}"
        )
    ranges = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
    for field, (lo, hi) in zip(fields, ranges):
        for part in field.split(","):
            base, sep, step = part.partition("/")
            if sep:
                if not step.isdigit() or int(step) <= 0:
                    raise RefreshGuardError(
                        f"REFRESH: {layer_id}: invalid cron field {part!r}"
                    )
            if base == "*":
                continue
            if "-" in base:
                a_s, _, b_s = base.partition("-")
                if not (a_s.isdigit() and b_s.isdigit()):
                    raise RefreshGuardError(
                        f"REFRESH: {layer_id}: invalid cron field {part!r}"
                    )
                a, b = int(a_s), int(b_s)
                if a < lo or b > hi or a > b:
                    raise RefreshGuardError(
                        f"REFRESH: {layer_id}: invalid cron field {part!r}"
                    )
                continue
            if not base.isdigit():
                raise RefreshGuardError(
                    f"REFRESH: {layer_id}: invalid cron field {part!r}"
                )
            val = int(base)
            if val < lo or val > hi:
                raise RefreshGuardError(
                    f"REFRESH: {layer_id}: invalid cron field {part!r}"
                )
    return cron.strip()


def validate_refresh_schedules(entries: Any) -> list[str]:
    """Validate ``refresh`` blocks on all registry entries and return ordered layer ids."""
    if not isinstance(entries, dict) or len(entries) == 0:
        raise RefreshGuardError(
            "REFRESH: entries must be a non-empty mapping"
        )
    ordered: list[str] = []
    for layer_id in sorted(entries.keys()):
        entry = entries[layer_id]
        raw = entry.raw if isinstance(entry, LayerEntry) else entry
        if not isinstance(raw, dict):
            raise RefreshGuardError(
                f"REFRESH: {layer_id}: entry must be a mapping"
            )
        ref = raw.get("refresh")
        if not isinstance(ref, dict):
            raise RefreshGuardError(
                f"REFRESH: {layer_id}: refresh must be a mapping"
            )
        validate_cron_5field(layer_id, ref.get("cron"))
        max_mb = ref.get("max_mb")
        if not _is_num(max_mb) or float(max_mb) <= 0:
            raise RefreshGuardError(
                f"REFRESH: {layer_id}: max_mb must be a positive number"
            )
        max_s = ref.get("max_s")
        if not _is_num(max_s) or float(max_s) <= 0:
            raise RefreshGuardError(
                f"REFRESH: {layer_id}: max_s must be a positive number"
            )
        if layer_id != "scotland-extent":
            ordered.append(layer_id)
    return (["scotland-extent"] if "scotland-extent" in entries else []) + ordered


def validate_receipt_payload(
    layer_id: str,
    payload: Any,
    *,
    clip_keep_all: bool = False,
) -> dict[str, Any]:
    """Validate one layer ingest receipt dict (offline guard)."""
    if not isinstance(payload, dict):
        raise RefreshGuardError(
            f"REFRESH: receipt {layer_id}: expected JSON object"
        )
    for key in _REQ_RECEIPT_KEYS:
        if key not in payload:
            raise RefreshGuardError(
                f"REFRESH: receipt {layer_id}: missing key {key!r}"
            )
    if payload["id"] != layer_id:
        raise RefreshGuardError(
            f"REFRESH: receipt {layer_id}: id mismatch {payload['id']!r}"
        )
    for k in ("before", "after", "outside", "repaired"):
        if not _is_int(payload[k]) or payload[k] < 0:
            raise RefreshGuardError(
                f"REFRESH: receipt {layer_id}: {k} must be a non-negative integer"
            )
    if payload["after"] == 0:
        raise RefreshGuardError(
            f"REFRESH: receipt {layer_id}: after must be > 0"
        )
    if payload["outside"] != 0:
        raise RefreshGuardError(
            f"REFRESH: receipt {layer_id}: outside={payload['outside']} != 0"
        )
    if clip_keep_all and payload["after"] != payload["before"]:
        raise RefreshGuardError(
            f"REFRESH: receipt {layer_id}: clip kept {payload['after']} of "
            f"{payload['before']} (clip_keep_all)"
        )
    url = payload["url"]
    if not isinstance(url, str) or not url.strip():
        raise RefreshGuardError(
            f"REFRESH: receipt {layer_id}: url must be a non-empty string"
        )
    if _SECRET_URL_RE.search(url):
        raise RefreshGuardError(
            f"REFRESH: receipt {layer_id}: unredacted secret in url"
        )
    as_of = payload["as_of"]
    if not isinstance(as_of, str):
        raise RefreshGuardError(
            f"REFRESH: receipt {layer_id}: bad as_of {as_of!r}"
        )
    try:
        date.fromisoformat(as_of)
    except ValueError as exc:
        raise RefreshGuardError(
            f"REFRESH: receipt {layer_id}: bad as_of {as_of!r}"
        ) from exc
    dv = payload["dataset_version"]
    if (
        not isinstance(dv, str)
        or not re.fullmatch(
            rf"{re.escape(layer_id)}@{re.escape(as_of)}-[0-9a-f]{{8}}", dv
        )
    ):
        raise RefreshGuardError(
            f"REFRESH: receipt {layer_id}: bad dataset_version {dv!r}"
        )
    ext_sha = payload["extent_sha256"]
    if not isinstance(ext_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", ext_sha):
        raise RefreshGuardError(
            f"REFRESH: receipt {layer_id}: bad extent_sha256"
        )
    return payload


def check_receipt_dir(
    receipt_dir: Path | str = RECEIPT_DIR,
    *,
    entries: dict[str, Any] | None = None,
    require_layers: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Validate every receipt JSON file in ``receipt_dir`` against ``entries``."""
    rdir = Path(receipt_dir)
    if not rdir.is_dir():
        raise RefreshGuardError(
            f"REFRESH: receipt dir not found: {rdir}"
        )
    reg = entries if entries is not None else load_registry(REGISTRY_DIR)
    validate_refresh_schedules(reg)
    files = sorted(rdir.glob("*.json"))
    if not files:
        raise RefreshGuardError(
            f"REFRESH: no receipts found in {rdir}"
        )
    checked: dict[str, dict[str, Any]] = {}
    for path in files:
        stem = path.name
        if stem.endswith(".receipt.json"):
            lid = stem[: -len(".receipt.json")]
        else:
            lid = path.stem
        if lid not in reg:
            raise RefreshGuardError(
                f"REFRESH: receipt {path.name}: unknown registry layer {lid!r}"
            )
        raw_text = path.read_text(encoding="utf-8")
        if not raw_text.strip():
            raise RefreshGuardError(
                f"REFRESH: receipt {lid}: empty file"
            )
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RefreshGuardError(
                f"REFRESH: receipt {lid}: invalid JSON"
            ) from exc
        entry = reg[lid]
        raw_entry = entry.raw if isinstance(entry, LayerEntry) else entry
        keep_all = bool(raw_entry.get("clip_keep_all"))
        checked[lid] = validate_receipt_payload(
            lid, data, clip_keep_all=keep_all
        )
    for req_id in require_layers or []:
        if req_id not in checked:
            raise RefreshGuardError(
                f"REFRESH: missing required receipt for {req_id!r}"
            )
    return checked


def run_weekly_refresh(
    *,
    entries: dict[str, Any] | None = None,
    runner: Callable[[str], dict[str, Any]] = run_layer,
    tile_builder: Callable[[str], dict[str, Any]] = build_tileset,
) -> dict[str, Any]:
    """Run ``run_layer`` (and ``build_tileset`` where ``serve.mode`` is pmtiles) in order."""
    reg = entries if entries is not None else load_registry(REGISTRY_DIR)
    ordered = validate_refresh_schedules(reg)
    refreshed: list[str] = []
    tiles_built: list[str] = []
    for lid in ordered:
        entry = reg[lid]
        raw_entry = entry.raw if isinstance(entry, LayerEntry) else entry
        if raw_entry.get("gated_by"):
            continue
        try:
            receipt = runner(lid)
        except (LayerPipelineError, RegistryError, RuntimeError) as exc:
            raise RefreshGuardError(
                f"REFRESH: {lid}: ingest failed: {exc}"
            ) from exc
        validate_receipt_payload(
            lid,
            receipt,
            clip_keep_all=bool(raw_entry.get("clip_keep_all")),
        )
        refreshed.append(lid)
        if is_tiled(raw_entry):
            try:
                tile_builder(lid)
            except (TilesError, RuntimeError) as exc:
                raise RefreshGuardError(
                    f"REFRESH: {lid}: tile build failed: {exc}"
                ) from exc
            tiles_built.append(lid)
    return {"refreshed": refreshed, "tiles_built": tiles_built}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Offline check of registry refresh blocks and committed receipts",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run weekly refresh across all ungated registry layers",
    )
    parser.add_argument(
        "--receipt-dir",
        type=Path,
        default=RECEIPT_DIR,
        help="Directory containing receipt JSON files",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.check == args.run:
        print(
            "REFRESH: specify exactly one of --check or --run",
            file=sys.stderr,
        )
        return 2
    try:
        if args.check:
            checked = check_receipt_dir(
                args.receipt_dir,
                require_layers=["settlements-2022"],
            )
            print(
                json.dumps(
                    {"ok": True, "checked": sorted(checked.keys())},
                    sort_keys=True,
                )
            )
            return 0
        summary = run_weekly_refresh()
        print(json.dumps({"ok": True, **summary}, sort_keys=True))
        return 0
    except (RefreshGuardError, RegistryError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
