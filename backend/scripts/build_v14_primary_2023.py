#!/usr/bin/env python3
"""2023 primary estimates and the builder output for that year.

Input is the B2 adapted house-sales rows. The year is screened before the
price field. Years 2004-2022 are skipped without a price read. A year of
2024 or later refuses before the price field is read. The 2023
sales-weighted mean, less DRC, is the share and the land per home.

When the B2 payload carries an ``am2`` disclosure block (AM-2), DRC zones
without a complete 2023 price are classified NOT_SCORED and dropped from
the scored set before DroppedRows runs.

Usage (from ``backend/``)::

    python -m scripts.build_v14_primary_2023 --b2-out b2.json --drc drc.json \\
        --primary-out primary_estimates_2023.json \\
        --builder-out builder_output_2023.json \\
        --not-scored-out not_scored_2023.json \\
        --reconcile-census am2_census_2023_not_scored.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Mapping

from georgist import surface_rent as sr
from georgist.v14_primary_inputs import land_share

FIELDS = ("zone", "year", "count", "price")
PRIMARY_KEYS = ("zone", "share", "land_per_home", "unavailable", "count_in_1d")
BUILDER_KEYS = ("zone", "price", "count_in_1d", "unavailable", "model_failure", "hla")
NOT_SCORED_REASONS = ("suppressed_price", "no_sales", "no_2023_row", "absent_from_file")
ABSENT_FROM_FILE_ZONES = frozenset(
    {
        "S01007788",
        "S01010206",
        "S01010226",
        "S01010462",
        "S01010493",
        "S01011598",
    }
)
_ABSENT_PIN_LIST = (
    "S01007788, S01010206, S01010226, S01010462, S01010493, S01011598"
)


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


def _require_am2_object(am2: object) -> dict:
    if type(am2) is not dict:
        raise PrimaryError(
            f"B4_PRIMARY_2023: ERROR: am2: expected object, got {type(am2).__name__}"
        )
    return am2


def _validate_am2_years(am2: Mapping) -> None:
    """Refuse bad excluded year types before any price field is read (§8)."""
    excluded_raw = am2.get("excluded")
    if not isinstance(excluded_raw, list):
        return
    for item in excluded_raw:
        if not isinstance(item, dict):
            continue
        year = item.get("year")
        if type(year) is not int:
            raise PrimaryError(
                "B4_PRIMARY_2023: ERROR: year row am2: expected integer, got "
                f"{type(year).__name__}"
            )


def _priced_zones_without_price_read(sales_payload: object) -> set[str]:
    """Zones with a complete 2023 sales row; does not call read_price_field."""
    priced: set[str] = set()
    for row_number, row in enumerate(_house_sales(sales_payload), start=1):
        year = _screen_year(row, row_number)
        if year < 2023:
            continue
        if not isinstance(row, dict):
            cells = list(row)
            for index, name in enumerate(FIELDS):
                if _blank(cells[index]):
                    raise PrimaryError(
                        f"B4_PRIMARY_2023: ERROR: {name} row {row_number}: "
                        "expected value, got blank"
                    )
            priced.add(str(cells[0]).strip())
            continue
        present = 0
        for name in FIELDS:
            if not _has_field(row, name):
                raise PrimaryError(
                    f"B4_PRIMARY_2023: ERROR: row {row_number}: expected "
                    f"{len(FIELDS)} fields, got {present}"
                )
            present += 1
            if name == "year":
                continue
            value = _raw_field(row, name)
            if _blank(value):
                raise PrimaryError(
                    f"B4_PRIMARY_2023: ERROR: {name} row {row_number}: "
                    "expected value, got blank"
                )
        priced.add(str(_raw_field(row, "zone")).strip())
    return priced


def classify_not_scored(
    am2: object, drc_zones: set[str], priced: set[str]
) -> list[dict[str, str]]:
    """Every DRC zone not priced gets one NOT_SCORED reason (AM-2 path)."""
    payload = _require_am2_object(am2)
    excluded_raw = payload.get("excluded")
    if not isinstance(excluded_raw, list):
        excluded_raw = []
    zones_present_raw = payload.get("zones_present")
    zones_present: set[str] = set()
    if isinstance(zones_present_raw, list):
        for code in zones_present_raw:
            zones_present.add(str(code))

    for code in ABSENT_FROM_FILE_ZONES:
        if code in zones_present:
            raise PrimaryError(
                f"B4_PRIMARY_2023: REFUSED: absent_from_file {code}: "
                "expected absent from house_sales, got present"
            )

    excluded_2023: dict[str, str] = {}
    for item in excluded_raw:
        if not isinstance(item, dict):
            continue
        year = item.get("year")
        if type(year) is not int:
            raise PrimaryError(
                "B4_PRIMARY_2023: ERROR: year row am2: expected integer, got "
                f"{type(year).__name__}"
            )
        if year == 2023:
            excluded_2023[str(item["zone"])] = str(item["reason"])

    not_scored: list[dict[str, str]] = []
    for zone in sorted(drc_zones):
        if zone in priced:
            continue
        if zone in excluded_2023:
            reason = excluded_2023[zone]
        elif zone in zones_present:
            reason = "no_2023_row"
        else:
            if zone not in ABSENT_FROM_FILE_ZONES:
                raise PrimaryError(
                    "B4_PRIMARY_2023: REFUSED: absent_from_file: expected one of "
                    f"{_ABSENT_PIN_LIST}, got {zone}"
                )
            reason = "absent_from_file"
        not_scored.append({"zone": zone, "reason": reason})
    return not_scored


def _counts(not_scored: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for reason in NOT_SCORED_REASONS:
        counts[reason] = 0
    for row in not_scored:
        reason = row["reason"]
        if reason in counts:
            counts[reason] = counts[reason] + 1
    return counts


def _load_census(path: Path) -> set[tuple[str, str]]:
    if not path.is_file():
        raise PrimaryError(f"B4_PRIMARY_2023: ERROR: census: expected {path}, got absent")
    text = path.read_text(encoding="utf-8")
    if text.strip() == "":
        raise PrimaryError(
            "B4_PRIMARY_2023: ERROR: census header: expected zone,reason, got absent"
        )
    reader = csv.reader(text.splitlines())
    try:
        header = next(reader)
    except StopIteration:
        raise PrimaryError(
            "B4_PRIMARY_2023: ERROR: census header: expected zone,reason, got absent"
        ) from None
    if header != ["zone", "reason"]:
        raise PrimaryError(
            "B4_PRIMARY_2023: ERROR: census header: expected zone,reason, got other header"
        )
    rows: set[tuple[str, str]] = set()
    for cells in reader:
        if len(cells) == 0:
            continue
        if len(cells) != 2:
            raise PrimaryError(
                "B4_PRIMARY_2023: ERROR: census row: expected zone,reason, got malformed"
            )
        zone, reason = cells[0].strip(), cells[1].strip()
        if zone == "" or reason == "" or reason not in NOT_SCORED_REASONS:
            raise PrimaryError(
                "B4_PRIMARY_2023: ERROR: census row: expected zone,reason, got malformed"
            )
        rows.add((zone, reason))
    if len(rows) == 0:
        raise PrimaryError(
            "B4_PRIMARY_2023: ERROR: census header: expected zone,reason, got absent"
        )
    return rows


def reconcile_census(path: Path, not_scored: list[dict[str, str]]) -> None:
    """Compare classification to the independent census CSV; refuse on mismatch."""
    census = _load_census(path)
    classified: set[tuple[str, str]] = set()
    for row in not_scored:
        classified.add((row["zone"], row["reason"]))
    only_s5 = classified - census
    only_census = census - classified
    if only_s5 or only_census:
        raise PrimaryError(
            "B4_PRIMARY_2023: REFUSED: not_scored reconcile: "
            f"expected {len(classified)} zones, got {len(census)}; "
            f"only_in_s5={len(only_s5)} only_in_census={len(only_census)}"
        )


def _not_scored_payload(
    denominator: int, not_scored: list[dict[str, str]]
) -> dict:
    return {
        "denominator": denominator,
        "counts": _counts(not_scored),
        "not_scored": not_scored,
    }


def build_primary_2023(
    b2_path: Path, drc_path: Path, *, census_path: Path | None = None
) -> dict:
    """Share and builder rows for 2023. Writes nothing.

    When ``am2`` is present on the B2 payload, also returns ``not_scored`` and
    ``not_scored_payload``. Legacy payloads (no ``am2`` key) are unchanged.

    AM-2 refusals (object/year types, absent_from_file pins, census reconcile)
    run before ``read_price_field`` (§8 spy 0 on every refusal).
    """
    _require_file(b2_path)
    _require_file(drc_path)
    sales_payload = json.loads(b2_path.read_text(encoding="utf-8"))
    drc = _drc_map(json.loads(drc_path.read_text(encoding="utf-8")))

    am2_present = isinstance(sales_payload, dict) and "am2" in sales_payload
    not_scored: list[dict[str, str]] = []
    if am2_present:
        am2 = _require_am2_object(sales_payload["am2"])
        _validate_am2_years(am2)
        priced_ids = _priced_zones_without_price_read(sales_payload)
        not_scored = classify_not_scored(am2, set(drc), priced_ids)
        if census_path is not None:
            reconcile_census(census_path, not_scored)
        restricted: dict[str, float] = {}
        for zone, cost in drc.items():
            if zone in priced_ids:
                restricted[zone] = cost
        drc = restricted
    elif census_path is not None:
        raise PrimaryError("B4_PRIMARY_2023: ERROR: am2: expected object, got absent")

    kept: list[dict[str, object]] = []
    for row_number, row in enumerate(_house_sales(sales_payload), start=1):
        screened = _sales_row(row, row_number)
        if screened is not None:
            kept.append(screened)
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
    result: dict = {"primary": primary, "builder": builder}
    if am2_present:
        result["not_scored"] = not_scored
        result["not_scored_payload"] = _not_scored_payload(len(means), not_scored)
    return result


def write_outputs(primary_path: Path, builder_path: Path, built: Mapping[str, list[dict]]) -> None:
    for path, key in ((primary_path, "primary"), (builder_path, "builder")):
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"zones": built[key]}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_not_scored(path: Path, payload: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b2-out", type=Path, required=True)
    parser.add_argument("--drc", type=Path, required=True)
    parser.add_argument("--primary-out", type=Path, required=True)
    parser.add_argument("--builder-out", type=Path, required=True)
    parser.add_argument("--not-scored-out", type=Path, default=None)
    parser.add_argument("--reconcile-census", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        built = build_primary_2023(
            args.b2_out, args.drc, census_path=args.reconcile_census
        )
    except DroppedRows as exc:
        sys.stdout.write(f"dropped_no_price={exc.no_price} dropped_no_cost={exc.no_cost}\n")
        return 1
    except PrimaryError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    # Reconcile (if any) succeeded; write outputs only after refusals are cleared.
    write_outputs(args.primary_out, args.builder_out, built)
    if "not_scored_payload" in built:
        counts = built["not_scored_payload"]["counts"]
        sys.stdout.write(
            "not_scored "
            f"suppressed_price={counts['suppressed_price']} "
            f"no_sales={counts['no_sales']} "
            f"no_2023_row={counts['no_2023_row']} "
            f"absent_from_file={counts['absent_from_file']}\n"
        )
        if args.not_scored_out is not None:
            write_not_scored(args.not_scored_out, built["not_scored_payload"])
    sys.stdout.write(f"zones={len(built['primary'])}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
