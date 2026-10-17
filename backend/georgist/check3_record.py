"""Shared check-3 plot-passes validator.

One reader for the 2023 NOT_RUN record and for a passes file. The entry
point supplies ``year``. The record's own year is never the authority.
"""

from __future__ import annotations

import json
from pathlib import Path

from georgist.surface_v14_checks import AM1_REASON

_FIELDS = ("reason", "status", "year")


class Check3RecordError(ValueError):
    """A check-3 plot-passes file failed a closed refusal."""


def not_run_record() -> dict:
    """The 2023 NOT_RUN record. The reason is the AM-1 constant."""
    return {"reason": AM1_REASON, "status": "NOT_RUN", "year": 2023}


def not_run_record_text() -> str:
    """UTF-8 text of the record, with a trailing newline."""
    return json.dumps(not_run_record(), sort_keys=True, indent=2) + "\n"


def _refuse(step: str, message: str) -> Check3RecordError:
    return Check3RecordError(f"{step}: REFUSED: check3_plot_passes{message}")


def validate_check3_record(payload: bytes | bytearray | Path, *, year: object, step: str) -> str:
    """Return ``not_run`` or ``passes``. Rules run in the fixed order.

    ``payload`` is raw file bytes or a path. Only ``JSONDecodeError`` and
    ``UnicodeDecodeError`` become the invalid-JSON refusal.
    """
    raw = payload.read_bytes() if isinstance(payload, Path) else bytes(payload)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _refuse(step, ": expected JSON object, got invalid JSON") from exc
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _refuse(step, ": expected JSON object, got invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise _refuse(step, f": expected JSON object, got {type(parsed).__name__}")
    if "status" not in parsed:
        return "passes"
    status = parsed["status"]
    if status != "NOT_RUN":
        raise _refuse(step, f" status: expected 'NOT_RUN', got {status!r}")
    if "passes" in parsed:
        raise _refuse(step, ": expected no passes with NOT_RUN, got passes")
    if set(parsed) != set(_FIELDS):
        raise _refuse(
            step,
            f" fields: expected ['reason', 'status', 'year'], got {sorted(parsed)!r}",
        )
    if parsed["reason"] != AM1_REASON:
        raise _refuse(step, f" reason: expected {AM1_REASON!r}, got {parsed['reason']!r}")
    record_year = parsed["year"]
    if not (type(record_year) is int and record_year == 2023):
        raise _refuse(step, f" year: expected 2023, got {record_year!r}")
    if year != 2023:
        raise _refuse(step, ": expected passes, got NOT_RUN record (AM-1 is 2023 only)")
    return "not_run"
