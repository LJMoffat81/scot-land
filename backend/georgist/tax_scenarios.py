"""Tax scenario illustrations from Wealth Engine Surface Rent (not AGR).

HOLD — INTERNAL ONLY. Configured land yield is read from shared
``data/config/surface.yaml`` (Valuation owns calibration; Georgist v3 metadata
passed through when present) — never hardcoded here. Every payload is
``publication_status=blocked`` and must not appear on public pages or public
API routes. No public £.

**Approved defaults (v0.1, Oct 2026)** (``data/config/tax_scenario_defaults.yaml``):
Laurie-approved, still configurable. Scenarios S1 (per-council revenue swap),
S2 (50%), S3 (85%). No ownership exemptions. Low-income home owners may defer
at r 2.62%. Phase-in 10 points/year. Revenue shared 50/50 councils/dividend.
Shadow never taxed.

**TEMP while blocked:** £ shown at Data Zone grain only; council views are
counts. Council + Scotland £ roll-ups are *built* behind that setting for
reconciliation (Σ councils = Scotland, each zone once) but not shown on
council/national response blocks. Roll-up unit of account is DZ2022 via the
#71 address-UPRN crosswalk; each zone's council is the spine ``la_code``.

Surface Rent (la-calc residual) is a different lens from AGR residual plot charge.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from georgist.display_views import ZERO_DWELLINGS, parse_zone_flags
from georgist.surface_dz2022 import combine_estimate_labels, estimate_label_for_fill
from georgist.surface_settings import yield_placeholder
from georgist.wealth_schema import publicly_served

_SHARE_SUM_TOLERANCE = 1e-9
_PHASE_IN_FULL_POINTS = 100

DISCLAIMER = "Experimental research estimate. Not an official valuation or tax bill."
LENS = "surface_rent"
LENS_NOTE = (
    "Lens: Surface Rent (Wealth Engine / la-calc residual). "
    "Not AGR residual plot charge. Not the Sandilands national rent pool."
)
CAPTURE_NOTE = (
    "Policy illustration only: capture_rate / scenario rates scale Surface Rent "
    "measured_rent. Approved defaults (v0.1, Oct 2026) — still configurable. "
    "Rates / exemptions / phase-in / revenue sharing stay separate from measured land values."
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
    "calibration lands. Do not publish on public pages. No public £ rent figures."
)
DRAFT_DEFAULTS_PATH = Path(__file__).resolve().parents[2] / "data" / "config" / "tax_scenario_defaults.yaml"
VALUE_TIERS = frozenset({"market", "proxy", "shadow"})
# Default + council/Scotland £ roll-up pin: DZ2022 via #71 UPRN-weighted crosswalk.
DEFAULT_DZ_VINTAGE = 2022
# DZ2022 unit of account via #71 UPRN-weighted crosswalk (address_uprn stamp).
UPRN_DZ2022_CROSSWALK = "address_uprn"
ALLOWED_TAX_CROSSWALK = frozenset({"none", "address_uprn", "value_weighted"})
# SQL path never loads an eligibility column — stamp until a later PR supplies the rule.
DEFERRAL_NOT_LOADED = "not_applied_eligibility_not_loaded"
DEFERRAL_NOT_LOADED_NOTE = (
    "Deferral eligibility is not loaded from surface_rent_dz "
    "(_TAX_SCENARIO_SQL has no eligibility column). "
    "Real low-income home-owner eligibility rule is a later separate PR."
)
# S1 rate keys follow the rent/yield band, not ascending capture rates.
S1_RATE_BAND_NOTE = (
    "s1_rate keys follow the Surface Rent yield band (low/central/high rent), "
    "not low-to-high capture rates. Each band rate is target / taxable_rent_band, "
    "so s1_rate.low is solved on the low rent band and is typically the highest "
    "rate; s1_rate.high is solved on the high rent band and is typically the lowest."
)

# Keys that must never appear on council/national *display* blocks while TEMP setting is on.
# Underscore-prefixed names are internal reconcile fields on solve_s1_per_council — never copy
# them onto API response bodies (s1_by_council / by_council / council / national).
_FORBIDDEN_AGGREGATE_GBP = frozenset({
    "measured_rent_total_gbp",
    "illustrated_collection_gbp",
    "measured_rent_gbp",
    "taxable_rent_gbp",
    "taxable_rent_central_gbp",
    "s1_revenue_gbp",
    "s1_revenue_central_gbp",
    "target_gbp",
    "s1_target_gbp",
    "council_tax_gbp",
    "business_rates_gbp",
    "council_share_gbp",
    "dividend_share_gbp",
    "_target_gbp",
    "_taxable_rent_gbp",
    "_s1_revenue_central_gbp",
})
# Top-level keys that must never appear on the API response (built internally only).
_FORBIDDEN_RESPONSE_TOP_LEVEL = frozenset({
    "blocked_aggregate_rollup",
})


class TaxScenarioError(ValueError):
    """Bad input or mixed price years that refuse a total."""

    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


def load_draft_defaults(path: Path | str = DRAFT_DEFAULTS_PATH) -> dict[str, Any]:
    """Load approved defaults (v0.1, Oct 2026); still configurable via YAML."""
    with Path(path).open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, Mapping):
        raise TaxScenarioError("invalid_policy_defaults", "tax_scenario_defaults.yaml must be a mapping")
    return dict(data)


# Alias — settings remain a configurable YAML file.
load_policy_defaults = load_draft_defaults


def policy_config_payload(defaults: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Approved defaults (v0.1, Oct 2026) stamped on every payload — still configurable."""
    cfg = defaults if defaults is not None else load_draft_defaults()
    scenarios = cfg.get("scenarios") or {}
    return {
        "status": str(cfg.get("status") or "approved_defaults"),
        "label": str(cfg.get("label") or "approved defaults (v0.1, Oct 2026)"),
        "approval": str(cfg.get("approval") or "approved_laurie_v0_1_oct_2026"),
        "version": str(cfg.get("version") or "0.1"),
        "approved": str(cfg.get("approved") or "2026-10"),
        "configurable": bool(cfg.get("configurable", True)),
        "owner": str(cfg.get("owner") or "Georgist"),
        "separate_from_measured_land_values": True,
        "publication_status": PUBLICATION_STATUS,
        "topics": ["rates", "exemptions", "phase_in", "revenue_sharing", "deferral", "scenarios"],
        "exemptions": dict(cfg.get("exemptions") or {"ownership_based": False, "shadow_taxed": False}),
        "deferral": dict(cfg.get("deferral") or {"low_income_home_owners": True, "rate": 0.0262}),
        "phase_in": dict(cfg.get("phase_in") or {"points_per_year": 10}),
        "revenue_sharing": dict(cfg.get("revenue_sharing") or {"council_share": 0.5, "dividend_share": 0.5}),
        "display_while_blocked": dict(cfg.get("display_while_blocked") or {}),
        "scenarios": {
            sid: {
                "id": (body or {}).get("id", sid),
                "label": _s1_label(sid, body or {}, cfg),
                "mode": (body or {}).get("mode"),
                **(
                    {"capture_rate": (body or {}).get("capture_rate")}
                    if (body or {}).get("capture_rate") is not None
                    else {}
                ),
                **(
                    {"scope": (body or {}).get("scope")}
                    if (body or {}).get("scope") is not None
                    else {}
                ),
                **(
                    {"national_single_rate": (body or {}).get("national_single_rate")}
                    if sid == "S1" and isinstance((body or {}).get("national_single_rate"), Mapping)
                    else {}
                ),
                **(
                    {"targets_status": _fiscal_targets_status(cfg)}
                    if sid == "S1"
                    else {}
                ),
            }
            for sid, body in scenarios.items()
        },
        "fiscal_targets_status": _fiscal_targets_status(cfg),
        "note": (
            "Approved defaults (v0.1, Oct 2026). Still configurable. No ownership-based "
            "exemptions. Shadow values are never taxed. S1 rate is solved per council "
            "against that council's council tax + business rates; national single-rate "
            "S1 is off by default."
            + (
                " S1 uses placeholder targets until SG Local Government Finance CT+NDR are loaded."
                if _fiscal_targets_status(cfg) == "placeholder_targets"
                else " S1 targets from SG Local Government Finance (OGL)."
            )
        ),
    }


