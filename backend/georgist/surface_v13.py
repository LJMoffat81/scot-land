"""Scot-LAND v1.3 methods helpers: checks 1d / 3 / 4, holdout labels, input loaders.

Prereg: sha256 ce9404455134c3dd96828bdc200832629a2c4e8932ad4bea2438e7a938907ead.
Synthetic fixtures only in tests. Farmland/LCA rates are never committed or published.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from georgist import surface_rent as sr
from georgist.surface_paths import REPO_ROOT

PREREG_SHA256 = "ce9404455134c3dd96828bdc200832629a2c4e8932ad4bea2438e7a938907ead"
HOLDOUT_GATING_LABEL = "temporal holdout, seen in v1.2, not out-of-sample"
PRICE_YEAR_LABEL = "2025-04 indexed"


def file_sha256(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(path: Path | str, expected: str) -> str:
    got = file_sha256(path)
    if got != expected:
        raise ValueError(f"sha256 mismatch for {path}: got {got}, expected {expected}")
    return got


def resolve_optional_path(
    configured: str | None,
    *,
    expected_sha256: str | None = None,
    env_var: str | None = None,
) -> Path | None:
    """Return a readable path, verifying sha when present. Missing -> None (caller skips)."""
    candidates: list[Path] = []
    if env_var:
        env_val = os.environ.get(env_var)
        if env_val:
            candidates.append(Path(env_val))
    if configured:
        p = Path(configured)
        candidates.append(p if p.is_absolute() else REPO_ROOT / p)
    for path in candidates:
        if path.is_file():
            if expected_sha256:
                verify_sha256(path, expected_sha256)
            return path
    return None


def land_share_clamped(land_value: float, price: float) -> float:
    """Land share clamped to [0, 1] (check 1c information only; clamp enables 1d)."""
    if price <= 0:
        raise ValueError("price must be positive for land share")
    return min(1.0, max(0.0, float(land_value) / float(price)))


def check_1_median_land_share(
    shares: Sequence[float],
    *,
    band: Sequence[float] = (0.10, 0.40),
) -> dict:
    """Check 1 gating: median land share in [10%, 40%]."""
    if not shares:
        return {"check": "1", "pass": None, "status": "pending", "median": None, "band": list(band)}
    ordered = sorted(float(s) for s in shares)
    n = len(ordered)
    mid = n // 2
    median = ordered[mid] if n % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])
    lo, hi = float(band[0]), float(band[1])
    ok = lo <= median <= hi
    return {
        "check": "1",
        "pass": ok,
        "status": "pass" if ok else "fail",
        "median": median,
        "band": [lo, hi],
        "n": n,
    }


def check_1d_zero_mass(
    shares: Sequence[float],
    *,
    max_share: float = 0.10,
    eps: float = 1e-12,
) -> dict:
    """Check 1d: FAIL if > max_share of priced zones are clamped at 0% or 100%."""
    if not shares:
        return {
            "check": "1d",
            "pass": None,
            "status": "pending",
            "share_at_bound": None,
            "max_share": max_share,
        }
    n = len(shares)
    at0 = sum(1 for s in shares if float(s) <= eps)
    at1 = sum(1 for s in shares if float(s) >= 1.0 - eps)
    at_bound = at0 + at1
    share = at_bound / n
    ok = share <= max_share
    return {
        "check": "1d",
        "pass": ok,
        "status": "pass" if ok else "fail",
        "n": n,
        "n_at_0": at0,
        "n_at_100": at1,
        "share_at_bound": share,
        "max_share": max_share,
        # check 1e: count at 0% is information only
        "info_1e_zones_at_0": at0,
        "info_1e_pct_at_0": at0 / n,
    }


def check_3_plot_comparison(
    zone_results: Sequence[Mapping],
    *,
    decide_radius_m: int = 30,
    report_radii_m: Sequence[int] = (20, 40),
    min_pass_share: float = 0.80,
) -> dict:
    """Check 3: pass/fail ONLY at decide_radius_m; report others; FRAGILE if 20↔40 flip.

    Each zone_result needs ``pass_at``: {radius_m: bool}.
    """
    if not zone_results:
        return {"check": "3", "pass": None, "status": "pending", "fragile": False}
    decide = int(decide_radius_m)
    n = len(zone_results)
    n_pass = sum(1 for z in zone_results if bool((z.get("pass_at") or {}).get(decide)))
    share = n_pass / n
    ok = share >= float(min_pass_share)
    reported = {}
    for r in report_radii_m:
        rr = int(r)
        n_r = sum(1 for z in zone_results if bool((z.get("pass_at") or {}).get(rr)))
        reported[rr] = {"n_pass": n_r, "share": n_r / n, "pass": (n_r / n) >= float(min_pass_share)}
    fragile = False
    if len(report_radii_m) >= 2:
        outcomes = [reported[int(r)]["pass"] for r in report_radii_m if int(r) in reported]
        if len(outcomes) >= 2 and len(set(outcomes)) > 1:
            fragile = True
    return {
        "check": "3",
        "pass": ok,
        "status": "pass" if ok else "fail",
        "decide_radius_m": decide,
        "n": n,
        "n_pass": n_pass,
        "share": share,
        "min_pass_share": float(min_pass_share),
        "reported": reported,
        "fragile": fragile,
        "note": "FRAGILE if 20 m and 40 m outcomes disagree; 30 m alone decides pass/fail",
    }


def map_bedroom_band_to_rent_beds(band: str | int) -> str:
    """Census band -> BRMA rent Beds label. 4+ -> '4 Bedroom'. Shared-room excluded upstream."""
    key = str(band).strip()
    if key in ("4", "4+", "4plus", "4_plus"):
        return "4 Bedroom"
    if key in ("1", "1 Bedroom"):
        return "1 Bedroom"
    if key in ("2", "2 Bedroom"):
        return "2 Bedroom"
    if key in ("3", "3 Bedroom"):
        return "3 Bedroom"
    raise KeyError(f"unknown bedroom band {band!r}")


def expected_rent_for_zone(
    shares: Mapping[str, float],
    rents_by_band: Mapping[str, float],
    *,
    ur6_class: int | None = None,
    plus4_factor: float = 1.15,
    plus4_classes: Iterable[int] = (5, 6),
    plus4_all_classes: bool = False,
) -> float:
    """F8 check 4: Σ share_k × rent_b,k. 4+ uses '4 Bedroom'; × plus4_factor in classes 5/6."""
    total = 0.0
    for band, share in shares.items():
        if float(share) <= 0:
            continue
        beds = map_bedroom_band_to_rent_beds(band)
        if beds not in rents_by_band:
            raise KeyError(f"rent missing for {beds}")
        rent = float(rents_by_band[beds])
        if beds == "4 Bedroom":
            apply = plus4_all_classes or (ur6_class is not None and int(ur6_class) in set(plus4_classes))
            if apply:
                rent *= float(plus4_factor)
        total += float(share) * rent
    return total


def capitalised_rent_land(monthly_rent: float, *, yield_rate: float = 0.045) -> float:
    """Annualise monthly rent and capitalise at the configured yield."""
    if yield_rate <= 0:
        raise ValueError("yield_rate must be positive")
    return (12.0 * float(monthly_rent)) / float(yield_rate)


def check_4_two_route_gap(
    gaps: Sequence[float],
    *,
    class_gaps: Mapping[int, Sequence[float]] | None = None,
    national_max_abs: float = 0.25,
    class_max_abs: float = 0.40,
) -> dict:
    """Check 4: national median gap within ±25%; each UR6 class within ±40%."""
    if not gaps:
        return {"check": "4", "pass": None, "status": "pending"}
    ordered = sorted(float(g) for g in gaps)
    n = len(ordered)
    mid = n // 2
    national = ordered[mid] if n % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])
    nat_ok = abs(national) <= float(national_max_abs)
    class_out = {}
    class_ok = True
    for ur6, gs in (class_gaps or {}).items():
        if not gs:
            class_out[int(ur6)] = {"median": None, "pass": None}
            continue
        o = sorted(float(x) for x in gs)
        m = len(o) // 2
        med = o[m] if len(o) % 2 else 0.5 * (o[m - 1] + o[m])
        ok = abs(med) <= float(class_max_abs)
        class_out[int(ur6)] = {"median": med, "pass": ok, "n": len(o)}
        class_ok = class_ok and ok
    ok = nat_ok and class_ok
    return {
        "check": "4",
        "pass": ok,
        "status": "pass" if ok else "fail",
        "national_median_gap": national,
        "national_max_abs": float(national_max_abs),
        "national_pass": nat_ok,
        "by_ur6": class_out,
        "class_max_abs": float(class_max_abs),
    }


def v13_config(cfg: Mapping | None = None) -> dict:
    c = cfg if cfg is not None else sr.load_config()
    return dict(c.get("v13") or {})


def holdout_gating_label(cfg: Mapping | None = None) -> str:
    v13 = v13_config(cfg)
    return str((v13.get("holdout") or {}).get("label") or HOLDOUT_GATING_LABEL)


def assert_prereg_sha(cfg: Mapping | None = None) -> str:
    v13 = v13_config(cfg)
    got = str(v13.get("prereg_sha256") or "")
    if got != PREREG_SHA256:
        raise ValueError(f"v13.prereg_sha256 {got!r} != {PREREG_SHA256}")
    return got
