"""AGR / Wealth Engine publication helpers (internal, blocked until yield config lands).

Yield rates are read from ``data/config/surface.yaml`` via
``georgist.surface_settings.yield_placeholder`` (same path as tax scenarios / #9).
Hardcoded rates are refused. Place £ figures are always low/central/high ranges.
"""

from __future__ import annotations

from typing import Any, Mapping

from agr.response_labels import stamp_experimental
from georgist.surface_settings import yield_placeholder

UNPUBLISHED_REASON = "yield_calibration_pending"
UNPUBLISHED_NOTE = (
    "Wealth Engine figures for place pages are internal and unpublished "
    "(publication_status=blocked). Data Zone grain only. Public rent £ routes "
    "are not served. Every figure is experimental and tagged market, proxy or "
    "shadow when published. Yield central/band come from surface.yaml."
)

# Sale/house price fields are not rent figures (e.g. sales store price_min_gbp).
_RENT_KEY_PARTS = (
    "rent",
    "liability",
    "site_capital",
    "site_rental",
    "site_share",
    "vacant_full_agr",
    "annual_ground",
    "measured_rent",
    "policy_rent",
    "price_indexed",
    "gross_plot",
    "net_contribution",
    "plot_gbp",
    "per_sqm",
    "total_gbp",
    "low_gbp",
    "high_gbp",
)

# Single-number £ keys rewritten to {low, central, high} on place payloads.
_SINGLE_GBP_KEYS = frozenset({
    "measured_rent_gbp",
    "policy_rent",
    "infra_share",
    "planning_uplift",
    "total_gbp",
    "annual_rent_gbp",
})


def _key_looks_like_rent(key: str) -> bool:
    lower = key.lower()
    if "price" in lower and "rent" not in lower and "indexed" not in lower:
        return False
    return any(part in lower for part in _RENT_KEY_PARTS)


