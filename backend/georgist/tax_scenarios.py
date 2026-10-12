"""Tax scenario illustrations from Wealth Engine Surface Rent (not AGR).

HOLD — INTERNAL ONLY. Configured land yield is read from shared
``data/config/surface.yaml`` (Valuation owns calibration; Georgist v3 metadata
passed through when present) — never hardcoded here. Every payload is
``publication_status=blocked`` and must not appear on public pages or public
API routes. No public £.

Money figures (£) are served at **Data Zone grain only**. Council / national
blocks carry counts and labels, never summed £.

**Policy config is separate from measured land values.** Capture rate, exemptions,
phase-in and revenue sharing are provisional policy knobs — not finalised here.
Georgist owns that spec; this module must not invent a policy schema.

Inputs may use publishable Wealth figures (``measured_rent`` from
``surface_rent_dz``); the scenario *output* stays blocked. No Sandilands pool,
no fiscal basket, no invented national totals.

Surface Rent (la-calc residual) is a different lens from AGR residual plot charge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from georgist.display_views import ZERO_DWELLINGS, parse_zone_flags
from georgist.surface_settings import yield_placeholder
from georgist.wealth_schema import publicly_served

DISCLAIMER = "Experimental research estimate. Not an official valuation or tax bill."
LENS = "surface_rent"
LENS_NOTE = (
    "Lens: Surface Rent (Wealth Engine / la-calc residual). "
    "Not AGR residual plot charge. Not the Sandilands national rent pool."
)
CAPTURE_NOTE = (
    "Policy illustration only: capture_rate scales publishable Surface Rent measured_rent. "
    "Rates / exemptions / phase-in / revenue sharing are policy config (not finalised; "
    "Georgist owns the spec) and are never folded into measured land values."
)
STATUS = "experimental_research_estimate"
PUBLICATION_STATUS = "blocked"
BLOCKED_REASON = (
    "yield_calibration_pending: land yield from shared surface.yaml is a placeholder "
    "assumption until calibration against RoS market evidence; tax scenario output is "
    "internal-only (defer to Valuation yield config — do not hardcode a rate here)"
)
INTERNAL_WARNING = (
    "INTERNAL ONLY. Tax scenario output is publication_status=blocked until yield "
    "calibration lands. Do not publish on public pages."
)
# Room rule: policy knobs stay out of measured land values; Georgist will write the spec.
POLICY_CONFIG = {
    "status": "not_finalised",
    "owner": "Georgist",
    "separate_from_measured_land_values": True,
    "topics": ["rates", "exemptions", "phase_in", "revenue_sharing"],
    "note": (
        "Rates, exemptions, phase-in and revenue sharing are policy config, kept "
        "separate from measured land values. Spec not finalised — Georgist will write "
        "it first. capture_rate here is a provisional illustration knob only."
    ),
}
MONEY_GRAIN = "data_zone"
MONEY_GRAIN_NOTE = (
    "Money figures (£) are Data Zone grain only. Council and national blocks list "
    "membership counts, never summed £."
)

# Provisional display presets only — not a finalised policy rate schedule.
DEFAULT_CAPTURE_RATES: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)

# Keys that must never appear on council/national blocks (Valuation: £ at DZ only).
_FORBIDDEN_AGGREGATE_GBP = frozenset({
    "measured_rent_total_gbp",
    "illustrated_collection_gbp",
    "measured_rent_gbp",
})


def _blocked_fields() -> dict[str, Any]:
    # Live read from shared surface.yaml — picks up Valuation's provisional yield when that PR lands.
    yp = yield_placeholder()
    return {
        "internal": True,
        "publication_status": PUBLICATION_STATUS,
        "blocked_reason": BLOCKED_REASON,
        "warning": INTERNAL_WARNING,
        "yield_placeholder": yp,
        "policy_config": dict(POLICY_CONFIG),
        "money_grain": MONEY_GRAIN,
        "money_grain_note": MONEY_GRAIN_NOTE,
    }


def stamp_blocked(payload: dict[str, Any]) -> dict[str, Any]:
    """Stamp scenario output as internal-only / publication_status=blocked (room rule)."""
    fields = _blocked_fields()
    payload.update(fields)
    yp = fields["yield_placeholder"]
    for key in ("national", "zone", "council"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            nested.update({
                "publication_status": PUBLICATION_STATUS,
                "blocked_reason": BLOCKED_REASON,
            })
    for row in payload.get("by_council") or []:
        if isinstance(row, dict):
            row.update({
                "publication_status": PUBLICATION_STATUS,
                "blocked_reason": BLOCKED_REASON,
            })
    for row in payload.get("by_zone") or []:
        if isinstance(row, dict):
            row.update({
                "publication_status": PUBLICATION_STATUS,
                "blocked_reason": BLOCKED_REASON,
                "yield_placeholder": dict(yp),
            })
    return payload


def assert_no_aggregate_gbp(payload: Mapping[str, Any]) -> None:
    """Refuse council/national £ fields (Valuation: money at Data Zone only)."""
    for block_name in ("national", "council"):
        block = payload.get(block_name)
        if not isinstance(block, dict):
            continue
        bad = sorted(_FORBIDDEN_AGGREGATE_GBP & set(block))
        if bad:
            raise TaxScenarioError(
                "aggregate_gbp_forbidden",
                f"{block_name} must not carry £ fields {bad}; money is Data Zone grain only.",
                fields=bad,
            )
    for row in payload.get("by_council") or []:
        if not isinstance(row, dict):
            continue
        bad = sorted(_FORBIDDEN_AGGREGATE_GBP & set(row))
        if bad:
            raise TaxScenarioError(
                "aggregate_gbp_forbidden",
                f"by_council must not carry £ fields {bad}; money is Data Zone grain only.",
                fields=bad,
            )


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
    """Policy illustration: measured Surface Rent × capture rate (Data Zone only)."""
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


def _zone_money_row(row: ZoneRentRow, *, capture_rate: float) -> dict[str, Any]:
    """£ fields for one Data Zone only."""
    return {
        "code": row.code,
        "vintage": row.vintage,
        "la_code": row.la_code,
        "la_name": row.la_name,
        "price_year": row.price_year,
        "measured_rent_gbp": row.measured_rent,
        "illustrated_collection_gbp": illustrated_collection(row.measured_rent, capture_rate),
        "money_grain": MONEY_GRAIN,
        "status": STATUS,
        "disclaimer": DISCLAIMER,
        "yield_placeholder": yield_placeholder(),
    }


def aggregate_by_council(
    rows: Iterable[ZoneRentRow],
    *,
    capture_rate: float,
    la_code: str | None = None,
) -> dict[str, Any]:
    """Council membership + per-zone £ (no council/national £ sums)."""
    rate = parse_capture_rate(capture_rate)
    usable = list(rows)
    if la_code:
        usable = [r for r in usable if r.la_code == la_code]
    if not usable:
        payload = stamp_blocked({
            "status": STATUS,
            "lens": LENS,
            "lens_note": LENS_NOTE,
            "disclaimer": DISCLAIMER,
            "capture_rate": rate,
            "capture_note": CAPTURE_NOTE,
            "price_year": None,
            "national": {"zone_count": 0},
            "by_council": [],
            "by_zone": [],
            "preset_rates": list(DEFAULT_CAPTURE_RATES),
            "note": "No publishable Surface Rent rows for this filter. Nothing was estimated.",
        })
        assert_no_aggregate_gbp(payload)
        return payload

    price_year = _refuse_mixed_price_years(usable, where="national")
    by_la: dict[str, list[ZoneRentRow]] = {}
    for r in usable:
        by_la.setdefault(r.la_code, []).append(r)

    councils: list[dict[str, Any]] = []
    for code in sorted(by_la, key=lambda c: by_la[c][0].la_name):
        group = by_la[code]
        _refuse_mixed_price_years(group, where=f"council:{code}")
        councils.append({
            "la_code": code,
            "la_name": group[0].la_name,
            "zone_count": len(group),
            "price_year": price_year,
            "zone_codes": sorted(z.code for z in group),
            "status": STATUS,
            "disclaimer": DISCLAIMER,
        })

    by_zone = [_zone_money_row(r, capture_rate=rate) for r in sorted(usable, key=lambda z: z.code)]
    payload = stamp_blocked({
        "status": STATUS,
        "lens": LENS,
        "lens_note": LENS_NOTE,
        "disclaimer": DISCLAIMER,
        "capture_rate": rate,
        "capture_note": CAPTURE_NOTE,
        "price_year": price_year,
        "national": {
            "zone_count": len(usable),
            "price_year": price_year,
            "status": STATUS,
            "disclaimer": DISCLAIMER,
        },
        "by_council": councils,
        "by_zone": by_zone,
        "preset_rates": list(DEFAULT_CAPTURE_RATES),
        "note": (
            "Internal tax scenario: £ at Data Zone grain only (by_zone). "
            "Council/national blocks are membership counts, not £ totals. "
            "capture_rate is provisional policy illustration — rates/exemptions/phase-in/"
            "revenue sharing are not finalised (Georgist owns that spec) and stay separate "
            "from measured land values. Not the Sandilands pool, not AGR, not a tax bill. "
            "publication_status=blocked; land yield deferred to shared surface.yaml "
            "(Valuation placeholder until calibrated)."
        ),
    })
    assert_no_aggregate_gbp(payload)
    return payload


def zone_illustration(
    row: ZoneRentRow,
    *,
    capture_rate: float,
    council_zone_count: int | None = None,
) -> dict[str, Any]:
    """Who-pays illustration for one Data Zone at a capture rate (£ on the zone only)."""
    rate = parse_capture_rate(capture_rate)
    zone = _zone_money_row(row, capture_rate=rate)
    payload = stamp_blocked({
        "status": STATUS,
        "lens": LENS,
        "lens_note": LENS_NOTE,
        "disclaimer": DISCLAIMER,
        "capture_rate": rate,
        "capture_note": CAPTURE_NOTE,
        "zone": zone,
        "council": {
            "la_code": row.la_code,
            "la_name": row.la_name,
            "zone_count": council_zone_count,
            "status": STATUS,
            "disclaimer": DISCLAIMER,
        },
        "note": (
            "Illustrated collection = Surface Rent measured_rent × capture_rate at Data Zone grain. "
            "Research estimate only; not AGR and not a tax bill. "
            "publication_status=blocked; land yield deferred to shared surface.yaml "
            "(Valuation owns r−g). Policy rates/exemptions/phase-in/revenue sharing "
            "are not finalised here."
        ),
    })
    assert_no_aggregate_gbp(payload)
    return payload
