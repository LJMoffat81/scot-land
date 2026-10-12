"""Engine view of Valuation's surface settings, READ from data/config/surface.yaml (never copied).

Keys (Valuation fd03c4b, rules v0.6/v0.7):
  surface_rent.depreciation.life_years.{low,central,high}
  surface_rent.depreciation.remaining_min.{low,central,high}
  surface_rent.depreciation.band_combination.rule
  surface_rent.yield.land_yield (+ optional land_yield_band)
"""

from __future__ import annotations

from typing import Any, Mapping

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


def yield_placeholder(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Configured land yield from shared surface.yaml — always tagged placeholder until calibrated.

    Tax scenarios and other consumers must call this (or ``configured_land_yield``) rather than
    hardcoding a rate. Valuation owns r−g / land_yield; optional ``land_yield_band`` is passed
    through when present in config (no invented band here).
    """
    cfg = dict(config) if config is not None else sr.load_config()
    ycfg = cfg.get("yield") or {}
    if not isinstance(ycfg, Mapping):
        raise SettingsError("surface_rent.yield must be a mapping in surface.yaml")
    land = sr.configured_land_yield(ycfg)
    out: dict[str, Any] = {
        "status": "placeholder",
        "land_yield": land,
        "source": "data/config/surface.yaml yield.land_yield",
        "owner": "Valuation",
        "note": (
            f"Configured land yield {land:.2%} (= r − g) is a PLACEHOLDER from shared "
            "surface.yaml (Valuation owns r−g and calibration). Consumers defer to this "
            "config; do not hardcode a yield rate in tax-scenario code."
        ),
    }
    # Optional band when Valuation publishes it (e.g. provisional [0.035, 0.045]); never invent.
    raw_band = ycfg.get("land_yield_band")
    if isinstance(raw_band, (list, tuple)) and len(raw_band) == 2:
        lo, hi = float(raw_band[0]), float(raw_band[1])
        if lo > hi:
            raise SettingsError("surface_rent.yield.land_yield_band must be [low, high]")
        out["land_yield_band"] = [lo, hi]
    return out
