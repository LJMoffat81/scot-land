"""Data-zone house prices for the urban residual.

The request path reads the slim 2023 lookup built from the open Registers of
Scotland residential sales-and-price table (UK Open Government Licence).
A click does not call data.gov.scot and does not download that table.

A cell with fewer than five sales is suppressed in the source. A blank median
is missing. It is never treated as zero. A thin count is shrunk toward the
parent median. The council median remains the fallback and the comparison.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "dz2011_prices.csv"

# package_show resource residential-properties-sales-and-price.csv (checked 2026-10-05).
PACKAGE_ID = "house_prices___residential_properties_sales_and_price"
RESOURCE_ID = "3d9a31a5-4b62-436a-a537-7d9bbeba1723"
PINNED_SOURCE_SHA256 = "702c9ada0b26dad9904e97f00ea7aa3357e1bf449e724e83292b5265f0549cf2"

_MISSING = {"*", "x", "c", "-", "na", "n/a", "suppressed", "null"}
_default_cache: dict[str, dict[str, dict[str, str]]] = {}


@dataclass(frozen=True)
class ZoneEvidence:
    """Published market value of one improved dwelling, plus how it was chosen."""

    market_value_gbp: float
    mv_council_gbp: float
    basis: str
    notes: list[str] = field(default_factory=list)
    zone_median_gbp: float | None = None
    parent_median_gbp: float | None = None
    sales_count: int | None = None


def _blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def _price(value: object) -> float | None:
    """A sale price. Blank, suppressed, and non-positive cells are missing."""
    if _blank(value):
        return None
    text = str(value).strip().lower()
    if text in _MISSING:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number <= 0:
        return None
    return number


def _count(value: object) -> int | None:
    """A sales count. Blank and suppressed cells are missing, not zero."""
    if _blank(value):
        return None
    text = str(value).strip().lower()
    if text in _MISSING:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number <= 0:
        return None
    return int(number)


def _kind(code: str) -> str | None:
    if code.startswith("S01"):
        return "data_zone"
    if code.startswith("S02"):
        return "intermediate_zone"
    if code.startswith("S12"):
        return "council_area"
    return None


def parse_sales_table(rows: list[dict[str, str]]) -> dict:
    """Latest-year Median and Count from the long open table.

    Mean and quartiles are ignored. A blank Median stays missing. The count
    comes from Measurement=Count, not from treating a blank as zero.
    """
    years = [
        int(str(row.get("DateCode") or "").strip())
        for row in rows
        if str(row.get("DateCode") or "").strip().isdigit()
    ]
    empty: dict = {
        "year": None,
        "data_zone": {},
        "intermediate_zone": {},
        "council_area": {},
    }
    if not years:
        return empty
    year = max(years)
    grouped: dict[str, dict[str, dict]] = {
        "data_zone": {},
        "intermediate_zone": {},
        "council_area": {},
    }
    for row in rows:
        if str(row.get("DateCode") or "").strip() != str(year):
            continue
        code = str(row.get("GeographyCode") or "").strip()
        kind = _kind(code)
        if kind is None:
            continue
        bucket = grouped[kind].setdefault(code, {"n": None, "median": None})
        measurement = str(row.get("Measurement") or "").strip().lower()
        if measurement == "median":
            bucket["median"] = _price(row.get("Value"))
        elif measurement == "count":
            count = _count(row.get("Value"))
            if count is None:
                count = _count(row.get("Sales"))
            bucket["n"] = count
    return {"year": year, **grouped}


def load_zone_table(path: Path | None = None) -> dict[str, dict[str, str]] | None:
    """Slim 2023 lookup keyed by 2011 data zone. None when the file cannot be read."""
    source = DEFAULT_PATH if path is None else path
    cache_key = None
    if path is None:
        cache_key = str(DEFAULT_PATH)
        cached = _default_cache.get(cache_key)
        if cached is not None:
            return cached
    try:
        if not source.is_file():
            return None
        found: dict[str, dict[str, str]] = {}
        with source.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                code = str(row.get("dz2011") or "").strip()
                if code:
                    found[code] = row
    except OSError:
        return None
    if cache_key is not None:
        _default_cache[cache_key] = found
    return found


def clear_zone_table_cache() -> None:
    _default_cache.clear()


def _parent(row: dict[str, str], council_median: float) -> tuple[float, str]:
    intermediate = _price(row.get("iz_med2023"))
    if intermediate is not None:
        return intermediate, "intermediate-zone median"
    council_area = _price(row.get("ca_med2023"))
    if council_area is not None:
        return council_area, "council-area median"
    return council_median, "council median"


def _evidence(
    market: float,
    council_median: float,
    basis: str,
    notes: list[str],
    *,
    zone_median: float | None = None,
    parent: float | None = None,
    sales: int | None = None,
) -> ZoneEvidence:
    return ZoneEvidence(
        market_value_gbp=round(float(market), 2),
        mv_council_gbp=round(float(council_median), 2),
        basis=basis,
        notes=notes,
        zone_median_gbp=None if zone_median is None else round(float(zone_median), 2),
        parent_median_gbp=None if parent is None else round(float(parent), 2),
        sales_count=sales,
    )


def _from_row(row: dict[str, str], council_median: float, shrinkage_k: float) -> ZoneEvidence:
    """Shrink a published thin median. A suppressed median falls through to the parent."""
    median = _price(row.get("dz_med2023"))
    sales = _count(row.get("dz_n2023"))
    parent, parent_label = _parent(row, council_median)
    k = float(shrinkage_k)
    if k < 0:
        k = 0.0

    if median is None:
        return _evidence(
            parent,
            council_median,
            "suppressed_parent",
            [
                "suppressed, parent median used",
                f"Parent is the {parent_label} (£{parent:,.0f}).",
            ],
            parent=parent,
            sales=sales,
        )

    if sales is None:
        return _evidence(
            parent,
            council_median,
            "missing_count_parent",
            [
                "Sales count missing, parent median used.",
                f"Parent is the {parent_label} (£{parent:,.0f}).",
            ],
            zone_median=median,
            parent=parent,
        )

    if k == 0:
        market = median
    else:
        market = (sales * median + k * parent) / (sales + k)
    return _evidence(
        market,
        council_median,
        "shrunk",
        [
            (
                f"Data zone median £{median:,.0f} on {sales} sales, shrunk toward "
                f"the {parent_label} £{parent:,.0f} with k={k:g}."
            )
        ],
        zone_median=median,
        parent=parent,
        sales=sales,
    )


def resolve_zone_market_value(
    zone_code: str | None,
    *,
    council_median_gbp: float,
    shrinkage_k: float = 8,
    path: Path | None = None,
) -> ZoneEvidence:
    """Published urban MV. Never invents a data-zone price."""
    council_median = float(council_median_gbp)
    table = load_zone_table(path)
    if table is None:
        return _evidence(
            council_median,
            council_median,
            "file_missing",
            [
                "Local price file missing or unreadable. Council median used. "
                "No data-zone price was fabricated.",
            ],
        )
    code = (zone_code or "").strip()
    row = table.get(code) if code else None
    if row is None:
        return _evidence(
            council_median,
            council_median,
            "council_median",
            ["No data zone price for this point. Council median used."],
        )
    return _from_row(row, council_median, shrinkage_k)


def package_resource_hash(package: dict) -> str | None:
    """sha256 published on the open CSV resource. The live field name is hash."""
    result = package.get("result") if isinstance(package.get("result"), dict) else package
    if not isinstance(result, dict):
        return None
    for resource in result.get("resources") or []:
        if not isinstance(resource, dict):
            continue
        if resource.get("id") != RESOURCE_ID and resource.get("name") != "residential-properties-sales-and-price.csv":
            continue
        value = resource.get("hash") or resource.get("sha256")
        if value:
            return str(value).strip().lower()
    return None


def refresh_price_table(fetch_package, download, dest: Path | None = None) -> str:
    """Check the open-table hash. A click does not call this.

    current: the pinned hash still matches, so the 70 MB file is not downloaded.
    kept: the check or the download failed. The local file is left as it is.
    A changed hash is not written over the slim lookup from this helper. The
    caller keeps the committed file rather than inventing a price.
    """
    try:
        package = fetch_package()
    except Exception:
        return "kept"
    digest = package_resource_hash(package if isinstance(package, dict) else {})
    if digest == PINNED_SOURCE_SHA256:
        return "current"
    if not digest:
        return "kept"
    try:
        blob = download()
    except Exception:
        return "kept"
    if not isinstance(blob, (bytes, bytearray)):
        return "kept"
    if hashlib.sha256(blob).hexdigest() != digest:
        return "kept"
    # Bytes match a new package hash. Leave the slim lookup in place until a
    # reviewed rebuild replaces it. Do not fabricate rows.
    _ = dest
    return "kept"
