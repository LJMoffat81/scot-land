"""Holdout validation harness for surface land value (skeleton).

Land value is not observed, so the harness scores the implied price
P_hat = L_hat + DRC against held-out RoS prices (spec section 6).
Designs: H1 stratified zone holdout, H2 suppression mimic, H3 IZ block,
H4 temporal, H5 leave-one-BRMA-out (yield). The model is pluggable:
`fit_predict(train_rows, test_rows) -> list[(pred, low, high)]`.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass
from typing import Iterable, Callable, Mapping, Sequence

TARGETS = {
    "median_ratio": (0.95, 1.05),
    "cod_max_urban": 15.0,
    "cod_max_rural": 20.0,
    "prd": (0.98, 1.03),
    "prb_abs_max": 0.05,
    "coverage_80": (0.75, 0.85),
}


from georgist import surface_rent as _sr  # noqa: E402

ZERO = _sr.ZERO_DWELLINGS_FALLBACK


@dataclass(frozen=True)
class Split:
    design: str
    train: list[str]
    test: list[str]
    seed: int


def stratified_zone_holdout(
    zones: Mapping[str, tuple], *, frac: float, seed: int, eligible: Callable[[str], bool] = lambda z: True,
    exclude: Iterable[str] = ZERO,
) -> Split:
    """H1: hold out `frac` of eligible zones within each stratum (e.g. (ur6, council)).
    Zero-dwelling zones (`exclude`) are in neither train nor test (rules v0.7)."""
    rng = random.Random(seed)
    zones = _sr.sample_for("holdout", dict(zones), exclude)
    strata: dict[tuple, list[str]] = {}
    for z, key in sorted(zones.items()):
        if eligible(z):
            strata.setdefault(key, []).append(z)
    test: list[str] = []
    for key in sorted(strata):
        members = strata[key]
        k = int(round(len(members) * frac))
        test += rng.sample(members, k) if k else []
    test_set = set(test)
    train = [z for z in sorted(zones) if z not in test_set]
    return Split("H1_zone_stratified", train, sorted(test), seed)


def suppression_mimic(sales_n: Mapping[str, int], *, lo: int = 5, hi: int = 9, seed: int = 0,
                      exclude: Iterable[str] = ZERO) -> Split:
    """H2: zones with lo <= n <= hi are scored as if suppressed. Zero-dwelling zones excluded."""
    sales_n = _sr.sample_for("holdout", dict(sales_n), exclude)
    test = sorted(z for z, n in sales_n.items() if lo <= n <= hi)
    train = sorted(z for z in sales_n if z not in set(test))
    return Split("H2_suppression_mimic", train, test, seed)


def block_holdout(parent: Mapping[str, str], *, frac: float, seed: int, exclude: Iterable[str] = ZERO) -> Split:
    """H3: hold out whole parents (IZs) to avoid leakage via the IZ effect. Zero-dwelling zones excluded."""
    parent = _sr.sample_for("holdout", dict(parent), exclude)
    rng = random.Random(seed)
    parents = sorted(set(parent.values()))
    held = set(rng.sample(parents, max(1, int(round(len(parents) * frac))))) if parents else set()
    test = sorted(z for z, p in parent.items() if p in held)
    train = sorted(z for z, p in parent.items() if p not in held)
    return Split("H3_iz_block", train, test, seed)


# --------------------------------------------------------------------------- metrics


def ratios(pred: Sequence[float], actual: Sequence[float]) -> list[float]:
    if len(pred) != len(actual) or not pred:
        raise ValueError("pred and actual must be same non-zero length")
    return [p / a for p, a in zip(pred, actual) if a > 0]


def cod(r: Sequence[float]) -> float:
    """Coefficient of dispersion (IAAO), percent."""
    med = statistics.median(r)
    return 100.0 * statistics.fmean(abs(x - med) for x in r) / med


def prd(pred: Sequence[float], actual: Sequence[float]) -> float:
    """Price-related differential: mean ratio / weighted mean ratio."""
    r = ratios(pred, actual)
    return statistics.fmean(r) / (sum(pred) / sum(actual))


def prb(pred: Sequence[float], actual: Sequence[float]) -> float:
    """Price-related bias (IAAO): slope of (ratio-med)/med on log2 of value proxy."""
    import math

    r = ratios(pred, actual)
    med = statistics.median(r)
    value = [0.5 * a + 0.5 * p / med for p, a in zip(pred, actual)]
    x = [math.log2(v) for v in value]
    y = [(ri - med) / med for ri in r]
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxx = sum((xi - mx) ** 2 for xi in x)
    return 0.0 if sxx == 0 else sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / sxx


def coverage(actual: Sequence[float], low: Sequence[float], high: Sequence[float]) -> float:
    return sum(lo <= a <= hi for a, lo, hi in zip(actual, low, high)) / len(actual)


def score(pred: Sequence[float], actual: Sequence[float], low=None, high=None) -> dict[str, float]:
    r = ratios(pred, actual)
    out = {
        "n": float(len(r)),
        "median_ratio": statistics.median(r),
        "cod": cod(r),
        "prd": prd(pred, actual),
        "prb": prb(pred, actual),
        "mdape": statistics.median(abs(x - 1) for x in r),
    }
    if low is not None and high is not None:
        out["coverage_80"] = coverage(actual, low, high)
    return out


def run_holdout(
    split: Split,
    rows: Mapping[str, Mapping],
    fit_predict: Callable[[list[Mapping], list[Mapping]], list[tuple[float, float, float]]],
    *,
    actual_key: str = "price_gbp",
    exclude: Iterable[str] = ZERO,
) -> dict:
    """Fit on split.train, score implied price on split.test. Model is pluggable.
    Zero-dwelling zones never enter the fit (model_fit) or the scored sample (holdout)."""
    fit_rows = _sr.sample_for("model_fit", dict(rows), exclude)
    test_rows = _sr.sample_for("holdout", dict(rows), exclude)
    train = [fit_rows[z] for z in split.train if z in fit_rows]
    test = [test_rows[z] for z in split.test if z in test_rows and test_rows[z].get(actual_key)]
    preds = fit_predict(train, test)
    if len(preds) != len(test):
        raise ValueError("fit_predict must return one prediction per test row")
    actual = [float(t[actual_key]) for t in test]
    return {
        "design": split.design,
        "seed": split.seed,
        "metrics": score([p[0] for p in preds], actual, [p[1] for p in preds], [p[2] for p in preds]),
    }


# =========================================================================== indirect land-share checks (rules 12)
#
# No open land-only sales series exists for Scotland, so the land share is
# tested indirectly. Each check returns a dict with `pass` and the evidence.


def _median_by(groups: Mapping[object, Sequence[float]]) -> dict[object, float]:
    return {g: statistics.median(v) for g, v in groups.items() if v}


INDEPENDENT_RENT_EVIDENCE = ("saa_rateable_value", "brma_held_out")  # rules 12.1 (v0.3)


def two_route_check(
    pairs: Sequence[Mapping],
    *,
    max_median_abs_log_ratio: float,
    calibration_brmas: Iterable[str] = (),
) -> dict:
    """(a) Sales route (mean P − mean DRC) vs rent-capitalisation route, per zone.

    Rules 12.1: a pair counts ONLY where the rent evidence does not feed the
    yield calibration: Assessors' rateable values (`saa_rateable_value`), or
    PRS rents from a BRMA held out of the calibration (`brma_held_out`, and the
    BRMA must not be in `calibration_brmas`). Anything else (same BRMA x class
    cell) reduces algebraically to P − DRC and is dropped. With no countable
    pair the check is `not_applicable`. Both routes still subtract the SAME
    rebuild cost, so agreement never validates the rebuild assumption.

    Each pair: {sales_route, rent_route, evidence, brma}.
    """
    import math

    cal = set(calibration_brmas)
    counted, dropped = [], 0
    for p in pairs:
        ev = p.get("evidence")
        independent = ev == "saa_rateable_value" or (ev == "brma_held_out" and p.get("brma") not in cal)
        if not independent:
            dropped += 1
            continue
        a, b = p.get("sales_route"), p.get("rent_route")
        if a and b and a > 0 and b > 0:
            counted.append(abs(math.log(b / a)))
    base = {
        "check": "two_routes",
        "n": len(counted),
        "n_dropped_not_independent": dropped,
        "independent_evidence": list(INDEPENDENT_RENT_EVIDENCE),
        "shared_assumption": "rebuild_gbp_per_m2 (both routes subtract the same DRC)",
    }
    if not counted:
        return {**base, "status": "not_applicable", "pass": None,
                "reason": "no rent evidence independent of the yield calibration"}
    mal = statistics.median(counted)
    ok = mal <= max_median_abs_log_ratio
    return {**base, "status": "pass" if ok else "fail", "pass": ok, "median_abs_log_ratio": mal,
            "threshold": max_median_abs_log_ratio}


def gradient_check(
    land_share_by_class: Mapping[int, Sequence[float]],
    *,
    expected_order: Sequence[Sequence[int]],
    tolerance: float = 0.0,
    access_bins: Mapping[int, Sequence[float]] | None = None,
) -> dict:
    """LEGACY ordering helper on any per-class values (medians).

    Rules v0.6 12.2: the location gradient is tested on land value per
    RESIDENTIAL HECTARE with `per_hectare_gradient_check`; land share is used
    only in the national plausibility check. Kept for diagnostics only.

    `expected_order` lists pairs (a, b) where median share in class a >= class b
    (UR6: 1 Large Urban ... 6 Remote Rural; partial order, 4 vs 5 not ranked).
    `access_bins`: ordered bins of travel time (0 = best access); medians
    must not rise as access worsens.
    """
    med = _median_by(land_share_by_class)
    violations = [
        {"higher": a, "lower": b, "median_a": med[a], "median_b": med[b]}
        for a, b in expected_order
        if a in med and b in med and med[a] + tolerance < med[b]
    ]
    out = {"check": "gradient", "median_share_by_ur6": med, "violations": violations, "pass": not violations}
    if access_bins is not None:
        am = _median_by(access_bins)
        keys = sorted(am)
        inv = [(k1, k2) for k1, k2 in zip(keys, keys[1:]) if am[k2] > am[k1] + tolerance]
        out["median_share_by_access_bin"] = am
        out["access_inversions"] = inv
        out["pass"] = out["pass"] and not inv
    return out


def negative_by_class_check(
    rows: Sequence[Mapping], *, high_demand_ur6: Iterable[int], max_share_high_demand: float
) -> dict:
    """Rules 12.2 sub-check: widespread negative residuals in high-demand urban
    classes count against that part of the rebuild band. Negatives in weak
    remote or post-industrial markets can be real and are reported, not failed.

    Each row: {ur6_class, negative_residual}.
    """
    by: dict[int, list[bool]] = {}
    for r in rows:
        if r.get("ur6_class") is not None:
            by.setdefault(int(r["ur6_class"]), []).append(bool(r.get("negative_residual")))
    shares = {c: sum(v) / len(v) for c, v in by.items() if v}
    hd = set(int(c) for c in high_demand_ur6)
    breaches = {c: s for c, s in shares.items() if c in hd and s > max_share_high_demand}
    return {"check": "negative_by_class", "share_negative_by_ur6": shares, "high_demand_ur6": sorted(hd),
            "threshold": max_share_high_demand, "breaches": breaches, "pass": not breaches,
            "note": "If used to narrow the rebuild band this is calibration: document it and re-run on held-out zones (rules 12.2)."}


def national_share_check(
    zones: Sequence[Mapping], *, plausible_range: Sequence[float], tolerance: float, sources: Sequence[str] = ()
) -> dict:
    """(c) National residential land value / total housing value.

    Each zone needs land_value (per dwelling), mean_price (per dwelling) and
    dwellings, all on the same vintage. Total housing value = Σ mean × count.
    """
    land = sum(float(z["land_value"]) * int(z["dwellings"]) for z in zones if z.get("land_value") is not None)
    total = sum(float(z["mean_price"]) * int(z["dwellings"]) for z in zones if z.get("land_value") is not None)
    if total <= 0:
        return {"check": "national_share", "pass": False, "reason": "no value"}
    share = land / total
    lo, hi = float(plausible_range[0]), float(plausible_range[1])
    return {
        "check": "national_share",
        "share": share,
        "range": [lo, hi],
        "tolerance": tolerance,
        "pass": (lo - tolerance) <= share <= (hi + tolerance),
        "within_core_range": lo <= share <= hi,
        "range_sources": list(sources),
    }


def rebuild_sensitivity(zones: Sequence[Mapping]) -> dict:
    """How far land value moves across the rebuild band.

    Each zone: price (MEAN, rules 6.1), dwellings, drc {low, central, high} (MEAN DRC of the same homes). Low rebuild gives
    HIGH land. Reports the median swing (L_at_low_rebuild − L_at_high_rebuild)
    / L_central, the share of zones that go negative per scenario, and the
    national land share per scenario.
    """
    swings: list[float] = []
    neg = {"low": 0, "central": 0, "high": 0}
    land_tot = {"low": 0.0, "central": 0.0, "high": 0.0}
    value_tot = 0.0
    for z in zones:
        p = float(z["mean_price"] if "mean_price" in z else z["price"])
        d = int(z.get("dwellings", 1))
        raw = {s: p - float(z["drc"][s]) for s in ("low", "central", "high")}
        for s in raw:
            neg[s] += raw[s] < 0
            land_tot[s] += max(0.0, raw[s]) * d
        value_tot += p * d
        if raw["central"] > 0:
            swings.append((max(0.0, raw["low"]) - max(0.0, raw["high"])) / raw["central"])
    n = len(zones)
    return {
        "report": "rebuild_sensitivity",
        "n_zones": n,
        "median_relative_swing": statistics.median(swings) if swings else None,
        "max_relative_swing": max(swings) if swings else None,
        "share_negative_by_rebuild": {s: (neg[s] / n if n else None) for s in neg},
        "national_land_share_by_rebuild": {s: (land_tot[s] / value_tot if value_tot else None) for s in land_tot},
        "note": "Scenario names refer to REBUILD cost; low rebuild -> high land value.",
        "bcis_trigger_hint": "If holdout error falls materially when rebuild moves within the band, rebuild drives error: consider BCIS licence (rules 6.2).",
    }


# --------------------------------------------------------------------------- rules 12.2 (v0.6): per-hectare gradient

ACCESS_DRIVE = ("drive_petrol", "drive_GP", "drive_post", "drive_primary", "drive_retail", "drive_secondary")
ACCESS_PT = ("PT_GP", "PT_post", "PT_retail")
ACCESS_FORBIDDEN_TOKENS = ("rank", "score", "decile", "quintile", "vigintile", "domain", "overall")
RES_LAND_METHODS_OK = ("parcel_based",)
RES_LAND_COLUMNS = ("code", "vintage", "residential_land_ha", "method")
OBSERVED_FILLS = ("observed_pooled", "shrunk_to_model")


def _vintage_ok(v, want=2011) -> bool:
    from georgist.surface_zones import vintage_int
    try:
        return vintage_int(v) == vintage_int(want)
    except ValueError:
        return False


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Spearman rank correlation (average ranks for ties), no SciPy."""
    n = len(x)
    if n != len(y) or n < 3:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r

    rx, ry = ranks(list(x)), ranks(list(y))
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    return sxy / (sxx * syy) ** 0.5 if sxx > 0 and syy > 0 else None


