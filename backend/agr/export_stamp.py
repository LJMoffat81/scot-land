"""Version stamp for saved exports. The stamp is metadata; it is not a figure."""

from __future__ import annotations

import json
from typing import Any

from agr.config import load_config
from agr.layers import engine_stamp


def current_stamp() -> dict[str, Any]:
    """Same object `/health` returns when the request did not override config."""
    return engine_stamp(load_config())


def stamp_json(stamp: dict[str, Any]) -> str:
    return json.dumps(stamp, sort_keys=True, separators=(",", ":"))


def stamp_comment(stamp: dict[str, Any]) -> str:
    """One leading line. Existing CSV columns stay as they are."""
    return f"# stamp: {stamp_json(stamp)}"


def with_stamp(payload: dict[str, Any], stamp: dict[str, Any] | None = None) -> dict[str, Any]:
    body = dict(payload)
    body["stamp"] = current_stamp() if stamp is None else stamp
    return body
