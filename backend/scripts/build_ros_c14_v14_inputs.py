#!/usr/bin/env python3
"""Build v1.4 DZ2011 inputs from RoS C14 counts.

The reader requests year, data zone, data zone code and volume only.
Printout is counts and flags. JSON goes under out/ (gitignored).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from georgist.ros_c14_input import (
    InputBuildError,
    build_inputs,
    load_cost_availability,
    write_outputs,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_head() -> str:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return done.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c14", type=Path, required=True)
    parser.add_argument("--lookup", type=Path, required=True)
    parser.add_argument("--crosswalk", type=Path, required=True)
    parser.add_argument("--merge-map", type=Path, required=True)
    parser.add_argument("--ur", type=Path, required=True)
    parser.add_argument("--frozen-plan", type=Path, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "out" / "v14_inputs" / "ros2024_dz2011_inputs.json",
    )
    parser.add_argument(
        "--shares-out",
        type=Path,
        default=REPO_ROOT / "out" / "v14_inputs" / "primary_shares.json",
    )
    parser.add_argument("--scored-run", action="store_true")
    parser.add_argument("--estimates-json", type=Path, default=None)
    parser.add_argument(
        "--cost-availability-json",
        type=Path,
        default=None,
        help="Price and rebuild cost. unavailable comes only from residual_land_value.",
    )
    parser.add_argument(
        "--exclusion-list",
        type=Path,
        default=None,
        help="Pinned DZ2011 exclusion list. Checked only for a 7,392-code lookup.",
    )
    parser.add_argument("--main-commit", default="")
    parser.add_argument(
        "--synthetic-fixtures",
        action="store_true",
        help="Synthetic fixture run. Skips the production sha pins.",
    )
    args = parser.parse_args(argv)
    estimates = None
    if args.estimates_json is not None:
        estimates = json.loads(args.estimates_json.read_text(encoding="utf-8"))
    commit = args.main_commit or _git_head()
    try:
        costs = None
        if args.cost_availability_json is not None:
            costs = load_cost_availability(args.cost_availability_json)
        result = build_inputs(
            c14_path=args.c14,
            lookup_path=args.lookup,
            crosswalk_path=args.crosswalk,
            merge_map_path=args.merge_map,
            ur_path=args.ur,
            frozen_plan_path=args.frozen_plan,
            scored_run=args.scored_run,
            estimates=estimates,
            cost_availability=costs,
            exclusion_list_path=args.exclusion_list,
            main_commit_sha=commit,
            check_pins=not args.synthetic_fixtures,
        )
    except InputBuildError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    write_outputs(result, args.out, shares_path=args.shares_out if args.scored_run else None)
    sys.stdout.write(result["printout"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
