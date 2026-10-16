#!/usr/bin/env python3
"""Build ``--check-inputs`` JSON for both v1.4 estimators.

Joins the builder output, primary estimates, the fitted hedonic, the
DZ2011-native check-3 plot passes, the frozen v1.3 two-route check-4 inputs,
dz2022 keys for check 6, and UR6. Every source needs a pinned sha256. A
missing pin is listed and nothing is substituted. No scored run. No 2024
price cell is read.

Usage (from ``backend/``)::

    python -m scripts.build_v14_check_inputs --out checks.json \\
        --builder-output builder.json --pin builder_output=<sha256> ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SOURCES = (
    "builder_output",
    "primary_estimates",
    "fitted_hedonic",
    "check3_plot_passes",
    "check4_rent_route",
    "dz2022_keys",
    "ur6",
)

SOURCE_FIELDS = {
    "builder_output": frozenset({"price", "count_in_1d", "unavailable", "model_failure", "hla"}),
    "primary_estimates": frozenset({"share", "land_per_home", "unavailable", "model_failure", "count_in_1d"}),
    "fitted_hedonic": frozenset({"share", "land_per_home", "unavailable", "model_failure", "count_in_1d"}),
    "check3_plot_passes": frozenset(
        {
            "pass_at",
            "pass_at_all_homes",
            "pass_at_dz22",
            "measured_detached_pass",
            "detached_plot_m2",
            "house_plot_m2",
        }
    ),
    "check4_rent_route": frozenset({"residual_land", "capitalised_land"}),
    "dz2022_keys": frozenset({"dz2022", "share_low", "share_central", "share_high"}),
    "ur6": frozenset({"ur6"}),
}

REQUIRED_ZONE_FIELDS = (
    "zone",
    "share",
    "price",
    "ur6",
    "land_per_home",
    "residual_land",
    "capitalised_land",
    "pass_at",
    "dz2022",
    "share_low",
    "share_central",
    "share_high",
)

ALLOWED_ZONE_FIELDS = frozenset(REQUIRED_ZONE_FIELDS) | frozenset(
    field for fields in SOURCE_FIELDS.values() for field in fields
)


class CheckInputError(ValueError):
    """A check-input source is unpinned, mismatched, or missing a frozen field."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def missing_pins(paths: dict[str, Path | None], pins: dict[str, str]) -> list[str]:
    """Sources that have no path or no sha pin. Order follows ``SOURCES``."""
    missing = []
    for name in SOURCES:
        path = paths.get(name)
        if path is None or not pins.get(name):
            missing.append(name)
    return missing


def assert_pinned(paths: dict[str, Path | None], pins: dict[str, str]) -> None:
    missing = missing_pins(paths, pins)
    if missing:
        listed = ", ".join(missing)
        raise CheckInputError(f"inputs without a pinned sha: {listed}")
    for name in SOURCES:
        path = paths[name]
        assert path is not None
        digest = sha256_file(path)
        if digest != pins[name]:
            raise CheckInputError(f"{name} sha256 {digest} != {pins[name]}")


def _rows(payload) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("zones"), list):
        return list(payload["zones"])
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict) and payload and all(isinstance(value, dict) for value in payload.values()):
        return [{"zone": zone, **fields} for zone, fields in payload.items()]
    raise CheckInputError("input JSON must be a zone list or a zone map")


def load_source(path: Path, source: str) -> dict[str, dict]:
    """One source, restricted to the fields that source is allowed to carry."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    allowed = SOURCE_FIELDS[source]
    zones: dict[str, dict] = {}
    for row in _rows(payload):
        if "year" in row and int(row["year"]) >= 2024:
            raise CheckInputError("year >= 2024 refused")
        if "zone" not in row:
            raise CheckInputError(f"{source} row has no zone")
        unknown = sorted(key for key in row if key not in allowed and key != "zone" and key != "year")
        if unknown:
            raise CheckInputError(f"{source} field not in the frozen text: {', '.join(unknown)}")
        code = str(row["zone"])
        zones[code] = {key: row[key] for key in row if key in allowed}
    return zones


def build_v14_check_inputs(tables: dict[str, dict[str, dict]]) -> dict[str, list[dict]]:
    """Join pinned sources into ``primary_zones`` and ``secondary_zones``."""
    if set(tables) != set(SOURCES):
        raise CheckInputError("tables do not match the source list")
    base = set(tables["builder_output"])
    for name in SOURCES:
        if set(tables[name]) != base:
            raise CheckInputError(f"{name} zones do not match the builder output")
    primary: list[dict] = []
    secondary: list[dict] = []
    missing: list[str] = []
    for code in sorted(base):
        shared: dict = {"zone": code}
        for name in ("builder_output", "check3_plot_passes", "check4_rent_route", "dz2022_keys", "ur6"):
            shared.update(tables[name][code])
        for label, estimate in (
            ("primary", tables["primary_estimates"][code]),
            ("secondary", tables["fitted_hedonic"][code]),
        ):
            zone = dict(shared)
            zone.update(estimate)
            unknown = sorted(key for key in zone if key not in ALLOWED_ZONE_FIELDS)
            if unknown:
                raise CheckInputError(f"field not in the frozen text: {', '.join(unknown)}")
            absent = [field for field in REQUIRED_ZONE_FIELDS if field not in zone]
            if absent:
                missing.append(f"{label} {code}: {', '.join(absent)}")
                continue
            if label == "primary":
                primary.append(zone)
            else:
                secondary.append(zone)
    if missing:
        raise CheckInputError("missing fields: " + "; ".join(missing))
    return {"primary_zones": primary, "secondary_zones": secondary}


def _parse_pins(items: list[str]) -> dict[str, str]:
    pins: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise CheckInputError(f"pin must be name=sha256, got {item}")
        name, digest = item.split("=", 1)
        pins[name] = digest
    return pins


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pin", action="append", default=[], help="name=sha256, one per source.")
    for name in SOURCES:
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, default=None, dest=name)
    args = parser.parse_args(argv)
    paths = {name: getattr(args, name) for name in SOURCES}
    try:
        pins = _parse_pins(list(args.pin))
        assert_pinned(paths, pins)
        tables = {name: load_source(paths[name], name) for name in SOURCES}
        payload = build_v14_check_inputs(tables)
    except (CheckInputError, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.write(f"wrote {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
