"""Frozen NatureScot CPM 2016 class, CRS, clip and conversion rules (M6b).

Econometrician pre-freeze constraints and GIS confirmations of 5 Nov 2026.
Hectare *totals* are parked as M6c; helpers here exist so M6c cannot reopen
the rules. Do not print a Scotland or zone total in the M6b UI.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ALLOWED_IMPORTANCE: frozenset[int] = frozenset({-2, -1, 0, 1, 2, 3, 4, 5})
HEADLINE_IMPORTANCE: frozenset[int] = frozenset({1, 2})
NOT_IN_HEADLINE: frozenset[int] = frozenset({3, 4})
CLASS_5 = 5
ZERO_PEAT_IMPORTANCE: frozenset[int] = frozenset({0, -2})
UNKNOWN_IMPORTANCE = -1

SOURCE_URL = "https://gis-downloads.nature.scot/CPM2016_SCOTLAND_GPKG_27700.zip"
SOURCE_BYTES = 237_469_970
SSDI = "51b36efb-3521-4243-9bb0-93f8a7a60a71"
CREATED = "2016-06-01"
PUBLISHED = "2016-06-29"
FIELD = "IMPORTANCE"
CRS = "EPSG:27700"
AREA_METHOD = "planar"
AREA_DISCLOSURE = "planar British National Grid (EPSG:27700)"
CLIP = "land"
CLIP_TOLERANCE_M = 50
ATTRIBUTION = "© SNH and JHI. Available under a Non-Commercial Government Licence."
LICENCE = "NCGL"
S71 = (
    "Shows where peat is likely, at a broad scale. "
    "Not for checking single sites (NatureScot)."
)
# Pending first download on Laurie's PC. Must be set before any M6c results.
GPKG_SHA256: str | None = None
HA_LESS_THAN_ONE = "Less than 1"

DISSOLVE_BY = "importance"
KEEP_FIELDS: tuple[str, ...] = ("importance",)
SIMPLIFY_M = 10
ZOOM_MIN = 0
ZOOM_MAX = 11
LOW_ZOOM = "coalesce"
SERVE_MAX_MB_PROVISIONAL = 40
BUDGET_TOTAL_MB_PROVISIONAL = 50
BUDGET_TILE_KB = 500
BUDGET_Z0_7_MB_PROVISIONAL = 5.0

FORBIDDEN_USER_TOKENS: tuple[str, ...] = (
    "tC",
    "tCO2",
    "tCO₂e",
    "carbon price",
    "emission factor",
    "\u00a3",
)

ROLE_HEADLINE = "headline"
ROLE_CLASS_5 = "class_5_separate"
ROLE_NOT_HEADLINE = "not_headline"
ROLE_ZERO = "zero"
ROLE_UNKNOWN = "unknown"


class Cpm2016RuleError(ValueError):
    """Raised when a CPM 2016 rule is broken."""


def normalize_importance(value: Any) -> int:
    """Return an integer IMPORTANCE code or raise."""
    if isinstance(value, bool) or value is None:
        raise Cpm2016RuleError("IMPORTANCE is missing or not an integer code")
    if isinstance(value, float):
        if not value.is_integer():
            raise Cpm2016RuleError(f"IMPORTANCE {value!r} is not an integer code")
        value = int(value)
    elif isinstance(value, str):
        raw = value.strip()
        if raw == "":
            raise Cpm2016RuleError("IMPORTANCE is missing or not an integer code")
        try:
            value = int(raw)
        except ValueError as exc:
            raise Cpm2016RuleError(
                f"IMPORTANCE {value!r} is not an integer code"
            ) from exc
    elif not isinstance(value, int):
        raise Cpm2016RuleError(f"IMPORTANCE {value!r} is not an integer code")
    if value not in ALLOWED_IMPORTANCE:
        raise Cpm2016RuleError(
            f"IMPORTANCE {value} is outside the official class set "
            f"{sorted(ALLOWED_IMPORTANCE)}"
        )
    return value


def peat_role(importance: Any) -> str:
    """How this class counts toward peat hectares (M6c) and paint grouping."""
    code = normalize_importance(importance)
    if code in HEADLINE_IMPORTANCE:
        return ROLE_HEADLINE
    if code == CLASS_5:
        return ROLE_CLASS_5
    if code in NOT_IN_HEADLINE:
        return ROLE_NOT_HEADLINE
    if code in ZERO_PEAT_IMPORTANCE:
        return ROLE_ZERO
    if code == UNKNOWN_IMPORTANCE:
        return ROLE_UNKNOWN
    raise Cpm2016RuleError(f"IMPORTANCE {code} has no peat-hectare role")


def headline_hectares(class_ha: Mapping[int, float]) -> float:
    """Sum Class 1 + 2 only. Never add 3, 4, 5, 0, −1 or −2."""
    total = 0.0
    for raw_code, area in class_ha.items():
        code = normalize_importance(raw_code)
        if peat_role(code) != ROLE_HEADLINE:
            continue
        if area < 0:
            raise Cpm2016RuleError(f"area for class {code} must not be negative")
        total += float(area)
    return total


def unknown_hectares(class_ha: Mapping[int, float]) -> float:
    """Class −1 area. Never imputed into the headline numerator."""
    if UNKNOWN_IMPORTANCE not in class_ha:
        return 0.0
    area = float(class_ha[UNKNOWN_IMPORTANCE])
    if area < 0:
        raise Cpm2016RuleError("area for class -1 must not be negative")
    return area


def class_5_hectares(class_ha: Mapping[int, float]) -> float:
    """Class 5 area, always separate from the headline."""
    if CLASS_5 not in class_ha:
        return 0.0
    area = float(class_ha[CLASS_5])
    if area < 0:
        raise Cpm2016RuleError("area for class 5 must not be negative")
    return area


def refuse_geodesic(method: str) -> None:
    """Area must be planar EPSG:27700. Geodesic (and any other method) is refused."""
    if method != AREA_METHOD:
        raise Cpm2016RuleError(
            f"area method must be {AREA_METHOD!r} in {CRS}; "
            f"refusing {method!r} (no geodesic)"
        )


def format_hectares(area_ha: float) -> str:
    """Whole-number hectares as M5/M2. Values above 0 that round below 1 show Less than 1."""
    if area_ha < 0:
        raise Cpm2016RuleError("hectares must not be negative")
    if area_ha > 0 and round(area_ha) < 1:
        return HA_LESS_THAN_ONE
    return f"{round(area_ha):,}"
