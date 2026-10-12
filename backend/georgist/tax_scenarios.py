"""Tax scenario illustrations from Wealth Engine Surface Rent (not AGR).

Policy capture-rate maths only. Inputs must already be publishable Wealth figures
(``measured_rent`` from ``surface_rent_dz``). No Sandilands pool, no fiscal basket,
no invented national totals.

Surface Rent (la-calc residual) is a different lens from AGR residual plot charge.
Sums of zone Surface Rent are research aggregates — not the national rent pool and
not a tax bill.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from georgist.display_views import ZERO_DWELLINGS, parse_zone_flags
from georgist.wealth_schema import publicly_served

DISCLAIMER = "Experimental research estimate. Not an official valuation or tax bill."
LENS = "surface_rent"
LENS_NOTE = (
    "Lens: Surface Rent (Wealth Engine / la-calc residual). "
    "Not AGR residual plot charge. Not the Sandilands national rent pool."
)
CAPTURE_NOTE = (
    "Policy illustration: capture_rate scales publishable Surface Rent measured_rent. "
    "This is not a measured tax liability and not an official bill."
)
STATUS = "experimental_research_estimate"

# Display presets only — not recommended policy rates.
DEFAULT_CAPTURE_RATES: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)


class TaxScenarioError(ValueError):
    """Bad input or mixed price years that refuse a total."""

    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


@dataclass(frozen=True)
class ZoneRentRow:
    """One Data Zone Surface Rent input for scenario maths."""

    code: str
    vintage: int
    la_code: str
    la_name: str
    measured_rent: float
    price_year: int


def parse_capture_rate(raw: Any) -> float:
    """Capture rate in [0, 1]. Loud failure outside the range."""
    try:
        rate = float(raw)
    except (TypeError, ValueError) as exc:
        raise TaxScenarioError(
            "invalid_capture_rate",
            "capture_rate must be a number between 0 and 1 inclusive.",
            capture_rate=raw,
        ) from exc
    if rate != rate or rate < 0.0 or rate > 1.0:  # NaN check
        raise TaxScenarioError(
            "invalid_capture_rate",
            "capture_rate must be a number between 0 and 1 inclusive.",
            capture_rate=raw,
        )
    return rate


def illustrated_collection(measured_rent: float, capture_rate: float) -> float:
    """Policy illustration: measured Surface Rent × capture rate."""
    return float(measured_rent) * float(capture_rate)


def _flags_tokens(flags: Any) -> set[str]:
    if flags is None:
        return set()
    return set(parse_zone_flags(flags))


def zone_row_from_db(row: Mapping[str, Any]) -> ZoneRentRow | None:
    """Accept a joined surface_rent_dz + zone_spine row, or None if not usable."""
    if not publicly_served(row):
        return None
    if ZERO_DWELLINGS in _flags_tokens(row.get("flags") or row.get("zs_flags")):
        return None
    rent = row.get("measured_rent")
    price_year = row.get("price_year")
    la_code = row.get("la_code")
    la_name = row.get("la_name")
    code = row.get("code")
    vintage = row.get("vintage")
    if rent is None or price_year is None or not la_code or not la_name or not code or vintage is None:
        return None
    try:
        return ZoneRentRow(
            code=str(code),
            vintage=int(vintage),
            la_code=str(la_code),
            la_name=str(la_name),
            measured_rent=float(rent),
            price_year=int(price_year),
        )
    except (TypeError, ValueError):
        return None


def _refuse_mixed_price_years(rows: Sequence[ZoneRentRow], *, where: str) -> int:
    years = sorted({r.price_year for r in rows})
    if len(years) > 1:
        raise TaxScenarioError(
            "mixed_price_years",
            f"Surface rents priced in different years cannot be added ({where}); no total returned.",
            price_years=years,
            where=where,
        )
    return years[0]


def aggregate_by_council(
    rows: Iterable[ZoneRentRow],
    *,
    capture_rate: float,
    la_code: str | None = None,
) -> dict[str, Any]:
    """Sum publishable zone Surface Rent by council; apply capture_rate as illustration."""
    rate = parse_capture_rate(capture_rate)
    usable = list(rows)
    if la_code:
        usable = [r for r in usable if r.la_code == la_code]
    if not usable:
        return {
            "status": STATUS,
            "lens": LENS,
            "lens_note": LENS_NOTE,
            "disclaimer": DISCLAIMER,
            "capture_rate": rate,
            "capture_note": CAPTURE_NOTE,
            "price_year": None,
            "national": {
                "zone_count": 0,
                "measured_rent_total_gbp": None,
                "illustrated_collection_gbp": None,
            },
            "by_council": [],
            "preset_rates": list(DEFAULT_CAPTURE_RATES),
            "note": "No publishable Surface Rent rows for this filter. Nothing was estimated.",
        }

    price_year = _refuse_mixed_price_years(usable, where="national")
    by_la: dict[str, list[ZoneRentRow]] = {}
    for r in usable:
        by_la.setdefault(r.la_code, []).append(r)

    councils: list[dict[str, Any]] = []
    for code in sorted(by_la, key=lambda c: by_la[c][0].la_name):
        group = by_la[code]
        _refuse_mixed_price_years(group, where=f"council:{code}")
        measured = sum(r.measured_rent for r in group)
        councils.append({
            "la_code": code,
            "la_name": group[0].la_name,
            "zone_count": len(group),
            "price_year": price_year,
            "measured_rent_total_gbp": measured,
            "illustrated_collection_gbp": illustrated_collection(measured, rate),
            "status": STATUS,
            "disclaimer": DISCLAIMER,
        })

    national_measured = sum(r.measured_rent for r in usable)
    return {
        "status": STATUS,
        "lens": LENS,
        "lens_note": LENS_NOTE,
        "disclaimer": DISCLAIMER,
        "capture_rate": rate,
        "capture_note": CAPTURE_NOTE,
        "price_year": price_year,
        "national": {
            "zone_count": len(usable),
            "measured_rent_total_gbp": national_measured,
            "illustrated_collection_gbp": illustrated_collection(national_measured, rate),
            "price_year": price_year,
            "status": STATUS,
            "disclaimer": DISCLAIMER,
        },
        "by_council": councils,
        "preset_rates": list(DEFAULT_CAPTURE_RATES),
        "note": (
            "Council and national figures are sums of publishable Data Zone Surface Rent "
            "(research aggregates). They are not the Sandilands national rent pool, not AGR, "
            "and not a tax bill."
        ),
    }


def zone_illustration(
    row: ZoneRentRow,
    *,
    capture_rate: float,
    council_measured_total: float | None = None,
    council_zone_count: int | None = None,
) -> dict[str, Any]:
    """Who-pays illustration for one Data Zone at a capture rate."""
    rate = parse_capture_rate(capture_rate)
    measured = row.measured_rent
    illustrated = illustrated_collection(measured, rate)
    share = None
    if council_measured_total is not None and council_measured_total > 0:
        share = measured / council_measured_total
    return {
        "status": STATUS,
        "lens": LENS,
        "lens_note": LENS_NOTE,
        "disclaimer": DISCLAIMER,
        "capture_rate": rate,
        "capture_note": CAPTURE_NOTE,
        "zone": {
            "code": row.code,
            "vintage": row.vintage,
            "la_code": row.la_code,
            "la_name": row.la_name,
            "price_year": row.price_year,
            "measured_rent_gbp": measured,
            "illustrated_collection_gbp": illustrated,
            "share_of_council_measured_rent": share,
            "status": STATUS,
            "disclaimer": DISCLAIMER,
        },
        "council": {
            "la_code": row.la_code,
            "la_name": row.la_name,
            "zone_count": council_zone_count,
            "measured_rent_total_gbp": council_measured_total,
            "illustrated_collection_gbp": (
                None if council_measured_total is None
                else illustrated_collection(council_measured_total, rate)
            ),
            "status": STATUS,
            "disclaimer": DISCLAIMER,
        },
        "note": (
            "Illustrated collection = Surface Rent measured_rent × capture_rate. "
            "Research estimate only; not AGR and not a tax bill."
        ),
    }