def access_minutes(rows: Iterable[Mapping], *, vintage=2011) -> dict[str, dict[str, float]]:
    """Data Zones `simd2020v2_access_indicators_dz2011` -> {code: {drive_min, pt_min}}.

    Raw travel minutes only: mean of the six drive-time and the three public
    transport indicators. SIMD ranks, scores, deciles or domain values are never
    used (rules 6.7); a file carrying them in place of the minutes is refused.
    Broadband is a driver in the fill model but not an access-to-services time.
    """
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        cols = set(r)
        missing = [c for c in ("code", "vintage", *ACCESS_DRIVE, *ACCESS_PT) if c not in cols]
        if missing:
            bad = [c for c in cols if any(t in c.lower() for t in ACCESS_FORBIDDEN_TOKENS)]
            raise ValueError(f"access file lacks raw minutes {missing}" + (f"; ranks/scores {bad} are never used" if bad else ""))
        if not _vintage_ok(r["vintage"], vintage):
            raise ValueError(f"access indicators must be {vintage} (same vintage as the price spine), got {r['vintage']!r}")
        try:
            d = [float(r[c]) for c in ACCESS_DRIVE]
            p = [float(r[c]) for c in ACCESS_PT]
        except (TypeError, ValueError):
            continue
        if any(v != v or v < 0 for v in d + p):
            continue
        out[str(r["code"])] = {"drive_min": sum(d) / len(d), "pt_min": sum(p) / len(p)}
    return out


