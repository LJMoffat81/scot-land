"""Spatial Hub GeoServer authkey helpers.

Improvement Service Spatial Hub WFS endpoints require a personal ``authkey``
query parameter (anonymous requests return 403). Operators set
``SPATIALHUB_AUTHKEY`` in the gitignored ``.env``; ``docker-compose.home.yml``
passes it into the API container.

Never commit a real key — this repo is public. When the env var is missing or
blank, callers must degrade gracefully to ``not loaded yet`` and must not invent
features.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ENV_NAME = "SPATIALHUB_AUTHKEY"
NOT_LOADED_YET = "not loaded yet"


def authkey() -> str | None:
    """Return the trimmed Spatial Hub GeoServer authkey, or None if unset."""
    key = (os.getenv(ENV_NAME) or "").strip()
    return key or None


def is_configured() -> bool:
    """True when ``SPATIALHUB_AUTHKEY`` is present and non-blank."""
    return authkey() is not None


def not_loaded_message(layer_label: str) -> str:
    """Honest empty-layer note when the authkey (or data) is missing."""
    label = (layer_label or "Spatial Hub layer").strip() or "Spatial Hub layer"
    return f"{label} is {NOT_LOADED_YET}"


def wfs_auth_params() -> dict[str, str]:
    """Auth params for Spatial Hub WFS, or empty when the key is missing."""
    key = authkey()
    if not key:
        return {}
    return {"authkey": key}


def with_wfs_auth(url: str, *, extra_params: dict[str, Any] | None = None) -> str:
    """Merge ``authkey`` (when configured) and optional params into a WFS URL.

    When the key is missing, returns ``url`` with only ``extra_params`` applied
    — callers that require auth must check :func:`is_configured` first and
    degrade to :func:`not_loaded_message`.
    """
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if extra_params:
        for key, value in extra_params.items():
            if value is None:
                continue
            query[str(key)] = str(value)
    query.update(wfs_auth_params())
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
