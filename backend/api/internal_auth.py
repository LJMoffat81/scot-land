"""Authentication for /internal developer routes.

Never fall open:
  * No INTERNAL_API_TOKEN configured → 403 internal_locked (even if the flag is on).
  * Missing / malformed Authorization → 401.
  * Wrong token → 401.
  * Valid Bearer token or X-API-Key matching the secret (constant-time) → allow.

ENABLE_INTERNAL_ENDPOINTS still controls whether the router is mounted (404 when off).
Auth is required whenever the router is mounted.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException

ENV_TOKEN = "INTERNAL_API_TOKEN"
HEADERS = ("authorization", "x-api-key")


def configured_token() -> str | None:
    """Return the configured secret, or None when unset/blank (locked)."""
    value = os.getenv(ENV_TOKEN, "").strip()
    return value or None


def _extract_presented(authorization: str | None, x_api_key: str | None) -> str | None:
    if x_api_key is not None and x_api_key.strip():
        return x_api_key.strip()
    if authorization is None:
        return None
    raw = authorization.strip()
    if not raw:
        return None
    if raw.lower().startswith("bearer "):
        return raw[7:].strip() or None
    return None


def require_internal_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """FastAPI dependency: lock or authenticate every /internal request."""
    secret = configured_token()
    if secret is None:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "internal_locked",
                "message": f"{ENV_TOKEN} is not configured; /internal endpoints are locked",
            },
        )
    presented = _extract_presented(authorization, x_api_key)
    if presented is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "Authorization: Bearer <token> or X-API-Key required",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(presented, secret):
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Invalid token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
