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
ADDENDUM5_DOC = "AM2_addendum5_check4_land_route_r5.md"
ADDENDUM5_SHA256 = "62ca5c561246b4990c575f8a1ce4e8c0c4f220b5cbbfbf64f8fbdf9c75b19c56"
ADDENDUM5_SIGNATURES_DOC = "AM2_addendum5_r5_signatures.md"
ADDENDUM5_SIGNATURES_SHA256 = "6e331f2c224b0f319e01dc0130a191ccd3aa7c96ee17ac9da0950badd61058da"
AM3_DOC = "AM3_check4_land_route_2024.md"
AM3_SHA256 = "8bbcdfbe02d202bdc62e647d5e8ba2ba24058ff57925a114df4893334a3e13d9"
AM3_SIGNATURES_DOC = "AM3_check4_land_route_2024_signatures_r2.md"
AM3_SIGNATURES_SHA256 = "7b916b37f13164bf1e9f52a5502a5f879d4c4bb41033f0c549016db06c04f8ec"
AM3_2024_INPUTS = ("rents", "drc", "prices")
AM3_ZONE_FLAGS = ("unavailable", "model_failure", "no_cell")
FORBIDDEN_REPORT_SUBSTRINGS = ("\u00a3", "_gbp", "GBP", "Pounds")
FORBIDDEN_MONEY_KEYS = frozenset(
    {
        "residual_median",
        "class_residual_medians",
        "residual_land",
        "capitalised_land",
        "capitalised_property",
        "drc_per_home",
        "land_per_home",
        "expected_monthly_rent",
        "price",
    }
)


def _median_sorted(values: Sequence[float]) -> float:
    ordered = sorted(float(v) for v in values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])


def assert_non_gbp_report(payload: Mapping[str, Any]) -> None:
    """Refuse any Check 4 score report carrying money keys or currency tokens."""
    def _walk(obj: Any) -> None:
        if isinstance(obj, Mapping):
            for k, v in obj.items():
                ks = str(k)
                if ks in FORBIDDEN_MONEY_KEYS or ks.lower().endswith("_gbp"):
                    raise Check4RouteError(
                        f"V14_CHECK4: REFUSED: report key {ks}: expected non-GBP summary key, got money key"
                    )
                for tok in FORBIDDEN_REPORT_SUBSTRINGS:
                    if tok in ks:
                        raise Check4RouteError(
                            "V14_CHECK4: REFUSED: report key: expected non-GBP summary key, got currency token"
                        )
                _walk(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item)
        elif isinstance(obj, str):
            for tok in FORBIDDEN_REPORT_SUBSTRINGS:
                if tok in obj:
                    raise Check4RouteError(
                        "V14_CHECK4: REFUSED: report text: expected non-GBP text, got currency token"
                    )

    _walk(payload)