def residential_land(rows: Iterable[Mapping], *, vintage=2011) -> dict[str, dict]:
    """GIS `dz_residential_land` -> {code: {ha, method}}. Schema: code, vintage, residential_land_ha, method."""
    out: dict[str, dict] = {}
    for r in rows:
        missing = [c for c in RES_LAND_COLUMNS if c not in r]
        if missing:
            raise ValueError(f"dz_residential_land lacks {missing}")
        if not _vintage_ok(r["vintage"], vintage):
            continue  # other vintage rows are ignored, never mixed
        try:
            ha = float(r["residential_land_ha"])
        except (TypeError, ValueError):
            ha = None
        out[str(r["code"])] = {"ha": ha if ha is not None and ha == ha and ha > 0 else None, "method": str(r["method"]),
                               "exclude": tuple(r.get("gradient_exclude") or ())}
    return out


def per_hectare_gradient_check(
    zones: Sequence[Mapping],
    *,
    residential_land_rows: Iterable[Mapping] | None,
    access_rows: Iterable[Mapping] | None,
    expected_order: Sequence[Sequence[int]],
    min_zones_per_class: int,
    access_rho_max: float,
    min_sales: int = 5,
    max_missing_share: float = 0.05,
    methods_ok: Sequence[str] = RES_LAND_METHODS_OK,
    vintage=2011,
    exclude: Iterable[str] = ZERO,
) -> dict:
    """Rules 12.2 (v0.6) location gradient on LAND VALUE PER RESIDENTIAL HECTARE.

    Between classes: median £/res-ha must fall from UR6 1 (Large Urban) through
    small towns to rural (pairs (a, b) in `expected_order`: median a >= median b).
    Within each class: £/res-ha must rise with access, i.e. Spearman rho against
    raw drive minutes and against public-transport minutes must each be
    <= `access_rho_max` (negative: shorter journeys, higher value).

    OBSERVED ZONES ONLY (Georgist ruling 2026-10-06): the travel times are fill
    model drivers, so model-filled zones would pass by construction. A zone is
    used only with >= `min_sales` sales and fill_method observed_pooled or
    shrunk_to_model, and then with its OBSERVED land value (sales price minus
    DRC, before any shrinkage), never the model blend.

    Residential land must be GIS's parcel-based method. The settlement-area
    method, a missing file, or more than `max_missing_share` of observed zones
    without residential land or access times returns `pending` with the reason.
    A class with fewer than `min_zones_per_class` observed zones is
    `pending/insufficient_n` and its between-class pairs are not tested.
    Land share is NOT used here (national plausibility check only).

    Each zone: {code, vintage, ur6_class, fill_method, sales_n, observed_land_value (per dwelling), dwellings}.
    """
    base = {"check": "gradient_per_res_ha", "measure": "observed land value per residential hectare",
            "uses_land_share": False, "min_sales": min_sales, "min_zones_per_class": min_zones_per_class}
    used, excluded_filled, excluded_other = [], 0, 0
    n_in = len(zones)
    zones = _sr.sample_for("holdout", list(zones), exclude)
    base["n_excluded_zero_dwellings"] = n_in - len(zones)
    for z in zones:
        if not _vintage_ok(z.get("vintage"), vintage):
            raise ValueError(f"zone {z.get('code')} vintage {z.get('vintage')!r} != {vintage}")
        filled = z.get("fill_method") not in OBSERVED_FILLS or int(z.get("sales_n") or 0) < min_sales
        if filled:
            excluded_filled += 1
        elif z.get("observed_land_value") is None or not z.get("dwellings") or z.get("ur6_class") is None:
            excluded_other += 1
        else:
            used.append(z)
    base.update(n_observed=len(used), n_excluded_model_filled=excluded_filled, n_excluded_no_observed_value=excluded_other)

    if residential_land_rows is None:
        return {**base, "status": "pending", "pass": None, "reason": "residential_land_missing (GIS dz_residential_land not supplied)"}
    land = residential_land(residential_land_rows, vintage=vintage)
    methods = sorted({land[z["code"]]["method"] for z in used if z["code"] in land})
    base["residential_land_methods"] = methods
    bad_methods = [m for m in methods if m not in methods_ok]
    if bad_methods:
        return {**base, "status": "pending", "pass": None,
                "reason": f"residential_land_method={','.join(bad_methods)} (gradient runs only on {list(methods_ok)})"}
    if access_rows is None:
        return {**base, "status": "pending", "pass": None, "reason": "access_indicators_missing (Data Zones simd2020v2_access_indicators_dz2011 not supplied)"}
    acc = access_minutes(access_rows, vintage=vintage)

    pts: dict[int, list[tuple[float, float, float]]] = {}
    missing = 0
    excl_by: dict[str, int] = {}
    kept = []
    for z in used:  # documented quality exclusions are dropped and counted, not treated as missing
        lz = land.get(z["code"])
        if lz and lz.get("exclude"):
            for reason in lz["exclude"]:
                excl_by[reason] = excl_by.get(reason, 0) + 1
            continue
        kept.append(z)
    base["n_excluded_res_land_quality"] = len(used) - len(kept)
    base["excluded_res_land_by_reason"] = excl_by
    used = kept
    for z in used:
        lz, az = land.get(z["code"]), acc.get(z["code"])
        if not lz or lz["ha"] is None or not az:
            missing += 1
            continue
        v = float(z["observed_land_value"]) * float(z["dwellings"]) / lz["ha"]
        pts.setdefault(int(z["ur6_class"]), []).append((v, az["drive_min"], az["pt_min"]))
    base["n_missing_land_or_access"] = missing
    if used and missing / len(used) > max_missing_share:
        return {**base, "status": "pending", "pass": None,
                "reason": f"missing residential land or access for {missing}/{len(used)} observed zones (> {max_missing_share:.0%})"}

    classes, med = {}, {}
    for c in sorted({int(z["ur6_class"]) for z in used} | set(pts)):
        p = pts.get(c, [])
        if len(p) < min_zones_per_class:
            classes[c] = {"n_used": len(p), "status": "pending", "reason": "insufficient_n"}
            continue
        vals = [a for a, _, _ in p]
        med[c] = statistics.median(vals)
        rd, rp = spearman(vals, [b for _, b, _ in p]), spearman(vals, [t for _, _, t in p])
        ok = rd is not None and rp is not None and rd <= access_rho_max and rp <= access_rho_max
        classes[c] = {"n_used": len(p), "median_gbp_per_res_ha": med[c], "rho_drive": rd, "rho_pt": rp,
                      "status": "pass" if ok else "fail"}
    pairs = []
    for a, b in expected_order:
        if a in med and b in med:
            pairs.append({"higher": a, "lower": b, "median_a": med[a], "median_b": med[b],
                          "status": "pass" if med[a] >= med[b] else "fail"})
        else:
            pairs.append({"higher": a, "lower": b, "status": "pending", "reason": "insufficient_n"})
    base.update(n_used_by_class={c: v["n_used"] for c, v in classes.items()}, classes=classes, between_class=pairs,
                access_rho_max=access_rho_max)
    statuses = [v["status"] for v in classes.values()] + [p["status"] for p in pairs]
    if "fail" in statuses:
        return {**base, "status": "fail", "pass": False}
    if "pending" in statuses or not statuses:
        return {**base, "status": "pending", "pass": None, "reason": "insufficient_n"}
    return {**base, "status": "pass", "pass": True}


