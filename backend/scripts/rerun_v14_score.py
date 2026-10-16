#!/usr/bin/env python3
"""v1.4 scoring harness — pins frozen MD/JSON shas, both estimators, no-switch rule.

£ display off. Outputs under out/ (gitignored). No re-tuning after results.
Synthetic or precomputed share lists only in CI; no public £.

Additive arguments (absent → output matches fe026b76):
``--check-inputs``, ``--secondary-estimator-json``, ``--holdout-2023``,
``--score-2024``, ``--allow-rerun-for-fidelity-bug``, ``--record-sha8s``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from georgist import surface_rent as sr
from georgist import surface_v14 as v14
from georgist.surface_paths import REPO_ROOT
from georgist.surface_v14_checks import score_both
from georgist.v14_hedonic import PriceYearError, refuse_2024_price_file
from georgist.v14_score_report import (
    HoldoutLockError,
    MergeMapError,
    PriceColumnReadLog,
    ReportAbort,
    assert_2024_allowed,
    assert_merge_map,
    build_report,
    git_commit,
    prepare_holdout_2023,
    require_commit_sha,
    sha256_file,
    write_holdout_lock,
    write_report,
)


def _legacy(args: argparse.Namespace) -> int:
    cfg = sr.load_config()
    pins = v14.pin_frozen_inputs(cfg)
    dep = v14.v14_depreciation(cfg)

    report = {
        "pins": pins,
        "gbp_display": False,
        "depreciation": {
            "method": dep.get("method"),
            "age_cap_years": dep.get("age_cap_years"),
            "rate_building": dep.get("rate_building"),
            "max_depreciation": dep.get("max_depreciation"),
        },
        "no_age_mix_remaining_factor": v14.no_age_mix_remaining(cfg),
        "no_switch_publication_rule": v14.NO_SWITCH_PUBLICATION_RULE,
        "note": (
            "Valuation runs the scored pass once on merged main. "
            "Both estimators are scored; publication follows the no-switch rule. "
            "No re-tuning in this PR."
        ),
    }

    if args.primary_shares_json and args.primary_shares_json.is_file():
        primary = json.loads(args.primary_shares_json.read_text(encoding="utf-8"))
        secondary = None
        if args.secondary_shares_json and args.secondary_shares_json.is_file():
            secondary = json.loads(args.secondary_shares_json.read_text(encoding="utf-8"))
        report["scores"] = v14.score_estimators(
            primary_shares=list(primary),
            secondary_shares=None if secondary is None else list(secondary),
            cfg=cfg,
        )
    else:
        report["scores"] = {
            "status": "pending_inputs",
            "reason": "pass --primary-shares-json (and optional --secondary-shares-json)",
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    if not pins.get("prereg_sha256"):
        print(
            "frozen prereg file absent locally; prefix pin only "
            f"({v14.PREREG_SHA256_PREFIX}…)",
            file=sys.stderr,
        )
    return 0


def _extended(args: argparse.Namespace) -> bool:
    return bool(
        args.check_inputs
        or args.secondary_estimator_json
        or args.holdout_2023
        or args.score_2024
        or args.allow_rerun_for_fidelity_bug
        or args.record_sha8s
        or args.merge_map
    )


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return value


def _score_holdout(path: Path) -> dict:
    """Estimate-and-score both estimators. Raises before any lock is written."""
    refuse_2024_price_file(path.name)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "primary_zones" not in payload or "secondary_zones" not in payload:
        raise ReportAbort("holdout needs primary_zones and secondary_zones")
    scored = score_both(payload["primary_zones"], payload["secondary_zones"])
    return _jsonable(scored)


def _check_summary(path: Path) -> dict:
    refuse_2024_price_file(path.name)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "primary_zones" not in payload or "secondary_zones" not in payload:
        return {"status": "pending_inputs"}
    scored = score_both(payload["primary_zones"], payload["secondary_zones"])
    return {
        "status": "scored",
        "primary_gating_pass": scored["primary"]["gating_pass"],
        "secondary_gating_pass": scored["secondary"]["gating_pass"],
        "publication": scored["publication"]["outcome"],
        "hbu_in_checks": scored["checks_include_hbu"],
    }


def _inputs_sha256(args: argparse.Namespace) -> str:
    digest = hashlib.sha256()
    used = False
    for path in (args.check_inputs, args.secondary_estimator_json, args.merge_map):
        if path is not None and path.is_file():
            digest.update(path.read_bytes())
            used = True
    if not used:
        return "synthetic"
    return digest.hexdigest()


def _extended_main(args: argparse.Namespace) -> int:
    score_dir = args.out.parent
    inputs_sha = _inputs_sha256(args)
    reads = PriceColumnReadLog()
    commit = require_commit_sha(git_commit())
    try:
        if args.merge_map:
            refuse_2024_price_file(args.merge_map.name)
            assert_merge_map(args.merge_map)
        if args.secondary_estimator_json:
            refuse_2024_price_file(args.secondary_estimator_json.name)
        holdout_scores = None
        if args.holdout_2023:
            if args.check_inputs is None:
                raise ReportAbort("holdout needs check inputs")
            prepare_holdout_2023(
                score_dir,
                inputs_sha256=inputs_sha,
                commit=commit,
                allow_incident=args.allow_rerun_for_fidelity_bug,
            )
            holdout_scores = _score_holdout(args.check_inputs)
        if args.score_2024:
            assert_2024_allowed(score_dir)
        report = build_report(price_columns_read=reads.snapshot(), commit=commit)
        if args.holdout_2023:
            report["holdout_scores"] = holdout_scores
            report["holdout_estimated"] = True
            report["checks"] = {
                "status": "scored",
                "primary_gating_pass": holdout_scores["primary"]["gating_pass"],
                "secondary_gating_pass": holdout_scores["secondary"]["gating_pass"],
                "publication": holdout_scores["publication"]["outcome"],
                "hbu_in_checks": holdout_scores["checks_include_hbu"],
            }
        elif args.check_inputs:
            report["checks"] = _check_summary(args.check_inputs)
        write_report(args.out, report)
        if args.holdout_2023:
            write_holdout_lock(
                score_dir,
                inputs_sha256=inputs_sha,
                commit=commit,
                report_sha256=sha256_file(args.out),
            )
    except Exception as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    print(f"wrote {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=REPO_ROOT / "out" / "v14_score" / "report.json")
    p.add_argument(
        "--primary-shares-json",
        type=Path,
        help="JSON list of primary (cost) land shares. Unavailable zones as 0.0.",
    )
    p.add_argument(
        "--secondary-shares-json",
        type=Path,
        help="JSON list of secondary (hedonic) land shares.",
    )
    p.add_argument("--check-inputs", type=Path, help="JSON check inputs for the full v1.4 checks.")
    p.add_argument(
        "--secondary-estimator-json",
        type=Path,
        help="Frozen secondary-estimator coefficients. Levels form is not swapped in.",
    )
    p.add_argument("--holdout-2023", action="store_true", help="Run the 2023 holdout once.")
    p.add_argument("--score-2024", action="store_true", help="2024 entry point. Requires the holdout lock.")
    p.add_argument("--allow-rerun-for-fidelity-bug", default=None, help="Incident id for a logged fidelity rerun.")
    p.add_argument("--record-sha8s", action="store_true", help="Write the sha8 run report.")
    p.add_argument("--merge-map", type=Path, help="Pinned CA2019 x UR3 merge map. Abort on sha256 mismatch.")
    args = p.parse_args(argv)
    if _extended(args):
        return _extended_main(args)
    return _legacy(args)


if __name__ == "__main__":
    raise SystemExit(main())
