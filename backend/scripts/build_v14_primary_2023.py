#!/usr/bin/env python3
"""2023 primary estimates and the builder output for that year.

Input is the B2 adapted house-sales rows. The year is screened before the
price field. Years 2004-2022 are skipped without a price read. A year of
2024 or later refuses before the price field is read. The 2023
sales-weighted mean, less DRC, is the share and the land per home.

Usage (from ``backend/``)::

    python -m scripts.build_v14_primary_2023 --b2-out b2.json --drc drc.json \\
        --primary-out primary_estimates_2023.json \\
        --builder-out builder_output_2023.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping

from georgist import surface_rent as sr
from georgist.v14_primary_inputs import land_share

FIELDS = ("zone", "year", "count", "price")
PRIMARY_KEYS = ("zone", "share", "land_per_home", "unavailable", "count_in_1d")
BUILDER_KEYS = ("zone", "price", "count_in_1d", "unavailable", "model_failure", "hla")


class PrimaryError(ValueError):
    """A 2023 primary input failed a year, file, or cell check."""


class DroppedRows(Exception):
    """Scored zones are missing a 2023 price or a DRC row."""

    def __init__(self, no_price: int, no_cost: int) -> None:
        super().__init__(f"dropped_no_price={no_price} dropped_no_cost={no_cost}")
        self.no_price = no_price
        self.no_cost = no_cost


def read_price_field(value: object) -> object:
    """Price hook. Skipped years and refused years do not call it."""
    return value


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise PrimaryError(f"B4_PRIMARY_2023: ERROR: file: expected {path}, got absent")


def _year_message(row_number: int, got: object) -> PrimaryError:
    return PrimaryError(
        f"B4_PRIMARY_2023: ERROR: year row {row_number}: expected integer, got {got}"
    )


def _parse_year(raw: object, row_number: int) -> int:
    if raw is None or isinstance(raw, bool):
        got = "blank" if raw is None or raw == "" else raw
        raise _year_message(row_number, got)
    if isinstance(raw, float):
        raise _year_message(row_number, raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text == "":
            raise _year_message(row_number, "blank")
        digits = text[1:] if text.startswith("-") else text
        if not digits.isdigit():
            raise _year_message(row_number, text)
        return int(text)
    raise _year_message(row_number, raw)


def _screen_year(row: object, row_number: int) -> int:
    """Read the year and stop. The price field is not inspected here."""
    if isinstance(row, dict):
        if "year" not in row:
            raise _year_message(row_number, "short")
        year = _parse_year(row["year"], row_number)
    elif isinstance(row, (list, tuple)):
        if len(row) < len(FIELDS):
            raise PrimaryError(
                f"B4_PRIMARY_2023: ERROR: row {row_number}: expected {len(FIELDS)} fields, got {len(row)}"
            )
        year = _parse_year(row[1], row_number)
    else:
        raise _year_message(row_number, "short")
    if year >= 2024:
        raise PrimaryError(f"B4_PRIMARY_2023: REFUSED: year: expected <2024, got {year}")
    return year


def _has_field(row: Mapping, name: str) -> bool:
    if name == "count":
        return "count" in row or "n_sales" in row
    return name in row


def _raw_field(row: Mapping, name: str) -> object:
    if name == "count" and "count" not in row:
        return row.get("n_sales")
    return row.get(name)


def _blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _sales_row(row: object, row_number: int) -> dict[str, object] | None:
    """One adapted row. Returns None when the year is before 2023."""
    year = _screen_year(row, row_number)
    if year < 2023:
        return None
    if not isinstance(row, dict):
        cells = list(row)
        names = FIELDS
        for index, name in enumerate(names):
            if _blank(cells[index]):
                raise PrimaryError(
                    f"B4_PRIMARY_2023: ERROR: {name} row {row_number}: expected value, got blank"
                )
        price = read_price_field(cells[3])
        return {"zone": str(cells[0]).strip(), "count": cells[2], "price": price}
    present = 0
    for name in FIELDS:
        if not _has_field(row, name):
            raise PrimaryError(
                f"B4_PRIMARY_2023: ERROR: row {row_number}: expected {len(FIELDS)} fields, got {present}"
            )
        present += 1
        if name == "year":
            continue
        value = _raw_field(row, name)
        if _blank(value):
            raise PrimaryError(
                f"B4_PRIMARY_2023: ERROR: {name} row {row_number}: expected value, got blank"
            )
    price = read_price_field(_raw_field(row, "price"))
    return {
        "zone": str(_raw_field(row, "zone")).strip(),
        "count": _raw_field(row, "count"),
        "price": price,
    }


def _house_sales(payload: object) -> list:
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict) and isinstance(payload.get("house_sales"), list):
        return list(payload["house_sales"])
    raise PrimaryError("B4_PRIMARY_2023: ERROR: house_sales: expected list, got absent")


def _drc_map(payload: object) -> dict[str, float]:
    if not isinstance(payload, dict):
        raise PrimaryError("B4_PRIMARY_2023: ERROR: drc: expected object, got absent")
    out: dict[str, float] = {}
    for key, value in payload.items():
        if key == "label":
            continue
        out[str(key)] = float(value)
    return out


def _weighted_means(rows: list[dict[str, object]]) -> dict[str, float]:
    totals: dict[str, list[float]] = {}
    for row in rows:
        zone = str(row["zone"])
        price = float(row["price"])
        count = float(row["count"])
        slot = totals.setdefault(zone, [0.0, 0.0])
        slot[0] += price * count
        slot[1] += count
    means: dict[str, float] = {}
    for zone, (value, count) in totals.items():
        if count <= 0:
            raise PrimaryError(f"B4_PRIMARY_2023: ERROR: count row {zone}: expected value, got blank")
        means[zone] = value / count
    return means


def build_primary_2023(b2_path: Path, drc_path: Path) -> dict[str, list[dict]]:
    """Share and builder rows for 2023. Writes nothing."""
    _require_file(b2_path)
    _require_file(drc_path)
    sales_payload = json.loads(b2_path.read_text(encoding="utf-8"))
    kept: list[dict[str, object]] = []
    for row_number, row in enumerate(_house_sales(sales_payload), start=1):
        screened = _sales_row(row, row_number)
        if screened is not None:
            kept.append(screened)
    drc = _drc_map(json.loads(drc_path.read_text(encoding="utf-8")))
    means = _weighted_means(kept)
    zones = sorted(set(means) | set(drc))
    no_price = sum(1 for zone in zones if zone not in means)
    no_cost = sum(1 for zone in zones if zone not in drc)
    if no_price > 0 or no_cost > 0:
        raise DroppedRows(no_price, no_cost)
    primary: list[dict] = []
    builder: list[dict] = []
    for zone in zones:
        price = float(means[zone])
        cost = float(drc[zone])
        residual = sr.residual_land_value(price, cost)
        unavailable = sr.estimate_label_for_residual(residual) == "unavailable"
        share = land_share(price, cost)
        primary.append(
            {
                "zone": zone,
                "share": share,
                "land_per_home": residual.land_value,
                "unavailable": unavailable,
                "count_in_1d": True,
            }
        )
        builder.append(
            {
                "zone": zone,
                "price": price,
                "count_in_1d": True,
                "unavailable": unavailable,
                "model_failure": False,
                "hla": False,
            }
        )
    for row in primary:
        if set(row) != set(PRIMARY_KEYS):
            raise PrimaryError("B4_PRIMARY_2023: ERROR: fields: expected primary keys, got extra")
    for row in builder:
        if set(row) != set(BUILDER_KEYS):
            raise PrimaryError("B4_PRIMARY_2023: ERROR: fields: expected builder keys, got extra")
    return {"primary": primary, "builder": builder}


def write_outputs(primary_path: Path, builder_path: Path, built: Mapping[str, list[dict]]) -> None:
    for path, key in ((primary_path, "primary"), (builder_path, "builder")):
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"zones": built[key]}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b2-out", type=Path, required=True)
    parser.add_argument("--drc", type=Path, required=True)
    parser.add_argument("--primary-out", type=Path, required=True)
    parser.add_argument("--builder-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        built = build_primary_2023(args.b2_out, args.drc)
    except DroppedRows as exc:
        sys.stdout.write(f"dropped_no_price={exc.no_price} dropped_no_cost={exc.no_cost}\n")
        return 1
    except PrimaryError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    write_outputs(args.primary_out, args.builder_out, built)
    sys.stdout.write(f"zones={len(built['primary'])}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
