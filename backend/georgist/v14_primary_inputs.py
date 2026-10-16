"""v1.4 primary estimator inputs: depreciated replacement cost and land share.

Rebuild cost comes from the merged surface-cost stack. Depreciation is
``straight_line_v14`` set explicitly. No price is read here.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Mapping, Sequence

from georgist import surface_costs as sc
from georgist import surface_rent as sr
from georgist import surface_v14 as v14

logger = logging.getLogger(__name__)

REQUIRED_METHOD = "straight_line_v14"
# Information only. These rates never replace the central 0.35%/yr path.
# The 1.33% and 0.86% lines keep the same rate, age cap and depreciation cap.
# The label states that the 55% cap is off and the 68-year age cap still applies.
NO_55_CAP_NOTE = "no 55% cap; 68-yr age cap applied"
SENSITIVITY_STRAIGHT_RATES = (
    ("rate_0.5pct_straight_line", 0.005, 68.0, 0.55, None),
    ("rate_0.7pct_straight_line", 0.007, 68.0, 0.55, None),
    ("rate_1.33pct", 0.0133, 68.0, 1.0, NO_55_CAP_NOTE),
    ("rate_0.86pct", 0.0086, 68.0, 1.0, NO_55_CAP_NOTE),
    ("band_end_0pct", 0.0, 68.0, 0.55, None),
    ("band_end_1.0pct", 0.010, 68.0, 0.55, None),
)
# Exhibit 2 six unmerged bands. Rates are only those stated in the frozen plan.
# Bands without one stated rate stay unmerged. They are not a gate.
EXHIBIT2_BANDS = (
    ("all_years", "unmerged"),
    ("lt5", "0.010"),
    ("6_20", "unmerged"),
    ("21_50", "0.006"),
    ("51_70", "0.005"),
    ("gt70", "0.003-0.004"),
)


class DepreciationMethodError(ValueError):
    """Depreciation method was missing or was not straight_line_v14."""


def assert_straight_line_v14(depreciation: Mapping) -> dict:
    """Return a copy whose method is straight_line_v14, or fail.

    The fidelity code falls back to compounding when no method is set, so the
    method has to be present on the mapping that is passed in.
    """
    method = depreciation.get("method")
    if method is None or str(method) != REQUIRED_METHOD:
        raise DepreciationMethodError(
            f"depreciation.method must be {REQUIRED_METHOD}, got {method!r}"
        )
    out = dict(depreciation)
    out["method"] = REQUIRED_METHOD
    return out


def v14_depreciation(cfg: Mapping | None = None) -> dict:
    """Loaded v1.4 depreciation with the method checked."""
    return assert_straight_line_v14(v14.v14_depreciation(cfg))


def remaining_factor_at_age(
    age_years: float,
    depreciation: Mapping,
    *,
    valuation_year: int = 2025,
) -> float:
    """``surface_rent.remaining_factor`` at an explicit age, method asserted."""
    dep = assert_straight_line_v14(depreciation)
    band = "pipeline_age"
    midpoints = dict(dep.get("age_band_midpoint_year") or {})
    midpoints[band] = float(valuation_year) - float(age_years)
    dep["age_band_midpoint_year"] = midpoints
    return sr.remaining_factor(band, valuation_year, dep)


def age_mix_remaining(
    age_shares: Mapping[str, float] | None,
    depreciation: Mapping,
    valuation_year: int,
    cfg: Mapping | None = None,
) -> float:
    """Age-mix-weighted remaining factor. No age mix uses the frozen 0.762 factor."""
    dep = assert_straight_line_v14(depreciation)
    if not age_shares:
        frozen = float(v14.no_age_mix_remaining(cfg))
        via_rent = sr.no_age_mix_remaining_factor(dep)
        if via_rent != frozen:
            raise DepreciationMethodError(
                "no-age-mix factor does not match surface_v14.no_age_mix_remaining"
            )
        return frozen
    total = sum(float(share) for share in age_shares.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError("age shares must sum to 1")
    return sum(
        float(share) * sr.remaining_factor(str(band), valuation_year, dep)
        for band, share in age_shares.items()
    )


def depreciated_replacement_cost(
    rebuild_cost: float,
    age_shares: Mapping[str, float] | None,
    depreciation: Mapping,
    valuation_year: int,
    cfg: Mapping | None = None,
) -> float:
    """DRC = rebuild cost times the age-mix remaining factor. No new factor."""
    remaining = age_mix_remaining(age_shares, depreciation, valuation_year, cfg)
    return float(rebuild_cost) * remaining


def zone_drc_v14(**kwargs) -> sr.RebuildResult:
    """One zone through ``surface_costs.zone_cost_rebuilds`` with v1.4 depreciation.

    The passed config's v1.3 depreciation block is not used. The v1.4 block is
    copied in with its method asserted.
    """
    cfg = kwargs.get("cfg")
    if cfg is None:
        raise DepreciationMethodError("zone cost rebuild needs a config")
    dep = v14_depreciation(cfg)
    cfg_v14 = dict(cfg)
    cfg_v14["depreciation"] = dep
    kwargs = dict(kwargs)
    kwargs["cfg"] = cfg_v14
    rebuilds = sc.zone_cost_rebuilds(**kwargs)
    central = rebuilds["central"]
    if central.rebuild_new_gbp:
        expected = central.rebuild_new_gbp * central.remaining_factor
        if central.drc_gbp != expected:
            raise DepreciationMethodError("DRC is not rebuild cost times remaining factor")
    return central


def _remaining_line(
    label: str,
    rate: float,
    age_cap: float,
    max_dep: float,
    base: Mapping,
    note: str | None = None,
) -> str:
    dep = dict(base)
    dep["method"] = REQUIRED_METHOD
    dep["rate_building"] = rate
    dep["max_depreciation"] = max_dep
    dep["age_cap_years"] = age_cap
    remaining = remaining_factor_at_age(age_cap, dep)
    note_part = f" note={note}" if note else ""
    return (
        f"label={label}{note_part} rate={rate} remaining_at_cap={remaining:.6f} "
        "gates=false"
    )


def sensitivity_lines(cfg: Mapping | None = None) -> list[str]:
    """Information-only depreciation lines. None of these gate."""
    loaded = cfg if cfg is not None else sr.load_config()
    base = v14_depreciation(loaded)
    lines = [
        _remaining_line(label, rate, cap, max_dep, base, note)
        for label, rate, cap, max_dep, note in SENSITIVITY_STRAIGHT_RATES
    ]
    v13 = dict(loaded["depreciation"])
    v13_rate = float(v13["rate_building"]["central"])
    v13["method"] = "compounding_v13"
    v13_remaining = sr.remaining_factor("before 1919", 2025, v13)
    lines.append(
        "label=v13_0.276pct_compounding "
        f"rate={v13_rate} remaining_at_cap={v13_remaining:.6f} gates=false"
    )
    for band, rate in EXHIBIT2_BANDS:
        lines.append(
            f"label=exhibit2_six_band band={band} rate={rate} gates=false"
        )
    for line in lines:
        if "gates=false" not in line:
            raise DepreciationMethodError("sensitivity line would gate")
    return lines


def land_share(price: float, drc: float) -> float:
    """Share = residual land value / price. A negative residual contributes 0."""
    if price <= 0:
        raise ValueError("price must be positive")
    residual = sr.residual_land_value(price, drc)
    return float(residual.land_value) / float(price)


def _zone_key(code: str) -> str:
    return str(code).strip().upper()


def _unique_scored(scored_zones: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for code in scored_zones:
        key = _zone_key(code)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def dropped_scored_counts(
    scored_zones: Sequence[str],
    price_by_dz2011: Mapping[str, float],
    drc_by_dz2011: Mapping[str, float],
) -> dict[str, int]:
    """Count scored zones omitted for a missing price, a missing cost, or both.

    A zone missing both inputs is counted in ``no_price`` and in ``no_cost``.
    """
    no_price = 0
    no_cost = 0
    for key in _unique_scored(scored_zones):
        if key not in price_by_dz2011:
            no_price += 1
        if key not in drc_by_dz2011:
            no_cost += 1
    return {"no_price": no_price, "no_cost": no_cost}


def cost_availability_for_scored(
    scored_zones: Sequence[str],
    price_by_dz2011: Mapping[str, float],
    drc_by_dz2011: Mapping[str, float],
) -> dict[str, dict[str, float]]:
    """``{dz2011: {price, drc}}`` for scored zones that have both inputs.

    A zone with no crosswalked price or no DRC is omitted. Nothing is imputed.
    Those omitted zones stay in the check 1d denominator via
    ``check_1d_shares_for_scored``.
    """
    out: dict[str, dict[str, float]] = {}
    for key in _unique_scored(scored_zones):
        if key not in price_by_dz2011 or key not in drc_by_dz2011:
            continue
        out[key] = {
            "price": float(price_by_dz2011[key]),
            "drc": float(drc_by_dz2011[key]),
        }
    return out


def check_1d_shares_for_scored(
    scored_zones: Sequence[str],
    price_by_dz2011: Mapping[str, float],
    drc_by_dz2011: Mapping[str, float],
    share_by_dz2011: Mapping[str, float],
) -> list[float]:
    """Land shares for check 1d. Dropped zones stay in the denominator.

    A scored zone with no price or no depreciated cost is not removed. It
    enters the denominator as 0, which also puts it in the numerator.
    """
    shares: list[float] = []
    for key in _unique_scored(scored_zones):
        if key not in price_by_dz2011 or key not in drc_by_dz2011:
            shares.append(0.0)
            continue
        shares.append(float(share_by_dz2011[key]))
    return shares


def primary_estimates(costs: Mapping[str, Mapping[str, float]]) -> dict[str, float]:
    """``{dz2011: land_share}`` from ``residual_land_value``."""
    return {
        str(code): land_share(float(row["price"]), float(row["drc"]))
        for code, row in costs.items()
    }


def write_json(path: Path, payload: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_information_files(out_dir: Path, cfg: Mapping | None = None) -> None:
    """Sensitivities and the median label. No prices."""
    out_dir.mkdir(parents=True, exist_ok=True)
    text = "\n".join(sensitivity_lines(cfg)) + "\n"
    (out_dir / "depreciation_sensitivities.txt").write_text(text, encoding="utf-8")
    (out_dir / "median_sensitivity.txt").write_text(
        "not_crosswalkable\n",
        encoding="utf-8",
    )
    logger.info("wrote information lines; no prices")


def write_scored_inputs(
    out_dir: Path,
    costs: Mapping[str, Mapping[str, float]],
    estimates: Mapping[str, float],
) -> None:
    """Gitignored scored-run files. Callers must not print these payloads."""
    write_json(out_dir / "cost_availability.json", costs)
    write_json(out_dir / "primary_estimates.json", estimates)
