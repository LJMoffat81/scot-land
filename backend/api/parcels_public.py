"""PARCELS_PUBLIC gate for cadastral parcel routes.

Default off (absent / anything other than true). Do not mount or unmount
routers from main.py — depend on this from the cadastral router module.
"""

from __future__ import annotations

import os

from fastapi import HTTPException

ENV_PARCELS_PUBLIC = "PARCELS_PUBLIC"


def parcels_public() -> bool:
    """True only when PARCELS_PUBLIC=true (case-insensitive). Default false."""
    return os.getenv(ENV_PARCELS_PUBLIC, "").strip().lower() == "true"


def require_parcels_public() -> None:
    """FastAPI dependency: 404 parcel routes unless the public flag is on."""
    if not parcels_public():
        raise HTTPException(status_code=404, detail="Not Found")
