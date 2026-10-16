"""LAYER_*_ENABLED env gates for LAYERS-ADD-1 (default OFF).

Flags are read from the environment only. Production must leave them unset
or false. Do not hard-code True defaults.
"""

from __future__ import annotations

import os
from typing import Final

# Exact gated set after LICENCE-ADDENDUM-1a (overrides frozen ADD-1 L4).
FLAG_LDP = "LAYER_LDP_ENABLED"
FLAG_HLS = "LAYER_HLS_ENABLED"
FLAG_SEPA_FRM = "LAYER_SEPA_FRM_MAPS_ENABLED"

# Optional: keep existing SEPA flood-extent overlay off unless explicitly on.
FLAG_SEPA_FLOOD_EXTENT = "LAYER_SEPA_FLOOD_EXTENT_ENABLED"

# Data Zone shares from the medium-likelihood zip. Off unless explicitly on.
FLAG_SEPA_FLOOD_DZ = "LAYER_SEPA_FLOOD_DZ_ENABLED"

GATED_FLAG_NAMES: Final[frozenset[str]] = frozenset(
    {
        FLAG_LDP,
        FLAG_HLS,
        FLAG_SEPA_FRM,
    }
)


def flag_enabled(flag_name: str | None) -> bool:
    """True only when the named env var is the string ``true`` (case-insensitive)."""
    if not flag_name:
        return False
    return os.getenv(flag_name, "").strip().lower() == "true"


def layer_ldp_enabled() -> bool:
    return flag_enabled(FLAG_LDP)


def layer_hls_enabled() -> bool:
    return flag_enabled(FLAG_HLS)


def layer_sepa_frm_enabled() -> bool:
    """Always treated as non-public; flag cannot make prohibited layers public."""
    return flag_enabled(FLAG_SEPA_FRM)


def layer_sepa_flood_extent_enabled() -> bool:
    """Existing SEPA Flood Maps extent paint — default OFF (kickoff: SEPA flood off)."""
    return flag_enabled(FLAG_SEPA_FLOOD_EXTENT)


def layer_sepa_flood_dz_enabled() -> bool:
    """Data Zone flood-share loader and route — default OFF."""
    return flag_enabled(FLAG_SEPA_FLOOD_DZ)


def derive_public(
    licence_status: str,
    flag_name: str | None,
    *,
    flag_on: bool | None = None,
    internal_only: bool = False,
) -> bool:
    """public = licence in {ogl, confirmed, open_other} and not internal_only and flag allows.

    ``prohibited`` and ``unconfirmed`` are never public. ``internal_only`` is
    never public, whatever the status or flag. When ``flag_name`` is set, the
    flag must be ON. ``sepa_frm_maps`` stays non-public even if its flag is
    forced on (licence_status=prohibited).
    """
    if internal_only:
        return False
    if licence_status == "prohibited":
        return False
    if licence_status not in {"ogl", "confirmed", "open_other"}:
        return False
    if flag_name is None:
        return True
    if flag_on is None:
        flag_on = flag_enabled(flag_name)
    return bool(flag_on)
