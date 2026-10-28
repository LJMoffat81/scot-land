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
import math
import sys
from pathlib import Path
from typing import Any, Mapping

from georgist.check3_record import Check3RecordError, validate_check3_record

from georgist.v14_hedonic import apply_frozen_coefficients, fit_headline

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
    "check4_f8": frozenset(
        {
            "capitalised_land",
            "capitalised_land_unadjusted",
            "capitalised_property",
            "capitalised_property_unadjusted",
            "drc",
            "plus4_applied",
        }
    ),
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
# 3c extends this tuple. The message joins the values with "|".
YEAR_MODES = (2023, 2024)
S2_S3 = ("builder_output", "primary_estimates", "fitted_hedonic")
# 2024 rows must carry these keys. Year is screened before any price cell.
SOURCE_REQUIRED = {
    "builder_output": ("zone", "year", "price", "count_in_1d", "unavailable", "model_failure", "hla"),
    "primary_estimates": ("zone", "year", "share", "land_per_home", "unavailable", "count_in_1d"),
    "fitted_hedonic": (
        "zone",
        "year",
        "share",
        "land_per_home",
        "unavailable",
        "model_failure",
        "count_in_1d",
        "cell",
    ),
}
# Bound for the fit spy. The 2024 path does not call it.
_REFIT = (fit_headline,)


class CheckInputError(ValueError):
    """A check-input source is unpinned, mismatched, or missing a frozen field."""


class Check3NotRun(dict):
    """Check-3 source with no per-zone fields. The 2023 record is not a passes file."""


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
    for name in SOURCES:
        path = paths.get(name)
        if path is not None and not path.is_file():
            raise CheckInputError(f"B6: ERROR: file: expected {path}, got absent")
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


