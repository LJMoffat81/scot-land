#!/usr/bin/env python3
"""v1.4 scoring harness — pins frozen MD/JSON shas, both estimators, no-switch rule.

£ display off. Outputs under out/ (gitignored). No re-tuning after results.
Synthetic or precomputed share lists only in CI; no public £.

Additive arguments (absent → output matches fe026b76):
``--check-inputs``, ``--secondary-estimator-json``, ``--holdout-2023``,
``--score-2024``, ``--allow-rerun-for-fidelity-bug``, ``--record-sha8s``,
``--lock-path``.
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
from georgist.check3_record import validate_check3_record
from georgist.v14_check4_route import assert_non_gbp_report, score_check4_non_gbp
from scripts.build_v14_check_inputs import load_check4_f8
from georgist.surface_v14_checks import score_both
from georgist.v14_hedonic import PriceYearError, refuse_2024_price_file
from georgist.v14_score_report import (
    HoldoutLockError,
    MergeMapError,
    PriceColumnReadLog,
    ReportAbort,
    assert_2024_allowed,
    assert_frozen_set,
    assert_merge_map,
    assert_score_years,
    build_report,
    frozen_set_members,
    git_commit,
    input_years,
    mark_score_2024,
    missing_lock_message,
    prepare_holdout_2023,
    read_year_files,
    require_commit_sha,
    secondary_estimator_fields,
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
        or getattr(args, "check4_f8", None)
        or getattr(args, "check4_summary_out", None)
    )


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return value


def _score_holdout(path: Path, *, year: int) -> dict:
    """Estimate-and-score both estimators. Raises before any lock is written.

    ``year`` is the literal from ``--holdout-2023`` or ``--score-2024``.
    """
    refuse_2024_price_file(path.name)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "primary_zones" not in payload or "secondary_zones" not in payload:
        raise ReportAbort("holdout needs primary_zones and secondary_zones")
    scored = score_both(payload["primary_zones"], payload["secondary_zones"], year=year)
    return _jsonable(scored)


def _check_summary(path: Path) -> dict:
    refuse_2024_price_file(path.name)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "primary_zones" not in payload or "secondary_zones" not in payload:
        return {"status": "pending_inputs"}
    scored = score_both(payload["primary_zones"], payload["secondary_zones"], year=2024)
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


def _input_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    if args.check_inputs is not None:
        paths["check_inputs"] = args.check_inputs
    if args.secondary_estimator_json is not None:
        paths["fitted_hedonic"] = args.secondary_estimator_json
    for name, value in (
        ("builder_output", getattr(args, "builder_output", None)),
        ("primary_estimates", getattr(args, "primary_estimates", None)),
        ("fitted_per_zone", getattr(args, "fitted_per_zone", None)),
        ("check4_f8", getattr(args, "check4_f8", None)),
    ):
        if value is not None:
            paths[name] = value
    return paths


FROZEN_MEMBER_ORDER = (
    "merge_map",
    "hedonic_coefs_2021_22",
    "code_sha8_block",
    "check3_plot_passes",
    "check4_rent_route",
    "ur6",
    "dz2022_keys",
)


def _frozen_mapping(args: argparse.Namespace) -> dict[str, Path | None]:
    return {
        "merge_map": args.merge_map,
        "hedonic_coefs_2021_22": getattr(args, "hedonic_coefs", None),
        "code_sha8_block": getattr(args, "sha8_block", None),
        "check3_plot_passes": getattr(args, "check3_plot_passes", None),
        "check4_rent_route": getattr(args, "check4_rent_route", None) or getattr(args, "check4_f8", None),
        "ur6": getattr(args, "ur6", None),
        "dz2022_keys": getattr(args, "dz2022_keys", None),
    }


def _missing_frozen(args: argparse.Namespace) -> list[str]:
    mapping = _frozen_mapping(args)
    return [name for name in FROZEN_MEMBER_ORDER if mapping[name] is None]


def _absent_frozen(missing: list[str], step: str) -> str:
    return "\n".join(
        f"{step}: REFUSED: frozen_set {name}: expected path, got absent" for name in missing
    )


def raise_missing_frozen(args: argparse.Namespace, step: str) -> None:
    """Refuse a holdout whose frozen-set paths are absent. Score-2024 uses ``_frozen_paths``."""
    missing = _missing_frozen(args)
    if missing:
        raise HoldoutLockError(_absent_frozen(missing, step))


def _frozen_paths(args: argparse.Namespace) -> dict[str, Path] | None:
    mapping = _frozen_mapping(args)
    present = [path for path in mapping.values() if path is not None]
    if not present:
        return None
    if len(present) != len(mapping):
        missing = [name for name in FROZEN_MEMBER_ORDER if mapping[name] is None]
        raise HoldoutLockError(
            "SCORE_2024: REFUSED: frozen_set: expected complete, got partial\n"
            + _absent_frozen(missing, "SCORE_2024")
        )
    return {name: path for name, path in mapping.items() if path is not None}


def _validate_frozen_check3(args: argparse.Namespace) -> None:
    """Validate a present check-3 path. An absent path keeps the frozen-set refusal."""
    if not (args.holdout_2023 or args.score_2024):
        return
    path = getattr(args, "check3_plot_passes", None)
    if path is None or not path.is_file():
        return
    if args.holdout_2023:
        step, year = "HOLDOUT_2023", 2023
    else:
        step, year = "SCORE_2024", 2024
    validate_check3_record(path, year=year, step=step)


def _validate_frozen_check4(args: argparse.Namespace) -> None:
    """Refuse conflicting check-4 flags and validate --check4-f8 before scoring."""
    rent_route = getattr(args, "check4_rent_route", None)
    f8_route = getattr(args, "check4_f8", None)
    if rent_route is not None and f8_route is not None:
        raise HoldoutLockError(
            "V14_SCORE: REFUSED: check4 route: expected one of --check4-rent-route or --check4-f8, got both"
        )
    if f8_route is not None:
        load_check4_f8(f8_route)


def _write_check4_summary(check_inputs_path: Path, summary_out: Path) -> dict:
    """Score Check 4 for both estimators and write a strictly non-GBP summary JSON."""
    refuse_2024_price_file(check_inputs_path.name)
    payload = json.loads(check_inputs_path.read_text(encoding="utf-8"))
    if "primary_zones" not in payload or "secondary_zones" not in payload:
        raise ReportAbort("check4 summary needs primary_zones and secondary_zones")
    prim = score_check4_non_gbp(payload["primary_zones"])
    sec = score_check4_non_gbp(payload["secondary_zones"])
    pub = v14.apply_no_switch_publication(
        primary_gating_pass=bool(prim["pass"]),
        secondary_gating_pass=bool(sec["pass"]),
    )
    summary = {
        "kind": "v15_check4_score_summary_v1",
        "status": "scored",
        "gbp_display": False,
        "primary": prim,
        "secondary": sec,
        "publication": pub["outcome"],
    }
    assert_non_gbp_report(summary)
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _extended_main(args: argparse.Namespace) -> int:
    score_dir = args.out.parent
    inputs_sha = _inputs_sha256(args)
    reads = PriceColumnReadLog()
    commit = require_commit_sha(git_commit())
    try:
        _validate_frozen_check3(args)
        _validate_frozen_check4(args)
        if (args.holdout_2023 or args.score_2024) and args.lock_path is None:
            raise HoldoutLockError("--lock-path is required")
        if args.holdout_2023:
            raise_missing_frozen(args, "HOLDOUT_2023")
        frozen_paths = _frozen_paths(args)
        if args.merge_map and frozen_paths is None:
            refuse_2024_price_file(args.merge_map.name)
            assert_merge_map(args.merge_map)
        elif args.merge_map and args.holdout_2023:
            refuse_2024_price_file(args.merge_map.name)
            assert_merge_map(args.merge_map)
        if args.secondary_estimator_json:
            refuse_2024_price_file(args.secondary_estimator_json.name)
        input_paths = _input_paths(args)
        secondary = None
        if args.secondary_estimator_json is not None:
            secondary = secondary_estimator_fields(args.secondary_estimator_json)
        holdout_scores = None
        score_2024_scores = None
        if args.holdout_2023:
            if args.check_inputs is None:
                raise ReportAbort("holdout needs check inputs")
            prepare_holdout_2023(
                score_dir,
                inputs_sha256=inputs_sha,
                commit=commit,
                allow_incident=args.allow_rerun_for_fidelity_bug,
                lock_path=args.lock_path,
            )
            holdout_scores = _score_holdout(args.check_inputs, year=2023)
        if args.score_2024:
            if args.check_inputs is None:
                raise ReportAbort("2024 scoring needs check inputs")
            if args.lock_path is None or not args.lock_path.is_file():
                raise HoldoutLockError(missing_lock_message(args.lock_path or Path("holdout_2023.lock")))
            locked = json.loads(args.lock_path.read_text(encoding="utf-8"))
            if not locked.get("frozen_set"):
                raise HoldoutLockError(
                    "SCORE_2024: REFUSED: lock frozen_set: expected present, got absent"
                )
            if locked.get("score_2024") is True:
                raise HoldoutLockError("second 2024 run refused")
            if frozen_paths is None:
                raise HoldoutLockError(
                    "SCORE_2024: REFUSED: frozen_set: expected complete, got absent\n"
                    + _absent_frozen(_missing_frozen(args), "SCORE_2024")
                )
            assert_frozen_set(locked["frozen_set"], frozen_set_members(frozen_paths))
            assert_2024_allowed(
                lock_path=args.lock_path,
                inputs_sha256=None,
                years=None,
            )
            if args.year_file is not None:
                assert_score_years(read_year_files(list(args.year_file)))
            else:
                check_years = input_years(args.check_inputs)
                unique_years = sorted({int(year) for year in check_years})
                if unique_years != [2024]:
                    rendered = "[" + ", ".join(str(year) for year in unique_years) + "]"
                    raise HoldoutLockError(
                        f"SCORE_2024: REFUSED: input_years: expected [2024], got {rendered}\n"
                        "2024 run refused: input year is not 2024"
                    )
            mark_score_2024(args.lock_path)
            score_2024_scores = _score_holdout(args.check_inputs, year=2024)
        report = build_report(
            input_paths=input_paths,
            price_columns_read=reads.snapshot(),
            commit=commit,
            secondary_estimator=secondary,
        )
        if not args.record_sha8s:
            report.pop("sha8", None)
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
        elif args.check_inputs and not args.score_2024:
            report["checks"] = _check_summary(args.check_inputs)
        if args.score_2024:
            report["score_2024"] = score_2024_scores
            report["checks"] = {
                "status": "scored",
                "full": True,
                "primary_gating_pass": score_2024_scores["primary"]["gating_pass"],
                "secondary_gating_pass": score_2024_scores["secondary"]["gating_pass"],
                "publication": score_2024_scores["publication"]["outcome"],
                "hbu_in_checks": score_2024_scores["checks_include_hbu"],
            }
        if getattr(args, "check4_summary_out", None) is not None:
            if args.check_inputs is None:
                raise ReportAbort("check4 summary needs check inputs")
            report["check4_summary"] = _write_check4_summary(args.check_inputs, args.check4_summary_out)
        write_report(args.out, report)
        if args.holdout_2023:
            write_holdout_lock(
                score_dir,
                inputs_sha256=inputs_sha,
                commit=commit,
                report_sha256=sha256_file(args.out),
                lock_path=args.lock_path,
                frozen_set=frozen_set_members(frozen_paths),
            )
    except Exception as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    print(f"wrote {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
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
    p.add_argument(
        "--lock-path",
        type=Path,
        help="Lock file for --holdout-2023 and --score-2024. Required by both.",
    )
    p.add_argument("--merge-map", type=Path, help="Pinned CA2019 x UR3 merge map. Abort on sha256 mismatch.")
    p.add_argument("--hedonic-coefs", type=Path, help="2021-22 hedonic coefficients in the frozen set.")
    p.add_argument("--sha8-block", type=Path, help="Code sha8 block in the frozen set.")
    p.add_argument("--check3-plot-passes", type=Path)
    p.add_argument("--check4-rent-route", type=Path)
    p.add_argument("--check4-f8", type=Path)
    p.add_argument("--check4-summary-out", type=Path)
    p.add_argument("--ur6", type=Path)
    p.add_argument("--dz2022-keys", type=Path)
    p.add_argument("--builder-output", type=Path, help="Year file. Recorded, not locked.")
    p.add_argument("--primary-estimates", type=Path, help="Year file. Recorded, not locked.")
    p.add_argument("--fitted-per-zone", type=Path, help="Year file. Recorded, not locked.")
    p.add_argument("--year-file", action="append", type=Path, default=None, help="Year file checked by input_years.")
    args = p.parse_args(argv)
    if _extended(args):
        return _extended_main(args)
    return _legacy(args)


if __name__ == "__main__":
    raise SystemExit(main())