# --------------------------------------------------------------------------- rules 12 (v0.7): central decides, corners are stress

def plausibility_checks(
    cases: Mapping[str, Sequence[Mapping]],
    *,
    plausible_range: Sequence[float],
    tolerance: float,
    high_demand_ur6: Iterable[int],
    max_share_high_demand: float,
    sources: Sequence[str] = (),
    swings: Mapping | None = None,
    exclude: Iterable[str] = ZERO,
) -> dict:
    """Rules 12 (v0.7): the plausibility checks PASS or FAIL on the CENTRAL case only.

    `cases` = {"central": zones, "low": zones, "high": zones} where low/high are
    the outer-band CORNERS (drc_high_land_low / drc_low_land_high). Corners are
    reported as STRESS results (`stress_inside` / `stress_outside` the range),
    never as a fail. One-at-a-time swings, if given, are carried through for the report.
    Each zone: {land_value, mean_price, dwellings, ur6_class, negative_residual}.
    """
    if "central" not in cases:
        raise ValueError("plausibility_checks needs the central case")
    hd = list(high_demand_ur6)
    cases = {k: _sr.sample_for("holdout", list(v), exclude) for k, v in cases.items()}

    def run(zs):
        return (national_share_check(zs, plausible_range=plausible_range, tolerance=tolerance, sources=sources),
                negative_by_class_check(zs, high_demand_ur6=hd, max_share_high_demand=max_share_high_demand))

    nat, neg = run(cases["central"])
    central = {"national_share": nat, "negative_by_class": neg, "pass": bool(nat["pass"] and neg["pass"]),
               "status": "pass" if nat["pass"] and neg["pass"] else "fail"}
    stress = {}
    for k in ("low", "high"):
        if k not in cases:
            continue
        n2, g2 = run(cases[k])
        inside = bool(n2["pass"] and g2["pass"])
        stress[k] = {"national_share": n2["share"], "within_range_plus_tolerance": n2["pass"],
                     "share_negative_by_ur6": g2["share_negative_by_ur6"], "high_demand_breaches": g2["breaches"],
                     "status": "stress_inside" if inside else "stress_outside"}
    return {"check": "plausibility", "decided_on": "central", "status": central["status"], "pass": central["pass"],
            "central": central, "corners_stress": stress, "swings": dict(swings) if swings else None,
            "note": "Corners (outer band) are stress results and never fail the check (rules 12, v0.7)."}


