"""SYNTHETIC join inputs for HOLDOUT-2023-RUN PR-A tests. Codes only, no prices."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from georgist.v14_fit_joins import (
    IZ_LOOKUP_HEADER,
    JOIN_PINS,
    MERGE_MAP_HEADER,
    _sha256,
)

SYNTHETIC_CA = "CA1"


def write_join_files(
    directory: Path, zones: Iterable[str], *, no_cell: Iterable[str] = ()
) -> dict[str, Path]:
    zones = sorted(set(zones))
    no_cell = sorted(set(no_cell))
    merge = directory / "merge_map.SYNTHETIC.csv"
    iz = directory / "iz_lookup.SYNTHETIC.csv"
    nc = directory / "no_cell.SYNTHETIC.txt"
    merge_rows = [",".join(MERGE_MAP_HEADER)]
    for zone in zones:
        if zone in no_cell:
            continue
        merge_rows.append(f"{zone},{SYNTHETIC_CA},TL1,1,urban,40.0,10,c_ca,c_itl3,c,ca")
    merge.write_text("\n".join(merge_rows) + "\n", encoding="utf-8")
    iz_rows = [",".join(IZ_LOOKUP_HEADER)] + [f"{zone},IZ1,{SYNTHETIC_CA}" for zone in zones]
    iz.write_text("\n".join(iz_rows) + "\n", encoding="utf-8")
    nc.write_text("".join(f"{zone}\n" for zone in no_cell), encoding="utf-8")
    return {"merge_map": merge, "iz_lookup": iz, "no_cell_list": nc}


def pin_join_files(paths: dict[str, Path]) -> dict[str, str]:
    """Point JOIN_PINS at the fixture files. Returns the saved production pins."""
    saved = dict(JOIN_PINS)
    JOIN_PINS["merge_map"] = _sha256(paths["merge_map"])
    JOIN_PINS["iz_lookup"] = _sha256(paths["iz_lookup"])
    JOIN_PINS["no_cell"] = _sha256(paths["no_cell_list"])
    return saved


def restore_join_pins(saved: dict[str, str]) -> None:
    JOIN_PINS.clear()
    JOIN_PINS.update(saved)


def join_argv(paths: dict[str, Path]) -> list[str]:
    return [
        "--merge-map", str(paths["merge_map"]),
        "--iz-lookup", str(paths["iz_lookup"]),
        "--no-cell-list", str(paths["no_cell_list"]),
    ]
