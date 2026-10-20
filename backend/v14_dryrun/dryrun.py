"""Synthetic dry run for the v1.4 steps this PR covers.

B2, the DRC component writer, B1, and the 2023 primary writer run as the
real commands. Pin tables for synthetic files are copies, then restored
where a module global is patched.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import openpyxl

from georgist.rent_table_pooled import RENT_TABLE_COLUMNS
from georgist.v14_real_headers import REAL_HEADERS
from georgist.v14_b2 import PIN_TABLE as B2_PINS
from georgist.v14_d7_chain import PIN_TABLE as D7_PINS
from georgist.v14_d7_chain import execute_filter1, execute_filter2, sha256_file
from georgist.v14_score_report import PIN_TABLE as MERGE_PINS
from georgist.v14_score_report import code_text_disagreements
from scripts.build_v14_b2 import main as b2_main
from scripts.build_v14_check_inputs import main as b6_main
from scripts.build_v14_check_sources import (
    copy_pin_table as copy_source_pins,
    save_check3,
    save_check4,
    save_dz2022,
    save_ur6,
)
from scripts.build_v14_drc import main as b1_main
from scripts.build_v14_drc_components import build_components, copy_pin_table, sha256_file as pin_sha
from scripts.build_v14_drc_components import write_components
from scripts.build_v14_primary_2023 import main as primary_main
from scripts.fit_v14_hedonic import main as fit_main
from scripts.rerun_v14_score import main as score_main

FILTERS = Path(__file__).resolve().parents[1] / "georgist" / "d7_filters"


def _stamp_year(source: Path, dest: Path, *, cell: str | None = None) -> None:
    """SYNTHETIC 2024 year file. Copies the synthetic 2023 rows and sets the year."""
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["label"] = "SYNTHETIC"
    for zone in payload.get("zones") or []:
        zone["year"] = 2024
        if cell is not None:
            zone["cell"] = cell
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
            count_tail = [
                "Number of sales",
                "6",
                "Number of sales",
                "c",
                str(40 + index),
                "1.0",
                "IZ1",
                "CA1",
                "urban",
                "0.2",
            ]
            price_tail = [
                "GBP",
                price,
                "6",
                "c",
                str(40 + index),
                "1.0",
                "IZ1",
                "CA1",
                "urban",
                "0.2",
            ]
            rows.append([*common, "Count", *count_tail])
            rows.append([*common, "Mean", *price_tail])
            rows.append([*common, "Median", *price_tail])
            rows.append([*common, "Lower Quartile", *price_tail])
            rows.append([*common, "Upper Quartile", *price_tail])
    return rows


def _filled(name: str, values: dict[str, str]) -> list[str]:
    return [values.get(column, "") for column in REAL_HEADERS[name]]


def _epc_row(zone: str) -> list[str]:
    values = {column: "" for column in REAL_HEADERS["epc"]}
    values["code"] = zone
    for column in REAL_HEADERS["epc"]:
        if "age_" in column and column.endswith("_share"):
            values[column] = "1" if column == "age_pre1919_share" else "0"
    return _filled("epc", values)


def _nrs_row(zone: str) -> list[str]:
    values = {column: "" for column in REAL_HEADERS["nrs2017"]}
    values["code"] = zone
    for column in REAL_HEADERS["nrs2017"]:
        if column.startswith("type_"):
            values[column] = "10" if column == "type_detached" else "0"
    return _filled("nrs2017", values)


def _plot_band_row(zone: str) -> list[str]:
    values = {column: "" for column in REAL_HEADERS["plot_bands"]}
    values["code"] = zone
    values["all_ages_share_lt005"] = "0.5"
    values["all_ages_share_005_010"] = "0.25"
    values["all_ages_share_gt010"] = "0.25"
    values["n_detached_all_ages_matched"] = "4"
    return _filled("plot_bands", values)


def _ur6_row(zone: str, ur6_class: str) -> list[str]:
    values = {column: "" for column in REAL_HEADERS["ur6"]}
    values["code"] = zone
    values["ur6_class"] = ur6_class
    values["ur6_name"] = "SYNTHETIC"
    values["ur8_code"] = ur6_class
    values["source"] = "SYNTHETIC"
    values["licence"] = "OGL-3.0"
    return _filled("ur6", values)


def _cross_row(dz2011: str, dz2022: str, count: str) -> list[str]:
    values = {column: "" for column in REAL_HEADERS["crosswalk"]}
    values["dz2011_code"] = dz2011
    values["dz2022_code"] = dz2022
    values["uprn_count"] = count
    return _filled("crosswalk", values)


def _write_n25i(path: Path, zones: list[str]) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "2025"
    sheet.append(["SYNTHETIC"])
    sheet.append([None])
    sheet.append([None])
    sheet.append([None])
    header = list(REAL_HEADERS["n25i"])
    sheet.append(header)
    for zone in zones:
        row = []
        for column in header:
            if column == "Data Zone code":
                row.append(zone)
            elif column == "Council area code":
                row.append("S12000001")
            elif column in {"Data zone name", "Council area name"}:
                row.append("SYNTHETIC")
            elif column == "Total number of dwellings":
                row.append("10")
            else:
                row.append("0")
        sheet.append(row)
    workbook.save(path)


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
        _write(epc, list(REAL_HEADERS["epc"]), [_epc_row(zone) for zone in zones])
        _write(nrs, list(REAL_HEADERS["nrs2017"]), [_nrs_row(zone) for zone in zones])
        _write(plots, list(REAL_HEADERS["plot_bands"]), [_plot_band_row(zone) for zone in zones])
        _write(ur6, list(REAL_HEADERS["ur6"]), [_ur6_row(zone, "1") for zone in zones])
        n25i = root / "n25i.xlsx"
        _write_n25i(n25i, list(zones))
        pins = copy_pin_table()
        pins["epc"] = pin_sha(epc)
        pins["nrs2017"] = pin_sha(nrs)
        pins["plot_bands"] = pin_sha(plots)
        pins["ur6"] = pin_sha(ur6)
        pins["n25i"] = pin_sha(n25i)
        records = build_components(
            {"epc": epc, "nrs2017": nrs, "plot_bands": plots, "ur6": ur6, "n25i": n25i},
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
        fit_path = root / "fitted_hedonic_2023.json"
        per_zone = root / "fitted_per_zone.json"
        fit_code = fit_main(
            ["--b2-out", str(dest), "--fit-out", str(fit_path), "--per-zone-out", str(per_zone)]
        )
        if fit_code != 0:
            raise RuntimeError("B3 dry run failed")
        check3 = root / "check3.json"
        check4 = root / "check4.json"
        dz_keys = root / "dz2022_keys.json"
        ur6_out = root / "ur6_source.json"
        plot_src = root / "check3_plots.csv"
        gis_src = root / "check3_houses.csv"
        rent_src = root / "rent_table.csv"
        walk_src = root / "dz_crosswalk.csv"
        _write(
            plot_src,
            [
                "code",
                "pass_20",
                "pass_30",
                "pass_40",
                "all_20",
                "all_30",
                "all_40",
                "dz22_20",
                "dz22_30",
                "dz22_40",
                "detached_plot_m2",
                "measured_detached_pass",
            ],
            [[zone, "1", "1", "1", "1", "1", "1", "1", "1", "1", "40", "1"] for zone in zones],
        )
        _write(gis_src, ["code", "house_plot_m2"], [[zone, "20"] for zone in zones])
        rent_header = list(RENT_TABLE_COLUMNS)
        rent_rows = []
        for zone in zones:
            item = {name: "1" for name in rent_header}
            item["zone_id"] = zone
            item["central"] = "4"
            item["low"] = "1"
            item["status"] = "observed_pooled"
            rent_rows.append([item[name] for name in rent_header])
        for index in range(129):
            item = {name: "1" for name in rent_header}
            item["zone_id"] = f"P{index}"
            item["status"] = "model_fill_pending"
            rent_rows.append([item[name] for name in rent_header])
        for index in range(3):
            item = {name: "1" for name in rent_header}
            item["zone_id"] = f"N{index}"
            item["status"] = "not_applicable"
            rent_rows.append([item[name] for name in rent_header])
        _write(rent_src, rent_header, rent_rows)
        _write(
            walk_src,
            list(REAL_HEADERS["crosswalk"]),
            [_cross_row(zone, zone, "1") for zone in zones],
        )
        source_pins = copy_source_pins()
        source_pins["plot_bands"] = pin_sha(plot_src)
        source_pins["gis_house_plot"] = pin_sha(gis_src)
        source_pins["rent_table"] = pin_sha(rent_src)
        source_pins["crosswalk"] = pin_sha(walk_src)
        ur6_in = root / "ur6_classes.csv"
        _write(ur6_in, list(REAL_HEADERS["ur6"]), [_ur6_row(zone, "1") for zone in zones])
        source_pins["ur6"] = pin_sha(ur6_in)
        save_check3({"plot_bands": plot_src, "gis_house_plot": gis_src}, check3, pins=source_pins)
        save_check4(rent_src, check4, pins=source_pins)
        save_dz2022(walk_src, primary, dz_keys, pins=source_pins)
        save_ur6(ur6_in, ur6_out, pins=source_pins)
        b6_out = root / "checks.json"
        b6_paths = {
            "builder_output": builder,
            "primary_estimates": primary,
            "fitted_hedonic": per_zone,
            "check3_plot_passes": check3,
            "check4_rent_route": check4,
            "dz2022_keys": dz_keys,
            "ur6": ur6_out,
        }
        b6_argv = ["--out", str(b6_out), "--year", "2023"]
        for name, path in b6_paths.items():
            b6_argv.extend([f"--{name.replace('_', '-')}", str(path), "--pin", f"{name}={pin_sha(path)}"])
        if b6_main(b6_argv) != 0:
            raise RuntimeError("B6 dry run failed")
        merge = root / "merge.csv"
        coefs = fit_path
        sha8_block = root / "sha8.json"
        _write(merge, ["dz2011", "cell"], [["S01", "c"]])
        sha8_block.write_text('{"label": "SYNTHETIC"}\n', encoding="utf-8")
        saved_merge = MERGE_PINS["merge_map"]
        MERGE_PINS["merge_map"] = pin_sha(merge)
        try:
            report = root / "holdout" / "report.json"
            lock = root / "holdout.lock"
            score_code = score_main(
                [
                    "--out",
                    str(report),
                    "--holdout-2023",
                    "--check-inputs",
                    str(b6_out),
                    "--lock-path",
                    str(lock),
                    "--merge-map",
                    str(merge),
                    "--hedonic-coefs",
                    str(coefs),
                    "--sha8-block",
                    str(sha8_block),
                    "--check3-plot-passes",
                    str(check3),
                    "--check4-rent-route",
                    str(check4),
                    "--ur6",
                    str(ur6_out),
                    "--dz2022-keys",
                    str(dz_keys),
                ]
            )
            if score_code != 0:
                raise RuntimeError("H dry run failed")
            s2_builder = root / "s2_builder.json"
            s2_primary = root / "s2_primary.json"
            s2_fitted = root / "s2_fitted.json"
            _stamp_year(builder, s2_builder)
            _stamp_year(primary, s2_primary)
            _stamp_year(per_zone, s2_fitted, cell="c")
            checks_2024 = root / "s4_checks.json"
            s4_paths = {
                "builder_output": s2_builder,
                "primary_estimates": s2_primary,
                "fitted_hedonic": s2_fitted,
                "check3_plot_passes": check3,
                "check4_rent_route": check4,
                "dz2022_keys": dz_keys,
                "ur6": ur6_out,
            }
            s4_argv = [
                "--out",
                str(checks_2024),
                "--year",
                "2024",
                "--lock",
                str(lock),
                "--hedonic-coefs",
                str(coefs),
            ]
            for name, path in s4_paths.items():
                s4_argv.extend(
                    [f"--{name.replace('_', '-')}", str(path), "--pin", f"{name}={pin_sha(path)}"]
                )
            if b6_main(s4_argv) != 0:
                raise RuntimeError("S4 dry run failed")
            report_2024 = root / "s5" / "report.json"
            s5_code = score_main(
                [
                    "--out",
                    str(report_2024),
                    "--score-2024",
                    "--check-inputs",
                    str(checks_2024),
                    "--lock-path",
                    str(lock),
                    "--merge-map",
                    str(merge),
                    "--hedonic-coefs",
                    str(coefs),
                    "--sha8-block",
                    str(sha8_block),
                    "--check3-plot-passes",
                    str(check3),
                    "--check4-rent-route",
                    str(check4),
                    "--ur6",
                    str(ur6_out),
                    "--dz2022-keys",
                    str(dz_keys),
                    "--builder-output",
                    str(s2_builder),
                    "--primary-estimates",
                    str(s2_primary),
                    "--fitted-per-zone",
                    str(s2_fitted),
                ]
            )
            if s5_code != 0:
                raise RuntimeError("S5 dry run failed")
        finally:
            MERGE_PINS["merge_map"] = saved_merge
        open_rows = [row["id"] for row in code_text_disagreements() if row["status"] in {"open", "pending"}]
        if open_rows:
            raise RuntimeError("open disagreement rows: " + ", ".join(open_rows))
        return {
            "out": dest,
            "components": components,
            "drc": drc,
            "primary": primary,
            "builder": builder,
            "fit": fit_path,
            "per_zone": per_zone,
            "checks": b6_out,
            "report": report,
            "lock": lock,
            "checks_2024": checks_2024,
            "score_2024": report_2024,
            "year_files": {
                "builder_output": s2_builder,
                "primary_estimates": s2_primary,
                "fitted_per_zone": s2_fitted,
            },
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