def score_check4_non_gbp(
    zones: Sequence[Mapping[str, Any]],
    *,
    national_max_abs: float = 0.25,
    class_max_abs: float = 0.40,
    am3_reporting: bool = False,
) -> dict[str, Any]:
    """Score Check 4 for one estimator and strip all money-level medians.

    ``am3_reporting`` (AM-3 M7) adds reporting-only keys after the gate is computed;
    with it off the output is byte-identical to the v1.5 (#280) shape.
    """
    from georgist import surface_v14 as v14

    if not isinstance(zones, (list, tuple)) or len(zones) == 0:
        raise Check4RouteError("V14_CHECK4: ERROR: score zones: expected zones, got absent")

    residual_list: list[float] = []
    cap_list: list[float] = []
    class_res: dict[int, list[float]] = {}
    class_cap: dict[int, list[float]] = {}
    n_unavail = 0
    n_pos_res = 0
    n_pos_cap = 0

    for z in zones:
        if not isinstance(z, Mapping) or "ur6" not in z or "residual_land" not in z or "capitalised_land" not in z:
            raise Check4RouteError("V14_CHECK4: ERROR: score zone: expected ur6/residual_land/capitalised_land, got absent")
        unavail = bool(z.get("unavailable") or z.get("model_failure"))
        if unavail:
            n_unavail += 1
        r_val = 0.0 if unavail else float(z["residual_land"])
        c_val = float(z["capitalised_land"])
        if not math.isfinite(r_val) or not math.isfinite(c_val):
            raise Check4RouteError("V14_CHECK4: ERROR: score zone: expected finite number, got non-finite")
        if r_val > 0.0:
            n_pos_res += 1
        if c_val > 0.0:
            n_pos_cap += 1
        ur6_k = int(z["ur6"])
        residual_list.append(r_val)
        cap_list.append(c_val)
        class_res.setdefault(ur6_k, []).append(r_val)
        class_cap.setdefault(ur6_k, []).append(c_val)

    raw = v14.check_4_from_routes(
        residual_list,
        cap_list,
        class_residual=class_res,
        class_capitalised=class_cap,
        national_max_abs=national_max_abs,
        class_max_abs=class_max_abs,
    )
    all_gaps = [v13.two_route_relative_gap(r, c) for r, c in zip(residual_list, cap_list)]
    all_finite = all(math.isfinite(g) for g in all_gaps)
    nat_gap = round(_median_sorted(all_gaps), 6) if all_finite and all_gaps else None
    res_med_pos = bool(raw.get("residual_median") is not None and float(raw["residual_median"]) > 0.0)
    class_res_pos = {
        str(k): bool(float(v) > 0.0)
        for k, v in sorted((raw.get("class_residual_medians") or {}).items())
    }

    by_ur6: dict[str, dict[str, Any]] = {}
    for k in sorted(class_res):
        rs = class_res[k]
        cs = class_cap[k]
        gs = [v13.two_route_relative_gap(r, c) for r, c in zip(rs, cs)]
        k_finite = all(math.isfinite(g) for g in gs)
        rmed_pos = bool(_median_sorted(rs) > 0.0) if rs else False
        gmed = round(_median_sorted(gs), 6) if k_finite and gs else None
        within = bool(rmed_pos and gmed is not None and abs(gmed) <= float(class_max_abs))
        by_ur6[str(k)] = {
            "n": len(rs),
            "residual_median_positive": rmed_pos,
            "median_relative_gap": gmed,
            "within_class_band": within,
        }

    out = {
        "check": "4",
        "status": str(raw["status"]),
        "pass": bool(raw["pass"]),
        "reason": raw.get("reason"),
        "national_max_abs": float(national_max_abs),
        "class_max_abs": float(class_max_abs),
        "n_zones": len(zones),
        "n_unavailable": n_unavail,
        "n_positive_residual": n_pos_res,
        "n_positive_capitalised": n_pos_cap,
        "residual_median_positive": res_med_pos,
        "class_residual_median_positive": class_res_pos,
        "national_median_gap": nat_gap,
        "national_within_band": bool(
            res_med_pos
            and all(class_res_pos.values())
            and nat_gap is not None
            and abs(nat_gap) <= float(national_max_abs)
        ),
        "by_ur6": by_ur6,
    }
    if am3_reporting:
        out.update(_am3_reporting_fields(zones, class_res_pos))
    assert_non_gbp_report(out)
    return out


def _am3_flag(z: Mapping[str, Any], name: str) -> bool:
    if name not in z:
        return False
    val = z[name]
    if not isinstance(val, bool):
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: score zone flag {name}: expected bool, got {type(val).__name__}"
        )
    return val


def _am3_unavailable_kind(z: Mapping[str, Any]) -> str | None:
    """Classify one zone under AM-3 M7. Precedence: model_failure > no_cell > negative_residual.

    Only zones that the gate zero-fills (``unavailable or model_failure``) are classified,
    so the three counts always sum to ``n_unavailable``.
    """
    unavailable, model_failure, no_cell = (_am3_flag(z, f) for f in AM3_ZONE_FLAGS)
    if not (unavailable or model_failure):
        return None
    if model_failure:
        return "model_failure"
    if no_cell:
        return "no_cell"
    return "negative_residual"


