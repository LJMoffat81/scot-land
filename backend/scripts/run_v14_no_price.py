#!/usr/bin/env python3
"""No-price check run. Stops after check_sources.

Order: drc_components, build_v14_drc, b2, check_sources --year 2023 --no-price.
check_inputs, the fit, primary_2023 and scoring are not part of this run.

Usage (from ``backend/``)::

    python -m scripts.run_v14_no_price --root out/no_price --year 2023 --no-price
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.build_v14_b2 import main as b2_main
from scripts.build_v14_check_inputs import main as check_inputs_main
from scripts.build_v14_check_sources import main as check_sources_main
from scripts.build_v14_drc import main as drc_main
from scripts.build_v14_drc_components import main as components_main
from scripts.build_v14_primary_2023 import main as primary_2023_main
from scripts.fit_v14_hedonic import main as fit_main
from scripts.rerun_v14_score import main as score_main

# Imported so the no-price run can be spied. None of these are called.
STOPPED_AFTER_CHECK_SOURCES = (check_inputs_main, fit_main, primary_2023_main, score_main)


def run_no_price(root: Path, year: str) -> int:
    """Run the four no-price steps and return the first non-zero status."""
    components = root / "components.json"
    code = components_main(
        [
            "--out",
            str(components),
            "--epc",
            str(root / "epc.csv"),
            "--nrs2017",
            str(root / "nrs2017.csv"),
            "--plot-bands",
            str(root / "plot_bands.csv"),
            "--ur6",
            str(root / "ur6.csv"),
            "--n25i",
            str(root / "n25i.xlsx"),
        ]
    )
    if code != 0:
        return code
    code = drc_main(["--drc-json", str(root / "drc.json"), "--components", str(components)])
    if code != 0:
        return code
    code = b2_main(
        [
            "--out",
            str(root / "b2.json"),
            "--no-price",
            "--house-sales",
            str(root / "house_sales.csv"),
            "--plot-split",
            str(root / "plot_split.csv"),
            "--crosswalk",
            str(root / "crosswalk.csv"),
            "--sold-tfa",
            str(root / "sold_tfa.csv"),
            "--access",
            str(root / "access.csv"),
            "--bedrooms",
            str(root / "bedrooms.csv"),
            "--filter1-script",
            str(root / "filter1.py"),
            "--filter1-output",
            str(root / "filter1.csv"),
            "--filter2-script",
            str(root / "filter2.py"),
            "--filter2-output",
            str(root / "filter2.csv"),
        ]
    )
    if code != 0:
        return code
    return check_sources_main(
        [
            "--year",
            year,
            "--no-price",
            "--plot-bands",
            str(root / "check3_plots.csv"),
            "--gis-house-plot",
            str(root / "gis_house_plot.csv"),
            "--check3-out",
            str(root / "check3.json"),
            "--rent-table",
            str(root / "rent_table.csv"),
            "--check4-out",
            str(root / "check4.json"),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--year", required=True)
    parser.add_argument("--no-price", action="store_true")
    args = parser.parse_args(argv)
    if not args.no_price:
        sys.stderr.write("no-price check run requires --no-price\n")
        return 1
    return run_no_price(args.root, args.year)


if __name__ == "__main__":
    raise SystemExit(main())
