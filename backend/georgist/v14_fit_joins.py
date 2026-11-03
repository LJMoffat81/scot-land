"""HOLDOUT-2023-RUN PR-A: join the hedonic fit fields onto B2 fit rows.

The fit (v14_hedonic.fit_headline) needs ``cell`` and ``a_m2`` (prereg
e1ab6d0a L170-173) and clusters on ``iz`` (L174). B2 sales rows carry none of
them. They come from two sha-pinned files only:

- merge map (prereg §8.9 O-MM, sha 581b0aa1...): cell_final, a_z_m2, ca2019,
  ur3, ur6, itl3. Counts and areas only, no prices.
- DZ2011 -> IZ2011 lookup (Scottish Government open data, OGL v3, sha a13d2853...).

No value is computed here. Every refusal is one exact line.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Mapping, Sequence

MERGE_MAP_SHA256 = "581b0aa1647c5af7ce5b9617e35fcfa73982bc8712a42eb63242243ee6a95947"
IZ_LOOKUP_SHA256 = "a13d2853e9737ccd6d499eea0ca29e417f5c9ac132828c2c24fce9b48bf004f4"
# AM-2 s3 D-3: the 570 fit-side zones with one complete fit year have no cell.
# They are excluded and disclosed (AM2_s3_addendum.md item 4), never re-celled.
NO_CELL_LIST_SHA256 = "f4a0bead7d9e8264b7bcd3c4881edbf0cee3b13853f4402fc7396421be27aaa6"
JOIN_PINS: dict[str, str] = {
    "merge_map": MERGE_MAP_SHA256,
    "iz_lookup": IZ_LOOKUP_SHA256,
    "no_cell": NO_CELL_LIST_SHA256,
}

MERGE_MAP_HEADER = (
    "dz2011", "ca2019", "itl3", "ur6", "ur3", "a_z_m2",
    "n_sales_fit", "cell_ca", "cell_itl3", "cell_final", "merge_level",
)
IZ_LOOKUP_HEADER = ("DZ2011", "IZ2011", "CA")
# fit-row field <- merge-map column
MERGE_FIELDS = (
    ("cell", "cell_final"),
    ("a_m2", "a_z_m2"),
    ("ca", "ca2019"),
    ("ur3", "ur3"),
    ("ur6", "ur6"),
    ("itl3", "itl3"),
)
JOIN_FIELDS = tuple(name for name, _ in MERGE_FIELDS) + ("iz",)
TOKEN = {"merge_map": "B2_MERGE_MAP", "iz_lookup": "B2_IZ_LOOKUP", "no_cell": "B2_NO_CELL"}


class JoinError(ValueError):
    """A fit-join input or row was refused."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_pin(path: Path, name: str) -> None:
    token = TOKEN[name]
    if not path.is_file():
        raise JoinError(f"{token}: REFUSED: file: expected {path}, got absent")
    expected = JOIN_PINS[name]
    actual = _sha256(path)
    if actual != expected:
        raise JoinError(f"{token}: REFUSED: sha256: expected {expected}, got {actual}")


def read_no_cell(path: Path) -> frozenset[str]:
    _check_pin(path, "no_cell")
    codes = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return frozenset(codes)


def _read(path: Path, name: str, header: Sequence[str], key: str) -> dict[str, dict[str, str]]:
    token = TOKEN[name]
    _check_pin(path, name)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        found = tuple(next(reader, ()))
        if found != tuple(header):
            raise JoinError(
                f"{token}: REFUSED: header: expected {','.join(header)}, got {','.join(found) or 'absent'}"
            )
        out: dict[str, dict[str, str]] = {}
        for row_number, row in enumerate(reader, start=1):
            if len(row) != len(header):
                raise JoinError(
                    f"{token}: REFUSED: row {row_number}: expected {len(header)} fields, got {len(row)}"
                )
            record = dict(zip(header, row))
            for column in header:
                if record[column].strip() == "":
                    raise JoinError(f"{token}: REFUSED: {column} row {row_number}: expected value, got blank")
            code = record[key]
            if code in out:
                raise JoinError(f"{token}: REFUSED: {key} row {row_number}: expected unique, got duplicate {code}")
            out[code] = record
    return out


def read_merge_map(path: Path) -> dict[str, dict[str, str]]:
    return _read(path, "merge_map", MERGE_MAP_HEADER, "dz2011")


def read_iz_lookup(path: Path) -> dict[str, dict[str, str]]:
    return _read(path, "iz_lookup", IZ_LOOKUP_HEADER, "DZ2011")


def join_fit_rows(
    rows: Sequence[Mapping],
    merge_map: Mapping[str, Mapping[str, str]],
    iz_lookup: Mapping[str, Mapping[str, str]],
    no_cell: frozenset[str],
) -> tuple[list[dict], list[str]]:
    """Add JOIN_FIELDS to each fit row.

    A zone on the pinned no_cell list is dropped and returned for disclosure.
    Any other zone missing from either file is refused.
    """
    joined = []
    dropped: list[str] = []
    for row_number, row in enumerate(rows, start=1):
        zone = str(row["zone"])
        if zone in no_cell:
            if zone in merge_map:
                raise JoinError(f"B2_FIT_ROWS: REFUSED: cell row {row_number}: expected no_cell zone absent from merge map, got present")
            dropped.append(zone)
            continue
        cell = merge_map.get(zone)
        if cell is None:
            raise JoinError(f"B2_FIT_ROWS: REFUSED: cell row {row_number}: expected merge-map zone, got absent")
        iz = iz_lookup.get(zone)
        if iz is None:
            raise JoinError(f"B2_FIT_ROWS: REFUSED: iz row {row_number}: expected IZ2011 code, got absent")
        if iz["CA"] != cell["ca2019"]:
            raise JoinError(
                f"B2_FIT_ROWS: REFUSED: ca row {row_number}: expected {cell['ca2019']}, got {iz['CA']}"
            )
        out = dict(row)
        for name, column in MERGE_FIELDS:
            value: object = cell[column]
            if name == "a_m2":
                value = float(value)
            elif name == "ur6":
                value = int(value)
            out[name] = value
        out["iz"] = iz["IZ2011"]
        joined.append(out)
    return joined, sorted(dropped)
