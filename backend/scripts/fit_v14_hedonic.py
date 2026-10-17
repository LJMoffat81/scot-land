#!/usr/bin/env python3
"""Fit the v1.4 headline on 2021-2022 B2 rows and write per-zone shares.

A year at or after 2024 is refused before any price field is read. A year at
or after 2023 is left out of the fit by its year field. S-x2 records the D7
filter2 pin and does not gate. A refused pin is passed as d7_accept=False
and does not call the S-x2 fit.

Usage (from ``backend/``)::

    python -m scripts.fit_v14_hedonic --b2-out b2.json \\
        --fit-out fitted_hedonic_2023.json --per-zone-out fitted_per_zone.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from georgist.v14_d7_chain import D7_FILTER2_OUTPUT_SHA256
from georgist.v14_hedonic import (
    FIDELITY_LIMITATION,
    _fit_s_x2,
    fit_headline,
    land_share_for_zone,
)
from georgist import v14_hedonic as hedonic

D7_SHA256 = D7_FILTER2_OUTPUT_SHA256
FIT_FIELDS = ("year", "zone", "cell", "price", "n_sales", "a_m2", "f_m2")
OPTIONAL_FIELDS = ("ratio_mean", "iz", "ca", "ur3", "ur6", "itl3", "flat_share", "iz2011")
PER_ZONE_KEYS = ("zone", "share", "land_per_home", "unavailable", "model_failure", "count_in_1d")
S_C3_MAXITER_OVERRIDE: int | None = None


class FitError(ValueError):
    """The hedonic fit CLI refused a year, file, or cell."""


def _test_set_s_c3_maxiter(value: int | None) -> None:
    """Test-only hook. Forces MixedLM maxiter for the next fit, then restores."""
    global S_C3_MAXITER_OVERRIDE
    S_C3_MAXITER_OVERRIDE = value


def read_price_field(value: object) -> object:
    """Price hook. A refused or excluded year does not call it."""
    return value


def fit_s_x2(rows: list[dict], d7_sha256: str):
    """S-x2 fit. Called only when the filter2 pin matches in full."""
    return _fit_s_x2(rows, d7_sha256)


def _parse_year(raw: object, row_number: int) -> int:
    if raw is None or isinstance(raw, bool):
        got = "blank" if raw is None or raw == "" else raw
        raise FitError(f"B3_FIT: ERROR: year row {row_number}: expected integer, got {got}")
    if isinstance(raw, float):
        raise FitError(f"B3_FIT: ERROR: year row {row_number}: expected integer, got {raw}")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text == "":
            raise FitError(f"B3_FIT: ERROR: year row {row_number}: expected integer, got blank")
        digits = text[1:] if text.startswith("-") else text
        if not digits.isdigit():
            raise FitError(f"B3_FIT: ERROR: year row {row_number}: expected integer, got {text}")
        return int(text)
    raise FitError(f"B3_FIT: ERROR: year row {row_number}: expected integer, got {raw}")


def _year_only(row: object, row_number: int) -> int:
    """Year field only. No later field of the row is read."""
    if isinstance(row, dict):
        if "year" not in row:
            raise FitError(f"B3_FIT: ERROR: year row {row_number}: expected integer, got short")
        return _parse_year(row["year"], row_number)
    if isinstance(row, (list, tuple)):
        if len(row) < 1:
            raise FitError(f"B3_FIT: ERROR: year row {row_number}: expected integer, got short")
        return _parse_year(row[0], row_number)
    raise FitError(f"B3_FIT: ERROR: year row {row_number}: expected integer, got short")


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FitError(f"B3_FIT: ERROR: file: expected {path}, got absent")


def _fit_rows(payload: object) -> tuple[list, object]:
    if isinstance(payload, dict) and isinstance(payload.get("fit_rows"), list):
        return list(payload["fit_rows"]), payload.get("d7_sha256")
    raise FitError("B3_FIT: ERROR: fit_rows: expected list, got absent")


def _d7_actual(value: object) -> str:
    if value is None:
        return "absent"
    text = str(value).strip()
    if text == "":
        return "absent"
    return text


def _screen_years(rows: list) -> list[int]:
    """Every year first. A 2024 row refuses before any price field is read."""
    kept: list[int] = []
    for row_number, row in enumerate(rows, start=1):
        year = _year_only(row, row_number)
        if year >= 2024:
            raise FitError(f"B3_FIT: REFUSED: year: expected <2024, got {year}")
        if year in (2021, 2022):
            kept.append(row_number)
    return kept


def _kept_row(row: object, row_number: int) -> dict:
    if isinstance(row, dict):
        present = 0
        values: dict = {}
        for name in FIT_FIELDS:
            if name not in row:
                raise FitError(
                    f"B3_FIT: ERROR: row {row_number}: expected {len(FIT_FIELDS)} fields, got {present}"
                )
            present += 1
            if name == "year":
                values["year"] = int(row["year"])
                continue
            value = row[name]
            if _blank(value):
                raise FitError(f"B3_FIT: ERROR: {name} row {row_number}: expected value, got blank")
            if name == "price":
                value = read_price_field(value)
            values[name] = value
        for name in OPTIONAL_FIELDS:
            if name in row and not _blank(row[name]):
                values[name] = row[name]
        values["zone"] = str(values["zone"])
        values["cell"] = str(values["cell"])
        values["n_sales"] = int(values["n_sales"])
        values["price"] = float(values["price"])
        values["a_m2"] = float(values["a_m2"])
        values["f_m2"] = float(values["f_m2"])
        return values
    cells = list(row)
    if len(cells) < len(FIT_FIELDS):
        raise FitError(
            f"B3_FIT: ERROR: row {row_number}: expected {len(FIT_FIELDS)} fields, got {len(cells)}"
        )
    values = {}
    for index, name in enumerate(FIT_FIELDS):
        value = cells[index]
        if name == "year":
            values["year"] = int(value)
            continue
        if _blank(value):
            raise FitError(f"B3_FIT: ERROR: {name} row {row_number}: expected value, got blank")
        if name == "price":
            value = read_price_field(value)
        values[name] = value
    values["zone"] = str(values["zone"])
    values["cell"] = str(values["cell"])
    values["n_sales"] = int(values["n_sales"])
    values["price"] = float(values["price"])
    values["a_m2"] = float(values["a_m2"])
    values["f_m2"] = float(values["f_m2"])
    return values


def _run_headline(rows: list[dict], d7: str, *, accept: bool) -> dict:
    saved = hedonic.S_C3_MAXITER
    if S_C3_MAXITER_OVERRIDE is not None:
        hedonic.S_C3_MAXITER = S_C3_MAXITER_OVERRIDE
    try:
        if accept:
            fit_s_x2(rows, d7)
            return fit_headline(rows, d7_sha256=d7, d7_accept=True)
        return fit_headline(
            rows,
            d7_sha256=d7 if d7 != "absent" else None,
            d7_accept=False,
        )
    finally:
        hedonic.S_C3_MAXITER = saved


def _mark_s_x2(fitted: dict, actual: str, *, accept: bool) -> None:
    if accept:
        return
    reason = (
        "B3_FIT: NOT_RUN: d7_sha256: expected "
        f"{D7_SHA256}, got {actual}"
    )
    for item in fitted["sensitivities"]:
        if item["id"] == "S-x2":
            item["status"] = "NOT_RUN"
            item["reason"] = reason
            item["beta_by_cell"] = None


def project_records(fitted: dict, rows: list[dict]) -> list[dict]:
    """One record per zone. Keys are exactly the B6 fitted_hedonic set."""
    chosen: dict[str, dict] = {}
    for row in rows:
        zone = str(row["zone"])
        current = chosen.get(zone)
        if current is None or int(row["year"]) >= int(current["year"]):
            chosen[zone] = row
    records = []
    for zone in sorted(chosen):
        raw = land_share_for_zone(fitted, chosen[zone])
        records.append({key: raw[key] for key in PER_ZONE_KEYS})
    status = next(item["status"] for item in fitted["sensitivities"] if item["id"] == "S-c3")
    if status in {"NOT_CONVERGED", "NOT_RUN"}:
        for record in records:
            record["model_failure"] = True
            record["unavailable"] = True
    return records


def fit_b2(path: Path) -> dict:
    """Read B2 fit rows and return the fit file plus the per-zone file."""
    _require_file(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows, d7_raw = _fit_rows(payload)
    kept_numbers = _screen_years(rows)
    kept = [_kept_row(rows[number - 1], number) for number in kept_numbers]
    actual = _d7_actual(d7_raw)
    accept = actual == D7_SHA256
    fitted = _run_headline(kept, actual, accept=accept)
    _mark_s_x2(fitted, actual, accept=accept)
    per_zone = project_records(fitted, kept)
    s_c3 = next(item for item in fitted["sensitivities"] if item["id"] == "S-c3")
    fit_payload = {
        "label": "SYNTHETIC",
        "row_count": len(kept),
        "d7_sha256": None if actual == "absent" else actual,
        "beta_by_cell": fitted["beta_by_cell"],
        "coefficients": fitted["coefficients"],
        "sensitivities": fitted["sensitivities"],
        "s_c3_status": s_c3["status"],
        "s_c3_reason": s_c3["reason"],
    }
    zone_payload = {
        "label": "SYNTHETIC",
        "fidelity_limitation": FIDELITY_LIMITATION,
        "zones": per_zone,
    }
    return {"fit": fit_payload, "per_zone": zone_payload}


def write_fit(fit_path: Path, per_zone_path: Path, built: dict) -> None:
    for path, key in ((fit_path, "fit"), (per_zone_path, "per_zone")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(built[key], indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b2-out", type=Path, required=True)
    parser.add_argument("--fit-out", type=Path, required=True)
    parser.add_argument("--per-zone-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        built = fit_b2(args.b2_out)
        write_fit(args.fit_out, args.per_zone_out, built)
    except FitError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
