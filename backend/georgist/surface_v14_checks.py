"""v1.4 checks for both estimators.

Checks 1, 1d and 1e already live in ``surface_v14.score_estimators``. This
module adds the remaining frozen marks and reuses ``surface_v13`` and
``surface_holdout``. Publication uses ``surface_v14.apply_no_switch_publication``.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from georgist import surface_holdout as ho
from georgist import surface_v13 as v13
from georgist import surface_v14 as v14

GATING_MARKS = {
    "1": "unweighted zone median in 10% to 40%",
    "1a": "class 1 has the highest median land per home",
    "1b": "top national price decile share is above the bottom decile share",
    "1d": "at most 10% of zones at 0% or 100%",
    "3": "detached-only plot comparison at least 80%",
    "4": "two-route gap within 25% national and 40% per UR6",
    "6": "one ordered range per zone",
}
INFORMATION_ONLY = (
    "1c",
    "1e",
    "2",
    "3-all",
    "3-dz22",
    "5",
    "7",
    "agreement",
    "gis_plot_median_ratio",
)


def _median(values: Sequence[float]) -> float:
    ordered = sorted(float(value) for value in values)
    count = len(ordered)
    mid = count // 2
    if count % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def _share(zone: Mapping) -> float:
    if zone.get("unavailable") or zone.get("model_failure"):
        return 0.0
    return float(zone["share"])


def _land_per_home(zone: Mapping) -> float:
    if zone.get("unavailable") or zone.get("model_failure"):
        return 0.0
    return float(zone["land_per_home"])


def check_1a(zones: Sequence[Mapping]) -> dict:
    """Class 1 median land per home is strictly above every other class. A tie fails."""
    by_class: dict[int, list[float]] = {}
    for zone in zones:
        by_class.setdefault(int(zone["ur6"]), []).append(_land_per_home(zone))
    medians = {klass: _median(values) for klass, values in by_class.items() if values}
    if 1 not in medians:
        return {"check": "1a", "pass": False, "status": "fail", "reason": "class_1_missing", "medians": medians}
    ok = all(medians[1] > other for klass, other in medians.items() if klass != 1)
    return {"check": "1a", "pass": ok, "status": "pass" if ok else "fail", "medians": medians}


def check_1b(zones: Sequence[Mapping]) -> dict:
    """Top national price decile has a higher median share than the bottom decile."""
    ordered = sorted(zones, key=lambda zone: float(zone["price"]))
    width = max(1, len(ordered) // 10)
    bottom = [_share(zone) for zone in ordered[:width]]
    top = [_share(zone) for zone in ordered[-width:]]
    top_median = _median(top)
    bottom_median = _median(bottom)
    ok = top_median > bottom_median
    return {
        "check": "1b",
        "pass": ok,
        "status": "pass" if ok else "fail",
        "top_median": top_median,
        "bottom_median": bottom_median,
        "decile_n": width,
    }


def check_1c(shares: Sequence[float]) -> dict:
    """Range [0, 1] is information only and does not gate."""
    inside = all(0.0 <= float(share) <= 1.0 for share in shares)
    return {"check": "1c", "role": "information_only", "pass": None, "within_range": inside}


def check_6_zone_range(zones: Sequence[Mapping]) -> dict:
    """Integrity: one finite low <= central <= high range per DZ2022 zone.

    The key is dz2022 only. A row with no dz2022 raises. There is no DZ2011 fallback.
    """
    seen: set[str] = set()
    failures: list[str] = []
    for zone in zones:
        if "dz2022" not in zone or not str(zone.get("dz2022") or "").strip():
            raise ValueError("check 6 requires dz2022")
        code = str(zone["dz2022"]).strip()
        if code in seen:
            failures.append(code)
            continue
        seen.add(code)
        try:
            low = float(zone["share_low"])
            central = float(zone["share_central"])
            high = float(zone["share_high"])
        except (KeyError, TypeError, ValueError):
            failures.append(code)
            continue
        finite = low == low and central == central and high == high
        if not finite or not (low <= central <= high):
            failures.append(code)
    ok = not failures and len(zones) > 0
    return {
        "check": "6",
        "pass": ok,
        "status": "pass" if ok else "fail",
        "n": len(seen),
        "failures": failures,
    }


_PLOT_RADII = (20, 30, 40)


def _pass_at_ints(raw: Mapping) -> dict[int, bool]:
    """JSON round-trips radii as strings. A non-integer key raises."""
    normalised: dict[int, bool] = {}
    for key, value in raw.items():
        if isinstance(key, bool) or isinstance(key, float):
            raise ValueError(f"pass_at key is not an integer radius: {key!r}")
        if isinstance(key, int):
            radius = key
        else:
            text = str(key).strip()
            if not text.isdigit():
                raise ValueError(f"pass_at key is not an integer radius: {key!r}")
            radius = int(text)
        if radius not in _PLOT_RADII:
            raise ValueError(f"pass_at key is not an integer radius: {key!r}")
        normalised[radius] = bool(value)
    return normalised


def _plot(zones: Sequence[Mapping], field: str) -> dict:
    rows = []
    for zone in zones:
        raw = zone.get(field) or {30: False, 20: False, 40: False}
        rows.append({"pass_at": _pass_at_ints(raw)})
    result = v13.check_3_plot_comparison(rows, min_pass_share=0.80)
    measured = [bool(zone.get("measured_detached_pass")) for zone in zones if "measured_detached_pass" in zone]
    if measured:
        measured_share = sum(1 for item in measured if item) / len(measured)
        measured_pass = measured_share >= 0.80
        if measured_pass != bool(result.get("pass")):
            result = dict(result)
            result["fragile"] = True
            result["fragile_measured"] = True
    return result


def _class_pairs(zones: Sequence[Mapping], field: str) -> dict[int, list[float]]:
    grouped: dict[int, list[float]] = {}
    for zone in zones:
        value = 0.0 if field == "residual_land" and (zone.get("unavailable") or zone.get("model_failure")) else float(zone[field])
        grouped.setdefault(int(zone["ur6"]), []).append(value)
    return grouped


def check_4(zones: Sequence[Mapping]) -> dict:
    """Two-route gap. Unavailable and model-failure zones contribute land value 0."""
    residual = [
        0.0 if zone.get("unavailable") or zone.get("model_failure") else float(zone["residual_land"])
        for zone in zones
    ]
    capitalised = [float(zone["capitalised_land"]) for zone in zones]
    return v14.check_4_from_routes(
        residual,
        capitalised,
        class_residual=_class_pairs(zones, "residual_land"),
        class_capitalised=_class_pairs(zones, "capitalised_land"),
    )


def _information_gradient(zones: Sequence[Mapping]) -> dict:
    by_class: dict[int, list[float]] = {}
    for zone in zones:
        by_class.setdefault(int(zone["ur6"]), []).append(_share(zone))
    result = ho.gradient_check(
        by_class,
        expected_order=((1, 2), (2, 3), (3, 4), (3, 5), (4, 6), (5, 6)),
    )
    return {"check": "2", "role": "information_only", "pass": None, "gradient": result}


def _information_negative(zones: Sequence[Mapping]) -> dict:
    rows = [
        {
            "ur6_class": int(zone["ur6"]),
            "negative_residual": bool(zone.get("unavailable") or zone.get("model_failure")),
        }
        for zone in zones
    ]
    result = ho.negative_by_class_check(rows, high_demand_ur6=(1, 2), max_share_high_demand=0.10)
    return {"check": "5", "role": "information_only", "pass": None, "negative_by_class": result}


def _information_plausibility(zones: Sequence[Mapping]) -> dict:
    central = [
        {
            "land_value": _land_per_home(zone),
            "mean_price": float(zone["price"]),
            "dwellings": int(zone.get("dwellings", 1)),
            "ur6_class": int(zone["ur6"]),
            "negative_residual": bool(zone.get("unavailable") or zone.get("model_failure")),
        }
        for zone in zones
    ]
    result = ho.plausibility_checks(
        {"central": central},
        plausible_range=(0.10, 0.40),
        tolerance=0.0,
        high_demand_ur6=(1, 2),
        max_share_high_demand=0.10,
    )
    return {"check": "7", "role": "information_only", "pass": None, "plausibility": result}


def _bland_altman(left: Sequence[float], right: Sequence[float]) -> dict:
    diff = [float(a) - float(b) for a, b in zip(left, right)]
    mean = sum(diff) / len(diff)
    variance = sum((item - mean) ** 2 for item in diff) / len(diff)
    sd = variance ** 0.5
    return {"mean_difference": mean, "lower": mean - 1.96 * sd, "upper": mean + 1.96 * sd}


def _matched_shares(
    primary: Sequence[Mapping],
    secondary: Sequence[Mapping],
    ur6: int | None = None,
) -> tuple[list[float], list[float]]:
    by_secondary = {str(zone["zone"]): zone for zone in secondary}
    left: list[float] = []
    right: list[float] = []
    for zone in primary:
        if ur6 is not None and int(zone["ur6"]) != ur6:
            continue
        other = by_secondary.get(str(zone["zone"]))
        if other is None:
            continue
        if ur6 is not None and int(other["ur6"]) != ur6:
            continue
        left.append(_share(zone))
        right.append(_share(other))
    return left, right


def _agreement_stats(left: Sequence[float], right: Sequence[float]) -> dict:
    if not left or len(left) != len(right):
        return {"spearman": None, "median_difference": None, "bland_altman": None, "n": 0}
    diff = [float(a) - float(b) for a, b in zip(left, right)]
    return {
        "spearman": ho.spearman(left, right),
        "median_difference": _median(diff),
        "bland_altman": _bland_altman(left, right),
        "n": len(diff),
    }


def agreement(primary: Sequence[Mapping], secondary: Sequence[Mapping]) -> dict:
    """Spearman, median difference and Bland-Altman, nationally and for UR6 classes 1–6."""
    national = _agreement_stats(*_matched_shares(primary, secondary))
    by_ur6 = {
        str(klass): _agreement_stats(*_matched_shares(primary, secondary, ur6=klass))
        for klass in range(1, 7)
    }
    return {
        "check": "agreement",
        "role": "information_only",
        "pass": None,
        "spearman": national["spearman"],
        "median_difference": national["median_difference"],
        "bland_altman": national["bland_altman"],
        "national": national,
        "by_ur6": by_ur6,
    }


def gis_plot_median_ratio(zones: Sequence[Mapping]) -> dict:
    """Detached-plot median over both pooled and zone-median house-plot denominators.

    The pooled denominator is the mean house plot in the UR6 class. The zone-median
    denominator is the median house plot in that class. Information only.
    """
    by_class: dict[int, list[tuple[float, float]]] = {}
    for zone in zones:
        if "detached_plot_m2" not in zone or "house_plot_m2" not in zone:
            continue
        by_class.setdefault(int(zone["ur6"]), []).append(
            (float(zone["detached_plot_m2"]), float(zone["house_plot_m2"]))
        )
    ratios = {}
    for klass, pairs in by_class.items():
        detached = _median([item[0] for item in pairs])
        house_values = [item[1] for item in pairs]
        zone_median = _median(house_values)
        pooled = sum(house_values) / len(house_values)
        ratios[str(klass)] = {
            "numerator_detached_median": detached,
            "pooled_denominator": pooled,
            "zone_median_denominator": zone_median,
            "ratio_pooled_denominator": None if pooled == 0 else detached / pooled,
            "ratio_zone_median_denominator": None if zone_median == 0 else detached / zone_median,
        }
    return {"check": "gis_plot_median_ratio", "role": "information_only", "pass": None, "ratio_by_ur6": ratios}


# Market value of new-build dwellings and permitted density are not named inputs.
HBU_NOT_RUN = "NOT_RUN: frozen HBU value/density inputs not specified; deferred to v1.5"
HBU_DEVELOPER_PROFIT = 0.15


def hbu_cost_side(mea_rebuild: float, on_costs: float) -> float:
    """MEA rebuild times on-costs, no depreciation, plus 15% of base build cost.

    Cost side only. No residual is produced and the line does not gate.
    """
    base = float(mea_rebuild)
    return base * float(on_costs) + HBU_DEVELOPER_PROFIT * base


def hbu_line(zones: Sequence[Mapping]) -> list[dict]:
    """Highest-and-best-use line for HLA zones only. Never part of checks 1–7."""
    return [
        {
            "zone": str(zone["zone"]),
            "hla": True,
            "in_checks_1_to_7": False,
            "gates": False,
            "status": HBU_NOT_RUN,
        }
        for zone in zones
        if zone.get("hla")
    ]


def _check_1d(zones: Sequence[Mapping]) -> dict:
    """Denominator is every scoring zone. Uninformative cells stay out of the numerator."""
    shares = [_share(zone) for zone in zones]
    eps = 1e-12
    informative = [zone for zone in zones if zone.get("count_in_1d", True)]
    info_shares = [_share(zone) for zone in informative]
    n_at_0 = sum(1 for share in info_shares if float(share) <= eps)
    n_at_100 = sum(1 for share in info_shares if float(share) >= 1.0 - eps)
    n = len(shares)
    excluded = [str(zone.get("zone")) for zone in zones if not zone.get("count_in_1d", True)]
    if n == 0:
        return {
            "check": "1d",
            "pass": None,
            "status": "pending",
            "n": 0,
            "n_at_0": 0,
            "n_at_100": 0,
            "share_at_bound": None,
            "max_share": 0.10,
            "info_1e_zones_at_0": 0,
            "info_1e_pct_at_0": None,
            "uninformative_excluded_from_numerator": excluded,
            "numerator_n": 0,
        }
    at_bound = n_at_0 + n_at_100
    share = at_bound / n
    ok = share <= 0.10
    return {
        "check": "1d",
        "pass": ok,
        "status": "pass" if ok else "fail",
        "n": n,
        "n_at_0": n_at_0,
        "n_at_100": n_at_100,
        "share_at_bound": share,
        "max_share": 0.10,
        "info_1e_zones_at_0": n_at_0,
        "info_1e_pct_at_0": n_at_0 / n,
        "uninformative_excluded_from_numerator": excluded,
        "numerator_n": len(info_shares),
    }


def score_estimator(zones: Sequence[Mapping]) -> dict:
    """One estimator against the frozen gating marks and the information checks."""
    shares = [_share(zone) for zone in zones]
    check_1 = v13.check_1_median_land_share(shares, band=(0.10, 0.40))
    check_1d = _check_1d(zones)
    gating = {
        "1": check_1,
        "1a": check_1a(zones),
        "1b": check_1b(zones),
        "1d": check_1d,
        "3": _plot(zones, "pass_at"),
        "4": check_4(zones),
        "6": check_6_zone_range(zones),
    }
    passed = all(bool(item.get("pass")) for item in gating.values())
    information = {
        "1c": check_1c(shares),
        "1e": {
            "check": "1e",
            "role": "information_only",
            "pass": None,
            "zones_at_0": check_1d.get("info_1e_zones_at_0"),
        },
        "2": _information_gradient(zones),
        "3-all": {**_plot(zones, "pass_at_all_homes"), "role": "information_only", "pass": None},
        "3-dz22": {**_plot(zones, "pass_at_dz22"), "role": "information_only", "pass": None},
        "5": _information_negative(zones),
        "7": _information_plausibility(zones),
        "gis_plot_median_ratio": gis_plot_median_ratio(zones),
    }
    return {
        "gating": gating,
        "information": information,
        "gating_pass": passed,
        "hbu_excluded_from_checks": True,
    }


def score_both(primary: Sequence[Mapping], secondary: Sequence[Mapping]) -> dict:
    """Both estimators, the agreement test, the HBU line, and the no-switch rule."""
    primary_score = score_estimator(primary)
    secondary_score = score_estimator(secondary)
    publication = v14.apply_no_switch_publication(
        primary_gating_pass=bool(primary_score["gating_pass"]),
        secondary_gating_pass=bool(secondary_score["gating_pass"]),
    )
    return {
        "primary": primary_score,
        "secondary": secondary_score,
        "agreement": agreement(primary, secondary),
        "hbu": hbu_line(primary) + hbu_line(secondary),
        "hbu_status": HBU_NOT_RUN,
        "hbu_gates": False,
        "publication": publication,
        "checks_include_hbu": False,
    }
