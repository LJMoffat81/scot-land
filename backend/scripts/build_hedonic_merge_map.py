#!/usr/bin/env python3
"""Build the v1.4 O-MM hedonic cell merge map (counts + A_z only).

Writes the merge-map CSV under a gitignored path (default
``data/external/hedonic/merge_map_v14.csv``) and prints its sha256 to stdout.

Never loads price/value/rent columns. Tie-break seed is
``seeds.hedonic_cluster_bootstrap`` from ``--freeze-json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from georgist.hedonic_merge_map import (
    DEFAULT_PREREG_FREEZE_PATH,
    PRODUCTION_INPUT_PINS,
    build_merge_map_from_paths,
    file_sha256,
    load_seed_from_prereg_freeze,
    write_merge_map,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "data" / "external" / "hedonic" / "merge_map_v14.csv"

# Spec §3.1 default locations (box paths); override with flags / env as needed.
DEFAULTS = {
    "counts": Path("/workspace/ros/house_sales.csv"),
    "counts_fallback": REPO_ROOT
    / "data"
    / "processed"
    / "methods_code_1"
    / "pr1"
    / "ros_dz2011_sales_n_2019_2023.csv",
    "plot_split": Path("/workspace/scotland-rules/v13_plot_split/dz2022_plot_split_v13.csv"),
    "plot_split_repo": REPO_ROOT / "data" / "reference" / "v13" / "dz2022_plot_split_v13.csv",
    "uprn_weights": Path("/workspace/scotland-gis/out/dz2011_dz2022_uprn_weights.csv"),
    "ur": Path("/workspace/scotland-rules/ur6/dz2011_urban_rural_6fold_2020.csv"),
    "ur_official": REPO_ROOT
    / "data"
    / "external"
    / "hedonic"
    / "dz2011_urban_rural_6fold_2020_urc2020.csv",
    "ur_fallback": REPO_ROOT / "data" / "processed" / "dz2011_urban_rural_2020.csv",
    "spd": Path("/workspace/scotland-gis/raw/spd_postcodeindex_cut_26_2_csv.zip"),
    "spd_fallback": REPO_ROOT / "data" / "external" / "raw" / "spd_postcodeindex_cut_26_2_csv.zip",
}


def _resolve(primary: Path, *fallbacks: Path) -> Path:
    if primary.is_file():
        return primary
    for fb in fallbacks:
        if fb.is_file():
            return fb
    return primary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--counts", type=Path, default=None, help="Sale COUNT file (no prices)")
    p.add_argument("--plot-split", type=Path, default=None, help="DZ2022 plot_split CSV")
    p.add_argument("--uprn-weights", type=Path, default=None, help="DZ2011↔DZ2022 UPRN weights")
    p.add_argument("--ur", type=Path, default=None, help="DZ2011 urban-rural lookup (URC 2020)")
    p.add_argument("--spd-zip", type=Path, default=None, help="SPD 2026/2 postcode index zip")
    p.add_argument(
        "--freeze-json",
        type=Path,
        default=DEFAULT_PREREG_FREEZE_PATH,
        help=(
            "v14_prereg_freeze.json — reads seeds.hedonic_cluster_bootstrap. "
            f"Default: {DEFAULT_PREREG_FREEZE_PATH}"
        ),
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output CSV (gitignored). Default: {DEFAULT_OUT}",
    )
    args = p.parse_args(argv)

    try:
        seed = load_seed_from_prereg_freeze(args.freeze_json)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (ValueError, json.JSONDecodeError, TypeError) as exc:
        print(f"freeze-json seed error: {exc}", file=sys.stderr)
        return 2

    counts = args.counts or _resolve(DEFAULTS["counts"], DEFAULTS["counts_fallback"])
    plot_split = args.plot_split or _resolve(
        DEFAULTS["plot_split"], DEFAULTS["plot_split_repo"]
    )
    uprn = args.uprn_weights or DEFAULTS["uprn_weights"]
    ur = args.ur or _resolve(
        DEFAULTS["ur"], DEFAULTS["ur_official"], DEFAULTS["ur_fallback"]
    )
    spd = args.spd_zip or _resolve(DEFAULTS["spd"], DEFAULTS["spd_fallback"])

    missing = [
        ("counts", counts),
        ("plot_split", plot_split),
        ("uprn_weights", uprn),
        ("ur", ur),
        ("spd_zip", spd),
    ]
    absent = [f"{name}: {path}" for name, path in missing if not path.is_file()]
    if absent:
        print("MISSING input data files:", file=sys.stderr)
        for line in absent:
            print(f"  {line}", file=sys.stderr)
        return 2

    print(f"seed={seed} from seeds.hedonic_cluster_bootstrap in {args.freeze_json}", file=sys.stderr)
    print(f"counts path={counts} sha256={file_sha256(counts)}", file=sys.stderr)
    print(f"ur path={ur} sha256={file_sha256(ur)}", file=sys.stderr)
    print(
        f"pinned ur6_dz2011 sha256={PRODUCTION_INPUT_PINS['ur']['sha256']} "
        f"(path {PRODUCTION_INPUT_PINS['ur']['path']})",
        file=sys.stderr,
    )
    print(
        f"pinned counts sha256={PRODUCTION_INPUT_PINS['counts']['sha256']}",
        file=sys.stderr,
    )

    rows = build_merge_map_from_paths(
        counts_path=counts,
        plot_split_path=plot_split,
        uprn_weights_path=uprn,
        ur_path=ur,
        spd_zip=spd,
        seed=int(seed),
    )
    digest = write_merge_map(args.out, rows)
    print(digest)
    print(f"wrote {args.out} ({len(rows)} zones)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
