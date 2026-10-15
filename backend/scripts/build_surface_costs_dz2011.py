"""CLI: rebuild-cost rows for every DZ2011 zone (SURFACE-COSTS-ALL).

Writes a gitignored CSV (default ``data/external/methods_runs/surface_costs_dz2011.csv``)
with one row per 2011 data zone (6,976). No price inputs; no 2011→2022 conversion.

Usage (from ``backend/``)::

    python -m scripts.build_surface_costs_dz2011
    python -m scripts.build_surface_costs_dz2011 --out /tmp/costs.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from georgist import surface_costs as sc

LOG = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output CSV (default: data/external/methods_runs/surface_costs_dz2011.csv)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    out = args.out if args.out is not None else sc.default_output_path()
    path, rows = sc.build_and_write(out_path=out)
    na = sum(1 for r in rows if r["rebuild_status"] == sc.NA_STATUS)
    LOG.info("wrote %s rows (%s n/a) to %s", len(rows), na, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