def _fiscal_targets_status(defaults: Mapping[str, Any]) -> str:
    fiscal = defaults.get("fiscal_targets") or {}
    raw = str(fiscal.get("targets_status") or fiscal.get("status") or "placeholder_targets")
    if raw in {"placeholder", "placeholders", "research_placeholders", "approved_defaults"}:
        return "placeholder_targets"
    if raw in {"loaded", "sg_local_government_finance", "sg_lgf"}:
        return "sg_local_government_finance"
    return raw


def _s1_label(sid: str, body: Mapping[str, Any], defaults: Mapping[str, Any]) -> str:
    base = str(body.get("label") or sid)
    if sid != "S1":
        return base
    if _fiscal_targets_status(defaults) == "placeholder_targets":
        if "placeholder targets" not in base.lower():
            return f"{base} (placeholder targets)"
    return base


def _default_policy_config() -> dict[str, Any]:
    try:
        return policy_config_payload()
    except Exception:  # pragma: no cover — missing file in odd test sandboxes
        return {
            "status": "approved_defaults",
            "label": "approved defaults (v0.1, Oct 2026)",
            "approval": "approved_laurie_v0_1_oct_2026",
            "version": "0.1",
            "approved": "2026-10",
            "configurable": True,
            "owner": "Georgist",
            "separate_from_measured_land_values": True,
            "topics": ["rates", "exemptions", "phase_in", "revenue_sharing", "deferral", "scenarios"],
            "note": "Approved defaults (v0.1, Oct 2026). Still configurable.",
        }


POLICY_CONFIG = _default_policy_config()

MONEY_GRAIN = "data_zone"
MONEY_GRAIN_NOTE = (
    "TEMP while blocked: money figures (£) are Data Zone grain only. Council and "
    "national blocks list membership counts, never summed £. Council/Scotland "
    "roll-ups are built behind the setting for reconciliation only."
)

# Provisional display presets only — not a finalised policy rate schedule.
DEFAULT_CAPTURE_RATES: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
SCENARIO_IDS = ("S1", "S2", "S3")


def money_triple(central: float, *, yield_central: float, band_low: float, band_high: float) -> dict[str, float]:
    """Map a central £ rent onto the configured yield band as {low, central, high}."""
    if yield_central <= 0:
        raise TaxScenarioError("invalid_yield", "yield central must be positive to form a £ triple")
    c = float(central)
    return {
        "low": round(c * (float(band_low) / float(yield_central)), 2),
        "central": round(c, 2),
        "high": round(c * (float(band_high) / float(yield_central)), 2),
    }


def scale_triple(triple: Mapping[str, float], rate: float) -> dict[str, float]:
    r = float(rate)
    return {k: round(float(triple[k]) * r, 2) for k in ("low", "central", "high")}


def phase_in_fraction(year: int, points_per_year: int = 10) -> float:
    """Applied fraction at policy year ``year`` (1-indexed). 10 pts/year → yr1=0.10 … yr10=1.0."""
    try:
        y = int(year)
        pts = int(points_per_year)
    except (TypeError, ValueError) as exc:
        raise TaxScenarioError(
            "invalid_phase_in",
            "phase_in year and points_per_year must be positive integers.",
            year=year,
            points_per_year=points_per_year,
        ) from exc
    if y < 1 or pts < 1:
        raise TaxScenarioError(
            "invalid_phase_in",
            "phase_in year and points_per_year must be >= 1.",
            year=year,
            points_per_year=points_per_year,
        )
    return min(1.0, (y * pts) / float(_PHASE_IN_FULL_POINTS))


