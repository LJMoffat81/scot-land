"""Engine view of Valuation's surface settings, READ from data/config/surface.yaml (never copied).

Keys (Valuation / Georgist yield calibration v3 / v1.3 methods):
  surface_rent.depreciation.method
  surface_rent.depreciation.rate_building.{low,central,high}
  surface_rent.depreciation.age_cap_years
  surface_rent.depreciation.building_share_sb
  surface_rent.depreciation.life_years.{low,central,high}   # yield path only
  surface_rent.depreciation.band_combination.rule
  surface_rent.yield.central (+ band / v3 flags / result_hash)
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
    method = dep.get("method") or "compounding_v13"
    out["method"] = method
    if "rate_building" in dep:
        band = dep["rate_building"]
        if not isinstance(band, dict) or any(b not in band or band[b] is None for b in BAND):
            raise SettingsError(f"surface_rent.depreciation.rate_building must have {BAND} in surface.yaml")
        out["rate_building"] = {b: band[b] for b in BAND}
    if "age_cap_years" in dep:
        out["age_cap_years"] = int(dep["age_cap_years"])
    if "building_share_sb" in dep:
        out["building_share_sb"] = float(dep["building_share_sb"])
    if "property_rate_central" in dep:
        out["property_rate_central"] = float(dep["property_rate_central"])
    # life_years kept for yield.building_depreciation = from_life_years
    for key in ("life_years", "remaining_min"):
        band = dep.get(key)
        if isinstance(band, dict) and all(b in band and band[b] is not None for b in BAND):
            out[key] = {b: band[b] for b in BAND}
    if "rate_building" not in out and "life_years" not in out:
        raise SettingsError(
            "surface_rent.depreciation must have rate_building (v1.3) or life_years in surface.yaml"
        )
    rule = (dep.get("band_combination") or {}).get("rule")
    if not rule:
        raise SettingsError("surface_rent.depreciation.band_combination.rule missing in surface.yaml")
    out["band_combination"] = {"rule": rule}
    return out


# Georgist yield calibration v3 flag keys (pass-through when present in surface.yaml).
YIELD_V3_FLAG_KEYS: tuple[str, ...] = (
    "central_at_cap",
    "band_clipped_outer",
    "bed_mapping_sensitive",
)

YIELD_SOURCE = "data/config/surface.yaml yield.central"


def _band_from_yield_cfg(ycfg: Mapping[str, Any]) -> list[float] | None:
    """Accept ``band: {low, high}`` or legacy ``land_yield_band: [low, high]``."""
    nested = ycfg.get("band")
    if isinstance(nested, Mapping) and "low" in nested and "high" in nested:
        lo, hi = float(nested["low"]), float(nested["high"])
        if lo > hi:
            raise SettingsError("surface_rent.yield.band must have low <= high")
        return [lo, hi]
    raw_band = ycfg.get("land_yield_band")
    if isinstance(raw_band, (list, tuple)) and len(raw_band) == 2:
        lo, hi = float(raw_band[0]), float(raw_band[1])
        if lo > hi:
            raise SettingsError("surface_rent.yield.land_yield_band must be [low, high]")
        return [lo, hi]
    return None


def yield_placeholder(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Configured land yield from shared surface.yaml — always tagged placeholder until calibrated.

    Tax scenarios and other consumers must call this (or ``configured_land_yield``) rather than
    hardcoding a rate. Valuation owns r−g / central. Optional Georgist calibration v3
    metadata is passed through only when present in shared config — never invented here:

    * ``central`` / ``land_yield`` (alias) / ``land_yield_band`` / ``result_hash``
    * flags ``central_at_cap``, ``band_clipped_outer``, ``bed_mapping_sensitive``
    * optional ``components`` {r, p, g} and legacy ``clipped_at_cap``
    """
    cfg = dict(config) if config is not None else sr.load_config()
    ycfg = cfg.get("yield") or {}
    if not isinstance(ycfg, Mapping):
        raise SettingsError("surface_rent.yield must be a mapping in surface.yaml")
    land = sr.configured_land_yield(ycfg)
    out: dict[str, Any] = {
        "status": "placeholder",
        "central": land,
        "land_yield": land,  # alias for callers that still read land_yield
        "source": YIELD_SOURCE,
        "owner": "Valuation",
        "note": (
            f"PLACEHOLDER: configured land yield central {land:.2%} (= r − g / r+p−g) from "
            "shared surface.yaml (Valuation owns calibration; Georgist sign-off metadata "
            "passed through when present). Consumers defer to this config; do not hardcode "
            "a yield rate in tax-scenario code. Bare land_yield 5% key removed."
        ),
    }
    band = _band_from_yield_cfg(ycfg)
    if band is not None:
        out["land_yield_band"] = band
        out["band"] = {"low": band[0], "central": land, "high": band[1]}
    if ycfg.get("result_hash"):
        out["result_hash"] = str(ycfg["result_hash"])
    if ycfg.get("calibration_version") is not None:
        out["calibration_version"] = ycfg["calibration_version"]
    # Georgist v3 flags (+ legacy clipped_at_cap) — pass-through only.
    flags_present: list[str] = []
    for key in YIELD_V3_FLAG_KEYS:
        if key in ycfg:
            out[key] = bool(ycfg[key])
            if out[key]:
                flags_present.append(key)
    if "clipped_at_cap" in ycfg:
        out["clipped_at_cap"] = bool(ycfg["clipped_at_cap"])
    nested_band = ycfg.get("band")
    if isinstance(nested_band, Mapping) and nested_band.get("high_clipped_at_cap") is not None:
        out["high_clipped_at_cap"] = bool(nested_band["high_clipped_at_cap"])
    # Optional explicit flags list from config (union with boolean keys above).
    raw_flags = ycfg.get("flags")
    if isinstance(raw_flags, (list, tuple)):
        for f in raw_flags:
            name = str(f)
            if name not in flags_present:
                flags_present.append(name)
            if name in YIELD_V3_FLAG_KEYS and name not in out:
                out[name] = True
    if flags_present:
        out["flags"] = flags_present
    components = ycfg.get("components")
    if isinstance(components, Mapping) and components:
        out["components"] = {str(k): float(v) for k, v in components.items()}
    return out
