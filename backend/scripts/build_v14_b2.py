#!/usr/bin/env python3
"""B2 adapters for the pinned v1.4 inputs.

The sold-TFA file is accepted only through the D7 provenance chain. The
DZ2022 low-parcel flag count must equal the pin (1,038 unless a test replaces
the pin table). This command does not score and does not read a 2024 price.

Usage (from ``backend/``)::

    python -m scripts.build_v14_b2 --out rows.json --house-sales sales.csv ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from georgist.v14_b2 import (
    FIDELITY_ADAPTATION,
    PIN_TABLE,
    B2Error,
    _jsonable,
    adapt_access,
    adapt_bedrooms,
    adapt_crosswalk,
    adapt_house_sales,
    adapt_plot_split,
    adapt_sold_tfa,
)
from georgist.v14_d7_chain import (
    D7ChainResult,
    run_d7_chain,
    sha256_file,
)
from georgist.v14_hedonic import FIT_YEARS, fit_headline


def _fit_rows(sales: list[dict], floors: list[dict]) -> list[dict]:
    """Rows made only from adapted fields. Nothing is added by the caller."""
    floor_by = {(str(row["zone"]), int(row["year"])): row["sold_tfa_mean"] for row in floors}
    built = []
    for sale in sales:
        if int(sale["year"]) not in FIT_YEARS:
            continue
        key = (str(sale["zone"]), int(sale["year"]))
        if key not in floor_by:
            continue
        row = {
            "zone": sale["zone"],
            "year": int(sale["year"]),
            "price": sale["price"],
            "median_price": sale["median_price"],
            "n_sales": sale["n_sales"],
            "f_m2": floor_by[key],
        }
        for name in ("cell", "a_m2", "ratio_mean", "iz", "ca", "ur3", "flat_share"):
            if name in sale:
                row[name] = sale[name]
        built.append(row)
    return built


def assert_fit_years(rows: list[dict]) -> None:
    """Refuse any fit row whose year is outside FIT_YEARS. Reads only year."""
    for row in rows:
        year = row["year"]
        if year not in FIT_YEARS:
            raise B2Error(
                f"B2_FIT_ROWS: REFUSED: year: expected 2021-2022, got {year}"
            )


def assert_house_sales_pin(path: Path) -> None:
    """Full sha256 only. The 702c9ada prefix is not enough."""
    expected = str(PIN_TABLE["house_sales"])
    if not path.is_file():
        raise B2Error(f"B2_HOUSE_SALES: ERROR: sha256: expected {expected}, got absent")
    actual = sha256_file(path)
    if actual != expected:
        raise B2Error(f"B2_HOUSE_SALES: ERROR: sha256: expected {expected}, got {actual}")


def _am2_payload(am2: dict, sales: list[dict]) -> dict:
    """Disclosure block: codes and counts only."""
    excluded_by_year: dict[int, dict[str, int]] = {}
    for item in am2["excluded"]:
        year = int(item["year"])
        if year not in excluded_by_year:
            excluded_by_year[year] = {"suppressed_price": 0, "no_sales": 0}
        reason = item["reason"]
        if reason in excluded_by_year[year]:
            excluded_by_year[year][reason] = excluded_by_year[year][reason] + 1
    complete_fit: dict[str, bool] = {}
    for row in sales:
        if int(row["year"]) in FIT_YEARS:
            complete_fit[str(row["zone"])] = True
    excluded_fit: dict[str, bool] = {}
    for item in am2["excluded"]:
        if int(item["year"]) in FIT_YEARS:
            excluded_fit[str(item["zone"])] = True
    fit_window_no_complete_row = []
    for zone in sorted(excluded_fit):
        if zone not in complete_fit:
            fit_window_no_complete_row.append(zone)
    return {
        "label": "excluding price-suppressed zone-years (AM-2)",
        "excluded": am2["excluded"],
        "excluded_by_year": excluded_by_year,
        "zones_present": am2["zones_present"],
        "skipped_geography": am2["skipped_geography"],
        "fit_window_no_complete_row": fit_window_no_complete_row,
    }


def build(args: argparse.Namespace) -> dict:
    assert_house_sales_pin(args.house_sales)
    am2: dict = {}
    sales = adapt_house_sales(args.house_sales, am2=am2)
    plots = adapt_plot_split(args.plot_split, expected_count=PIN_TABLE["low_parcel_count"])
    crosswalk = adapt_crosswalk(args.crosswalk)
    access = adapt_access(args.access)
    bedrooms = adapt_bedrooms(args.bedrooms, args.crosswalk)
    chain: D7ChainResult = run_d7_chain(
        source=args.sold_tfa,
        filter1_script=args.filter1_script,
        filter1_output=args.filter1_output,
        filter2_script=args.filter2_script,
        filter2_output=args.filter2_output,
        run_fit=False,
    )
    if not chain.passed or chain.d7_sha256 is None:
        raise B2Error(chain.message)
    floors = adapt_sold_tfa(args.filter2_output)
    fit_rows = _fit_rows(sales, floors)
    assert_fit_years(fit_rows)
    fitted = fit_headline(fit_rows, d7_sha256=chain.d7_sha256)
    s_x2 = "NOT_RUN"
    if isinstance(fitted, dict):
        s_x2 = next(item["status"] for item in fitted["sensitivities"] if item["id"] == "S-x2")
    return {
        "label": "SYNTHETIC",
        "fidelity_adaptation": FIDELITY_ADAPTATION,
        "d7_sha256": chain.d7_sha256,
        "d7_provenance": chain.manifest,
        "house_sales": sales,
        "plot_split": plots,
        "crosswalk": crosswalk,
        "access": access,
        "bedrooms": bedrooms["rows"],
        "sold_tfa": floors,
        "fit_rows": fit_rows,
        "fit": {"s_x2": s_x2},
        "am2": _am2_payload(am2, sales),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--house-sales", type=Path, required=True)
    parser.add_argument("--plot-split", type=Path, required=True)
    parser.add_argument("--crosswalk", type=Path, required=True)
    parser.add_argument("--sold-tfa", type=Path, required=True)
    parser.add_argument("--access", type=Path, required=True)
    parser.add_argument("--bedrooms", type=Path, required=True)
    parser.add_argument("--filter1-script", type=Path, required=True)
    parser.add_argument("--filter1-output", type=Path, required=True)
    parser.add_argument("--filter2-script", type=Path, required=True)
    parser.add_argument("--filter2-output", type=Path, required=True)
    parser.add_argument("--no-price", action="store_true", help="Do not open house sales or fit.")
    args = parser.parse_args(argv)
    if args.no_price:
        payload = {"label": "SYNTHETIC", "no_price": True}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sys.stdout.write(f"wrote {args.out}\n")
        return 0
    try:
        payload = build(args)
    except B2Error as exc:  # our own messages: never contain a Value cell
        sys.stderr.write(str(exc) + "\n")
        return 1
    except Exception as exc:  # anything else: type name only
        sys.stderr.write(
            f"B2: ERROR: build: expected B2Error, got {type(exc).__name__} (message withheld)\n"
        )
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.write(f"wrote {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
