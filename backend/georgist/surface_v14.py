"""Scot-LAND v1.4 fidelity helpers: straight-line depreciation, O-G1, check 4, scorer pins.

Frozen prereg sha prefix ``e1ab6d0a…``; fidelity_fix_spec sha prefix ``1694c8ad…``.
Synthetic fixtures only in tests. No public £. Nothing tuned.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from georgist import surface_rent as sr
from georgist import surface_v13 as v13
from georgist.surface_paths import REPO_ROOT

PREREG_SHA256_PREFIX = "e1ab6d0a"
FIDELITY_FIX_SPEC_SHA256_PREFIX = "1694c8ad"

# Decision rule 3.2 — never switch to whichever estimator passes.
NO_SWITCH_PUBLICATION_RULE = (
    "Never switch to whichever passes. "
    "Primary passes + secondary passes → publish range spanning both (never a blend). "
    "Primary passes + secondary fails → publish primary; report secondary failures. "
    "Primary fails + secondary passes → report both; publish neither as official. "
    "Both fail → publish neither; report both."
)


def v14_config(cfg: Mapping | None = None) -> dict:
    c = cfg if cfg is not None else sr.load_config()
    return dict(c.get("v14") or {})


def v14_depreciation(cfg: Mapping | None = None) -> dict:
    """v1.4 straight_line depreciation, midpoints taken from the v1.3 block."""
    c = cfg if cfg is not None else sr.load_config()
    base = dict(c.get("depreciation") or {})
    v14 = v14_config(c)
    dep = dict(v14.get("depreciation") or {})
    if "age_band_midpoint_year" not in dep and "age_band_midpoint_year" in base:
        dep["age_band_midpoint_year"] = dict(base["age_band_midpoint_year"])
    return dep


def assert_prereg_prefix(cfg: Mapping | None = None) -> str:
    v14 = v14_config(cfg)
    got = str(v14.get("prereg_sha256_prefix") or "")
    if got != PREREG_SHA256_PREFIX:
        raise ValueError(f"v14.prereg_sha256_prefix {got!r} != {PREREG_SHA256_PREFIX}")
    return got


def assert_fidelity_fix_spec_prefix(cfg: Mapping | None = None) -> str:
    v14 = v14_config(cfg)
    got = str(v14.get("fidelity_fix_spec_sha256_prefix") or "")
    if got != FIDELITY_FIX_SPEC_SHA256_PREFIX:
        raise ValueError(
            f"v14.fidelity_fix_spec_sha256_prefix {got!r} != {FIDELITY_FIX_SPEC_SHA256_PREFIX}"
        )
    return got


def verify_frozen_file_prefix(path: Path | str, prefix: str) -> str:
    """When the frozen scotland-rules file is present, assert sha starts with prefix."""
    p = Path(path)
    if not p.is_file():
        return ""
    got = v13.file_sha256(p)
    if not got.startswith(prefix):
        raise ValueError(f"sha256 of {p} is {got}, expected prefix {prefix}")
    return got


def pin_frozen_inputs(cfg: Mapping | None = None) -> dict:
    """Pin frozen MD/JSON sha prefixes; verify on disk when files are mounted."""
    c = cfg if cfg is not None else sr.load_config()
    v14 = v14_config(c)
    assert_prereg_prefix(c)
    assert_fidelity_fix_spec_prefix(c)
    out = {
        "prereg_sha256_prefix": PREREG_SHA256_PREFIX,
        "fidelity_fix_spec_sha256_prefix": FIDELITY_FIX_SPEC_SHA256_PREFIX,
        "prereg_sha256": None,
        "fidelity_fix_spec_sha256": None,
        "freeze_json_sha256": None,
    }
    for key, prefix_key, out_key in (
        ("prereg_path", "prereg_sha256_prefix", "prereg_sha256"),
        ("fidelity_fix_spec_path", "fidelity_fix_spec_sha256_prefix", "fidelity_fix_spec_sha256"),
        ("freeze_json_path", None, "freeze_json_sha256"),
    ):
        rel = v14.get(key)
        if not rel:
            continue
        path = Path(rel) if Path(rel).is_absolute() else REPO_ROOT / rel
        if prefix_key:
            out[out_key] = verify_frozen_file_prefix(path, str(v14[prefix_key])) or None
        elif path.is_file():
            out[out_key] = v13.file_sha256(path)
    return out


def no_age_mix_remaining(cfg: Mapping | None = None) -> float:
    """Frozen central remaining factor for zones with no age mix (not 0.55)."""
    c = cfg if cfg is not None else sr.load_config()
    v14 = v14_config(c)
    nam = v14.get("no_age_mix") or {}
    if "central_remaining_factor" in nam:
        return float(nam["central_remaining_factor"])
    return sr.central_remaining_factor_v14(v14_depreciation(c))


def shares_for_gating(rows: Sequence[Mapping]) -> list[float]:
    """Land shares for checks 1/1b/1d: unavailable zones enter at 0% (O-G1)."""
    return [sr.gating_land_share_for_row(r) for r in rows]


def apply_no_switch_publication(
    *,
    primary_gating_pass: bool,
    secondary_gating_pass: bool,
) -> dict:
    """Decision rule 3.2 — never switch to whichever passes."""
    if primary_gating_pass and secondary_gating_pass:
        outcome = "publish_range_both"
        publish_primary = True
        publish_secondary = True
        as_range = True
    elif primary_gating_pass and not secondary_gating_pass:
        outcome = "publish_primary_only"
        publish_primary = True
        publish_secondary = False
        as_range = False
    elif (not primary_gating_pass) and secondary_gating_pass:
        outcome = "primary_fail_secondary_pass_publish_neither_until_v15"
        publish_primary = False
        publish_secondary = False
        as_range = False
    else:
        outcome = "both_fail_publish_neither"
        publish_primary = False
        publish_secondary = False
        as_range = False
    return {
        "rule": NO_SWITCH_PUBLICATION_RULE,
        "outcome": outcome,
        "publish_primary": publish_primary,
        "publish_secondary": publish_secondary,
        "publish_as_range": as_range,
        "never_blend": True,
        "never_switch_to_passing": True,
    }


def check_4_from_routes(
    residual_lands: Sequence[float],
    capitalised_lands: Sequence[float],
    *,
    class_residual: Mapping[int, Sequence[float]] | None = None,
    class_capitalised: Mapping[int, Sequence[float]] | None = None,
    national_max_abs: float = 0.25,
    class_max_abs: float = 0.40,
) -> dict:
    """Compute check-4 gaps and score; residual median ≤0 → fail."""
    if len(residual_lands) != len(capitalised_lands):
        raise ValueError("residual_lands and capitalised_lands length mismatch")
    gaps = [
        v13.two_route_relative_gap(r, c)
        for r, c in zip(residual_lands, capitalised_lands)
    ]
    res_med = v13._median(residual_lands) if residual_lands else None
    class_gaps: dict[int, list[float]] = {}
    class_res_med: dict[int, float] = {}
    for ur6, rs in (class_residual or {}).items():
        cs = list((class_capitalised or {}).get(ur6) or [])
        if len(cs) != len(rs):
            raise ValueError(f"class {ur6} residual/capitalised length mismatch")
        class_gaps[int(ur6)] = [v13.two_route_relative_gap(r, c) for r, c in zip(rs, cs)]
        if rs:
            class_res_med[int(ur6)] = v13._median(rs)
    return v13.check_4_two_route_gap(
        gaps,
        class_gaps=class_gaps,
        national_max_abs=national_max_abs,
        class_max_abs=class_max_abs,
        residual_median=res_med,
        class_residual_medians=class_res_med or None,
    )


def score_estimators(
    *,
    primary_shares: Sequence[float],
    secondary_shares: Sequence[float] | None = None,
    cfg: Mapping | None = None,
    primary_check4: dict | None = None,
    secondary_check4: dict | None = None,
    primary_zones: Sequence[Mapping] | None = None,
    secondary_zones: Sequence[Mapping] | None = None,
) -> dict:
    """Score both estimators and report every check for both.

    ``surface_v14_checks`` is imported here because that module imports
    ``surface_v14`` at module scope (circular dependency). Missing inputs are
    reported as ``pending`` and are never omitted. Share-only calls still gate
    on checks 1 and 1d, which are the inputs that call actually carries.
    """
    from georgist import surface_v14_checks as checks

    c = cfg if cfg is not None else sr.load_config()
    pins = pin_frozen_inputs(c)
    lsc = c.get("land_share_checks") or {}
    band = list(lsc.get("national_range") or [0.10, 0.40])
    zero_max = float(lsc.get("zero_mass_max_share", 0.10))
    c4cfg = (v14_config(c).get("check4") or (c.get("v13") or {}).get("check4") or {})
    gating_names = ("1", "1a", "1b", "1d", "3", "4", "6")
    information_names = (
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

    def _pending(name: str) -> dict:
        return {"check": name, "status": "pending", "pass": None}

    def _safe(name: str, fn):
        try:
            return fn()
        except (KeyError, TypeError, ValueError):
            return _pending(name)

    def _pack(gating: dict, information: dict, gating_pass: bool, check4: dict | None) -> dict:
        out = {
            "check_1": gating["1"],
            "check_1d": gating["1d"],
            "check_1e": information["1e"],
            "gating": gating,
            "information": information,
            "gating_pass": gating_pass,
            "hbu_excluded_from_checks": True,
        }
        if check4 is not None:
            out["check_4"] = check4
        return out

    def _from_zones(zones: Sequence[Mapping], check4: dict | None) -> dict:
        detailed = _safe("estimator", lambda: checks.score_estimator(list(zones)))
        if detailed.get("status") == "pending" or "gating" not in detailed:
            gating = {name: _pending(name) for name in gating_names}
            information = {name: _pending(name) for name in information_names}
            gating["1a"] = _safe("1a", lambda: checks.check_1a(list(zones)))
            gating["1b"] = _safe("1b", lambda: checks.check_1b(list(zones)))
            gating["4"] = check4 if check4 is not None else _safe("4", lambda: checks.check_4(list(zones)))
            gating["6"] = _safe("6", lambda: checks.check_6_zone_range(list(zones)))
            information["1c"] = _safe("1c", lambda: checks.check_1c([checks._share(zone) for zone in zones]))
            information["gis_plot_median_ratio"] = _safe(
                "gis_plot_median_ratio", lambda: checks.gis_plot_median_ratio(list(zones))
            )
            decided = [
                bool(item.get("pass"))
                for item in gating.values()
                if item.get("status") != "pending" and item.get("pass") is not None
            ]
            gating_pass = bool(decided) and all(decided) and all(
                item.get("status") != "pending" for item in gating.values()
            )
            return _pack(gating, information, gating_pass, check4)
        gating = dict(detailed["gating"])
        information = dict(detailed["information"])
        information.setdefault("agreement", _pending("agreement"))
        if check4 is not None:
            gating["4"] = check4
        gating_pass = all(
            item.get("status") != "pending" and bool(item.get("pass")) for item in gating.values()
        )
        return _pack(gating, information, gating_pass, check4)

    def _from_shares(shares: Sequence[float] | None, check4: dict | None) -> dict:
        gating = {name: _pending(name) for name in gating_names}
        information = {name: _pending(name) for name in information_names}
        if shares is None:
            return _pack(gating, information, False, check4)
        listed = list(shares)
        gating["1"] = v13.check_1_median_land_share(listed, band=band)
        gating["1d"] = v13.check_1d_zero_mass(listed, max_share=zero_max)
        if check4 is not None:
            gating["4"] = check4
        information["1c"] = _safe("1c", lambda: checks.check_1c(listed))
        c1d = gating["1d"]
        information["1e"] = {
            "check": "1e",
            "role": "information_only",
            "status": "information_only",
            "pass": None,
            "zones_at_0": c1d.get("info_1e_zones_at_0"),
            "pct_at_0": c1d.get("info_1e_pct_at_0"),
        }
        gating_pass = bool(gating["1"].get("pass")) and bool(gating["1d"].get("pass"))
        if check4 is not None:
            gating_pass = gating_pass and bool(check4.get("pass"))
        return _pack(gating, information, gating_pass, check4)

    if primary_zones is not None:
        primary = _from_zones(primary_zones, primary_check4)
    else:
        primary = _from_shares(primary_shares, primary_check4)
    if secondary_zones is not None:
        secondary = _from_zones(secondary_zones, secondary_check4)
    else:
        secondary = _from_shares(secondary_shares, secondary_check4)
    if primary_zones is not None and secondary_zones is not None:
        agreement = _safe(
            "agreement",
            lambda: checks.agreement(list(primary_zones), list(secondary_zones)),
        )
    else:
        agreement = _pending("agreement")
    primary["information"]["agreement"] = agreement
    secondary["information"]["agreement"] = agreement
    publication = apply_no_switch_publication(
        primary_gating_pass=bool(primary["gating_pass"]),
        secondary_gating_pass=bool(secondary["gating_pass"]),
    )
    hbu_zones: list[Mapping] = []
    if primary_zones is not None:
        hbu_zones.extend(primary_zones)
    if secondary_zones is not None:
        hbu_zones.extend(secondary_zones)
    return {
        "pins": pins,
        "gbp_display": bool(v14_config(c).get("gbp_display", False)),
        "depreciation_method": v14_depreciation(c).get("method"),
        "no_age_mix_remaining_factor": no_age_mix_remaining(c),
        "check4_thresholds": {
            "national_max_abs_gap": float(c4cfg.get("national_max_abs_gap", 0.25)),
            "class_max_abs_gap": float(c4cfg.get("class_max_abs_gap", 0.40)),
        },
        "primary": primary,
        "secondary": secondary,
        "agreement": agreement,
        "hbu": checks.hbu_line(hbu_zones),
        "hbu_status": checks.HBU_NOT_RUN,
        "hbu_gates": False,
        "publication": publication,
    }
