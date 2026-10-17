"""Synthetic dry run for the v1.4 steps this PR covers.

B2, the DRC component writer, B1, and the 2023 primary writer run as the
real commands. Pin tables for synthetic files are copies, then restored
where a module global is patched.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from georgist.v14_b2 import PIN_TABLE as B2_PINS
from georgist.v14_d7_chain import PIN_TABLE as D7_PINS
from georgist.v14_d7_chain import execute_filter1, execute_filter2, sha256_file
from georgist.v14_score_report import code_text_disagreements
from scripts.build_v14_b2 import main as b2_main
from scripts.build_v14_drc import main as b1_main
from scripts.build_v14_drc_components import build_components, copy_pin_table, sha256_file as pin_sha
from scripts.build_v14_drc_components import write_components
from scripts.build_v14_primary_2023 import main as primary_main

FILTERS = Path(__file__).resolve().parents[1] / "georgist" / "d7_filters"


def _write(path: Path, header: list[str], rows: list[list[str]], *, comment: bool = True) -> None:
    buffer = io.StringIO()
    if comment:
        buffer.write("# SYNTHETIC\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8")


def _sales_rows() -> list[list[str]]:
    rows = []
    for index, zone in enumerate(("Z1", "Z2", "Z3", "Z4")):
        for year in (2021, 2022, 2023):
            price = str(10 + index)
            common = [zone, "SYNTHETIC zone", "2011 Data Zones", str(year)]
            tail = ["GBP", price, "6", "c", str(40 + index), "1.0", "IZ1", "CA1", "urban", "0.2"]
            rows.append([*common, "Mean", *tail])
            rows.append([*common, "Median", *tail])
    return rows


def _sold_rows() -> list[list[str]]:
    rows = []
    for index, zone in enumerate(("Z1", "Z2", "Z3", "Z4")):
        for year in range(2019, 2024):
            rows.append([zone, str(year), str(50 + index)])
    return rows


def run(root: Path) -> dict:
    """Run B2 on synthetic files. Pins are restored before returning."""
    root.mkdir(parents=True, exist_ok=True)
    sales = root / "house_sales.csv"
    plots = root / "plot_split.csv"
    crosswalk = root / "crosswalk.csv"
    sold = root / "sold_tfa.csv"
    access = root / "access.csv"
    bedrooms = root / "bedrooms.csv"
    out1 = root / "filter1.csv"
    out2 = root / "filter2.csv"
    dest = root / "b2.json"
    sales_header = [
        "GeographyCode",
        "GeographyName",
        "GeographyType",
        "DateCode",
        "Measurement",
        "Units",
        "Value",
        "Sales",
        "cell",
        "a_m2",
        "ratio_mean",
        "iz",
        "ca",
        "ur3",
        "flat_share",
    ]
    _write(sales, sales_header, _sales_rows())
    _write(plots, ["dz2022_code", "method_flags"], [["Z1", "low_parcel_coverage_lt0.5"]])
    _write(crosswalk, ["dz2011_code", "dz2022_code", "uprn_count"], [["D1", "Z1", "4"]])
    sold_rows = [row + ["SYNTHETIC"] for row in _sold_rows()]
    _write(sold, ["code", "year", "sold_tfa_mean", "label"], sold_rows, comment=False)
    _write(access, ["code", "vintage", "job_access"], [["Z1", "2011", "1.5"]])
    _write(
        bedrooms,
        ["dz2022_code", "households_total", "share_1", "share_3", "share_4plus"],
        [["Z1", "10", "0.5", "0.3", "0.2"]],
    )
    script1 = FILTERS / "filter1_drop_year_2024.py"
    script2 = FILTERS / "filter2_keep_2019_2023.py"
    saved_d7 = dict(D7_PINS)
    saved_b2 = dict(B2_PINS)
    try:
        execute_filter1(script1, sold, out1)
        execute_filter2(script2, out1, out2)
        data_rows = [line for line in out2.read_text(encoding="utf-8").splitlines() if line.strip()][1:]
        D7_PINS["source"] = sha256_file(sold)
        D7_PINS["filter1_output"] = sha256_file(out1)
        D7_PINS["filter2_output"] = sha256_file(out2)
        D7_PINS["row_count"] = len(data_rows)
        B2_PINS["low_parcel_count"] = 1
        B2_PINS["house_sales"] = sha256_file(sales)
        code = b2_main(
            [
                "--out",
                str(dest),
                "--house-sales",
                str(sales),
                "--plot-split",
                str(plots),
                "--crosswalk",
                str(crosswalk),
                "--sold-tfa",
                str(sold),
                "--access",
                str(access),
                "--bedrooms",
                str(bedrooms),
                "--filter1-script",
                str(script1),
                "--filter1-output",
                str(out1),
                "--filter2-script",
                str(script2),
                "--filter2-output",
                str(out2),
            ]
        )
        if code != 0:
            raise RuntimeError("B2 dry run failed")
        epc = root / "epc.csv"
        nrs = root / "nrs.csv"
        plots = root / "plots.csv"
        ur6 = root / "ur6.csv"
        components = root / "components.json"
        drc = root / "drc.json"
        primary = root / "primary_estimates_2023.json"
        builder = root / "builder_output_2023.json"
        zones = ("Z1", "Z2", "Z3", "Z4")
        _write(
            epc,
            ["code", "age_pre1919_share"],
            [[zone, "1"] for zone in zones],
        )
        _write(
            nrs,
            ["code", "type_detached", "type_semi_detached", "type_terraced", "type_flat", "type_unknown"],
            [[zone, "10", "0", "0", "0", "0"] for zone in zones],
        )
        _write(
            plots,
            [
                "code",
                "all_ages_share_lt005",
                "all_ages_share_005_010",
                "all_ages_share_gt010",
                "n_detached_all_ages_matched",
            ],
            [[zone, "0.5", "0.25", "0.25", "4"] for zone in zones],
        )
        _write(
            ur6,
            ["code", "council_code", "ur6_class"],
            [[zone, "A", "1"] for zone in zones],
        )
        pins = copy_pin_table()
        pins["epc"] = pin_sha(epc)
        pins["nrs2017"] = pin_sha(nrs)
        pins["plot_bands"] = pin_sha(plots)
        pins["ur6"] = pin_sha(ur6)
        records = build_components(
            {"epc": epc, "nrs2017": nrs, "plot_bands": plots, "ur6": ur6},
            pins=pins,
        )
        write_components(components, records)
        b1_code = b1_main(["--drc-json", str(drc), "--components", str(components)])
        if b1_code != 0:
            raise RuntimeError("B1 dry run failed")
        primary_code = primary_main(
            [
                "--b2-out",
                str(dest),
                "--drc",
                str(drc),
                "--primary-out",
                str(primary),
                "--builder-out",
                str(builder),
            ]
        )
        if primary_code != 0:
            raise RuntimeError("2023 primary dry run failed")
        open_rows = [row["id"] for row in code_text_disagreements() if row["status"] in {"open", "pending"}]
        if open_rows:
            raise RuntimeError("open disagreement rows: " + ", ".join(open_rows))
        return {
            "out": dest,
            "components": components,
            "drc": drc,
            "primary": primary,
            "builder": builder,
            "status": "passed",
        }
    finally:
        D7_PINS.clear()
        D7_PINS.update(saved_d7)
        B2_PINS.clear()
        B2_PINS.update(saved_b2)


def main() -> int:
    run(Path("out") / "v14_dryrun_pr2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