def _screen_year(value) -> int:
    """Blank, non-integer and 2024 years fail closed before later fields are used."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise CheckInputError("year field is blank")
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (int, str)):
        raise CheckInputError("year is not an integer")
    if isinstance(value, str):
        stripped = value.strip()
        digits = stripped[1:] if stripped[0:1] == "-" else stripped
        if not digits.isdigit():
            raise CheckInputError("year is not an integer")
        year = int(stripped)
    else:
        year = int(value)
    if year >= 2024:
        raise CheckInputError("year >= 2024 refused")
    return year


def read_price_cell(value):
    """Price hook. A refused year does not call it."""
    return value


def _year_error(row_number: int, got: object) -> CheckInputError:
    return CheckInputError(f"B6: ERROR: year row {row_number}: expected integer, got {got}")


def _parse_mode_year(value, row_number: int) -> int:
    if value is None:
        raise _year_error(row_number, "short" if value is None else value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            raise _year_error(row_number, "blank")
        digits = text[1:] if text[0:1] == "-" else text
        if not digits.isdigit():
            raise _year_error(row_number, text)
        return int(text)
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, int):
        raise _year_error(row_number, value)
    return int(value)


def _screen_mode_year(row: dict, row_number: int, mode: int) -> int:
    """Year before any later field. 2023 keeps the >=2024 refusal. 2024 keeps only 2024."""
    if "year" not in row:
        raise _year_error(row_number, "short")
    year = _parse_mode_year(row["year"], row_number)
    if mode == 2024:
        if year != 2024:
            raise CheckInputError(f"B6: REFUSED: year: expected 2024, got {year}")
        return year
    if year >= 2024:
        raise CheckInputError(f"B6: REFUSED: year: expected <2024, got {year}")
    return year


def _cell_text(value: object) -> str:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return "absent"
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _refuse_cell(row_number: int, got: str) -> CheckInputError:
    return CheckInputError(
        f"B6: REFUSED: cell row {row_number}: expected one of beta_by_cell, got {got}"
    )


def _screen_mode_row(row: dict, source: str, row_number: int, mode: int) -> None:
    if mode != 2024 or source not in S2_S3:
        if "year" in row:
            _screen_mode_year(row, row_number, mode)
        return
    _screen_mode_year(row, row_number, mode)
    if source == "fitted_hedonic" and _cell_text(row.get("cell")) == "absent":
        raise _refuse_cell(row_number, "absent")
    required = SOURCE_REQUIRED[source]
    present = sum(1 for key in required if key in row)
    if present < len(required):
        raise CheckInputError(
            f"B6: ERROR: row {row_number}: expected {len(required)} fields, got {present}"
        )
    for key in required:
        value = row[key]
        if value is None or (isinstance(value, str) and value.strip() == ""):
            raise CheckInputError(
                f"B6: ERROR: {key} row {row_number}: expected value, got blank"
            )



def _validate_f8_capitalised(zone: str, row: Mapping[str, Any]) -> float:
    if "capitalised_land" not in row:
        raise CheckInputError(
            f"V14_CHECK_INPUTS: ERROR: check4_f8 {zone}: expected capitalised_land, got absent"
        )
    raw = row["capitalised_land"]
    if raw is None or isinstance(raw, bool) or not isinstance(raw, (int, float)):
        tname = "None" if raw is None else type(raw).__name__
        raise CheckInputError(
            f"V14_CHECK_INPUTS: ERROR: check4_f8 {zone}: expected positive number, got {tname}"
        )
    val = float(raw)
    if not math.isfinite(val):
        raise CheckInputError(
            f"V14_CHECK_INPUTS: ERROR: check4_f8 {zone}: expected positive number, got non-finite"
        )
    drc_val = row.get("drc")
    has_drc = isinstance(drc_val, (int, float)) and not isinstance(drc_val, bool) and float(drc_val) > 0.0
    if not has_drc and val <= 0.0:
        raise CheckInputError(
            f"V14_CHECK_INPUTS: ERROR: check4_f8 {zone}: expected positive number, got out of range"
        )
    cap_prop = row.get("capitalised_property")
    if cap_prop is not None:
        if isinstance(cap_prop, bool) or not isinstance(cap_prop, (int, float)) or not math.isfinite(float(cap_prop)) or float(cap_prop) <= 0.0:
            raise CheckInputError(
                f"V14_CHECK_INPUTS: ERROR: check4_f8 {zone}: expected positive number, got out of range"
            )
    return val


def load_check4_f8(path: Path) -> dict[str, dict]:
    if not path.is_file():
        raise CheckInputError(f"B6: ERROR: file: expected {path}, got absent")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckInputError(
            "V14_CHECK4: ERROR: check4_f8: expected JSON object, got invalid"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("zones"), list) or not payload["zones"]:
        raise CheckInputError(
            "V14_CHECK4: ERROR: check4_f8: expected JSON object, got invalid"
        )
    out: dict[str, dict] = {}
    for row in payload["zones"]:
        if not isinstance(row, dict) or "zone" not in row:
            raise CheckInputError(
                "V14_CHECK4: ERROR: check4_f8: expected JSON object, got invalid"
            )
        z = row["zone"]
        if type(z) is not str or not z.strip():
            tname = "None" if z is None else type(z).__name__
            raise CheckInputError(
                f"V14_CHECK4: ERROR: check4_f8 zone: expected str, got {tname}"
            )
        code = z.strip()
        if code in out:
            raise CheckInputError(
                f"V14_CHECK4: ERROR: check4_f8 {code}: expected one row, got duplicate"
            )
        cap_val = _validate_f8_capitalised(code, row)
        out[code] = {"capitalised_land": cap_val}
        if "drc" in row:
            out[code]["drc"] = row["drc"]
        if "capitalised_property" in row:
            out[code]["capitalised_property"] = row["capitalised_property"]
    return out


def load_source(path: Path, source: str, mode: int | None = None) -> dict[str, dict]:
    """One source, restricted to the fields that source is allowed to carry."""
    if source == "check4_f8":
        return load_check4_f8(path)
    if mode is not None and not path.is_file():
        raise CheckInputError(f"B6: ERROR: file: expected {path}, got absent")
    if source == "check3_plot_passes" and path.is_file():
        kind = validate_check3_record(path, year=mode, step="B6")
        if kind == "not_run":
            return Check3NotRun()
    payload = json.loads(path.read_text(encoding="utf-8"))
    allowed = SOURCE_FIELDS[source]
    zones: dict[str, dict] = {}
    for row_number, row in enumerate(_rows(payload), start=1):
        if mode is None:
            if "year" in row:
                _screen_year(row["year"])
        else:
            _screen_mode_row(row, source, row_number, mode)
        if "zone" not in row:
            raise CheckInputError(f"{source} row has no zone")
        carried = {"zone", "year"}
        if mode == 2024 and source == "fitted_hedonic":
            carried.add("cell")
        unknown = sorted(key for key in row if key not in allowed and key not in carried)
        if unknown:
            raise CheckInputError(f"{source} field not in the frozen text: {', '.join(unknown)}")
        if "price" in row and "price" in allowed:
            read_price_cell(row["price"])
        code = str(row["zone"])
        zones[code] = {key: row[key] for key in row if key in allowed}
        if mode == 2024 and source == "fitted_hedonic":
            zones[code]["cell"] = _cell_text(row.get("cell"))
            zones[code]["_source_row"] = row_number
    return zones



def _build_f8_check_inputs(
    tables: dict[str, dict[str, dict]],
    pins: Mapping[str, str] | None = None,
    mode: int | None = None,
) -> dict:
    for src_name, tbl in tables.items():
        if not isinstance(tbl, dict):
            continue
        for k in tbl:
            if type(k) is not str or not k.strip():
                tname = "None" if k is None else type(k).__name__
                raise CheckInputError(
                    f"V14_CHECK4: ERROR: {src_name} zone: expected str, got {tname}"
                )
    base = set(tables["builder_output"])
    check3_not_run = isinstance(tables["check3_plot_passes"], Check3NotRun)
    for code in sorted(base):
        if code not in tables["check4_f8"]:
            raise CheckInputError(
                f"V14_CHECK_INPUTS: ERROR: check4_f8 {code}: expected capitalised_land, got absent"
            )
        _validate_f8_capitalised(code, tables["check4_f8"][code])
        for label, src_key in (("primary", "primary_estimates"), ("secondary", "fitted_hedonic")):
            if code not in tables[src_key]:
                raise CheckInputError(
                    f"V14_CHECK_INPUTS: ERROR: check4 {label} {code}: expected residual_land, got absent"
                )
            est = tables[src_key][code]
            b_row = tables["builder_output"][code]
            is_zeroed = bool(
                est.get("unavailable")
                or est.get("model_failure")
                or est.get("no_cell")
                or b_row.get("unavailable")
                or b_row.get("model_failure")
            )
            if "land_per_home" not in est and not is_zeroed:
                raise CheckInputError(
                    f"V14_CHECK_INPUTS: ERROR: check4 {label} {code}: expected residual_land, got absent"
                )
            if "land_per_home" in est and not is_zeroed:
                lph = est["land_per_home"]
                if lph is None or isinstance(lph, bool) or not isinstance(lph, (int, float)) or not math.isfinite(float(lph)):
                    raise CheckInputError(
                        f"V14_CHECK_INPUTS: ERROR: check4 {label} {code}: expected residual_land, got absent"
                    )
    for name in ("builder_output", "primary_estimates", "fitted_hedonic", "check3_plot_passes", "check4_f8", "dz2022_keys", "ur6"):
        if check3_not_run and name == "check3_plot_passes":
            continue
        if set(tables[name]) != base:
            raise CheckInputError(f"{name} zones do not match the builder output")

    primary: list[dict] = []
    secondary: list[dict] = []
    missing: list[str] = []
    required_fields = REQUIRED_ZONE_FIELDS
    if check3_not_run:
        required_fields = tuple(field for field in REQUIRED_ZONE_FIELDS if field != "pass_at")

    for code in sorted(base):
        shared: dict = {"zone": code}
        for name in ("builder_output", "check3_plot_passes", "dz2022_keys", "ur6"):
            if check3_not_run and name == "check3_plot_passes":
                continue
            shared.update(tables[name][code])
        cap_land = _validate_f8_capitalised(code, tables["check4_f8"][code])
        for label, src_key in (("primary", "primary_estimates"), ("secondary", "fitted_hedonic")):
            est = dict(tables[src_key][code])
            no_cell = bool(est.pop("no_cell", False))
            zone = dict(shared)
            zone.update(est)
            if no_cell and "share" not in zone:
                zone["share"] = 0.0
            if no_cell and "land_per_home" not in zone:
                zone["land_per_home"] = 0.0
            if no_cell:
                zone["unavailable"] = True
            is_unavail = bool(zone.get("unavailable") or zone.get("model_failure") or no_cell)
            res_land = 0.0 if is_unavail else float(zone["land_per_home"])
            zone["residual_land"] = res_land
            zone["capitalised_land"] = cap_land
            unknown = sorted(key for key in zone if key not in ALLOWED_ZONE_FIELDS)
            if unknown:
                raise CheckInputError(f"field not in the frozen text: {', '.join(unknown)}")
            absent = [field for field in required_fields if field not in zone]
            if absent:
                missing.append(f"{label} {code}: {', '.join(absent)}")
                continue
            if mode == 2024:
                zone["year"] = 2024
            if label == "primary":
                primary.append(zone)
            else:
                secondary.append(zone)
    if missing:
        raise CheckInputError("missing fields: " + "; ".join(missing))
    built: dict = {"primary_zones": primary, "secondary_zones": secondary}
    if pins:
        pin_keys = (*SOURCES, "check4_f8")
        built["pins"] = {name: pins[name] for name in pin_keys if name in pins}
    return built


def build_v14_check_inputs(
    tables: dict[str, dict[str, dict]],
    pins: Mapping[str, str] | None = None,
    mode: int | None = None,
) -> dict:
    """Join pinned sources into ``primary_zones`` and ``secondary_zones``."""
    f8_sources = (set(SOURCES) - {"check4_rent_route"}) | {"check4_f8"}
    if set(tables) == f8_sources:
        return _build_f8_check_inputs(tables, pins=pins, mode=mode)
    if set(tables) != set(SOURCES):
        raise CheckInputError("tables do not match the source list")
    base = set(tables["builder_output"])
    check3_not_run = isinstance(tables["check3_plot_passes"], Check3NotRun)
    for name in SOURCES:
        if check3_not_run and name == "check3_plot_passes":
            continue
        if set(tables[name]) != base:
            raise CheckInputError(f"{name} zones do not match the builder output")
    primary: list[dict] = []
    secondary: list[dict] = []
    missing: list[str] = []
    required_fields = REQUIRED_ZONE_FIELDS
    if check3_not_run:
        required_fields = tuple(field for field in REQUIRED_ZONE_FIELDS if field != "pass_at")
    for code in sorted(base):
        shared: dict = {"zone": code}
        for name in ("builder_output", "check3_plot_passes", "check4_rent_route", "dz2022_keys", "ur6"):
            if check3_not_run and name == "check3_plot_passes":
                continue
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
            absent = [field for field in required_fields if field not in zone]
            if absent:
                missing.append(f"{label} {code}: {', '.join(absent)}")
                continue
            if mode == 2024:
                zone["year"] = 2024
            if label == "primary":
                primary.append(zone)
            else:
                secondary.append(zone)
    if missing:
        raise CheckInputError("missing fields: " + "; ".join(missing))
    built: dict = {"primary_zones": primary, "secondary_zones": secondary}
    if pins:
        built["pins"] = {name: pins[name] for name in SOURCES if name in pins}
    return built


def _parse_pins(items: list[str]) -> dict[str, str]:
    pins: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise CheckInputError(f"pin must be name=sha256, got {item}")
        name, digest = item.split("=", 1)
        pins[name] = digest
    return pins


def require_year(value: str | None) -> int:
    """Required ``--year``. Anything outside ``YEAR_MODES`` refuses before readers run."""
    allowed = "|".join(str(year) for year in YEAR_MODES)
    got = "absent" if value is None else str(value)
    if got not in {str(year) for year in YEAR_MODES}:
        raise CheckInputError(f"B6: ERROR: year: expected one of {allowed}, got {got}")
    return int(got)


def read_s2_s3(paths: dict[str, Path], mode: int | None = None) -> dict[str, dict[str, dict]]:
    """S2 and S3, plus the other pinned sources. Spy target for a refused year.

    Check 3 is read first so a refused record does not open the other sources.
    """
    ordered = ("check3_plot_passes", *(name for name in SOURCES if name != "check3_plot_passes"))
    return {name: load_source(paths[name], name, mode=mode) for name in ordered}


def join_sources(
    tables: dict[str, dict[str, dict]],
    pins: Mapping[str, str],
    mode: int | None = None,
) -> dict:
    """Join spy. A refused year never calls this."""
    return build_v14_check_inputs(tables, pins, mode=mode)


def _locked_coefficient_sha(lock_path: Path) -> str:
    if not lock_path.is_file():
        raise CheckInputError(f"B6: ERROR: file: expected {lock_path}, got absent")
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    frozen = payload.get("frozen_set") if isinstance(payload, dict) else None
    expected = None if not isinstance(frozen, dict) else frozen.get("hedonic_coefs_2021_22")
    if not isinstance(expected, str) or expected.strip() == "":
        raise CheckInputError(
            "B6: REFUSED: frozen_set hedonic_coefs_2021_22 sha256: expected full sha256, got absent"
        )
    if len(expected) != 64:
        raise CheckInputError(
            "B6: REFUSED: frozen_set hedonic_coefs_2021_22 sha256: "
            f"expected full sha256, got {expected}"
        )
    return expected


def assert_frozen_coefficients(coef_path: Path, lock_path: Path) -> dict:
    """Refuse a coefficients file that is not the lock's frozen 2021-22 sha.

    ``apply_frozen_coefficients`` is not called from here.
    """
    if not coef_path.is_file():
        raise CheckInputError(f"B6: ERROR: file: expected {coef_path}, got absent")
    expected = _locked_coefficient_sha(lock_path)
    actual = sha256_file(coef_path)
    if actual != expected:
        raise CheckInputError(
            "B6: REFUSED: frozen_set hedonic_coefs_2021_22 sha256: "
            f"expected {expected}, got {actual}"
        )
    payload = json.loads(coef_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "coefficients" not in payload or "beta_by_cell" not in payload:
        raise CheckInputError("B6: ERROR: hedonic_coefs: expected frozen fit, got absent")
    return payload


def apply_2024_coefficients(fit: Mapping, tables: dict[str, dict[str, dict]]) -> dict:
    """Apply each zone's own frozen 2021-22 cell coefficient. Does not refit."""
    beta = fit["beta_by_cell"]
    if not isinstance(beta, dict) or not beta:
        raise CheckInputError("B6: ERROR: hedonic_coefs: expected frozen fit, got absent")
    primary = tables["primary_estimates"]
    fitted = tables["fitted_hedonic"]
    rows = []
    for zone in sorted(primary):
        if zone not in fitted:
            raise CheckInputError(f"B6: REFUSED: fitted_hedonic: expected {zone}, got absent")
        record = fitted[zone]
        cell = _cell_text(record.get("cell"))
        if cell not in beta:
            raise _refuse_cell(int(record.get("_source_row") or 0), cell)
        rows.append({"zone": zone, "cell": cell, "year": 2024})
    applied = apply_frozen_coefficients(fit, rows)
    if applied.get("refit") is not False or applied.get("coefficients_unchanged") is not True:
        raise CheckInputError("B6: REFUSED: refit: expected false, got true")
    for zone in applied["zones"]:
        fitted[str(zone["zone"])]["share"] = zone["share"]
    for record in fitted.values():
        record.pop("cell", None)
        record.pop("_source_row", None)
    return applied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--year", default=None, help="Required. Allowed values are YEAR_MODES.")
    parser.add_argument("--lock", type=Path, default=None, help="Holdout lock. 2024 mode reads frozen_set.")
    parser.add_argument(
        "--hedonic-coefs",
        type=Path,
        default=None,
        help="Frozen 2021-22 coefficients. 2024 mode checks the lock sha before applying them.",
    )
    parser.add_argument("--pin", action="append", default=[], help="name=sha256, one per source.")
    for name in SOURCES:
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, default=None, dest=name)
    parser.add_argument("--check4-f8", type=Path, default=None, dest="check4_f8")
    args = parser.parse_args(argv)
    paths = {name: getattr(args, name) for name in SOURCES}
    f8_path: Path | None = getattr(args, "check4_f8", None)
    try:
        mode = require_year(args.year)
        if f8_path is not None and mode == 2023:
            active_sources = tuple("check4_f8" if s == "check4_rent_route" else s for s in SOURCES)
            f8_paths = {s: (f8_path if s == "check4_f8" else paths[s]) for s in active_sources}
            pins = _parse_pins(list(args.pin))
            for s in active_sources:
                pth = f8_paths.get(s)
                if pth is not None and not pth.is_file():
                    raise CheckInputError(f"B6: ERROR: file: expected {pth}, got absent")
            missing_f8 = [s for s in active_sources if f8_paths.get(s) is None or not pins.get(s)]
            if missing_f8:
                raise CheckInputError(f"inputs without a pinned sha: {', '.join(missing_f8)}")
            for s in active_sources:
                pth = f8_paths[s]
                assert pth is not None
                dig = sha256_file(pth)
                if dig != pins[s]:
                    raise CheckInputError(f"{s} sha256 {dig} != {pins[s]}")
            ordered_f8 = ("check3_plot_passes", *(s for s in active_sources if s != "check3_plot_passes"))
            tables = {s: load_source(f8_paths[s], s, mode=mode) for s in ordered_f8}
        else:
            if mode == 2024:
                for name in SOURCES:
                    source_path = paths[name]
                    if source_path is None or not source_path.is_file():
                        shown = "absent" if source_path is None else source_path
                        raise CheckInputError(f"B6: ERROR: file: expected {shown}, got absent")
            pins = _parse_pins(list(args.pin))
            assert_pinned(paths, pins)
            tables = read_s2_s3(paths, mode)
        if mode == 2024:
            if args.hedonic_coefs is None:
                raise CheckInputError("B6: ERROR: file: expected hedonic_coefs, got absent")
            if args.lock is None:
                raise CheckInputError("B6: ERROR: file: expected lock, got absent")
            fit = assert_frozen_coefficients(args.hedonic_coefs, args.lock)
            apply_2024_coefficients(fit, tables)
        payload = join_sources(tables, pins, mode=mode)
    except (CheckInputError, Check3RecordError, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sys.stdout.write(f"wrote {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
