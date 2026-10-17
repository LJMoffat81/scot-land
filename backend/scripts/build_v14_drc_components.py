#!/usr/bin/env python3
"""Write one DRC component record per DZ2011 zone.

``epc_row`` comes from the EPC rollup, ``nrs2017_row`` from NRS dwellings by
type and rooms, and ``estate_row`` from plot-band shares after
``borrow_plot_bands`` (council x UR6, then UR6 national). No price column
is read. Pins are full sha256 digests.

Usage (from ``backend/``)::

    python -m scripts.build_v14_drc_components --out components.json \\
        --epc epc.csv --nrs2017 nrs.csv --plot-bands plots.csv --ur6 ur6.csv
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

from georgist import surface_rent as sr

PIN_TABLE = {
    "epc": "13a5f647a833d89ec7aad0a82cd3cfc52d375b31b05e3b5ad7f4f12c998e2618",
    "nrs2017": "b9bd3364ade0a843a3157fe7e33de5003144f18c54f87c9e410c4dd3fc04a9da",
    "plot_bands": "9bb56d3be6181740ae07fb06607c45374ce448d6c73a00cdea3c7c81b4886e48",
    "ur6": "1f32a81532912334e3cd071e2f12f523e66068d14c73e5db4ae51add239b1a92",
}
PIN_ORDER = ("epc", "nrs2017", "plot_bands", "ur6")
FULL_SHA = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_COLUMNS = {
    "epc": ("code",),
    "nrs2017": ("code",),
    "plot_bands": ("code",),
    "ur6": ("code", "council_code", "ur6_class"),
}


class ComponentsError(ValueError):
    """A DRC component input failed a pin, file, or cell check."""


def copy_pin_table() -> dict[str, str]:
    """Test-only hook. A copy, so production pins stay put."""
    return {key: str(PIN_TABLE[key]) for key in PIN_ORDER}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def read_price_cell(value: str) -> str:
    """Price-column hook. The component readers do not call it."""
    return value


def borrow_plot_bands(rows, zone_meta, estate_cfg):
    """Council x UR6, then UR6 national. Tests spy on this wrapper."""
    return sr.borrow_plot_bands(rows, zone_meta, estate_cfg)


def _pin_text(value: object) -> str:
    if value is None:
        return "blank"
    text = str(value)
    if text.strip() == "":
        return "blank"
    return text


def assert_pins(paths: dict[str, Path], pins: dict[str, str]) -> None:
    """Full sha256, then the file, then the digest. Readers have not run."""
    for name in PIN_ORDER:
        text = _pin_text(pins.get(name))
        if text == "blank" or FULL_SHA.fullmatch(text) is None:
            raise ComponentsError(
                f"B1_COMPONENTS: REFUSED: pin: expected full sha256, got {text}"
            )
    for name in PIN_ORDER:
        path = paths[name]
        if not path.is_file():
            raise ComponentsError(f"B1_COMPONENTS: ERROR: file: expected {path}, got absent")
        actual = sha256_file(path)
        if actual != pins[name]:
            raise ComponentsError(
                f"B1_COMPONENTS: REFUSED: {name} sha256: expected {pins[name]}, got {actual}"
            )


def _table(path: Path, kind: str) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if not lines:
        raise ComponentsError(f"B1_COMPONENTS: ERROR: header: expected header, got absent")
    reader = csv.reader(io.StringIO("\n".join(lines) + "\n"))
    parsed = list(reader)
    header = parsed[0]
    width = len(header)
    required = REQUIRED_COLUMNS[kind]
    rows: list[dict[str, str]] = []
    for row_number, cells in enumerate(parsed[1:], start=1):
        if len(cells) < width:
            raise ComponentsError(
                f"B1_COMPONENTS: ERROR: row {row_number}: expected {width} fields, got {len(cells)}"
            )
        item: dict[str, str] = {}
        for index, column in enumerate(header):
            if column == "price":
                continue
            value = cells[index]
            if column in required and value.strip() == "":
                raise ComponentsError(
                    f"B1_COMPONENTS: ERROR: {column} row {row_number}: expected value, got blank"
                )
            item[column] = value
        rows.append(item)
    return rows


def load_epc(path: Path) -> dict[str, dict[str, str]]:
    return {row["code"]: row for row in _table(path, "epc")}


def load_nrs2017(path: Path) -> dict[str, dict[str, str]]:
    return {row["code"]: row for row in _table(path, "nrs2017")}


def load_plot_bands(path: Path) -> dict[str, dict[str, str]]:
    return {row["code"]: row for row in _table(path, "plot_bands")}


def load_ur6(path: Path) -> dict[str, tuple[str, int]]:
    meta: dict[str, tuple[str, int]] = {}
    for row in _table(path, "ur6"):
        meta[row["code"]] = (row["council_code"], int(row["ur6_class"]))
    return meta


def build_components(
    paths: dict[str, Path],
    *,
    pins: dict[str, str] | None = None,
) -> list[dict]:
    """One record per UR6 zone. Plot-band shares are borrowed before return."""
    table = PIN_TABLE if pins is None else pins
    assert_pins(paths, table)
    epc = load_epc(paths["epc"])
    nrs = load_nrs2017(paths["nrs2017"])
    plots = load_plot_bands(paths["plot_bands"])
    zones = load_ur6(paths["ur6"])
    estate_cfg = sr.load_config()["estate"]
    estate = borrow_plot_bands(plots, zones, estate_cfg)
    records = []
    for code in sorted(zones):
        records.append(
            {
                "dz2011": code,
                "epc_row": epc.get(code),
                "nrs2017_row": nrs.get(code),
                "estate_row": estate.get(code),
            }
        )
    return records


def write_components(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epc", type=Path, required=True)
    parser.add_argument("--nrs2017", type=Path, required=True)
    parser.add_argument("--plot-bands", type=Path, required=True)
    parser.add_argument("--ur6", type=Path, required=True)
    args = parser.parse_args(argv)
    paths = {
        "epc": args.epc,
        "nrs2017": args.nrs2017,
        "plot_bands": args.plot_bands,
        "ur6": args.ur6,
    }
    try:
        records = build_components(paths)
        write_components(args.out, records)
    except ComponentsError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stdout.write(f"zones={len(records)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
