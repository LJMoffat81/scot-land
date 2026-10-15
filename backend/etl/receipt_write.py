"""Non-fatal ingest receipt / stamp writes.

`/app/data` is often mounted read-only in home/canary compose. Receipt JSON
(e.g. ``builtup_mask.ingest.json``, HLA ``*.ingest.json``) must never abort
a successful PostGIS load — try the preferred path, then a writable fallback.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def receipt_fallback_dirs() -> list[Path]:
    """Writable dirs for receipts when DATA_DIR / preferred path is read-only."""
    dirs: list[Path] = []
    env = (os.getenv("INGEST_RECEIPT_DIR") or "").strip()
    if env:
        dirs.append(Path(env).expanduser())
    tmp = Path(os.getenv("TMPDIR") or os.getenv("TEMP") or "/tmp")
    dirs.append(tmp / "scot-land-ingest")
    return dirs


def write_receipt(
    preferred: Path,
    payload: dict[str, Any],
    *,
    fallback_name: str | None = None,
) -> Path | None:
    """Write receipt JSON; return the path written, or None if every path failed.

    Never raises for OSError / PermissionError — logs a warning instead.
    """
    name = fallback_name or preferred.name
    body = json.dumps(payload, indent=2) + "\n"
    candidates: list[Path] = [preferred]
    for folder in receipt_fallback_dirs():
        candidates.append(folder / name)

    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.parent.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
            if path != preferred:
                logger.warning(
                    "Receipt preferred path unwritable; wrote fallback %s",
                    path,
                )
            return path
        except OSError as exc:
            logger.warning("Receipt write failed at %s: %s", path, exc)
    logger.warning(
        "Skipping receipt write for %s (no writable path)",
        preferred.name,
    )
    return None
