#!/usr/bin/env python3
"""Write the four B6 check sources for the 2023 holdout.

check 3 uses integer radii 20, 30 and 40. check 4 follows the frozen v1.3
two-route method (prereg ce940445, check 4): residual_land is the residual
route and capitalised_land is the capitalised route. dz2022 keys use O-D1
weights. UR6 is one class per DZ2011 zone. No 2024 price cell is read.

Usage (from ``backend/``)::

    python -m scripts.build_v14_check_sources --plot-bands plots.csv \\
        --gis-house-plot houses.csv --check3-out check3.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

from georgist import surface_v13 as v13
from georgist.rent_table_pooled import RENT_TABLE_COLUMNS

PIN_TABLE = {
    "plot_bands": "9bb56d3be6181740ae07fb06607c45374ce448d6c73a00cdea3c7c81b4886e48",
    "gis_house_plot": "3320797696c876e7cb6b41163724f0346cbeb284f89d6792bf87a1e9c600735d",
    "rent_table": "21190bfc70e1fee3a5b7e1804bba966b7777eb82e21b42ac43a35b77c5d63f11",
    "crosswalk": "7690bcbebf9968ca9b02cf898832aa9be8fca56f3eb9af70b20e25b5d23e13e4",
    "ur6": "1f32a81532912334e3cd071e2f12f523e66068d14c73e5db4ae51add239b1a92",
}
PIN_ORDER = ("plot_bands", "gis_house_plot", "rent_table", "crosswalk", "ur6")
FULL_SHA = re.compile(r"^[0-9a-f]{64}$")
CHECK3_YIELD = 0.045
PLOT_FIELDS = (
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
)
GIS_FIELDS = ("code", "house_plot_m2")
UR6_FIELDS = ("code", "ur6")
CROSSWALK_FIELDS = ("dz2011_code", "dz2022_code", "uprn_count")
PRIMARY_FIELDS = ("zone", "share_low", "share_central", "share_high")
STEP_FOR_PIN = {
    "plot_bands": "B5_CHECK3",
    "gis_house_plot": "B5_CHECK3",
    "rent_table": "B5_CHECK4",
    "crosswalk": "B5_CROSSWALK",
    "ur6": "B5_UR6",
}
SHA_STEP = {
    "plot_bands": "B5_PLOT_BANDS",
    "gis_house_plot": "B5_GIS_HOUSE_PLOT",
    "rent_table": "B5_CHECK4",
    "crosswalk": "B5_CROSSWALK",
    "ur6": "B5_UR6",
    "primary_estimates": "B5_PRIMARY",
}


class CheckSourceError(ValueError):
    """A check-source input failed a pin, file, or cell check."""


def copy_pin_table() -> dict[str, str]:
    """Test-only hook. A copy, so production pins stay put."""
    return {key: str(PIN_TABLE[key]) for key in PIN_ORDER}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _pin_text(value: object) -> str:
    if value is None:
        return "blank"
    text = str(value)
    if text.strip() == "":
        return "blank"
    return text


def _assert_pin_format(name: str, pins: dict[str, str]) -> None:
    text = _pin_text(pins.get(name))
    if text == "blank" or FULL_SHA.fullmatch(text) is None:
        step = STEP_FOR_PIN[name]
        raise CheckSourceError(f"{step}: REFUSED: pin: expected full sha256, got {text}")


def _assert_file_sha(name: str, path: Path, pins: dict[str, str]) -> None:
    step = SHA_STEP[name]
    if not path.is_file():
        raise CheckSourceError(f"{step}: ERROR: file: expected {path}, got absent")
    actual = sha256_file(path)
    expected = pins[name]
    if actual != expected:
        raise CheckSourceError(f"{step}: REFUSED: {name} sha256: expected {expected}, got {actual}")


def _csv_table(path: Path, step: str, fields: tuple[str, ...]) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if not lines:
        raise CheckSourceError(f"{step}: ERROR: header: expected header, got absent")
    parsed = list(csv.reader(io.StringIO("\n".join(lines) + "\n")))
    header = parsed[0]
    width = len(header)
    missing = [name for name in fields if name not in header]
    if missing:
        raise CheckSourceError(f"{step}: ERROR: header: expected {fields[0]}, got absent")
    rows = []
    for row_number, cells in enumerate(parsed[1:], start=1):
        if len(cells) < width:
            raise CheckSourceError(
                f"{step}: ERROR: row {row_number}: expected {width} fields, got {len(cells)}"
            )
        item = {column: cells[index] for index, column in enumerate(header)}
        if "year" in item:
            _screen_year(step, item["year"], row_number)
        for name in fields:
            if item.get(name, "").strip() == "":
                raise CheckSourceError(
                    f"{step}: ERROR: {name} row {row_number}: expected value, got blank"
                )
        rows.append(item)
    return rows


def _screen_year(step: str, raw: str, row_number: int) -> None:
    text = raw.strip()
    if text == "":
        raise CheckSourceError(f"{step}: ERROR: year row {row_number}: expected integer, got blank")
    digits = text[1:] if text.startswith("-") else text
    if not digits.isdigit():
        raise CheckSourceError(f"{step}: ERROR: year row {row_number}: expected integer, got {text}")
    year = int(text)
    if year >= 2024:
        raise CheckSourceError(f"{step}: REFUSED: year: expected <2024, got {year}")


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def _radii(row: dict[str, str], prefix: str) -> dict[int, bool]:
    return {radius: _truthy(row[f"{prefix}{radius}"]) for radius in (20, 30, 40)}


def load_plot_bands(path: Path) -> list[dict[str, str]]:
    return _csv_table(path, "B5_PLOT_BANDS", PLOT_FIELDS)


def load_gis_house_plot(path: Path) -> list[dict[str, str]]:
    return _csv_table(path, "B5_GIS_HOUSE_PLOT", GIS_FIELDS)


def load_rent_table(path: Path) -> list[dict[str, str]]:
    return _csv_table(path, "B5_CHECK4", tuple(RENT_TABLE_COLUMNS))


def load_crosswalk(path: Path) -> list[dict[str, str]]:
    return _csv_table(path, "B5_CROSSWALK", CROSSWALK_FIELDS)


def load_ur6_rows(path: Path) -> list[dict[str, str]]:
    return _csv_table(path, "B5_UR6", UR6_FIELDS)


def load_primary(path: Path) -> dict[str, dict[str, float]]:
    step = "B5_PRIMARY"
    if not path.is_file():
        raise CheckSourceError(f"{step}: ERROR: file: expected {path}, got absent")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("zones") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise CheckSourceError(f"{step}: ERROR: zones: expected list, got absent")
    estimates: dict[str, dict[str, float]] = {}
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise CheckSourceError(f"{step}: ERROR: row {row_number}: expected {len(PRIMARY_FIELDS)} fields, got 0")
        if "year" in row:
            raw = row["year"]
            _screen_year(step, "" if raw is None else str(raw), row_number)
        present = 0
        for name in PRIMARY_FIELDS:
            if name not in row and not (name != "zone" and "share" in row and name.startswith("share_")):
                if name not in row:
                    raise CheckSourceError(
                        f"{step}: ERROR: row {row_number}: expected {len(PRIMARY_FIELDS)} fields, got {present}"
                    )
            if name not in row:
                continue
            present += 1
            value = row[name]
            if value is None or (isinstance(value, str) and value.strip() == ""):
                raise CheckSourceError(f"{step}: ERROR: {name} row {row_number}: expected value, got blank")
        zone = str(row["zone"])
        if "share_low" in row:
            estimates[zone] = {
                "share_low": float(row["share_low"]),
                "share_central": float(row["share_central"]),
                "share_high": float(row["share_high"]),
            }
        else:
            share = float(row["share"])
            estimates[zone] = {"share_low": share, "share_central": share, "share_high": share}
    return estimates


def two_route_lands(row: dict[str, str]) -> tuple[float, float]:
    """Frozen v1.3 two-route check 4 (prereg ce940445, check 4).

    residual_land is the residual route, the pooled table's central figure.
    capitalised_land is the capitalised route: ``capitalised_rent_land`` of
    the low column at the v1.3 check-4 yield 0.045.
    """
    residual = float(row["central"])
    capitalised = v13.capitalised_rent_land(float(row["low"]), yield_rate=CHECK3_YIELD)
    return residual, capitalised


def write_output(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_check3(paths: dict[str, Path], *, pins: dict[str, str] | None = None) -> dict:
    table = PIN_TABLE if pins is None else pins
    _assert_pin_format("plot_bands", table)
    _assert_pin_format("gis_house_plot", table)
    _assert_file_sha("plot_bands", paths["plot_bands"], table)
    _assert_file_sha("gis_house_plot", paths["gis_house_plot"], table)
    plots = load_plot_bands(paths["plot_bands"])
    houses = {row["code"]: row for row in load_gis_house_plot(paths["gis_house_plot"])}
    zones = []
    for row in plots:
        house = houses[row["code"]]
        zones.append(
            {
                "zone": row["code"],
                "pass_at": _radii(row, "pass_"),
                "pass_at_all_homes": _radii(row, "all_"),
                "pass_at_dz22": _radii(row, "dz22_"),
                "measured_detached_pass": _truthy(row["measured_detached_pass"]),
                "detached_plot_m2": float(row["detached_plot_m2"]),
                "house_plot_m2": float(house["house_plot_m2"]),
            }
        )
    return {"label": "SYNTHETIC", "zones": zones}


def build_check4(path: Path, *, pins: dict[str, str] | None = None) -> dict:
    table = PIN_TABLE if pins is None else pins
    _assert_pin_format("rent_table", table)
    _assert_file_sha("rent_table", path, table)
    zones = []
    for row in load_rent_table(path):
        residual, capitalised = two_route_lands(row)
        zones.append(
            {
                "zone": row["zone_id"],
                "residual_land": residual,
                "capitalised_land": capitalised,
            }
        )
    return {"label": "SYNTHETIC", "zones": zones}


def build_dz2022_keys(
    crosswalk: Path,
    primary: Path,
    *,
    pins: dict[str, str] | None = None,
) -> tuple[dict, int]:
    table = PIN_TABLE if pins is None else pins
    _assert_pin_format("crosswalk", table)
    _assert_file_sha("crosswalk", crosswalk, table)
    if not primary.is_file():
        raise CheckSourceError(f"B5_PRIMARY: ERROR: file: expected {primary}, got absent")
    edges = load_crosswalk(crosswalk)
    estimates = load_primary(primary)
    grouped: dict[str, list[dict[str, str]]] = {}
    for edge in edges:
        grouped.setdefault(edge["dz2022_code"], []).append(edge)
    zones = []
    suppressed = 0
    for code in sorted(grouped):
        group = grouped[code]
        if any(edge["dz2011_code"] not in estimates for edge in group):
            suppressed += 1
            continue
        total = sum(int(edge["uprn_count"]) for edge in group)
        def weighted(field: str, group: list[dict[str, str]] = group, total: int = total) -> float:
            return sum(
                int(edge["uprn_count"]) / total * estimates[edge["dz2011_code"]][field] for edge in group
            )

        zones.append(
            {
                "zone": code,
                "dz2022": code,
                "share_low": weighted("share_low"),
                "share_central": weighted("share_central"),
                "share_high": weighted("share_high"),
            }
        )
    return {"label": "SYNTHETIC", "zones": zones}, suppressed


def build_ur6(path: Path, *, pins: dict[str, str] | None = None) -> dict:
    table = PIN_TABLE if pins is None else pins
    _assert_pin_format("ur6", table)
    _assert_file_sha("ur6", path, table)
    zones = []
    for row_number, row in enumerate(load_ur6_rows(path), start=1):
        text = row["ur6"].strip()
        if not text.isdigit():
            raise CheckSourceError(f"B5_UR6: ERROR: ur6 row {row_number}: expected 1-6, got {text}")
        value = int(text)
        if value < 1 or value > 6:
            raise CheckSourceError(f"B5_UR6: ERROR: ur6 row {row_number}: expected 1-6, got {value}")
        zones.append({"zone": row["code"], "ur6": value})
    return {"label": "SYNTHETIC", "zones": zones}


def save_check3(paths: dict[str, Path], dest: Path, *, pins: dict[str, str] | None = None) -> dict:
    payload = build_check3(paths, pins=pins)
    write_output(dest, payload)
    return payload


def save_check4(path: Path, dest: Path, *, pins: dict[str, str] | None = None) -> dict:
    payload = build_check4(path, pins=pins)
    write_output(dest, payload)
    return payload


def save_dz2022(
    crosswalk: Path,
    primary: Path,
    dest: Path,
    *,
    pins: dict[str, str] | None = None,
) -> tuple[dict, int]:
    payload, suppressed = build_dz2022_keys(crosswalk, primary, pins=pins)
    write_output(dest, payload)
    return payload, suppressed


def save_ur6(path: Path, dest: Path, *, pins: dict[str, str] | None = None) -> dict:
    payload = build_ur6(path, pins=pins)
    write_output(dest, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plot-bands", type=Path)
    parser.add_argument("--gis-house-plot", type=Path)
    parser.add_argument("--check3-out", type=Path)
    parser.add_argument("--rent-table", type=Path)
    parser.add_argument("--check4-out", type=Path)
    parser.add_argument("--crosswalk", type=Path)
    parser.add_argument("--primary-estimates", type=Path)
    parser.add_argument("--dz2022-out", type=Path)
    parser.add_argument("--ur6", type=Path)
    parser.add_argument("--ur6-out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.check3_out is not None:
            save_check3(
                {"plot_bands": args.plot_bands, "gis_house_plot": args.gis_house_plot},
                args.check3_out,
            )
        if args.check4_out is not None:
            save_check4(args.rent_table, args.check4_out)
        if args.dz2022_out is not None:
            _payload, suppressed = save_dz2022(args.crosswalk, args.primary_estimates, args.dz2022_out)
            sys.stdout.write(f"B5_DZ2022_KEYS: suppressed={suppressed}\n")
        if args.ur6_out is not None:
            save_ur6(args.ur6, args.ur6_out)
    except CheckSourceError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
