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
        outcome = "publish_neither_report_both"
        publish_primary = False
        publish_secondary = False
        as_range = False
    else:
        outcome = "publish_neither_report_both"
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
) -> dict:
    """Score both estimators; apply no-switch publication; £ display off."""
    c = cfg if cfg is not None else sr.load_config()
    pins = pin_frozen_inputs(c)
    lsc = c.get("land_share_checks") or {}
    band = list(lsc.get("national_range") or [0.10, 0.40])
    zero_max = float(lsc.get("zero_mass_max_share", 0.10))
    c4cfg = (v14_config(c).get("check4") or (c.get("v13") or {}).get("check4") or {})

    def _score(shares: Sequence[float], check4: dict | None) -> dict:
        c1 = v13.check_1_median_land_share(list(shares), band=band)
        c1d = v13.check_1d_zero_mass(list(shares), max_share=zero_max)
        out = {
            "check_1": c1,
            "check_1d": c1d,
            "check_1e": {
                "status": "information_only",
                "zones_at_0": c1d.get("info_1e_zones_at_0"),
                "pct_at_0": c1d.get("info_1e_pct_at_0"),
            },
            "gating_pass": bool(c1.get("pass")) and bool(c1d.get("pass")),
        }
        if check4 is not None:
            out["check_4"] = check4
            out["gating_pass"] = out["gating_pass"] and bool(check4.get("pass"))
        return out

    primary = _score(primary_shares, primary_check4)
    secondary = _score(secondary_shares, secondary_check4) if secondary_shares is not None else None
    publication = apply_no_switch_publication(
        primary_gating_pass=bool(primary["gating_pass"]),
        secondary_gating_pass=bool(secondary["gating_pass"]) if secondary else False,
    )
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
        "publication": publication,
    }
