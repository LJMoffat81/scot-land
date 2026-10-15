#!/usr/bin/env python3
"""v1.3 scoring harness (ports the amend-2 scoring path to prereg ce940445…).

Reads measured residual rows + cost inputs, applies v1.3 check gates, and writes
an internal JSON report. Farmland/LCA other-land file is read from a gitignored
local path (env ``V13_OTHER_LAND_LCA_PATH``); absent -> skipped with a clear message.

No public £. GBP-LIVE stays enabled:false. Synthetic fixtures only in tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from georgist import surface_rent as sr
from georgist import surface_v13 as v13
from georgist.surface_paths import REPO_ROOT


def _skip_msg(name: str, path_hint: str) -> dict:
    return {
        "status": "skipped",
        "reason": f"{name} input missing at {path_hint} (CI/local without private data)",
    }


def load_plot_split(cfg: dict) -> tuple[Path | None, dict]:
    c3 = (cfg.get("v13") or {}).get("check3") or {}
    path = v13.resolve_optional_path(
        c3.get("plot_split_path"),
        expected_sha256=c3.get("plot_split_sha256"),
    )
    if path is None:
        return None, _skip_msg("plot_split", str(c3.get("plot_split_path")))
    return path, {"status": "ok", "path": str(path), "sha256": c3.get("plot_split_sha256")}


def load_bedroom_bands(cfg: dict) -> tuple[Path | None, dict]:
    c4 = (cfg.get("v13") or {}).get("check4") or {}
    path = v13.resolve_optional_path(
        c4.get("bedroom_bands_path"),
        expected_sha256=c4.get("bedroom_bands_sha256"),
    )
    if path is None:
        return None, _skip_msg("bedroom_bands", str(c4.get("bedroom_bands_path")))
    return path, {"status": "ok", "path": str(path), "sha256": c4.get("bedroom_bands_sha256")}


def load_other_land(cfg: dict) -> tuple[Path | None, dict]:
    c3 = (cfg.get("v13") or {}).get("check3") or {}
    env = c3.get("other_land_lca_path_env") or "V13_OTHER_LAND_LCA_PATH"
    path = v13.resolve_optional_path(
        None,
        expected_sha256=c3.get("other_land_lca_sha256"),
        env_var=env,
    )
    if path is None:
        return None, {
            "status": "skipped",
            "reason": (
                f"other-land LCA file absent (env {env}); used in check 3 only, "
                "never published, never committed"
            ),
        }
    return path, {"status": "ok", "path": str(path), "sha256": c3.get("other_land_lca_sha256")}


def score_from_shares(
    shares: list[float],
    *,
    cfg: dict,
    check3_zones: list[dict] | None = None,
    check4_gaps: list[float] | None = None,
    check4_class_gaps: dict[int, list[float]] | None = None,
) -> dict:
    """Score checks that need only precomputed synthetic or run outputs."""
    v13.assert_prereg_sha(cfg)
    lsc = cfg.get("land_share_checks") or {}
    band = list(lsc.get("national_range") or [0.10, 0.40])
    zero_max = float(lsc.get("zero_mass_max_share", 0.10))
    c1 = v13.check_1_median_land_share(shares, band=band)
    c1d = v13.check_1d_zero_mass(shares, max_share=zero_max)
    out = {
        "prereg_sha256": v13.PREREG_SHA256,
        "price_year_label": sr.price_year_label(cfg),
        "holdout_label": v13.holdout_gating_label(cfg),
        "oncost_central": sr.oncost_factor_v13(cfg["rebuild"]),
        "oncost_replace": sr.oncost_replace_factor(cfg["rebuild"]),
        "check_1": c1,
        "check_1d": c1d,
        "check_1c": {"status": "information_only", "note": "shares clamped to [0,1]; cannot fail"},
        "check_1e": {
            "status": "information_only",
            "zones_at_0": c1d.get("info_1e_zones_at_0"),
            "pct_at_0": c1d.get("info_1e_pct_at_0"),
        },
    }
    c3cfg = (cfg.get("v13") or {}).get("check3") or {}
    if check3_zones is not None:
        out["check_3"] = v13.check_3_plot_comparison(
            check3_zones,
            decide_radius_m=int(c3cfg.get("decide_radius_m", 30)),
            report_radii_m=list(c3cfg.get("report_radii_m") or [20, 40]),
            min_pass_share=float(c3cfg.get("min_pass_share", 0.80)),
        )
    c4cfg = (cfg.get("v13") or {}).get("check4") or {}
    if check4_gaps is not None:
        out["check_4"] = v13.check_4_two_route_gap(
            check4_gaps,
            class_gaps=check4_class_gaps,
            national_max_abs=float(c4cfg.get("national_max_abs_gap", 0.25)),
            class_max_abs=float(c4cfg.get("class_max_abs_gap", 0.40)),
        )
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=REPO_ROOT / "out" / "v13_score" / "report.json")
    p.add_argument(
        "--shares-json",
        type=Path,
        help="JSON list of land shares (synthetic or internal run). Required for gated checks.",
    )
    args = p.parse_args(argv)
    cfg = sr.load_config()
    v13.assert_prereg_sha(cfg)

    plot_path, plot_meta = load_plot_split(cfg)
    bed_path, bed_meta = load_bedroom_bands(cfg)
    other_path, other_meta = load_other_land(cfg)

    report = {
        "prereg_sha256": v13.PREREG_SHA256,
        "price_year_label": sr.price_year_label(cfg),
        "holdout_label": v13.holdout_gating_label(cfg),
        "holdout": {
            "gating": "temporal_2023",
            "hold_year": v13.temporal_holdout_year(cfg),
            "n_min": int((cfg.get("v13") or {}).get("holdout", {}).get("n_min", 5)),
            "fit": "observations_excluding_hold_year (pool/fit without hold_year)",
            "score": "zones with sales_n >= n_min in hold_year (H4_temporal_year)",
        },
        "inputs": {

            "plot_split": plot_meta,
            "bedroom_bands": bed_meta,
            "other_land_lca": other_meta,
            "plot_path": str(plot_path) if plot_path else None,
            "bedroom_path": str(bed_path) if bed_path else None,
            "other_land_path": str(other_path) if other_path else None,
        },
        "gbp_live_enabled": False,
        "note": (
            "Valuation runs the scored pass once on merged main. "
            "Check 1 is expected to fail on the projected central (median 0.0%, 52.4% at zero); "
            "no re-tuning in this PR."
        ),
    }
    if args.shares_json and args.shares_json.is_file():
        shares = json.loads(args.shares_json.read_text(encoding="utf-8"))
        report["scores"] = score_from_shares(list(shares), cfg=cfg)
    else:
        report["scores"] = {
            "status": "pending_inputs",
            "reason": "pass --shares-json with land-share list to score checks 1/1d",
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    if other_meta.get("status") == "skipped":
        print(other_meta["reason"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