# --------------------------------------------------------------------------- Georgist guard: plot size selects the rate only

def plot_size_rate_diagnostic(
    zones: Sequence[Mapping],
    *,
    residential_land_rows: Iterable[Mapping] | None,
    estate_rows: Iterable[Mapping] | None,
    estate_columns: Mapping[str, str],
    min_zones_per_class: int = 30,
    rho_flag: float = -0.10,
    min_sales: int = 5,
    vintage=2011,
    exclude: Iterable[str] = ZERO,
) -> dict:
    """Holdout DIAGNOSTIC (never a pass/fail of the model): within each UR6 class,
    Spearman rho of land value per residential hectare against (i) the zone's median
    post-1980 detached parcel size and (ii) the share of dwellings drawing the
    one-off (non-estate) detached rate.

    Each rho is computed twice: on the ACTUAL observed land value (blended
    estate/one-off rates) and on a UNIFORM-RATE COUNTERFACTUAL (every post-1980
    detached home at one national rate). FLAG `big_plot_lower_due_to_rate` for a
    class where big-plot / one-off zones come out LOWER (rho <= rho_flag) on the
    actual values but NOT under the uniform rate (rho > rho_flag): the dip is
    caused by the higher rebuild rate, not by location.

    Observed zones only (>= min_sales, observed fill), as for the gradient check.
    Each zone: {code, vintage, ur6_class, fill_method, sales_n, dwellings,
    observed_land_value, observed_land_value_uniform_rate, oneoff_share}.
    Pending if the GIS residential land or estate (parcel band) input is missing.
    Output inherits publish_level internal (GIS parcel data, OS terms).
    """
    base = {"report": "plot_size_rate_diagnostic", "publish_level": "internal", "rho_flag": rho_flag,
            "min_zones_per_class": min_zones_per_class, "is_driver": False,
            "note": "Plot size selects the rebuild rate only; it is never a land-value driver."}
    if residential_land_rows is None:
        return {**base, "status": "pending", "reason": "residential_land_missing (GIS dz_residential_land not supplied)"}
    if estate_rows is None:
        return {**base, "status": "pending", "reason": "estate_parcel_bands_missing (GIS dz_residential_land estate fields not supplied)"}
    land = residential_land(residential_land_rows, vintage=vintage)
    med_col = estate_columns["median_parcel_ha"]
    parcel: dict[str, float] = {}
    for r in estate_rows:
        if not _vintage_ok(r.get("vintage"), vintage):
            continue
        try:
            v = float(r.get(med_col))
        except (TypeError, ValueError):
            continue
        if v == v and v > 0:
            parcel[str(r["code"])] = v
    pts: dict[int, list[tuple]] = {}
    n_excl = 0
    for z in _sr.sample_for("holdout", list(zones), exclude):
        if z.get("fill_method") not in OBSERVED_FILLS or int(z.get("sales_n") or 0) < min_sales:
            continue
        lz = land.get(str(z["code"]))
        if lz and lz.get("exclude"):
            n_excl += 1
            continue
        if not lz or lz["ha"] is None or z.get("observed_land_value") is None or z.get("observed_land_value_uniform_rate") is None:
            continue
        if z.get("ur6_class") is None or not z.get("dwellings"):
            continue
        k = float(z["dwellings"]) / lz["ha"]
        pts.setdefault(int(z["ur6_class"]), []).append(
            (float(z["observed_land_value"]) * k, float(z["observed_land_value_uniform_rate"]) * k,
             parcel.get(str(z["code"])), z.get("oneoff_share")))
    if not pts:
        return {**base, "status": "pending", "reason": "no observed zones with residential land"}
    classes, flagged = {}, []
    for c, p in sorted(pts.items()):
        out = {"n": len(p)}
        for name, idx in (("median_parcel_ha", 2), ("oneoff_share", 3)):
            q = [t for t in p if t[idx] is not None]
            if len(q) < min_zones_per_class:
                out[name] = {"n": len(q), "status": "insufficient_n"}
                continue
            x = [float(t[idx]) for t in q]
            ra, ru = spearman([t[0] for t in q], x), spearman([t[1] for t in q], x)
            flag = ra is not None and ru is not None and ra <= rho_flag and ru > rho_flag
            out[name] = {"n": len(q), "rho_actual": ra, "rho_uniform_rate": ru,
                         "rho_shift_from_rate": (ra - ru) if ra is not None and ru is not None else None,
                         "flag_big_plot_lower_due_to_rate": flag}
            if flag:
                flagged.append((c, name))
        classes[c] = out
    tested = [v for o in classes.values() for k, v in o.items() if k != "n" and "rho_actual" in v]
    status = "flagged" if flagged else ("ok" if tested else "pending")
    res = {**base, "status": status, "classes": classes, "flagged": flagged, "n_excluded_res_land_quality": n_excl}
    if status == "pending":
        res["reason"] = "insufficient_n"
    return res


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


