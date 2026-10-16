"""Write v1.4 primary inputs.

Default mode writes depreciation sensitivities and the median label. It does
not read a price column. ``--scored-run`` is the only entry point that may
read C14 total value. Prices are written under the output directory and are
not printed.

Usage (from ``backend/``)::

    python -m scripts.build_v14_primary_inputs --out-dir /tmp/v14_inputs
    python -m scripts.build_v14_primary_inputs --scored-run --c14 ... --drc-json ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from georgist import surface_rent as sr
from georgist.ros_c14_input import InputBuildError, build_inputs
from georgist.ros_c14_prices import (
    MEDIAN_SENSITIVITY,
    PriceColumnError,
    crosswalk_means,
    dz2022_status_map,
    read_value_volume,
)
from georgist.v14_primary_inputs import (
    cost_availability_for_scored,
    primary_estimates,
    write_information_files,
    write_scored_inputs,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "out" / "v14_inputs")
    parser.add_argument("--scored-run", action="store_true")
    parser.add_argument("--c14", type=Path, default=None)
    parser.add_argument("--lookup", type=Path, default=None)
    parser.add_argument("--crosswalk", type=Path, default=None)
    parser.add_argument("--merge-map", type=Path, default=None)
    parser.add_argument("--ur", type=Path, default=None)
    parser.add_argument("--drc-json", type=Path, default=None)
    parser.add_argument("--frozen-plan", type=Path, default=None)
    parser.add_argument("--synthetic-fixtures", action="store_true")
    return parser


def _require(args: argparse.Namespace) -> None:
    missing = [
        name
        for name in ("c14", "lookup", "crosswalk", "merge_map", "ur", "drc_json")
        if getattr(args, name) is None
    ]
    if missing:
        raise InputBuildError("scored run needs " + ", ".join(missing))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        write_information_files(args.out_dir, sr.load_config())
        if not args.scored_run:
            sys.stdout.write("scored_run=false price_columns_read=false\n")
            sys.stdout.write(f"median_sensitivity={MEDIAN_SENSITIVITY}\n")
            return 0
        _require(args)
        inputs = build_inputs(
            c14_path=args.c14,
            lookup_path=args.lookup,
            crosswalk_path=args.crosswalk,
            merge_map_path=args.merge_map,
            ur_path=args.ur,
            frozen_plan_path=args.frozen_plan,
            scored_run=False,
            check_pins=not args.synthetic_fixtures,
        )
        value_volume = read_value_volume(args.c14, scored_run=True)
        means = crosswalk_means(
            dz2022_status=dz2022_status_map(inputs),
            crosswalk_path=args.crosswalk,
            value_volume_by_dz2022=value_volume,
        )
        drc = {
            str(code).strip().upper(): float(value)
            for code, value in json.loads(args.drc_json.read_text(encoding="utf-8")).items()
        }
        scored = [
            str(zone["dz2011"])
            for zone in inputs["dz2011"]
            if zone["status"] == "scored"
        ]
        costs = cost_availability_for_scored(scored, means, drc)
        estimates = primary_estimates(costs)
        write_scored_inputs(args.out_dir, costs, estimates)
    except (InputBuildError, PriceColumnError, ValueError) as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stdout.write("scored_run=true price_columns_read=true\n")
    sys.stdout.write(f"zones={len(costs)}\n")
    sys.stdout.write(f"median_sensitivity={MEDIAN_SENSITIVITY}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
