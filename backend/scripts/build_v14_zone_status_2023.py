#!/usr/bin/env python3
"""HOLDOUT-2023-RUN PR-B2: one status row per DZ2011 for the 2023 holdout.

Ranks, flags, codes and counts only. No price, share, DRC or land value is
written: a column outside ``COLUMNS`` is refused before the file is written.

Inputs (all produced earlier in the same run):
  --primary     primary_estimates_2023.json  (P_C share/land_per_home/unavailable)
  --builder     builder_output_2023.json     (2023 zone price, read in memory only)
  --drc-corners drc_corners.json             (PR-B1)
  --per-zone    fitted_per_zone.json         (S_C)
  --not-scored  not_scored_2023.json         (AM-2)
  --merge-map / --iz-lookup                  (pinned, PR-A readers)

Rulings (Econometrician, 2 Nov 2026): 4. corners are P_L, P_C, P_H and S_C;
5. no_cell = priced 2023 zones not in the merge map, pre-registered at 419.
Any other count is NOT_RUN with the difference reported.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from georgist import surface_rent as sr
from georgist.v14_fit_joins import JoinError, read_iz_lookup, read_merge_map

STATUSES = ("estimated", "unavailable", "model_failure", "no_cell", "not_scored")
NOT_SCORED_REASONS = ("suppressed_price", "no_2023_row", "absent_from_file", "no_sales")
NO_CELL_PREREGISTERED = 419
SURFACES = ("P_L", "P_C", "P_H", "S_C")
COLUMNS = (
    "zone", "council", "status_P", "status_S", "not_scored_reason",
    "rank_P_L", "rank_P_C", "rank_P_H", "rank_S_C",
)
TOKEN = "B7_ZONE_STATUS"
RANK_METRIC = "residual_land_value_per_dwelling"
TIE_SEED = 20261015  # D1 r3: numpy default_rng permutation breaks exact ties


class StatusError(ValueError):
    """Refused, or NOT_RUN under a pre-registered assertion."""


def _load(path: Path, name: str) -> object:
    if not path.is_file():
        raise StatusError(f"{TOKEN}: REFUSED: {name}: expected file, got absent")
    return json.loads(path.read_text(encoding="utf-8"))


def _zones(payload: object, name: str) -> dict[str, Mapping]:
    rows = payload.get("zones") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        raise StatusError(f"{TOKEN}: REFUSED: {name}: expected zones list, got other")
    return {str(row["zone"]): row for row in rows}


def seeded_ranks(values: Mapping[str, float]) -> dict[str, int]:
    """1 = lowest. Zero-filled zones (value 0) are excluded (D1 r3 §3, never ranked as zero).

    Exact ties are ordered by one numpy default_rng(TIE_SEED) permutation over the
    sorted zone codes, so the ranks are a deterministic 1..n with no gaps.
    """
    kept = sorted(zone for zone, value in values.items() if value != 0)
    order = np.random.default_rng(TIE_SEED).permutation(len(kept))
    tiebreak = {zone: int(position) for zone, position in zip(kept, order)}
    ordered = sorted(kept, key=lambda zone: (values[zone], tiebreak[zone]))
    return {zone: rank for rank, zone in enumerate(ordered, start=1)}


def assert_corner_order(land: Mapping[str, Mapping[str, float]]) -> None:
    """In-memory only: P_L <= P_C <= P_H per zone, checked before any ranking."""
    for zone in sorted(land["P_C"]):
        low, central, high = land["P_L"].get(zone), land["P_C"][zone], land["P_H"].get(zone)
        if (low is not None and low > central) or (high is not None and central > high):
            raise StatusError(f"{TOKEN}: REFUSED: corner order zone {zone}: expected P_L<=P_C<=P_H, got other")


def assert_no_cell(priced: Sequence[str], merge_map: Mapping[str, object]) -> set[str]:
    no_cell = {zone for zone in priced if zone not in merge_map}
    if len(no_cell) != NO_CELL_PREREGISTERED:
        raise StatusError(
            f"{TOKEN}: NOT_RUN: no_cell: expected {NO_CELL_PREREGISTERED}, got {len(no_cell)} "
            f"(diff {len(no_cell) - NO_CELL_PREREGISTERED:+d})"
        )
    return no_cell


def status_s(zone: str, not_scored: Mapping[str, str], no_cell: set[str], per_zone: Mapping[str, Mapping]) -> str:
    if zone in not_scored:
        return "not_scored"
    if zone in no_cell:
        return "no_cell"
    record = per_zone.get(zone)
    if record is None:
        raise StatusError(f"{TOKEN}: REFUSED: S_C zone {zone}: expected per-zone record, got absent")
    if record.get("model_failure"):
        return "model_failure"
    if record.get("unavailable"):
        return "unavailable"
    return "estimated"


def build_status(
    *,
    primary: Mapping[str, Mapping],
    builder: Mapping[str, Mapping],
    corners: Mapping[str, Mapping],
    per_zone: Mapping[str, Mapping],
    not_scored: Mapping[str, str],
    merge_map: Mapping[str, object],
    iz_lookup: Mapping[str, Mapping[str, str]],
) -> list[dict]:
    for zone, reason in not_scored.items():
        if reason not in NOT_SCORED_REASONS:
            raise StatusError(f"{TOKEN}: REFUSED: not_scored reason {zone}: expected enum, got {reason}")
    priced = sorted(primary)
    no_cell = assert_no_cell(priced, merge_map)
    land: dict[str, dict[str, float]] = {name: {} for name in ("P_L", "P_C", "P_H")}
    status_p: dict[str, str] = {}
    for zone in priced:
        if zone not in builder or zone not in corners:
            raise StatusError(f"{TOKEN}: REFUSED: zone {zone}: expected builder and corner rows, got absent")
        price = float(builder[zone]["price"])
        corner = corners[zone]
        residuals = {
            # Low DRC is the HIGH land corner (PR-B1 note).
            "P_H": sr.residual_land_value(price, float(corner["drc_low"])),
            "P_C": sr.residual_land_value(price, float(corner["drc_central"])),
            "P_L": sr.residual_land_value(price, float(corner["drc_high"])),
        }
        central = residuals["P_C"]
        central_unavailable = sr.estimate_label_for_residual(central) == "unavailable"
        if central_unavailable != bool(primary[zone]["unavailable"]) or (
            central.land_value != primary[zone]["land_per_home"]
        ):
            raise StatusError(f"{TOKEN}: REFUSED: P_C zone {zone}: expected equal to primary file, got different")
        status_p[zone] = "unavailable" if central_unavailable else "estimated"
        if central_unavailable:
            continue
        for name in ("P_L", "P_C", "P_H"):
            residual = residuals[name]
            if sr.estimate_label_for_residual(residual) != "unavailable":
                land[name][zone] = float(residual.land_value)
    s_status = {zone: status_s(zone, not_scored, no_cell, per_zone) for zone in priced}
    s_values = {
        zone: float(per_zone[zone]["land_per_home"]) for zone, value in s_status.items() if value == "estimated"
    }
    assert_corner_order(land)
    ranks = {name: seeded_ranks(values) for name, values in land.items()}
    ranks["S_C"] = seeded_ranks(s_values)
    rows = []
    for zone in sorted(iz_lookup):
        council = iz_lookup[zone]["CA"]
        if zone in not_scored:
            row = {"status_P": "not_scored", "status_S": "not_scored", "not_scored_reason": not_scored[zone]}
        elif zone in primary:
            row = {"status_P": status_p[zone], "status_S": s_status[zone], "not_scored_reason": None}
        else:
            raise StatusError(f"{TOKEN}: REFUSED: zone {zone}: expected priced or not_scored, got neither")
        row.update({"zone": zone, "council": council})
        for name in SURFACES:
            row[f"rank_{name}"] = ranks[name].get(zone)
        rows.append({column: row[column] for column in COLUMNS})
    for zone in list(primary) + list(not_scored):
        if zone not in iz_lookup:
            raise StatusError(f"{TOKEN}: REFUSED: zone {zone}: expected DZ2011 in lookup, got absent")
    assert_rows(rows)
    return rows


def assert_rows(rows: Sequence[Mapping]) -> None:
    for row in rows:
        if tuple(row) != COLUMNS:
            raise StatusError(f"{TOKEN}: REFUSED: columns: expected {','.join(COLUMNS)}, got {','.join(row)}")
        for column in ("status_P", "status_S"):
            if row[column] not in STATUSES:
                raise StatusError(f"{TOKEN}: REFUSED: {column} {row['zone']}: expected enum, got {row[column]}")
        if row["status_P"] in {"model_failure", "no_cell"}:
            raise StatusError(f"{TOKEN}: REFUSED: status_P {row['zone']}: expected P status, got {row['status_P']}")
        if row["status_P"] != "estimated" and any(row[f"rank_{n}"] is not None for n in ("P_L", "P_C", "P_H")):
            raise StatusError(f"{TOKEN}: REFUSED: rank_P {row['zone']}: expected null, got rank")
        if row["status_S"] != "estimated" and row["rank_S_C"] is not None:
            raise StatusError(f"{TOKEN}: REFUSED: rank_S_C {row['zone']}: expected null, got rank")


def counts_by_council(rows: Sequence[Mapping]) -> dict:
    out: dict[str, dict[str, dict[str, int]]] = {}
    for row in rows:
        entry = out.setdefault(row["council"], {"P": {s: 0 for s in STATUSES}, "S": {s: 0 for s in STATUSES}})
        entry["P"][row["status_P"]] += 1
        entry["S"][row["status_S"]] += 1
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("primary", "builder", "drc-corners", "per-zone", "not-scored", "merge-map", "iz-lookup", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        not_scored_payload = _load(args.not_scored, "not_scored")
        not_scored = {str(row["zone"]): str(row["reason"]) for row in not_scored_payload["not_scored"]}
        rows = build_status(
            primary=_zones(_load(args.primary, "primary"), "primary"),
            builder=_zones(_load(args.builder, "builder"), "builder"),
            corners=_load(args.drc_corners, "drc_corners")["zones"],
            per_zone=_zones(_load(args.per_zone, "per_zone"), "per_zone"),
            not_scored=not_scored,
            merge_map=read_merge_map(args.merge_map),
            iz_lookup=read_iz_lookup(args.iz_lookup),
        )
    except (StatusError, JoinError) as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    payload = {
        "label": "Estimate, internal only. Ranks, flags and counts; no values.",
        "surfaces": list(SURFACES),
        "rank_metric": RANK_METRIC,
        "rank_rule": "ascending, 1 = lowest; zero-filled and No-estimate zones excluded; ties by numpy default_rng(20261015) permutation",
        "counts_by_council": counts_by_council(rows),
        "zones": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.write(f"{TOKEN}: OK zones={len(rows)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
