"""CHECK4-ROUTE (v1.5 item 1): F8 Median-rent bridge + Addendum 5 DRC deduction for Check 4.

Implements the signed ``AM2_addendum5_check4_land_route_r5.md`` (sha256 ``62ca5c56``)
and ``V14-CHECK4-ROUTE`` specification:
- Route 1 (``residual_land_{E,z}``): each estimator ``E in {primary, secondary}`` uses its
  own ``land_per_home`` (``0.0`` when ``unavailable``, ``model_failure``, or ``no_cell``).
- Route 2 (``capitalised_land_z``):
    ``expected_rent_z = sum_b h_{b,z} * expected_rent_for_zone(shares_z, rent_b, ur6_class=ur6_z, plus4_factor=1.15, plus4_classes=(5, 6))``
    ``capitalised_property_z = 12 * expected_rent_z / 0.045``
    ``capitalised_land_z = capitalised_property_z - drc_z``
- Building-cost cancellation identity for the residual estimator holds to ``<= 1e-12``:
    ``(P_z - drc_z) - (capitalised_property_z - drc_z) == P_z - capitalised_property_z``.
- Zero cell text is ever printed in error messages; no price column is read or written.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from georgist import surface_v13 as v13

REPO_ROOT = Path(__file__).resolve().parents[2]
SURFACE_YAML = REPO_ROOT / "data" / "config" / "surface.yaml"

PIN_TABLE: dict[str, str] = {
    "brma_rents": "14f2368b47ec4e9fdc30fc8fa2985511ce37b87307c13a20c38587fa61aae88a",
    "brma_share": "abb626a3305f91264b45f679abc348e0f8335adb671d69781ad8e1cda95b2f11",
    "bedroom_bands": "6d15b887bf7bea4b96488e5374a7ea75f9e2beaa3f2544f275072de674cfa603",
    "crosswalk": "7690bcbebf9968ca9b02cf898832aa9be8fca56f3eb9af70b20e25b5d23e13e4",
    "ur6": "1f32a81532912334e3cd071e2f12f523e66068d14c73e5db4ae51add239b1a92",
}
PIN_ORDER = ("brma_rents", "brma_share", "bedroom_bands", "crosswalk", "ur6")

EXPECTED_HEADERS: dict[str, tuple[str, ...]] = {
    "brma_rents": ("BRMA", "Year", "Measure", "Beds", "Value"),
    "brma_share": (
        "code",
        "vintage",
        "brma_id",
        "brma_name",
        "household_share",
        "hh2022_weight",
        "method",
    ),
    "bedroom_bands": (
        "dz2022_code",
        "households_total",
        "share_1",
        "share_2",
        "share_3",
        "share_4plus",
        "share_house",
        "share_flat",
        "house_share_1",
        "house_share_2",
        "house_share_3",
        "house_share_4plus",
        "flat_share_1",
        "flat_share_2",
        "flat_share_3",
        "flat_share_4plus",
        "house_households_sum",
        "flat_households_sum",
        "source",
        "licence",
    ),
    "crosswalk": (
        "dz2011_code",
        "dz2022_code",
        "uprn_count",
        "share_of_dz2011",
        "hh2022_share",
        "share_diff_flag",
        "method",
    ),
    "ur6": ("code", "ur6_class", "ur6_name", "ur8_code", "source", "licence"),
}

BRMA_NAME_MAP: dict[str, str] = {"Ayrshire": "Ayrshires"}
BRMA_NAME_DISCLOSURE = (
    "BRMA name corrected: dz_brma_share 'Ayrshire' (S33000003) matched to "
    "rent file 'Ayrshires'; no other name mapped."
)
ADDENDUM5_DEDUCTION_DISCLOSURE = (
    "AM2_addendum5_r5 (62ca5c56): capitalised_land = 12 * expected_rent / 0.045 - drc; "
    "for residual estimator (price - drc), building term cancels to 1e-12."
)

USED_RENT_BEDS = ("1 Bedroom", "2 Bedroom", "3 Bedroom", "4 Bedroom")
EXPECTED_YIELD = 0.045
SHARE_SUM_TOL = 1e-5
CANCELLATION_TOL = 1e-12
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_BOOL_WORDS = frozenset({"true", "false"})


class Check4RouteError(ValueError):
    """Raised when any CHECK4-ROUTE input, pin, cell, sum, or identity check fails."""


def copy_f8_pins() -> dict[str, str]:
    """Return a mutable copy of ``PIN_TABLE`` for synthetic test fixtures."""
    return {k: str(PIN_TABLE[k]) for k in PIN_ORDER}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def read_rent_value_cell(raw: str) -> str:
    """Spy hook for reading ``brma_rents`` ``Value`` cells (never called when ``Year != 2025``)."""
    return raw


def assert_check4_yield(surface_yaml: Path = SURFACE_YAML) -> float:
    """Rule 1: Verify ``v13.check4.capitalisation_yield == v14.check4.capitalisation_yield == 0.045`` before opening any data file."""
    if not isinstance(surface_yaml, Path) or not surface_yaml.is_file():
        raise Check4RouteError(
            "V14_CHECK4: REFUSED: yield: expected 0.045 in v13.check4 and v14.check4, got mismatch"
        )
    try:
        raw = yaml.safe_load(surface_yaml.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise Check4RouteError(
            "V14_CHECK4: REFUSED: yield: expected 0.045 in v13.check4 and v14.check4, got mismatch"
        ) from exc
    sr_cfg = (raw or {}).get("surface_rent") if isinstance(raw, dict) else None
    v13_c4 = ((sr_cfg or {}).get("v13") or {}).get("check4") if isinstance(sr_cfg, dict) else None
    v14_c4 = ((sr_cfg or {}).get("v14") or {}).get("check4") if isinstance(sr_cfg, dict) else None
    y13 = (v13_c4 or {}).get("capitalisation_yield") if isinstance(v13_c4, dict) else None
    y14 = (v14_c4 or {}).get("capitalisation_yield") if isinstance(v14_c4, dict) else None
    if (
        isinstance(y13, bool)
        or isinstance(y14, bool)
        or not isinstance(y13, (int, float))
        or not isinstance(y14, (int, float))
        or float(y13) != EXPECTED_YIELD
        or float(y14) != EXPECTED_YIELD
    ):
        raise Check4RouteError(
            "V14_CHECK4: REFUSED: yield: expected 0.045 in v13.check4 and v14.check4, got mismatch"
        )
    return EXPECTED_YIELD


def _check_file_and_sha(name: str, path: Path, pins: Mapping[str, str]) -> str:
    """Rule 2: Check file existence first, then sha256 before parsing."""
    if not isinstance(path, Path) or not path.is_file():
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: {name} file: expected {path}, got absent"
        )
    pin = str(pins.get(name) or "").strip()
    actual = sha256_file(path)
    if not _FULL_SHA_RE.fullmatch(pin) or actual != pin:
        raise Check4RouteError(
            f"V14_CHECK4: REFUSED: {name} sha256: expected {pin or 'absent'}, got {actual}"
        )
    return path.read_text(encoding="utf-8-sig")


def _read_csv_rows(name: str, text: str) -> tuple[tuple[str, ...], list[tuple[int, dict[str, str]]]]:
    """Rule 3: Validate exact CSV header and row width without printing cell text."""
    expected = EXPECTED_HEADERS[name]
    joined = ",".join(expected)
    lines = [ln for ln in text.splitlines() if ln.strip() != ""]
    if not lines:
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: {name} header: expected {joined}, got absent"
        )
    parsed = list(csv.reader(io.StringIO("\n".join(lines) + "\n")))
    if not parsed:
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: {name} header: expected {joined}, got absent"
        )
    header = tuple(col.strip() for col in parsed[0])
    if header != expected:
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: {name} header: expected {joined}, got other header"
        )
    if len(parsed) < 2:
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: {name} header: expected {joined}, got absent"
        )
    width = len(expected)
    out: list[tuple[int, dict[str, str]]] = []
    for row_num, cells in enumerate(parsed[1:], start=1):
        if len(cells) != width:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: {name} row {row_num}: expected {width} fields, got {len(cells)}"
            )
        out.append((row_num, {expected[i]: cells[i] for i in range(width)}))
    return expected, out


def _parse_number_cell(
    raw: str,
    *,
    err_prefix: str,
    allow_zero: bool,
) -> float:
    s = raw.strip()
    if s == "" or s.lower() in _BOOL_WORDS:
        raise Check4RouteError(f"{err_prefix}, got non-numeric")
    try:
        val = float(s)
    except ValueError as exc:
        raise Check4RouteError(f"{err_prefix}, got non-numeric") from exc
    if not math.isfinite(val):
        raise Check4RouteError(f"{err_prefix}, got non-finite")
    if allow_zero:
        if val < 0.0:
            raise Check4RouteError(f"{err_prefix}, got out of range")
        if val == 0.0:
            return 0.0
    else:
        if val <= 0.0 or math.copysign(1.0, val) < 0.0:
            raise Check4RouteError(f"{err_prefix}, got out of range")
    return val


def load_brma_rents_2025(
    path: Path,
    pins: Mapping[str, str],
) -> dict[str, dict[str, float]]:
    """Load 2025 BRMA Median monthly rents for 1..4 Bedroom (excluding 'Scotland' and '1 Bedroom shared')."""
    text = _check_file_and_sha("brma_rents", path, pins)
    _, rows = _read_csv_rows("brma_rents", text)
    rents: dict[str, dict[str, float]] = {}
    all_brmas: set[str] = set()
    for row_num, row in rows:
        raw_year = row["Year"]
        # Reject leading/trailing whitespace or decimals on Year
        if raw_year != raw_year.strip() or raw_year.strip() == "":
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: brma_rents Year row {row_num}: expected integer, got non-integer"
            )
        yr_str = raw_year.strip()
        digits = yr_str[1:] if yr_str.startswith("-") else yr_str
        if not digits.isdigit():
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: brma_rents Year row {row_num}: expected integer, got non-integer"
            )
        year = int(yr_str)
        # Rule 4: Skip rows with Year != 2025 BEFORE reading Measure or Value.
        if year != 2025:
            continue
        brma = row["BRMA"].strip()
        if brma == "Scotland" or brma == "":
            continue
        all_brmas.add(brma)
        measure = row["Measure"].strip()
        if measure != "Median":
            continue
        beds = row["Beds"].strip()
        if beds == "1 Bedroom shared" or beds not in USED_RENT_BEDS:
            continue
        raw_val = read_rent_value_cell(row["Value"])
        val = _parse_number_cell(
            raw_val,
            err_prefix=f"V14_CHECK4: ERROR: brma_rents {brma} {beds}: expected positive number",
            allow_zero=False,
        )
        brma_map = rents.setdefault(brma, {})
        if beds in brma_map:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: brma_rents {brma} {beds}: expected one 2025 Median, got duplicate"
            )
        brma_map[beds] = val

    if not all_brmas:
        raise Check4RouteError(
            "V14_CHECK4: ERROR: brma_rents: expected 2025 BRMA rows, got absent"
        )
    for brma in sorted(all_brmas):
        bmap = rents.get(brma, {})
        for beds in USED_RENT_BEDS:
            if beds not in bmap:
                raise Check4RouteError(
                    f"V14_CHECK4: ERROR: brma_rents {brma} {beds}: expected one 2025 Median, got absent"
                )
    return rents


def load_brma_share_2011(
    path: Path,
    pins: Mapping[str, str],
) -> dict[str, list[tuple[str, str, float]]]:
    """Load DZ2011 -> [(brma_id, brma_name, household_share)] from ``dz_brma_share.csv``."""
    text = _check_file_and_sha("brma_share", path, pins)
    _, rows = _read_csv_rows("brma_share", text)
    by_zone: dict[str, list[tuple[str, str, float]]] = {}
    for row_num, row in rows:
        vintage = row["vintage"].strip()
        if vintage != "2011":
            continue
        zone = row["code"].strip()
        brma_id = row["brma_id"].strip()
        brma_name = row["brma_name"]
        share = _parse_number_cell(
            row["household_share"],
            err_prefix=f"V14_CHECK4: ERROR: brma_share household_share row {row_num}: expected number",
            allow_zero=True,
        )
        by_zone.setdefault(zone, []).append((brma_id, brma_name, share))
    if not by_zone:
        raise Check4RouteError(
            "V14_CHECK4: ERROR: brma_share: expected zones, got absent"
        )
    for zone in sorted(by_zone):
        total = sum(item[2] for item in by_zone[zone])
        if abs(total - 1.0) > SHARE_SUM_TOL:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: brma_share {zone}: expected shares summing to 1, got out of range"
            )
    return by_zone


def load_bedroom_bands_dz2022(
    path: Path,
    pins: Mapping[str, str],
) -> dict[str, tuple[float, float, float, float, float]]:
    """Load DZ2022 -> (households_total, share_1, share_2, share_3, share_4plus)."""
    text = _check_file_and_sha("bedroom_bands", path, pins)
    _, rows = _read_csv_rows("bedroom_bands", text)
    out: dict[str, tuple[float, float, float, float, float]] = {}
    for row_num, row in rows:
        code = row["dz2022_code"].strip()
        if not code:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: bedroom_bands dz2022_code row {row_num}: expected code, got absent"
            )
        if code in out:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: bedroom_bands {code}: expected one row, got duplicate"
            )
        hh = _parse_number_cell(
            row["households_total"],
            err_prefix=f"V14_CHECK4: ERROR: bedroom_bands households_total row {row_num}: expected number",
            allow_zero=True,
        )
        s1 = _parse_number_cell(
            row["share_1"],
            err_prefix=f"V14_CHECK4: ERROR: bedroom_bands share_1 row {row_num}: expected number",
            allow_zero=True,
        )
        s2 = _parse_number_cell(
            row["share_2"],
            err_prefix=f"V14_CHECK4: ERROR: bedroom_bands share_2 row {row_num}: expected number",
            allow_zero=True,
        )
        s3 = _parse_number_cell(
            row["share_3"],
            err_prefix=f"V14_CHECK4: ERROR: bedroom_bands share_3 row {row_num}: expected number",
            allow_zero=True,
        )
        s4 = _parse_number_cell(
            row["share_4plus"],
            err_prefix=f"V14_CHECK4: ERROR: bedroom_bands share_4plus row {row_num}: expected number",
            allow_zero=True,
        )
        if hh > 0.0 and abs((s1 + s2 + s3 + s4) - 1.0) > SHARE_SUM_TOL:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: bedroom_bands {code}: expected shares summing to 1, got out of range"
            )
        out[code] = (hh, s1, s2, s3, s4)
    return out


def load_crosswalk_2011_to_2022(
    path: Path,
    pins: Mapping[str, str],
) -> dict[str, list[tuple[str, float]]]:
    """Load DZ2011 -> [(dz2022_code, share_of_dz2011)] from UPRN crosswalk."""
    text = _check_file_and_sha("crosswalk", path, pins)
    _, rows = _read_csv_rows("crosswalk", text)
    by_dz11: dict[str, list[tuple[str, float]]] = {}
    for row_num, row in rows:
        d11 = row["dz2011_code"].strip()
        d22 = row["dz2022_code"].strip()
        w = _parse_number_cell(
            row["share_of_dz2011"],
            err_prefix=f"V14_CHECK4: ERROR: crosswalk share_of_dz2011 row {row_num}: expected number",
            allow_zero=True,
        )
        by_dz11.setdefault(d11, []).append((d22, w))
    if not by_dz11:
        raise Check4RouteError(
            "V14_CHECK4: ERROR: crosswalk: expected zones, got absent"
        )
    for d11 in sorted(by_dz11):
        total = sum(w for _, w in by_dz11[d11])
        if abs(total - 1.0) > SHARE_SUM_TOL:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: crosswalk {d11}: expected shares summing to 1, got out of range"
            )
    return by_dz11


def load_ur6_2011(
    path: Path,
    pins: Mapping[str, str],
) -> dict[str, int]:
    """Load DZ2011 -> ur6_class (1..6)."""
    text = _check_file_and_sha("ur6", path, pins)
    _, rows = _read_csv_rows("ur6", text)
    out: dict[str, int] = {}
    for row_num, row in rows:
        code = row["code"].strip()
        if code in out:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: ur6 {code}: expected one row, got duplicate"
            )
        raw_c = row["ur6_class"].strip()
        if not raw_c.isdigit() or not (1 <= int(raw_c) <= 6):
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: ur6 ur6_class row {row_num}: expected number, got out of range"
            )
        out[code] = int(raw_c)
    return out


def bridge_bedroom_shares_for_zone(
    zone: str,
    edges: list[tuple[str, float]],
    dz22_beds: Mapping[str, tuple[float, float, float, float, float]],
) -> dict[str, float]:
    """M-R2 household-weighted UPRN crosswalk bridge for DZ2022 -> DZ2011 bedroom shares."""
    denom = 0.0
    num1 = 0.0
    num2 = 0.0
    num3 = 0.0
    num4 = 0.0
    for d22, w in edges:
        if d22 not in dz22_beds:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: bedroom_bands: expected DZ2022 {d22}, got absent"
            )
        hh, s1, s2, s3, s4 = dz22_beds[d22]
        wh = w * hh
        denom += wh
        num1 += wh * s1
        num2 += wh * s2
        num3 += wh * s3
        num4 += wh * s4
    if denom <= 0.0:
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: bedroom_bands {zone}: expected positive households, got out of range"
        )
    b1 = num1 / denom
    b2 = num2 / denom
    b3 = num3 / denom
    b4 = num4 / denom
    if abs((b1 + b2 + b3 + b4) - 1.0) > SHARE_SUM_TOL:
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: bedroom_bands {zone}: expected shares summing to 1, got out of range"
        )
    return {"1": b1, "2": b2, "3": b3, "4+": b4}


def _validate_drc_for_zone(zone: str, drc_map: Mapping[str, Any]) -> float:
    if zone not in drc_map:
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: drc: expected DZ2011 {zone}, got absent"
        )
    raw = drc_map[zone]
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: drc {zone}: expected finite non-negative number, got {type(raw).__name__}"
        )
    val = float(raw)
    if not math.isfinite(val):
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: drc {zone}: expected finite non-negative number, got non-finite"
        )
    if val < 0.0:
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: drc {zone}: expected finite non-negative number, got out of range"
        )
    return val


def check_cancellation_identity(
    price: float,
    expected_rent: float,
    drc: float,
    *,
    yield_rate: float = EXPECTED_YIELD,
) -> dict[str, float]:
    """AM-2 Addendum 5 §4: verify building-cost term ``drc`` cancels to ``<= 1e-12`` for the residual route."""
    for name, val in (
        ("price", price),
        ("expected_rent", expected_rent),
        ("drc", drc),
        ("yield_rate", yield_rate),
    ):
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(float(val)):
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: cancellation {name}: expected finite number, got non-numeric"
            )
    if float(expected_rent) <= 0.0 or float(drc) < 0.0 or float(yield_rate) <= 0.0:
        raise Check4RouteError(
            "V14_CHECK4: ERROR: cancellation: expected positive rent/yield and non-negative drc, got out of range"
        )
    p = float(price)
    d = float(drc)
    cap_prop = v13.capitalised_rent_land(float(expected_rent), yield_rate=float(yield_rate))
    residual_land = p - d
    capitalised_land = cap_prop - d
    lhs = residual_land - capitalised_land
    rhs = p - cap_prop
    scale = max(1.0, abs(p), abs(cap_prop), abs(d))
    rel_err = abs(lhs - rhs) / scale
    if rel_err > CANCELLATION_TOL:
        raise Check4RouteError(
            "V14_CHECK4: REFUSED: cancellation identity: expected rel_err <= 1e-12, got out of range"
        )
    return {
        "residual_land": residual_land,
        "capitalised_property": cap_prop,
        "capitalised_land": capitalised_land,
        "lhs": lhs,
        "rhs": rhs,
        "rel_err": rel_err,
    }


def capitalised_by_zone(
    zones: Sequence[Any],
    *,
    brma_rents_path: Path,
    brma_share_path: Path,
    bedroom_bands_path: Path,
    crosswalk_path: Path,
    ur6_path: Path,
    drc_map: Mapping[str, Any] | None = None,
    pins: Mapping[str, str] | None = None,
    surface_yaml: Path = SURFACE_YAML,
) -> dict[str, Any]:
    """Compute F8 capitalised property and Addendum-5 land values per DZ2011 zone."""
    yield_rate = assert_check4_yield(surface_yaml)
    if not isinstance(zones, (list, tuple)) or len(zones) == 0:
        raise Check4RouteError("V14_CHECK4: ERROR: zones: expected zones, got absent")
    clean_zones: list[str] = []
    seen_z: set[str] = set()
    for z in zones:
        if not isinstance(z, str) or isinstance(z, bool):
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: zones zone: expected str, got {type(z).__name__}"
            )
        zc = z.strip()
        if not zc:
            raise Check4RouteError("V14_CHECK4: ERROR: zones: expected zones, got absent")
        if zc in seen_z:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: zones {zc}: expected one row, got duplicate"
            )
        seen_z.add(zc)
        clean_zones.append(zc)

    pin_map = PIN_TABLE if pins is None else pins
    rents = load_brma_rents_2025(brma_rents_path, pin_map)
    brma_shares = load_brma_share_2011(brma_share_path, pin_map)
    dz22_beds = load_bedroom_bands_dz2022(bedroom_bands_path, pin_map)
    crosswalk = load_crosswalk_2011_to_2022(crosswalk_path, pin_map)
    ur6_map = load_ur6_2011(ur6_path, pin_map)

    out_zones: dict[str, dict[str, Any]] = {}
    for zone in clean_zones:
        if zone not in brma_shares:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: brma_share: expected DZ2011 {zone}, got absent"
            )
        if zone not in crosswalk:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: crosswalk: expected DZ2011 {zone}, got absent"
            )
        if zone not in ur6_map:
            raise Check4RouteError(
                f"V14_CHECK4: ERROR: ur6: expected DZ2011 {zone}, got absent"
            )
        shares = bridge_bedroom_shares_for_zone(zone, crosswalk[zone], dz22_beds)
        ur6_class = ur6_map[zone]
        exp_rent = 0.0
        exp_rent_unadj = 0.0
        for brma_id, brma_name, h_b in brma_shares[zone]:
            # Exact match only (no case folding or whitespace trimming before map lookup)
            mapped_name = BRMA_NAME_MAP.get(brma_name, brma_name)
            if mapped_name not in rents:
                raise Check4RouteError(
                    f"V14_CHECK4: ERROR: brma {brma_id}: expected rent BRMA, got absent"
                )
            exp_rent += h_b * v13.expected_rent_for_zone(
                shares,
                rents[mapped_name],
                ur6_class=ur6_class,
                plus4_factor=1.15,
                plus4_classes=(5, 6),
            )
            exp_rent_unadj += h_b * v13.expected_rent_for_zone(
                shares,
                rents[mapped_name],
                ur6_class=ur6_class,
                plus4_factor=1.0,
                plus4_classes=(5, 6),
            )

        cap_prop = v13.capitalised_rent_land(exp_rent, yield_rate=yield_rate)
        cap_prop_unadj = v13.capitalised_rent_land(exp_rent_unadj, yield_rate=yield_rate)
        drc_val = _validate_drc_for_zone(zone, drc_map) if drc_map is not None else 0.0
        cap_land = cap_prop - drc_val
        cap_land_unadj = cap_prop_unadj - drc_val
        plus4_applied = bool(ur6_class in (5, 6) and shares["4+"] > 0.0)

        out_zones[zone] = {
            "expected_monthly_rent": exp_rent,
            "capitalised_property": cap_prop,
            "capitalised_property_unadjusted": cap_prop_unadj,
            "drc": drc_val,
            "capitalised_land": cap_land,
            "capitalised_land_unadjusted": cap_land_unadj,
            "plus4_applied": plus4_applied,
            "bedroom_shares": shares,
            "ur6": ur6_class,
        }

    return {
        "zones": out_zones,
        "disclosure": {
            "brma_name_map": BRMA_NAME_DISCLOSURE,
            "addendum5_deduction": ADDENDUM5_DEDUCTION_DISCLOSURE,
        },
    }