def phase_in_schedule(
    full_collection: Mapping[str, float],
    *,
    points_per_year: int = 10,
    years: int | None = None,
) -> list[dict[str, Any]]:
    """Year-by-year LCH schedule at Data Zone grain (10 percentage points per year)."""
    pts = int(points_per_year)
    n_years = int(years) if years is not None else max(1, (_PHASE_IN_FULL_POINTS + pts - 1) // pts)
    schedule: list[dict[str, Any]] = []
    for year in range(1, n_years + 1):
        frac = phase_in_fraction(year, pts)
        schedule.append({
            "year": year,
            "points": min(_PHASE_IN_FULL_POINTS, year * pts),
            "applied_fraction": frac,
            "illustrated_collection_gbp": scale_triple(full_collection, frac),
        })
    return schedule


def resolve_revenue_sharing(
    defaults: Mapping[str, Any],
    override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Council/dividend shares from defaults or per-request override; must sum to 1."""
    if override is not None:
        try:
            council = float(override["council_share"])
            dividend = float(override["dividend_share"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TaxScenarioError(
                "invalid_revenue_share",
                "revenue_sharing override requires council_share and dividend_share numbers that sum to 1.",
                override=dict(override),
            ) from exc
        source = "request"
    else:
        sharing = defaults.get("revenue_sharing") or {}
        council = float(sharing.get("council_share", 0.5))
        dividend = float(sharing.get("dividend_share", 0.5))
        source = "defaults"
    if council < 0.0 or dividend < 0.0 or council > 1.0 or dividend > 1.0:
        raise TaxScenarioError(
            "invalid_revenue_share",
            "council_share and dividend_share must each be in [0, 1] and sum to 1.",
            council_share=council,
            dividend_share=dividend,
        )
    if abs((council + dividend) - 1.0) > _SHARE_SUM_TOLERANCE:
        raise TaxScenarioError(
            "invalid_revenue_share",
            "council_share and dividend_share must sum to 1.",
            council_share=council,
            dividend_share=dividend,
            sum=council + dividend,
        )
    return {
        "council_share": council,
        "dividend_share": dividend,
        "source": source,
        "status": "approved_defaults",
        "version": "0.1",
    }


def apply_deferral(
    collection: Mapping[str, float],
    *,
    eligible: bool,
    rate: float,
    enabled: bool = True,
    eligibility_loaded: bool = False,
) -> dict[str, Any]:
    """Model low-income home-owner deferral: deferred amount + annual accrual at ``rate``.

    When ``eligibility_loaded`` is False (SQL path today), do not apply deferral —
    stamp ``status=not_applied_eligibility_not_loaded``. Real eligibility is a later PR.
    """
    r = float(rate)
    if r < 0.0:
        raise TaxScenarioError("invalid_deferral_rate", "deferral rate must be >= 0.", rate=rate)
    if not eligibility_loaded:
        cash = {k: round(float(collection[k]), 2) for k in ("low", "central", "high")}
        return {
            "status": DEFERRAL_NOT_LOADED,
            "deferral_eligible": False,
            "deferral_applied": False,
            "deferral_rate": r,
            "deferred_gbp": {"low": 0.0, "central": 0.0, "high": 0.0},
            "accrual_gbp_per_year": {"low": 0.0, "central": 0.0, "high": 0.0},
            "cash_collected_gbp": cash,
            "note": DEFERRAL_NOT_LOADED_NOTE,
        }
    if enabled and eligible:
        deferred = {k: round(float(collection[k]), 2) for k in ("low", "central", "high")}
        accrual = scale_triple(deferred, r)
        cash = {"low": 0.0, "central": 0.0, "high": 0.0}
        status = "applied"
    else:
        deferred = {"low": 0.0, "central": 0.0, "high": 0.0}
        accrual = {"low": 0.0, "central": 0.0, "high": 0.0}
        cash = {k: round(float(collection[k]), 2) for k in ("low", "central", "high")}
        status = "not_eligible" if enabled else "disabled"
    return {
        "status": status,
        "deferral_eligible": bool(eligible),
        "deferral_applied": bool(enabled and eligible),
        "deferral_rate": r,
        "deferred_gbp": deferred,
        "accrual_gbp_per_year": accrual,
        "cash_collected_gbp": cash,
    }


def _yield_band_parts(yp: Mapping[str, Any]) -> tuple[float, float, float]:
    central = float(yp.get("central", yp.get("land_yield")))
    band = yp.get("land_yield_band")
    if isinstance(band, (list, tuple)) and len(band) == 2:
        return float(band[0]), central, float(band[1])
    nested = yp.get("band")
    if isinstance(nested, Mapping):
        return float(nested["low"]), float(nested.get("central", central)), float(nested["high"])
    # Degenerate: no band published — triple collapses to central.
    return central, central, central


def _blocked_fields(defaults: Mapping[str, Any] | None = None) -> dict[str, Any]:
    yp = yield_placeholder()
    return {
        "internal": True,
        "publication_status": PUBLICATION_STATUS,
        "blocked_reason": BLOCKED_REASON,
        "warning": INTERNAL_WARNING,
        "yield_placeholder": yp,
        "policy_config": policy_config_payload(defaults) if defaults is not None else dict(POLICY_CONFIG),
        "money_grain": MONEY_GRAIN,
        "money_grain_note": MONEY_GRAIN_NOTE,
        "approved_defaults": True,
    }


def stamp_blocked(payload: dict[str, Any], *, defaults: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Stamp scenario output as internal-only / publication_status=blocked (room rule)."""
    fields = _blocked_fields(defaults)
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
    """Refuse council/national £ fields and leaky top-level roll-ups (TEMP: money at DZ only)."""
    top_bad = sorted(_FORBIDDEN_RESPONSE_TOP_LEVEL & set(payload))
    if top_bad:
        raise TaxScenarioError(
            "aggregate_gbp_forbidden",
            f"response must not carry top-level {top_bad}; build roll-up internally only.",
            fields=top_bad,
        )
    for block_name in ("national", "council"):
        block = payload.get(block_name)
        if not isinstance(block, dict):
            continue
        bad = sorted(_FORBIDDEN_AGGREGATE_GBP & set(block))
        if bad:
            raise TaxScenarioError(
                "aggregate_gbp_forbidden",
                f"{block_name} must not carry £ fields {bad}; money is Data Zone grain only while blocked.",
                fields=bad,
            )
    for row in payload.get("by_council") or []:
        if not isinstance(row, dict):
            continue
        bad = sorted(_FORBIDDEN_AGGREGATE_GBP & set(row))
        if bad:
            raise TaxScenarioError(
                "aggregate_gbp_forbidden",
                f"by_council must not carry £ fields {bad}; money is Data Zone grain only while blocked.",
                fields=bad,
            )
    for code, body in (payload.get("s1_by_council") or {}).items():
        if not isinstance(body, dict):
            continue
        bad = sorted(_FORBIDDEN_AGGREGATE_GBP & set(body))
        if bad:
            raise TaxScenarioError(
                "aggregate_gbp_forbidden",
                f"s1_by_council[{code}] must not carry £ fields {bad}; return rate + source only.",
                fields=bad,
                la_code=code,
            )


@dataclass(frozen=True)
class ZoneRentRow:
    """One Data Zone Surface Rent input for scenario maths."""

    code: str
    vintage: int
    la_code: str
    la_name: str
    measured_rent: float
    price_year: int
    value_tier: str = "proxy"
    uncertainty_low: float | None = None
    uncertainty_high: float | None = None
    deferral_eligible: bool = False  # low-income home owner (approved defaults)
    # True only when a caller injects known eligibility; SQL path leaves this False.
    deferral_eligibility_loaded: bool = False
    crosswalk_method: str = "none"  # none | address_uprn | value_weighted
    estimate_label: str | None = None  # measured | partly_estimated | fully_estimated


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


def tax_scenario_input_admitted(row: Mapping[str, Any]) -> bool:
    """Whether a surface_rent_dz (+ spine) row may feed internal tax scenarios.

    - DZ2022 (default / roll-up pin): UPRN-weighted crosswalk rows (``address_uprn``),
      which stay ``publish_level=internal`` / ``publication_status=blocked`` (#71).
      Council membership is the spine ``la_code`` for that zone.
    - DZ2011 (optional vintage=2011): publicly served native rows only.
    """
    if row.get("quality") == "placeholder":
        return False
    try:
        vintage = int(row.get("vintage"))
    except (TypeError, ValueError):
        return False
    method = str(row.get("crosswalk_method") or "none")
    if method not in ALLOWED_TAX_CROSSWALK:
        return False
    if vintage == 2022:
        return (
            method == UPRN_DZ2022_CROSSWALK
            and row.get("publish_level") == "internal"
            and str(row.get("publication_status") or "") == PUBLICATION_STATUS
        )
    if vintage == 2011:
        return publicly_served(row) and method in {"none", UPRN_DZ2022_CROSSWALK, "value_weighted"}
    return False


def _estimate_label_from_row(row: Mapping[str, Any]) -> str:
    """Read estimate_label from a 2022 surface row (or derive from fill_method / proxy_tags)."""
    raw = row.get("estimate_label")
    if raw:
        return str(raw)
    tags = row.get("proxy_tags") or ()
    if isinstance(tags, str):
        tags = [t for t in tags.split(";") if t]
    for tag in tags:
        text = str(tag)
        if text.startswith("estimate_label="):
            return text.split("=", 1)[1]
    return estimate_label_for_fill(row.get("fill_method"))


def zone_row_from_db(row: Mapping[str, Any]) -> ZoneRentRow | None:
    """Accept a joined surface_rent_dz + zone_spine row, or None if not usable."""
    if not tax_scenario_input_admitted(row):
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
    tier = str(row.get("value_tier") or "proxy")
    if tier not in VALUE_TIERS:
        tier = "proxy"
    method = str(row.get("crosswalk_method") or "none")
    try:
        ulo = row.get("uncertainty_low")
        uhi = row.get("uncertainty_high")
        # SQL never selects eligibility; ignore any stray keys so DB path stays explicit.
        return ZoneRentRow(
            code=str(code),
            vintage=int(vintage),
            la_code=str(la_code),
            la_name=str(la_name),
            measured_rent=float(rent),
            price_year=int(price_year),
            value_tier=tier,
            uncertainty_low=float(ulo) if ulo is not None else None,
            uncertainty_high=float(uhi) if uhi is not None else None,
            deferral_eligible=False,
            deferral_eligibility_loaded=False,
            crosswalk_method=method,
            estimate_label=_estimate_label_from_row(row),
        )
    except (TypeError, ValueError):
        return None


def surface_path_payload(vintage: int, rows: Sequence[ZoneRentRow]) -> dict[str, Any]:
    """Describe which surface path fed the scenario (DZ2011 native vs UPRN DZ2022)."""
    methods = sorted({r.crosswalk_method for r in rows}) if rows else []
    if int(vintage) == 2022:
        return {
            "vintage": 2022,
            "path": "uprn_weighted_dz2022",
            "crosswalk_method": UPRN_DZ2022_CROSSWALK,
            "methods_seen": methods,
            "rollup_pin_vintage": DEFAULT_DZ_VINTAGE,
            "council_source": "datazones.zone_spine",
            "note": (
                "Unit of account: DZ2022 via #71 address-UPRN crosswalk "
                f"({UPRN_DZ2022_CROSSWALK}). Council/Scotland £ roll-up is pinned to "
                "DZ2022; each zone uses the spine council (la_code). "
                "Tax output stays publication_status=blocked."
            ),
        }
    return {
        "vintage": 2011,
        "path": "native_dz2011",
        "crosswalk_method": methods[0] if len(methods) == 1 else "none",
        "methods_seen": methods,
        "rollup_pin_vintage": DEFAULT_DZ_VINTAGE,
        "council_source": "datazones.zone_spine",
        "note": (
            "Optional native DZ2011 Surface Rent path (vintage=2011). "
            "Default council/Scotland £ roll-up pin is DZ2022 via address_uprn."
        ),
    }


def _combine_estimate_labels_or_refuse(
    rows: Sequence[ZoneRentRow],
    *,
    where: str,
) -> str:
    """Combine zone estimate labels; refuse any zone with no label (match #71 roll-up)."""
    labels = [z.estimate_label for z in rows]
    missing = [z.code for z, lbl in zip(rows, labels) if not lbl]
    if missing:
        raise TaxScenarioError(
            "missing_estimate_label",
            f"estimate_label required on every zone for {where} roll-up "
            f"(missing on {missing[:3]}).",
            where=where,
            missing_codes=missing[:10],
        )
    return combine_estimate_labels([str(lbl) for lbl in labels])


def is_taxable(row: ZoneRentRow) -> bool:
    """Shadow values are never taxed. No ownership-based exemptions."""
    return row.value_tier != "shadow"


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


def _refuse_mixed_vintage(rows: Sequence[ZoneRentRow], *, where: str) -> int:
    vintages = sorted({r.vintage for r in rows})
    if len(vintages) > 1:
        raise TaxScenarioError(
            "mixed_vintage",
            f"One Data Zone version throughout; mixed vintages refused ({where}).",
            vintages=vintages,
            where=where,
        )
    return vintages[0]


def _rent_triple_for_row(row: ZoneRentRow, yp: Mapping[str, Any]) -> dict[str, float]:
    lo_y, c_y, hi_y = _yield_band_parts(yp)
    if row.uncertainty_low is not None and row.uncertainty_high is not None:
        return {
            "low": round(float(row.uncertainty_low), 2),
            "central": round(float(row.measured_rent), 2),
            "high": round(float(row.uncertainty_high), 2),
        }
    return money_triple(row.measured_rent, yield_central=c_y, band_low=lo_y, band_high=hi_y)


def _apply_rate_triple(
    rent: Mapping[str, float],
    rate: float | Mapping[str, float],
    *,
    taxable: bool,
) -> dict[str, float]:
    """Scale a rent triple by a single rate or an LCH rate triple."""
    if not taxable:
        return {"low": 0.0, "central": 0.0, "high": 0.0}
    if isinstance(rate, Mapping):
        return {
            k: round(float(rent[k]) * float(rate[k]), 2)
            for k in ("low", "central", "high")
        }
    return scale_triple(rent, float(rate))


def _zone_money_row(
    row: ZoneRentRow,
    *,
    capture_rate: float | Mapping[str, float],
    yp: Mapping[str, Any] | None = None,
    phase_in_points_per_year: int = 10,
    phase_in_year: int | None = None,
    deferral_enabled: bool = True,
    deferral_rate: float = 0.0262,
    revenue_sharing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """£ fields for one Data Zone only — every £ field is a low/central/high triple.

    Applies phase-in schedule (10 pts/year), deferral (eligible low-income home owners),
    and council/dividend revenue split at Data Zone grain.
    """
    yp = yp or yield_placeholder()
    rent = _rent_triple_for_row(row, yp)
    taxable = is_taxable(row)
    full_collection = _apply_rate_triple(rent, capture_rate, taxable=taxable)
    schedule = phase_in_schedule(full_collection, points_per_year=phase_in_points_per_year)
    # Default applied year = fully phased-in (last schedule year) unless caller selects one.
    applied_year = int(phase_in_year) if phase_in_year is not None else schedule[-1]["year"]
    frac = phase_in_fraction(applied_year, phase_in_points_per_year)
    collection = scale_triple(full_collection, frac)
    deferral = apply_deferral(
        collection,
        eligible=bool(row.deferral_eligible) and taxable,
        rate=deferral_rate,
        enabled=deferral_enabled,
        eligibility_loaded=bool(row.deferral_eligibility_loaded),
    )
    sharing = revenue_sharing or {"council_share": 0.5, "dividend_share": 0.5}
    council_share = float(sharing["council_share"])
    dividend_share = float(sharing["dividend_share"])
    # Split the phased illustrated liability (deferral tracked separately).
    council_gbp = scale_triple(collection, council_share)
    dividend_gbp = scale_triple(collection, dividend_share)
    out: dict[str, Any] = {
        "code": row.code,
        "vintage": row.vintage,
        "la_code": row.la_code,
        "la_name": row.la_name,
        "price_year": row.price_year,
        "value_tier": row.value_tier,
        "tag": row.value_tier,  # market | proxy | shadow
        "taxable": taxable,
        "measured_rent_gbp": rent,
        "illustrated_collection_full_gbp": full_collection,
        "illustrated_collection_gbp": collection,
        "crosswalk_method": row.crosswalk_method,
        "phase_in": {
            "points_per_year": int(phase_in_points_per_year),
            "applied_year": applied_year,
            "applied_fraction": frac,
            "schedule": schedule,
        },
        "deferral": deferral,
        "revenue_sharing": {
            "council_share": council_share,
            "dividend_share": dividend_share,
            "council_share_gbp": council_gbp,
            "dividend_share_gbp": dividend_gbp,
        },
        "money_grain": MONEY_GRAIN,
        "status": STATUS,
        "disclaimer": DISCLAIMER,
        "yield_placeholder": dict(yp),
    }
    if row.estimate_label is not None:
        out["estimate_label"] = row.estimate_label
    return out


def council_fiscal_targets(defaults: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """la_code → {council_tax_gbp, business_rates_gbp, la_name, year/source, ...}."""
    fiscal = defaults.get("fiscal_targets") or {}
    ct_meta = fiscal.get("council_tax") or {}
    nbr_meta = fiscal.get("business_rates") or {}
    out: dict[str, dict[str, Any]] = {}
    for row in fiscal.get("by_council") or []:
        if not isinstance(row, Mapping):
            continue
        code = str(row["la_code"])
        out[code] = {
            "la_code": code,
            "la_name": str(row.get("la_name") or code),
            "council_tax_gbp": float(row["council_tax_gbp"]),
            "business_rates_gbp": float(row["business_rates_gbp"]),
            "target_gbp": float(row["council_tax_gbp"]) + float(row["business_rates_gbp"]),
            "council_tax_year": row.get("council_tax_year") or ct_meta.get("year"),
            "council_tax_source": row.get("council_tax_source") or ct_meta.get("source"),
            "business_rates_year": row.get("business_rates_year") or nbr_meta.get("year"),
            "business_rates_source": row.get("business_rates_source") or nbr_meta.get("source"),
            "targets_status": _fiscal_targets_status(defaults),
        }
    return out


def solve_s1_per_council(
    rows: Sequence[ZoneRentRow],
    *,
    defaults: Mapping[str, Any] | None = None,
    yp: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Solve S1 capture rate per council so revenue equals that council's CT + business rates.

    Rates are solved as a low/central/high triple against each band of the taxable
    Surface Rent base (keys follow the *rent* band, not ascending rates — see
    ``S1_RATE_BAND_NOTE``). Shadow zones are excluded. National single-rate is not
    used. Any band rate above 100% is flagged (``s1_rate_above_100_pct``).
    """
    cfg = defaults if defaults is not None else load_draft_defaults()
    yp = yp or yield_placeholder()
    targets = council_fiscal_targets(cfg)
    by_la: dict[str, list[ZoneRentRow]] = {}
    for r in rows:
        by_la.setdefault(r.la_code, []).append(r)

    solved: dict[str, dict[str, Any]] = {}
    for la_code, group in by_la.items():
        taxable = {"low": 0.0, "central": 0.0, "high": 0.0}
        for z in group:
            if not is_taxable(z):
                continue
            triple = _rent_triple_for_row(z, yp)
            for k in ("low", "central", "high"):
                taxable[k] += float(triple[k])
        for k in ("low", "central", "high"):
            taxable[k] = round(taxable[k], 2)
        tgt = targets.get(la_code)
        if tgt is None:
            raise TaxScenarioError(
                "missing_council_fiscal_target",
                f"No approved-defaults CT+NBR target for council {la_code}.",
                la_code=la_code,
            )
        target = float(tgt["target_gbp"])
        rate: dict[str, float] = {}
        for k in ("low", "central", "high"):
            rate[k] = 0.0 if taxable[k] <= 0 else target / taxable[k]
        above = any(rate[k] > 1.0 for k in ("low", "central", "high"))
        solved[la_code] = {
            "la_code": la_code,
            "la_name": group[0].la_name,
            "s1_rate": rate,
            "s1_rate_above_100_pct": above,
            "s1_rate_band_note": S1_RATE_BAND_NOTE,
            "s1_rate_source": {
                "basis": "council_tax_plus_business_rates",
                "council_tax_year": tgt.get("council_tax_year"),
                "council_tax_source": tgt.get("council_tax_source"),
                "business_rates_year": tgt.get("business_rates_year"),
                "business_rates_source": tgt.get("business_rates_source"),
                "targets_status": tgt.get("targets_status"),
            },
            # Internal reconcile fields — never copy onto the API response.
            "_taxable_rent_gbp": taxable,
            "_target_gbp": target,
            "_s1_revenue_central_gbp": round(rate["central"] * taxable["central"], 2),
            "zone_count": len(group),
            "taxable_zone_count": sum(1 for z in group if is_taxable(z)),
        }
    return solved


def _s1_rate_as_triple(solved_body: Mapping[str, Any]) -> dict[str, float]:
    raw = solved_body.get("s1_rate") or 0.0
    if isinstance(raw, Mapping):
        return {k: float(raw[k]) for k in ("low", "central", "high")}
    v = float(raw)
    return {"low": v, "central": v, "high": v}


def build_aggregate_rollup(
    rows: Sequence[ZoneRentRow],
    *,
    rate_by_zone: Mapping[str, float],
    yp: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build council + Scotland £ roll-ups (behind TEMP setting). Each zone counted once.

    Returns internal rollup with triples; caller must not put these on display blocks
    while ``display_while_blocked.gbp_grain == data_zone_only``.
    """
    yp = yp or yield_placeholder()
    lo_y, c_y, hi_y = _yield_band_parts(yp)
    _refuse_mixed_vintage(rows, where="rollup")
    price_year = _refuse_mixed_price_years(rows, where="rollup")

    by_la: dict[str, list[ZoneRentRow]] = {}
    for r in rows:
        by_la.setdefault(r.la_code, []).append(r)

    councils: list[dict[str, Any]] = []
    scotland = {"low": 0.0, "central": 0.0, "high": 0.0}
    scotland_collection = {"low": 0.0, "central": 0.0, "high": 0.0}
    seen: set[str] = set()

    for la_code in sorted(by_la, key=lambda c: by_la[c][0].la_name):
        group = by_la[la_code]
        rent = {"low": 0.0, "central": 0.0, "high": 0.0}
        coll = {"low": 0.0, "central": 0.0, "high": 0.0}
        for z in group:
            if z.code in seen:
                raise TaxScenarioError("duplicate_zone", f"Zone {z.code} counted more than once.", code=z.code)
            seen.add(z.code)
            triple = _rent_triple_for_row(z, yp)
            rate = 0.0 if not is_taxable(z) else float(rate_by_zone.get(z.code, 0.0))
            scaled = scale_triple(triple, rate)
            for k in ("low", "central", "high"):
                rent[k] += triple[k]
                coll[k] += scaled[k]
        for k in ("low", "central", "high"):
            rent[k] = round(rent[k], 2)
            coll[k] = round(coll[k], 2)
            scotland[k] += rent[k]
            scotland_collection[k] += coll[k]
        councils.append({
            "la_code": la_code,
            "la_name": group[0].la_name,
            "zone_count": len(group),
            "measured_rent_gbp": rent,
            "illustrated_collection_gbp": coll,
            "zone_codes": sorted(z.code for z in group),
        })

    for k in ("low", "central", "high"):
        scotland[k] = round(scotland[k], 2)
        scotland_collection[k] = round(scotland_collection[k], 2)

    # Exact reconcile: sum of council centrals == Scotland central (zone-once invariant).
    sum_council = round(sum(c["measured_rent_gbp"]["central"] for c in councils), 2)
    if sum_council != scotland["central"]:
        raise TaxScenarioError(
            "rollup_mismatch",
            f"Σ council measured_rent ({sum_council}) != Scotland ({scotland['central']}).",
            sum_council=sum_council,
            scotland=scotland["central"],
        )

    return {
        "price_year": price_year,
        "vintage": rows[0].vintage if rows else None,
        "zone_count": len(seen),
        "by_council": councils,
        "scotland": {
            "zone_count": len(seen),
            "measured_rent_gbp": scotland,
            "illustrated_collection_gbp": scotland_collection,
        },
        "yield_band_used": {"low": lo_y, "central": c_y, "high": hi_y},
        "publication_status": PUBLICATION_STATUS,
        "internal": True,
        "note": (
            "Blocked aggregate roll-up built behind TEMP display_while_blocked setting "
            f"(DZ{rows[0].vintage if rows else DEFAULT_DZ_VINTAGE} unit; spine council). "
            "Not shown on council/national display blocks while gbp_grain=data_zone_only."
        ),
    }


def _scenario_rate_for_zone(
    row: ZoneRentRow,
    *,
    scenario_id: str,
    s1_by_council: Mapping[str, Mapping[str, Any]],
    defaults: Mapping[str, Any],
    capture_rate: float | None,
) -> float | dict[str, float]:
    if not is_taxable(row):
        return 0.0
    sid = scenario_id.upper()
    scenarios = defaults.get("scenarios") or {}
    if sid == "S1":
        solved = s1_by_council.get(row.la_code) or {}
        return _s1_rate_as_triple(solved)
    if sid in scenarios:
        body = scenarios[sid] or {}
        if body.get("capture_rate") is not None:
            return parse_capture_rate(body["capture_rate"])
    if capture_rate is not None:
        return parse_capture_rate(capture_rate)
    raise TaxScenarioError("unknown_scenario", f"Unknown scenario_id {scenario_id!r}.", scenario_id=scenario_id)


def _central_rate(rate: float | Mapping[str, float]) -> float:
    if isinstance(rate, Mapping):
        return float(rate.get("central") or 0.0)
    return float(rate)


def aggregate_by_council(
    rows: Iterable[ZoneRentRow],
    *,
    capture_rate: float = 1.0,
    la_code: str | None = None,
    scenario_id: str = "S2",
    defaults: Mapping[str, Any] | None = None,
    include_national_s1: bool = False,
    phase_in_year: int | None = None,
    revenue_sharing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Council membership + per-zone £ triples (no council/national £ on display blocks)."""
    cfg = dict(defaults) if defaults is not None else load_draft_defaults()
    sid = (scenario_id or "S2").upper()
    if sid not in SCENARIO_IDS:
        raise TaxScenarioError("unknown_scenario", f"scenario_id must be one of {SCENARIO_IDS}.", scenario_id=scenario_id)

    usable = list(rows)
    if la_code:
        usable = [r for r in usable if r.la_code == la_code]
    yp = yield_placeholder()
    sharing = resolve_revenue_sharing(cfg, revenue_sharing)
    phase_cfg = cfg.get("phase_in") or {"points_per_year": 10}
    points_per_year = int(phase_cfg.get("points_per_year") or 10)
    defer_cfg = cfg.get("deferral") or {"low_income_home_owners": True, "rate": 0.0262}
    deferral_enabled = bool(defer_cfg.get("low_income_home_owners", True))
    deferral_rate = float(defer_cfg.get("rate", 0.0262))
    targets_status = _fiscal_targets_status(cfg)

    if not usable:
        payload = stamp_blocked({
            "status": STATUS,
            "lens": LENS,
            "lens_note": LENS_NOTE,
            "disclaimer": DISCLAIMER,
            "scenario_id": sid,
            "capture_rate": parse_capture_rate(capture_rate) if sid != "S1" else None,
            "capture_note": CAPTURE_NOTE,
            "price_year": None,
            "national": {"zone_count": 0},
            "by_council": [],
            "by_zone": [],
            "preset_rates": list(DEFAULT_CAPTURE_RATES),
            "revenue_sharing": sharing,
            "phase_in": {"points_per_year": points_per_year, "applied_year": phase_in_year},
            "deferral": {
                "status": DEFERRAL_NOT_LOADED,
                "low_income_home_owners": deferral_enabled,
                "rate": deferral_rate,
                "note": DEFERRAL_NOT_LOADED_NOTE,
            },
            "note": "No publishable Surface Rent rows for this filter. Nothing was estimated.",
        }, defaults=cfg)
        assert_no_aggregate_gbp(payload)
        return payload

    _refuse_mixed_vintage(usable, where="national")
    price_year = _refuse_mixed_price_years(usable, where="national")
    s1_by_council = solve_s1_per_council(usable, defaults=cfg, yp=yp) if sid == "S1" else {}

    rate_for_zone: dict[str, float | dict[str, float]] = {
        z.code: _scenario_rate_for_zone(
            z,
            scenario_id=sid,
            s1_by_council=s1_by_council,
            defaults=cfg,
            capture_rate=capture_rate,
        )
        for z in usable
    }
    # Internal roll-up uses central rates only; never attached to the response.
    rate_by_zone_central: dict[str, float] = {
        code: _central_rate(rate) for code, rate in rate_for_zone.items()
    }

    by_la: dict[str, list[ZoneRentRow]] = {}
    for r in usable:
        by_la.setdefault(r.la_code, []).append(r)

    councils: list[dict[str, Any]] = []
    for code in sorted(by_la, key=lambda c: by_la[c][0].la_name):
        group = by_la[code]
        _refuse_mixed_price_years(group, where=f"council:{code}")
        entry: dict[str, Any] = {
            "la_code": code,
            "la_name": group[0].la_name,
            "zone_count": len(group),
            "price_year": price_year,
            "zone_codes": sorted(z.code for z in group),
            "status": STATUS,
            "disclaimer": DISCLAIMER,
            "estimate_label": _combine_estimate_labels_or_refuse(
                group, where=f"council:{code}"
            ),
        }
        if sid == "S1" and code in s1_by_council:
            # Rate + source only — no £ totals on the display block.
            entry["s1_rate"] = dict(s1_by_council[code]["s1_rate"])
            entry["s1_rate_above_100_pct"] = bool(s1_by_council[code]["s1_rate_above_100_pct"])
            entry["s1_rate_band_note"] = S1_RATE_BAND_NOTE
            entry["s1_rate_source"] = dict(s1_by_council[code]["s1_rate_source"])
        councils.append(entry)

    by_zone = [
        _zone_money_row(
            r,
            capture_rate=rate_for_zone[r.code],
            yp=yp,
            phase_in_points_per_year=points_per_year,
            phase_in_year=phase_in_year,
            deferral_enabled=deferral_enabled,
            deferral_rate=deferral_rate,
            revenue_sharing=sharing,
        )
        for r in sorted(usable, key=lambda z: z.code)
    ]

    display = cfg.get("display_while_blocked") or {}
    build_rollup = bool(display.get("build_council_scotland_rollup", True))
    if build_rollup:
        # Reconcile Σ councils = Scotland internally; do not put £ roll-up on the response.
        build_aggregate_rollup(usable, rate_by_zone=rate_by_zone_central, yp=yp)

    applied_year = phase_in_year if phase_in_year is not None else (
        by_zone[0]["phase_in"]["applied_year"] if by_zone else None
    )

    path_info = surface_path_payload(usable[0].vintage, usable)
    if usable[0].vintage == 2022:
        bad_methods = sorted({r.crosswalk_method for r in usable if r.crosswalk_method != UPRN_DZ2022_CROSSWALK})
        if bad_methods:
            raise TaxScenarioError(
                "invalid_dz2022_crosswalk",
                f"DZ2022 tax scenarios require {UPRN_DZ2022_CROSSWALK}; saw {bad_methods}.",
                methods=bad_methods,
            )

    national: dict[str, Any] = {
        "zone_count": len(usable),
        "price_year": price_year,
        "status": STATUS,
        "disclaimer": DISCLAIMER,
        "estimate_label": _combine_estimate_labels_or_refuse(usable, where="scotland"),
    }

    payload: dict[str, Any] = {
        "status": STATUS,
        "lens": LENS,
        "lens_note": LENS_NOTE,
        "disclaimer": DISCLAIMER,
        "scenario_id": sid,
        "capture_rate": None if sid == "S1" else parse_capture_rate(
            (cfg.get("scenarios") or {}).get(sid, {}).get("capture_rate", capture_rate)
        ),
        "capture_note": CAPTURE_NOTE,
        "price_year": price_year,
        "vintage": usable[0].vintage,
        "surface_path": path_info,
        "national": national,
        "by_council": councils,
        "by_zone": by_zone,
        "preset_rates": list(DEFAULT_CAPTURE_RATES),
        "revenue_sharing": sharing,
        "phase_in": {
            "points_per_year": points_per_year,
            "applied_year": applied_year,
            "applied_fraction": phase_in_fraction(int(applied_year), points_per_year) if applied_year else None,
        },
        "deferral": {
            "status": DEFERRAL_NOT_LOADED
            if not any(z.deferral_eligibility_loaded for z in usable)
            else "eligibility_loaded",
            "low_income_home_owners": deferral_enabled,
            "rate": deferral_rate,
            "note": DEFERRAL_NOT_LOADED_NOTE
            if not any(z.deferral_eligibility_loaded for z in usable)
            else "Deferral eligibility supplied by caller; not from SQL.",
        },
        "note": (
            "Internal tax scenario approved defaults (v0.1, Oct 2026): £ at Data Zone grain "
            "only (by_zone) as low/central/high triples with market/proxy/shadow tags. "
            "Council/national blocks are membership counts while blocked. Shadow never taxed. "
            "S1 is per-council revenue-swap; national single-rate S1 is off by default. "
            "Phase-in, deferral and revenue-share applied at Data Zone grain. "
            "Not the Sandilands pool, not AGR, not a tax bill. publication_status=blocked."
        ),
    }
    if sid == "S1":
        payload["s1_by_council"] = {
            code: {
                "s1_rate": dict(body["s1_rate"]),
                "s1_rate_above_100_pct": bool(body["s1_rate_above_100_pct"]),
                "s1_rate_band_note": S1_RATE_BAND_NOTE,
                "s1_rate_source": dict(body["s1_rate_source"]),
            }
            for code, body in s1_by_council.items()
        }
        payload["s1_targets_status"] = targets_status
        payload["s1_rate_band_note"] = S1_RATE_BAND_NOTE
        nat_cfg = ((cfg.get("scenarios") or {}).get("S1") or {}).get("national_single_rate") or {}
        s1_label = _s1_label("S1", (cfg.get("scenarios") or {}).get("S1") or {}, cfg)
        payload["s1_national_single_rate"] = {
            "enabled": bool(include_national_s1 or nat_cfg.get("enabled")),
            "id": nat_cfg.get("id", "S1_national"),
            "label": nat_cfg.get("label", "Revenue swap (national single rate)"),
            "default": False,
            "note": "Separate scenario; off by default. Per-council S1 is the default.",
        }
        payload["s1_label"] = s1_label

    stamped = stamp_blocked(payload, defaults=cfg)
    assert_no_aggregate_gbp(stamped)
    return stamped


def zone_illustration(
    row: ZoneRentRow,
    *,
    capture_rate: float = 1.0,
    council_zone_count: int | None = None,
    scenario_id: str = "S2",
    defaults: Mapping[str, Any] | None = None,
    council_rows: Sequence[ZoneRentRow] | None = None,
    phase_in_year: int | None = None,
    revenue_sharing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Who-pays illustration for one Data Zone (£ triples + tag on the zone only)."""
    cfg = dict(defaults) if defaults is not None else load_draft_defaults()
    sid = (scenario_id or "S2").upper()
    peers = list(council_rows) if council_rows is not None else [row]
    s1_by_council = solve_s1_per_council(peers, defaults=cfg) if sid == "S1" else {}
    rate = _scenario_rate_for_zone(
        row,
        scenario_id=sid,
        s1_by_council=s1_by_council,
        defaults=cfg,
        capture_rate=capture_rate,
    )
    yp = yield_placeholder()
    sharing = resolve_revenue_sharing(cfg, revenue_sharing)
    phase_cfg = cfg.get("phase_in") or {"points_per_year": 10}
    points_per_year = int(phase_cfg.get("points_per_year") or 10)
    defer_cfg = cfg.get("deferral") or {"low_income_home_owners": True, "rate": 0.0262}
    zone = _zone_money_row(
        row,
        capture_rate=rate,
        yp=yp,
        phase_in_points_per_year=points_per_year,
        phase_in_year=phase_in_year,
        deferral_enabled=bool(defer_cfg.get("low_income_home_owners", True)),
        deferral_rate=float(defer_cfg.get("rate", 0.0262)),
        revenue_sharing=sharing,
    )
    council_block: dict[str, Any] = {
        "la_code": row.la_code,
        "la_name": row.la_name,
        "zone_count": council_zone_count,
        "status": STATUS,
        "disclaimer": DISCLAIMER,
    }
    if sid == "S1" and row.la_code in s1_by_council:
        council_block["s1_rate"] = dict(s1_by_council[row.la_code]["s1_rate"])
        council_block["s1_rate_above_100_pct"] = bool(
            s1_by_council[row.la_code]["s1_rate_above_100_pct"]
        )
        council_block["s1_rate_band_note"] = S1_RATE_BAND_NOTE
        council_block["s1_rate_source"] = dict(s1_by_council[row.la_code]["s1_rate_source"])
    if row.estimate_label is not None:
        council_block["estimate_label"] = row.estimate_label
    payload = stamp_blocked({
        "status": STATUS,
        "lens": LENS,
        "lens_note": LENS_NOTE,
        "disclaimer": DISCLAIMER,
        "scenario_id": sid,
        "capture_rate": None if sid == "S1" else _central_rate(rate),
        "capture_note": CAPTURE_NOTE,
        "zone": zone,
        "surface_path": surface_path_payload(row.vintage, [row]),
        "revenue_sharing": sharing,
        "council": council_block,
        "note": (
            "Illustrated collection = taxable Surface Rent × scenario rate at Data Zone grain "
            "(low/central/high), with phase-in schedule, deferral and revenue-share applied. "
            "Shadow never taxed. Research estimate only; not AGR and not a "
            "tax bill. publication_status=blocked. Approved defaults (v0.1, Oct 2026)."
        ),
    }, defaults=cfg)
    assert_no_aggregate_gbp(payload)
    return payload
