"""Rebuild cost tables for residual DRC — single place for professional parameters."""

from __future__ import annotations


def _rebuild_rate(rebuild: dict, key: str) -> float:
    if key not in rebuild:
        raise KeyError(key)
    return float(rebuild[key])


def blended_rebuild_per_m2(config: dict) -> float:
    rebuild = config.get("valuer_roll", {}).get("rebuild", {})
    mix = config.get("valuer_roll", {}).get("property_mix") or {}
    house = _rebuild_rate(rebuild, "house_gbp_per_m2")
    flat = _rebuild_rate(rebuild, "flat_gbp_per_m2")
    house_share = float(mix.get("house_share", 0.75))
    flat_share = float(mix.get("flat_share", 0.25))
    total = house_share + flat_share
    if total <= 0:
        return house
    return (house * house_share + flat * flat_share) / total


def region_factor(council_code: str, config: dict) -> float:
    rebuild = config.get("valuer_roll", {}).get("rebuild", {})
    factors = rebuild.get("region_factors") or {}
    return float(factors.get(council_code, factors.get("default", 1.0)))