def _am3_reporting_fields(
    zones: Sequence[Mapping[str, Any]],
    class_res_pos: Mapping[str, bool],
) -> dict[str, Any]:
    kinds = ("negative_residual", "model_failure", "no_cell")
    split = {k: 0 for k in kinds}
    by_class: dict[str, dict[str, int]] = {}
    no_cell_not_zero_filled = 0
    for z in zones:
        kind = _am3_unavailable_kind(z)
        cls = by_class.setdefault(str(int(z["ur6"])), {k: 0 for k in kinds})
        if kind is None:
            if _am3_flag(z, "no_cell"):
                no_cell_not_zero_filled += 1
            continue
        split[kind] += 1
        cls[kind] += 1
    return {
        "failing_classes": sorted(int(k) for k, ok in class_res_pos.items() if not ok),
        "unavailable_split": {**split, "zero_filled": sum(split.values())},
        "unavailable_split_by_ur6": {k: by_class[k] for k in sorted(by_class, key=int)},
        "no_cell_not_zero_filled": no_cell_not_zero_filled,
    }


_AM3_SUMMARY_KEYS = ("status", "pass", "reason", "n_zones", "national_median_gap", "national_within_band")


def _am3_summary(zones: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not zones:
        return {"gating": False, "status": "not_computable", "detail": "no zones after exclusion"}
    scored = score_check4_non_gbp(list(zones))
    out: dict[str, Any] = {"gating": False}
    out.update({k: scored[k] for k in _AM3_SUMMARY_KEYS})
    out["by_ur6_median_relative_gap"] = {k: v["median_relative_gap"] for k, v in scored["by_ur6"].items()}
    return out


def check4_sensitivities(zones: Sequence[Mapping[str, Any]], *, estimator: str) -> dict[str, Any]:
    """AM-3 M6 sensitivities S1-S4. Reported beside the gate; never gating; no money levels.

    Works on shallow copies so no input zone is mutated (the gate result cannot move).
    """
    if estimator not in ("primary", "secondary"):
        raise Check4RouteError(
            f"V14_CHECK4: ERROR: sensitivity estimator: expected primary or secondary, got {estimator!r}"
        )
    zs = [dict(z) for z in zones]
    s1 = _am3_summary([z for z in zs if _am3_unavailable_kind(z) is None])
    if all("capitalised_land_no_plus4" in z for z in zs):
        s2 = _am3_summary([{**z, "capitalised_land": z["capitalised_land_no_plus4"]} for z in zs])
    else:
        s2 = {"gating": False, "status": "not_computable", "detail": "input absent: capitalised_land_no_plus4"}
    if estimator == "secondary":
        s3 = _am3_summary([z for z in zs if not _am3_flag(z, "no_cell")])
    else:
        s3 = {"gating": False, "status": "not_applicable", "detail": "secondary only"}
    if all("drc_gt_price" in z and "drc_gt_capitalised_property" in z for z in zs):
        s4_by: dict[str, dict[str, int]] = {}
        for z in zs:
            row = s4_by.setdefault(str(int(z["ur6"])), {"drc_gt_price": 0, "drc_gt_capitalised_property": 0})
            for key in ("drc_gt_price", "drc_gt_capitalised_property"):
                if _am3_flag(z, key):
                    row[key] += 1
        s4: dict[str, Any] = {"gating": False, "status": "reported", "by_ur6": {k: s4_by[k] for k in sorted(s4_by, key=int)}}
    else:
        s4 = {"gating": False, "status": "not_computable", "detail": "input absent: drc_gt_price/drc_gt_capitalised_property"}
    out = {
        "gating": False,
        "S1_exclude_zero_filled": s1,
        "S2_no_plus4_uplift": s2,
        "S3_secondary_no_cell_excluded": s3,
        "S4_drc_exceeds_counts": s4,
    }
    assert_non_gbp_report(out)
    return out


def check_2024_inputs(
    inputs: Mapping[str, Path] | None,
    pins: Mapping[str, str] | None,
) -> dict[str, str] | None:
    """AM-3 M5: return a NOT_RUN reason for the first missing/unpinned/altered 2024 input, else None.

    Checks are in the fixed order rents, drc, prices; file presence before pin before hash.
    """
    inputs = inputs or {}
    pins = pins or {}
    for name in AM3_2024_INPUTS:
        path = inputs.get(name)
        if not isinstance(path, Path) or not path.is_file():
            return {"input": name, "detail": "file absent"}
        pin = pins.get(name)
        if not isinstance(pin, str) or not _FULL_SHA_RE.fullmatch(pin):
            return {"input": name, "detail": "pin absent"}
        if sha256_file(path) != pin:
            return {"input": name, "detail": "pin mismatch"}
    return None


def _not_run_report(*, missing: Mapping[str, str], pins: Mapping[str, str]) -> dict[str, Any]:
    from georgist import surface_v14 as v14

    reason = f"source unavailable: {missing['input']}"
    est = {"check": "4", "status": "NOT_RUN", "pass": False, "reason": reason, "detail": missing["detail"]}
    report = {
        "kind": "v15_check4_score_report_v1",
        "publish_level": "internal",
        "methods_alignment": "v1.5",
        "pr": "v15_check4_score",
        "gbp_display": False,
        "year": 2024,
        "status": "NOT_RUN",
        "reason": reason,
        "method_authority": _am3_authority(),
        "pins": {str(k): str(v) for k, v in sorted(pins.items())},
        "primary": dict(est),
        "secondary": dict(est),
        "publication": v14.apply_no_switch_publication(primary_gating_pass=False, secondary_gating_pass=False),
    }
    assert_non_gbp_report(report)
    return report


def _am3_authority() -> dict[str, str]:
    return {
        "addendum": ADDENDUM5_DOC,
        "addendum_sha256": ADDENDUM5_SHA256,
        "signatures": ADDENDUM5_SIGNATURES_DOC,
        "signatures_sha256": ADDENDUM5_SIGNATURES_SHA256,
        "am3": AM3_DOC,
        "am3_sha256": AM3_SHA256,
        "am3_signatures": AM3_SIGNATURES_DOC,
        "am3_signatures_sha256": AM3_SIGNATURES_SHA256,
    }


def build_v15_check4_score_report(
    *,
    primary_zones: Sequence[Mapping[str, Any]],
    secondary_zones: Sequence[Mapping[str, Any]],
    pins: Mapping[str, str],
    year: int = 2023,
    lookup_zones: int = 6976,
    not_scored_zones: int = 730,
    secondary_scored_zones: int = 5826,
    secondary_no_cell_zones: int = 420,
    brma_count: int = 18,
    bands_per_brma: int = 4,
    plus4_applied_zones: int = 1101,
    cancellation_zones_checked: int = 6246,
    cancellation_max_rel_err: float = 0.0,
    inputs_2024: Mapping[str, Path] | None = None,
    pins_2024: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble the committed non-GBP v1.5 Check 4 score report artifact.

    Year 2024 (AM-3): input pins are verified before any zone is scored; a missing or
    altered pin returns a NOT_RUN report that can never pass. AM-3 reporting fields and
    S1-S4 sensitivities are written for 2024 only; 2023 output is unchanged.
    """
    from georgist import surface_v14 as v14

    if type(year) is not int or year not in (2023, 2024):
        raise Check4RouteError(f"V14_CHECK4: REFUSED: year: expected 2023 or 2024, got {year!r}")
    if year == 2024:
        missing = check_2024_inputs(inputs_2024, pins_2024)
        if missing is not None:
            return _not_run_report(missing=missing, pins=pins)
    am3 = year == 2024
    if (
        isinstance(cancellation_max_rel_err, bool)
        or not isinstance(cancellation_max_rel_err, (int, float))
        or not math.isfinite(float(cancellation_max_rel_err))
        or float(cancellation_max_rel_err) < 0.0
        or float(cancellation_max_rel_err) > CANCELLATION_TOL
    ):
        raise Check4RouteError(
            "V14_CHECK4: REFUSED: cancellation identity: expected rel_err <= 1e-12, got out of range"
        )
    if len(primary_zones) != len(secondary_zones):
        raise Check4RouteError("V14_CHECK4: ERROR: score zones: expected matching primary and secondary counts, got mismatch")
    if int(lookup_zones) - int(not_scored_zones) != len(primary_zones):
        raise Check4RouteError("V14_CHECK4: ERROR: coverage: expected lookup minus not_scored == priced_zones, got mismatch")
    if int(secondary_scored_zones) + int(secondary_no_cell_zones) != len(secondary_zones):
        raise Check4RouteError("V14_CHECK4: ERROR: coverage: expected secondary_scored + no_cell == priced_zones, got mismatch")

    prim_score = score_check4_non_gbp(primary_zones, am3_reporting=am3)
    sec_score = score_check4_non_gbp(secondary_zones, am3_reporting=am3)
    publication = v14.apply_no_switch_publication(
        primary_gating_pass=bool(prim_score["pass"]),
        secondary_gating_pass=bool(sec_score["pass"]),
    )

    pos_cap = prim_score["n_positive_capitalised"]
    non_pos_cap = len(primary_zones) - pos_cap

    report = {
        "kind": "v15_check4_score_report_v1",
        "publish_level": "internal",
        "methods_alignment": "v1.5",
        "pr": "v15_check4_score",
        "gbp_display": False,
        "year": year,
        "status": "scored",
        "previous_v14_status": "NOT_RUN",
        "method_authority": _am3_authority() if am3 else {
            "addendum": ADDENDUM5_DOC,
            "addendum_sha256": ADDENDUM5_SHA256,
            "signatures": ADDENDUM5_SIGNATURES_DOC,
            "signatures_sha256": ADDENDUM5_SIGNATURES_SHA256,
        },
        "pins": {str(k): str(v) for k, v in sorted(pins.items())},
        "thresholds": {
            "national_max_abs_gap": 0.25,
            "class_max_abs_gap": 0.40,
            "capitalisation_yield": 0.045,
            "plus4_factor_ur6_5_6": 1.15,
            "plus4_classes": [5, 6],
        },
        "coverage": {
            "lookup_zones": int(lookup_zones),
            "not_scored_zones": int(not_scored_zones),
            "priced_zones": len(primary_zones),
            "secondary_scored_zones": int(secondary_scored_zones),
            "secondary_no_cell_zones": int(secondary_no_cell_zones),
            "brma_count": int(brma_count),
            "bands_per_brma": int(bands_per_brma),
            "plus4_applied_zones": int(plus4_applied_zones),
            "positive_capitalised_land_zones": int(pos_cap),
            "non_positive_capitalised_land_zones": int(non_pos_cap),
        },
        "cancellation_identity": {
            "formula": "(P_z - drc_z) - (capitalised_property_z - drc_z) == P_z - capitalised_property_z",
            "tolerance": CANCELLATION_TOL,
            "zones_checked": int(cancellation_zones_checked),
            "all_within_tolerance": True,
            "pass": True,
        },
        "primary": prim_score,
        "secondary": sec_score,
        "publication": publication,
        "disclosures": {
            "brma_name_map": BRMA_NAME_DISCLOSURE,
            "addendum5_deduction": ADDENDUM5_DEDUCTION_DISCLOSURE,
        },
    }
    if am3:
        report["pins_2024"] = {k: str((pins_2024 or {})[k]) for k in AM3_2024_INPUTS}
        report["sensitivities"] = {
            "gating": False,
            "primary": check4_sensitivities(primary_zones, estimator="primary"),
            "secondary": check4_sensitivities(secondary_zones, estimator="secondary"),
        }
    assert_non_gbp_report(report)
    return report