RES_LAND_EXCLUDE_REASONS = ("weak_match", "mask_too_big_parcel", "res_uprn_exceeds_dwellings", "zero_dwellings",
                            "no_residential_parcel")


def residential_land_rows_from_gis(rows: Iterable[Mapping], *, low_coverage: str = "exclude", min_share: float = 0.5,
                                   zero_codes: Iterable[str] = ()) -> list[dict]:
    """Map GIS `dz_residential_land.csv` (parcel method) onto the check schema.

    Returns {code, vintage, residential_land_ha, method, gradient_exclude, low_confidence}. The area is
    always carried (it is a per-hectare DENOMINATOR only and never changes totals). `gradient_exclude`
    lists why a zone is dropped from the per-hectare gradient: share_res_uprn_in_parcels < min_share
    (weak_match; kept when low_coverage='keep', sensitivity), mask_too_big_parcel,
    res_uprn_exceeds_dwellings, zero_dwellings (GIS flag/column or Data Zones zero_dwellings codes),
    no_residential_parcel. `low_confidence` lists per-hectare output tags (weak_match, mask_too_big,
    uprn_exceeds)."""
    if low_coverage not in ("exclude", "keep"):
        raise ValueError("low_coverage must be exclude or keep")
    zc = set(zero_codes)
    out = []
    for r in rows:
        if "residential_land_ha" in r and "method" in r:
            out.append({"gradient_exclude": (), "low_confidence": (), **dict(r)})
            continue
        flags = str(r.get("method_flags") or "").split(";")
        share = r.get("share_res_uprn_in_parcels")
        try:
            share = float(share)
        except (TypeError, ValueError):
            share = None
        weak = (share is not None and share == share and share < min_share) or "low_parcel_coverage_lt0.5" in flags
        mask = _truthy(r.get("mask_too_big_parcel"))
        over = _truthy(r.get("res_uprn_exceeds_dwellings")) or "res_uprn_exceeds_dwellings" in flags
        zero = _truthy(r.get("zero_dwellings")) or "zero_dwellings" in flags or str(r["code"]) in zc
        nopar = "no_residential_parcel" in flags
        excl = [n for n, hit in (("weak_match", weak and low_coverage == "exclude"), ("mask_too_big_parcel", mask),
                                 ("res_uprn_exceeds_dwellings", over), ("zero_dwellings", zero),
                                 ("no_residential_parcel", nopar)) if hit]
        low = [n for n, hit in (("weak_match", weak), ("mask_too_big", mask), ("uprn_exceeds", over)) if hit]
        method = "parcel_based" if any(f.startswith("parcel_residential_uprn") for f in flags) else "settlement_area"
        out.append({"code": str(r["code"]), "vintage": r["vintage"], "residential_land_ha": r.get("residential_parcel_ha"),
                    "method": method, "gradient_exclude": tuple(excl), "low_confidence": tuple(low)})
    return out


# =========================================================================== rules 12.2 v0.7: PRE-REGISTERED job-access gradient
#
# Registered 2026-10-06 (rules 23df6297) before GIS dz_access.csv exists. Config `gradient_v07` fixes the
# driver, decay settings, thresholds and sample. The SIMD-minutes check above stays as the superseded
# driver, reported as run.

import hashlib as _hashlib  # noqa: E402
import json as _json  # noqa: E402
from datetime import datetime as _dt, timezone as _tz  # noqa: E402
from pathlib import Path as _Path  # noqa: E402


class AccessMetadataMismatch(ValueError):
    """dz_access.csv metadata contradicts the pre-registered GIS settings."""


class RepeatScoredRunError(RuntimeError):
    """A second scored run on the same dz_access checksum without an explicit override."""


def _norm(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, Mapping):
        return sorted((str(k).strip().lower(), _norm(x)) for k, x in v.items())
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple, set)):
        return sorted(_norm(x) for x in v)
    s = str(v).strip()
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if ";" in s:
        return sorted(_norm(x) for x in s.split(";") if x.strip())
    try:
        return float(s)
    except ValueError:
        return s.lower()