def rent_figure_paths(obj: Any, *, prefix: str = "") -> list[str]:
    """Dotted paths where a rent-like key holds a numeric figure."""
    found: list[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if _key_looks_like_rent(str(key)):
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    found.append(path)
                elif isinstance(value, Mapping | list):
                    nested = rent_figure_paths(value, prefix=path)
                    found.extend(nested if nested else [path])
            else:
                found.extend(rent_figure_paths(value, prefix=path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            found.extend(rent_figure_paths(item, prefix=f"{prefix}[{i}]"))
    return found


def gbp_range(
    central: float | None,
    *,
    low: float | None = None,
    high: float | None = None,
    yield_cfg: Mapping[str, Any] | None = None,
) -> dict[str, float | None] | None:
    """Build a low/central/high GBP range. Never returns a bare number."""
    if central is None and low is None and high is None:
        return None
    c = float(central) if central is not None else None
    lo = float(low) if low is not None else None
    hi = float(high) if high is not None else None
    if c is not None and (lo is None or hi is None) and yield_cfg is not None:
        y_lo, y_c, y_hi = _yield_band_parts(yield_cfg)
        if y_c and abs(y_c) > 1e-15:
            if lo is None:
                lo = c * (y_lo / y_c)
            if hi is None:
                hi = c * (y_hi / y_c)
    if c is None:
        c = lo if lo is not None else hi
    if lo is None:
        lo = c
    if hi is None:
        hi = c
    return {
        "low": None if lo is None else round(float(lo), 2),
        "central": None if c is None else round(float(c), 2),
        "high": None if hi is None else round(float(hi), 2),
    }


def _yield_band_parts(yp: Mapping[str, Any]) -> tuple[float, float, float]:
    central = float(yp.get("central", yp.get("land_yield")))
    band = yp.get("land_yield_band")
    if isinstance(band, (list, tuple)) and len(band) == 2:
        return float(band[0]), central, float(band[1])
    nested = yp.get("band")
    if isinstance(nested, Mapping) and "low" in nested and "high" in nested:
        return float(nested["low"]), float(nested.get("central", central)), float(nested["high"])
    return central, central, central


def internal_yield_from_surface() -> dict[str, Any]:
    """Yield config for internal place pages — always from surface.yaml (#9 path)."""
    yp = yield_placeholder()
    y_lo, y_c, y_hi = _yield_band_parts(yp)
    out: dict[str, Any] = {
        "status": "provisional_internal_pending",
        "scope": "internal_only",
        "yield_source": yp.get("source") or "data/config/surface.yaml yield.central",
        "central": y_c,
        "band": {"low": y_lo, "central": y_c, "high": y_hi},
        "land_yield": y_c,
        "land_yield_band": [y_lo, y_hi],
        "owner": yp.get("owner"),
        "note": (
            "Applied internally from surface.yaml yield.central / yield.band "
            "(Georgist calibration v3 metadata passed through when present). "
            "Place £ stay publication_status=blocked; no public £."
        ),
    }
    for key in (
        "result_hash",
        "calibration_version",
        "central_at_cap",
        "band_clipped_outer",
        "bed_mapping_sensitive",
        "flags",
        "components",
        "high_clipped_at_cap",
    ):
        if key in yp:
            out[key] = yp[key]
    return out


def wealth_to_ranges(
    wealth: Mapping[str, Any],
    *,
    yield_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    """Rewrite wealth payload so every £ figure is a low/central/high range."""
    out = dict(wealth)
    components = []
    for comp in wealth.get("components") or []:
        if not isinstance(comp, Mapping):
            components.append(comp)
            continue
        row = dict(comp)
        central = row.pop("measured_rent_gbp", None)
        if central is None and "annual_rent_gbp" in row:
            central = row.pop("annual_rent_gbp", None)
        lo = row.pop("uncertainty_low", None)
        hi = row.pop("uncertainty_high", None)
        row["measured_rent_gbp"] = gbp_range(
            None if central is None else float(central),
            low=None if lo is None else float(lo),
            high=None if hi is None else float(hi),
            yield_cfg=yield_cfg,
        )
        components.append(row)
    out["components"] = components

    totals: dict[str, Any] = {}
    for tier, block in (wealth.get("totals_by_tier") or {}).items():
        if not isinstance(block, Mapping):
            totals[tier] = block
            continue
        b = dict(block)
        totals[tier] = {
            **{k: v for k, v in b.items() if k not in {"total_gbp", "low_gbp", "high_gbp"}},
            "measured_rent_gbp": gbp_range(
                b.get("total_gbp"),
                low=b.get("low_gbp"),
                high=b.get("high_gbp"),
                yield_cfg=yield_cfg,
            ),
        }
    out["totals_by_tier"] = totals

    for nest_key in ("attribution", "policy"):
        nested = wealth.get(nest_key)
        if not isinstance(nested, Mapping):
            continue
        cleaned: dict[str, Any] = {}
        for k, v in nested.items():
            if k in _SINGLE_GBP_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool):
                cleaned[k] = gbp_range(float(v), yield_cfg=yield_cfg)
            else:
                cleaned[k] = v
        out[nest_key] = cleaned
    return out


def blocked_wealth_place(
    *,
    lat: float,
    lng: float,
    zone: Mapping[str, Any],
    wealth: Mapping[str, Any],
    yield_cfg: Mapping[str, Any] | None = None,
    estimate_label: str | None = None,
    value_tier: str | None = None,
) -> dict[str, Any]:
    """Internal place page: Wealth Engine at Data Zone, blocked; yield from surface.yaml."""
    ycfg = dict(yield_cfg) if yield_cfg is not None else internal_yield_from_surface()
    ranged = wealth_to_ranges(wealth, yield_cfg=ycfg)
    body: dict[str, Any] = {
        "internal": True,
        "unpublished": True,
        "publication_status": "blocked",
        "unpublished_reason": UNPUBLISHED_REASON,
        "note": UNPUBLISHED_NOTE,
        "source": "wealth_engine",
        "geometry_level": "zone",
        "lat": lat,
        "lng": lng,
        "zone": dict(zone),
        "wealth": ranged,
        "yield": ycfg,
        "status": "research_estimate",
    }
    if estimate_label is not None:
        body["estimate_label"] = estimate_label
    return stamp_experimental(body, value_tier=value_tier)
