"""Engine view of Valuation's surface settings, READ from data/config/surface.yaml (never copied).

Keys (Valuation fd03c4b, rules v0.6/v0.7):
  surface_rent.depreciation.life_years.{low,central,high}
  surface_rent.depreciation.remaining_min.{low,central,high}
  surface_rent.depreciation.band_combination.rule
"""

from __future__ import annotations

from typing import Any

from georgist import surface_rent as sr

BAND = ("low", "central", "high")


class SettingsError(ValueError):
    pass


def depreciation_settings(config: dict | None = None) -> dict[str, Any]:
    dep = (config if config is not None else sr.load_config()).get("depreciation") or {}
    out: dict[str, Any] = {}
    for key in ("life_years", "remaining_min"):
        band = dep.get(key)
        if not isinstance(band, dict) or any(b not in band or band[b] is None for b in BAND):
            raise SettingsError(f"surface_rent.depreciation.{key} must have {BAND} in surface.yaml")
        out[key] = {b: band[b] for b in BAND}
    rule = (dep.get("band_combination") or {}).get("rule")
    if not rule:
        raise SettingsError("surface_rent.depreciation.band_combination.rule missing in surface.yaml")
    out["band_combination"] = {"rule": rule}
    return out