def check_access_metadata(meta: Mapping | None, expected: Mapping) -> dict:
    """Assert GIS's dz_access settings against the pre-registered `expected_metadata`.

    Any key present with a different value raises AccessMetadataMismatch. Keys missing from
    `meta` leave status `incomplete` (the scored run then refuses). All keys equal -> `verified`."""
    meta = dict(meta or {})
    missing = [k for k in expected if k not in meta]
    bad = {k: (meta[k], expected[k]) for k in expected if k in meta and _norm(meta[k]) != _norm(expected[k])}
    if bad:
        raise AccessMetadataMismatch(f"dz_access metadata differs from pre-registration: {bad}")
    return {"status": "verified" if not missing else "incomplete", "missing": missing}


def config_hash(section: Mapping) -> str:
    return _hashlib.sha256(_json.dumps(section, sort_keys=True, default=str).encode()).hexdigest()


class RunGuard:
    """Internal JSONL run log for the once-only scored run (rules 12.2 v0.7). Records the dz_access sha256
    and the pre-registration config hash; refuses a second scored run on the same input unless
    `override=True` (the override and its reason are logged)."""

    def __init__(self, log_path):
        self.path = _Path(log_path)

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [_json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def register(self, *, access_sha256: str, cfg_hash: str, override: bool = False, reason: str = "") -> dict:
        prior = [e for e in self.entries() if e.get("access_sha256") == access_sha256]
        if prior and not override:
            raise RepeatScoredRunError(f"scored run already recorded for dz_access {access_sha256[:8]} at {prior[0]['at']}; "
                                       "pass override=True with a reason to re-run")
        if override and not reason:
            raise ValueError("an override needs a stated reason")
        e = {"at": _dt.now(_tz.utc).isoformat(), "access_sha256": access_sha256, "config_hash": cfg_hash,
             "override": bool(override), "reason": reason, "n_prior": len(prior)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps(e) + "\n")
        return e


def access_flags(value, sep: str = ";") -> tuple[str, ...]:
    """Tokens of a GIS semicolon-separated flags cell ('' / NaN -> ())."""
    if value is None or value != value:
        return ()
    return tuple(t.strip() for t in str(value).split(sep) if t.strip())


def job_access_rows(rows: Iterable[Mapping], columns: Mapping[str, str], *, vintage=2011, island_flag_token: str | None = None,
                    flags_separator: str = ";") -> dict[str, dict]:
    """dz_access rows -> {code: {job_access, centre_km, island, flags}} for one vintage (rank/score columns refused).

    With a `flags` column, `island` = `island_flag_token` present in the row's flags (GIS: luc_distance_euclid_x1.3).
    Flags never exclude a zone here (rules 12.2 v0.7 sample is unchanged)."""
    for c in (columns["job_access"], columns["centre_km"]):
        if any(t in c.lower() for t in ACCESS_FORBIDDEN_TOKENS):
            raise ValueError(f"{c}: ranks/scores are not access measures")
    out = {}
    for r in rows:
        if not _vintage_ok(r.get("vintage"), vintage):
            continue
        try:
            ja, km = float(r[columns["job_access"]]), float(r[columns["centre_km"]])
        except (KeyError, TypeError, ValueError):
            continue
        if ja != ja or km != km:
            continue
        fl = access_flags(r.get(columns["flags"]), flags_separator) if columns.get("flags") else ()
        isl = columns.get("island_flag")
        island = (island_flag_token in fl) if island_flag_token else (_truthy(r.get(isl)) if isl else False)
        out[str(r["code"])] = {"job_access": ja, "centre_km": km, "island": island, "flags": fl}
    return out


def job_access_gradient_check(
    zones: Sequence[Mapping],
    *,
    residential_land_rows: Iterable[Mapping] | None,
    access_rows: Iterable[Mapping] | None,
    gcfg: Mapping,
    expected_order: Sequence[Sequence[int]],
    access_metadata: Mapping | None,
    exclude: Iterable[str] = ZERO,
    vintage=2011,
) -> dict:
    """Pre-registered rules 12.2 v0.7 within-class gradient (config `gradient_v07`).

    PRIMARY (decides): Spearman rho(GBP per residential ha, job accessibility) >= primary.rho_min in EVERY
    UR6 class. SECONDARY (reported only): rho(GBP/res-ha, road km to nearest large urban centre) <=
    secondary.rho_max. Sample: observed zones (observed_pooled/shrunk_to_model, >= min_sales), minus the
    residential-land quality exclusions (counted by reason) and zero-dwelling zones. A class below
    min_zones_per_class is insufficient_n. A class failing the primary is `failed` (never inconclusive);
    its model-filled zones get the on_class_fail band multiplier. Between-class test unchanged.
    Pending without residential land, without dz_access, or with unverified metadata."""
    s = gcfg["sample"]
    base = {"check": "gradient_v07_job_access", "pre_registered": gcfg.get("registered"), "status": "pending",
            "pass": None, "decides_on": "primary"}
    if residential_land_rows is None:
        return {**base, "reason": "residential_land_missing"}
    if access_rows is None:
        return {**base, "reason": "dz_access_missing (pre-registered; awaiting GIS)"}
    meta = check_access_metadata(access_metadata, gcfg["expected_metadata"])
    base["metadata"] = meta
    if meta["status"] != "verified":
        return {**base, "reason": f"dz_access metadata unverified: missing {meta['missing']}"}
    land = residential_land(residential_land_rows, vintage=vintage)
    acc = job_access_rows(access_rows, gcfg["input"]["columns"], vintage=vintage,
                          island_flag_token=gcfg["input"].get("island_flag_token"),
                          flags_separator=gcfg["input"].get("flags_separator", ";"))
    zs = _sr.sample_for("holdout", list(zones), exclude)
    base["n_excluded_zero_dwellings"] = len(zones) - len(zs)
    used, excl_by, n_filled, missing = [], {}, 0, 0
    for z in zs:
        if z.get("fill_method") not in tuple(s["observed_fill_methods"]) or int(z.get("sales_n") or 0) < int(s["min_sales"]):
            n_filled += 1
            continue
        lz = land.get(str(z["code"]))
        if lz and lz.get("exclude"):
            for reason in lz["exclude"]:
                excl_by[reason] = excl_by.get(reason, 0) + 1
            continue
        az = acc.get(str(z["code"]))
        if not lz or lz["ha"] is None or not az or z.get("observed_land_value") is None or not z.get("dwellings"):
            missing += 1
            continue
        v = float(z["observed_land_value"]) * float(z["dwellings"]) / lz["ha"]
        used.append((int(z["ur6_class"]), v, az["job_access"], az["centre_km"], az["island"], az.get("flags", ())))
    flag_counts: dict[str, int] = {}
    for u in used:
        for t in u[5]:
            flag_counts[t] = flag_counts.get(t, 0) + 1
    base.update(n_excluded_not_observed=n_filled, excluded_res_land_by_reason=excl_by, n_missing_land_or_access=missing,
                n_used=len(used), n_islands_used=sum(1 for u in used if u[4]),
                access_flag_counts_used_reported_only=flag_counts)
    rmin, rmax, nmin = float(gcfg["primary"]["rho_min"]), float(gcfg["secondary"]["rho_max"]), int(s["min_zones_per_class"])
    classes, med, failed = {}, {}, []
    for c in sorted({u[0] for u in used}):
        p = [u for u in used if u[0] == c]
        if len(p) < nmin:
            classes[c] = {"n_used": len(p), "status": "insufficient_n"}
            continue
        vals = [u[1] for u in p]
        med[c] = statistics.median(vals)
        rj, rc = spearman(vals, [u[2] for u in p]), spearman(vals, [u[3] for u in p])
        ok = rj is not None and rj >= rmin
        classes[c] = {"n_used": len(p), "median_gbp_per_res_ha": med[c], "rho_job_access": rj, "primary_pass": ok,
                      "rho_centre_km": rc, "secondary_pass_reported": rc is not None and rc <= rmax,
                      "status": "pass" if ok else "failed"}
        if not ok:
            failed.append(c)
    pairs = [{"higher": a, "lower": b, "status": ("pass" if med[a] >= med[b] else "fail") if a in med and b in med else "insufficient_n"}
             for a, b in expected_order]
    st = [v["status"] for v in classes.values()]
    status = "fail" if failed or any(p["status"] == "fail" for p in pairs) else ("pending" if "insufficient_n" in st or not st else "pass")
    return {**base, "classes": classes, "between_class": pairs, "failed_classes": failed, "status": status,
            "pass": {"pass": True, "fail": False}.get(status), "rho_min": rmin, "secondary_rho_max": rmax}


FAIL_BAND_PENDING_TAG = "fail_band_pending_holdout"


def widen_failed_class_band(land_value: float | None, low: float | None, high: float | None, *, fill_method: str,
                            ur6_class: int, failed_classes: Iterable[int], multiplier: float,
                            multiplier_status: str) -> tuple[float | None, float | None, tuple[str, ...]]:
    """Rules 12.2 v0.7: MODEL-FILLED zones in a class that failed the pre-registered measure.

    With `multiplier_status` REJECTED_* (Georgist, 2026-10-06) the multiplier is NEVER applied: the band is
    returned unwidened and tagged `fail_band_pending_holdout` (the active behaviour). Otherwise the band
    is widened (distance from the value scaled by `multiplier`, low floored at 0). Observed zones unchanged."""
    if fill_method != "model_filled" or ur6_class is None or int(ur6_class) not in set(failed_classes):
        return low, high, ()
    if str(multiplier_status).upper().startswith("REJECTED"):
        return low, high, (FAIL_BAND_PENDING_TAG,)
    if land_value is None or low is None or high is None:
        return low, high, ()
    m = float(multiplier)
    tags = ("band_widened_gradient_v07_class_failed",)
    if multiplier_status != "SIGNED_OFF":
        tags += ("band_multiplier_placeholder",)
    return max(0.0, land_value - (land_value - low) * m), land_value + (high - land_value) * m, tags


def access_metadata_from_gis(manifest_row: Mapping, access_config: Mapping, header: Sequence[str]) -> dict:
    """Map GIS's dz_access manifest row, its pre-registered access_config.json and the CSV header line to the
    keys of `gradient_v07.expected_metadata`. Reads no data rows. A phrase that is not recognised is passed
    through raw, so `check_access_metadata` raises on it rather than guessing."""
    emp, net, ja, luc = (access_config.get(k) or {} for k in ("employment", "network", "job_access", "large_urban_centres"))
    src = str(manifest_row.get("source", ""))
    geo = str(emp.get("geography", ""))
    year_cfg, year_man = emp.get("bres_year"), manifest_row.get("source_year")
    falloff = str(ja.get("falloff", ""))
    pair = str(net.get("pair_distance", ""))
    centres = luc.get("centres") or {}
    origin = str((access_config.get("origins") or {}).get("origin_method", ""))
    return {
        "employment_source": "BRES" if "BRES" in str(emp.get("source", "")) and "BRES" in src else emp.get("source"),
        "employment_geography": "DZ2011" if "2011" in geo and "datazone" in geo.lower().replace(" ", "") else geo,
        "employment_year": (int(year_cfg) if year_man is not None and str(year_man).strip() == str(year_cfg) else
                            f"config {year_cfg} / manifest {year_man}"),
        "decay": "exponential" if "exponential" in falloff else falloff,
        "decay_scale_km": ja.get("scale_km"),
        "cutoff_km": ja.get("cutoff_km"),
        "own_zone_jobs_included": str(ja.get("own_zone", "")).lower().startswith("included") or ja.get("own_zone"),
        "network": "OS Open Roads" if str(net.get("source", "")).startswith("OS Open Roads") else net.get("source"),
        "origins": "SG population-weighted centroids" if origin == "sg_popweighted_centroid" else origin,
        "large_urban_centres": sorted(centres),
        "centre_point_basis": "documented_landmarks" if "landmark" in str(luc.get("point_source", "")).lower() else luc.get("point_source"),
        "centre_landmarks": {c: v.get("landmark") for c, v in centres.items()},
        "island_rule": ("straight_line_x1.3" if float(net.get("euclid_factor") or 0) == 1.3 and "x 1.3" in pair else pair),
        "island_flagged": "flags" in list(header) and "distance_method" in list(header),
    }
