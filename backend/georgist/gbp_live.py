"""GBP-LIVE — public £ surface rent display behind one config flag (default OFF).

Reads ``data/config/gbp_live.yaml``. When disabled, place card / legend / How it
works stay pre-£ (existing publishable guards). When enabled, Data Zone surface
rent is shown as £ per m² of land a year (low–central–high + estimate label);
zones listed in ``under_review_zones``, clamped residuals, or missing/invalid
land-area denominators show "estimate unavailable" with no £. Placeholders
never show £. Totals stay off; nothing finer than Data Zone.

GBP-LIVE-V1c (display layer only; surface model untouched):
  - Numerator = residential surface rent only (``uncertainty_low`` /
    ``measured_rent`` / ``uncertainty_high``). Farmland / other-land lines are
    never used.
  - Denominator = ``residential_land_ha`` (v1.3 plot-split residential land),
    never ``other_land_ha`` / whole-zone area.
  - Visitor unit label (frontend) is exact; API ``unit_wording`` carries no £.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

from georgist.surface_dz2022 import (
    ESTIMATE_FULLY,
    ESTIMATE_MEASURED,
    ESTIMATE_PARTLY,
    estimate_label_for_fill,
)
from georgist.wealth_schema import publicly_served

CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "config" / "gbp_live.yaml"

# Visitor-facing estimate labels (machine → prose).
ESTIMATE_VISITOR: dict[str, str] = {
    ESTIMATE_MEASURED: "Measured",
    ESTIMATE_PARTLY: "Partly estimated",
    ESTIMATE_FULLY: "Fully estimated",
}

# GBP-LIVE-V1c: replaces "Under review" — never show £0 for these cases.
ESTIMATE_UNAVAILABLE_LABEL = "estimate unavailable"
# Back-compat alias for imports that still name the under-review path.
UNDER_REVIEW_LABEL = ESTIMATE_UNAVAILABLE_LABEL

EARLY_ESTIMATES_BANNER = "Early estimates; ranges are wide and will change."
# Signed-off visitor rent-rate lines (Scot-LAND) — never the banned word "yield".
RENT_RATE_WORDING_CARD = "Yearly rent: up to 4.5% of the land's value"
RENT_RATE_WORDING_HOW_IT_WORKS = (
    "We turn land value into a yearly rent of up to 4.5% of that value."
)
# API unit strings carry no £ glyph; frontend formats the exact on-screen label.
UNIT = "per m²"
# Prose without £ — frontend prepends £ for the signed-off screen label.
UNIT_WORDING = "per square metre of land, per year"
CENTRAL_LABEL = "most likely"

# Residential surface-rent numerator (zone £/year). Never farmland / other-land.
NUMERATOR_LOW_FIELD = "uncertainty_low"
NUMERATOR_CENTRAL_FIELD = "measured_rent"
NUMERATOR_HIGH_FIELD = "uncertainty_high"
NUMERATOR_FIELDS = (
    NUMERATOR_LOW_FIELD,
    NUMERATOR_CENTRAL_FIELD,
    NUMERATOR_HIGH_FIELD,
)
# v1.3 plot-split residential land (hectares). Never other_land_ha / zone_ha.
AREA_FIELD = "residential_land_ha"
EXCLUDED_AREA_FIELDS = ("other_land_ha", "zone_ha", "farmland_ha", "settlement_area_ha")
HA_TO_M2 = 10_000


class GbpLiveConfigError(ValueError):
    pass


@lru_cache(maxsize=4)
def _load_raw(path_str: str) -> dict[str, Any]:
    path = Path(path_str)
    if not path.is_file():
        return {"enabled": False, "under_review_zones": []}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    block = data.get("gbp_live") if isinstance(data, Mapping) else None
    if block is None and isinstance(data, Mapping):
        block = data
    if not isinstance(block, Mapping):
        raise GbpLiveConfigError("gbp_live config must be a mapping")
    enabled = bool(block.get("enabled", False))
    raw_zones = block.get("under_review_zones") or []
    if not isinstance(raw_zones, (list, tuple)):
        raise GbpLiveConfigError("gbp_live.under_review_zones must be a list")
    zones = tuple(str(z).strip() for z in raw_zones if str(z).strip())
    return {"enabled": enabled, "under_review_zones": zones}


def clear_gbp_live_cache() -> None:
    """Test helper — drop cached config after monkeypatching the path or file."""
    _load_raw.cache_clear()


def load_gbp_live_config(path: Path | str | None = None) -> dict[str, Any]:
    """Return ``{enabled: bool, under_review_zones: tuple[str, ...]}``."""
    return dict(_load_raw(str(path or CONFIG_PATH)))


def gbp_live_enabled(path: Path | str | None = None) -> bool:
    return bool(load_gbp_live_config(path)["enabled"])


def under_review_zones(path: Path | str | None = None) -> frozenset[str]:
    return frozenset(load_gbp_live_config(path)["under_review_zones"])


def is_under_review(code: str | None, path: Path | str | None = None) -> bool:
    if not code:
        return False
    return str(code).strip() in under_review_zones(path)


def resolve_estimate_label(row: Mapping[str, Any]) -> str:
    """Machine estimate_label from row, proxy_tags, or fill_method."""
    raw = row.get("estimate_label")
    if isinstance(raw, str) and raw.strip() in ESTIMATE_VISITOR:
        return raw.strip()
    tags = row.get("proxy_tags") or ()
    for tag in tags:
        text = str(tag)
        if text.startswith("estimate_label="):
            value = text.split("=", 1)[1].strip()
            if value in ESTIMATE_VISITOR:
                return value
    return estimate_label_for_fill(row.get("fill_method"))


def visitor_estimate_label(machine: str) -> str:
    return ESTIMATE_VISITOR.get(machine, ESTIMATE_VISITOR[ESTIMATE_FULLY])


def rent_rate_wording_card() -> str:
    """Place-card rent-rate line (signed off; no 'yield')."""
    return RENT_RATE_WORDING_CARD


def rent_rate_wording_how_it_works() -> str:
    """How it works rent-rate line (signed off; no 'yield')."""
    return RENT_RATE_WORDING_HOW_IT_WORKS


def _money_fields(row: Mapping[str, Any]) -> dict[str, float] | None:
    """Return low/central/high residential surface rent when all three are finite."""
    try:
        low = float(row[NUMERATOR_LOW_FIELD])
        central = float(row[NUMERATOR_CENTRAL_FIELD])
        high = float(row[NUMERATOR_HIGH_FIELD])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(map(_finite, (low, central, high))):
        return None
    return {"low": low, "central": central, "high": high}


def _finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


def _area_ha(row: Mapping[str, Any]) -> float | None:
    """Positive ``residential_land_ha`` (v1.3 plot-split residential), or None.

    Never falls back to ``other_land_ha`` / farmland / whole-zone area.
    """
    raw = row.get(AREA_FIELD)
    if raw is None or raw == "":
        return None
    try:
        ha = float(raw)
    except (TypeError, ValueError):
        return None
    if not _finite(ha) or ha <= 0:
        return None
    return ha


def _is_clamped(row: Mapping[str, Any], money: Mapping[str, float]) -> bool:
    """Negative residual floored to zero — never publish £0 behind the flag."""
    if bool(row.get("negative_residual")):
        return True
    if money["central"] <= 0 or money["low"] < 0 or money["high"] < 0:
        return True
    return False


def _per_m2(zone_rent: float, area_ha: float) -> float:
    """Zone £/year → £ per m² of land a year (display only; full precision)."""
    return zone_rent / (area_ha * HA_TO_M2)


def _unavailable_payload() -> dict[str, Any]:
    return {
        "state": "under_review",
        "label": ESTIMATE_UNAVAILABLE_LABEL,
        "estimate_label": None,
        "low": None,
        "central": None,
        "high": None,
        "rent_rate_wording": None,
        "unit": None,
        "unit_wording": None,
        "central_label": None,
    }


def _hidden_payload() -> dict[str, Any]:
    return {
        "state": "hidden",
        "label": None,
        "estimate_label": None,
        "low": None,
        "central": None,
        "high": None,
        "rent_rate_wording": None,
        "unit": None,
        "unit_wording": None,
        "central_label": None,
    }


def surface_rent_display_for_row(
    row: Mapping[str, Any] | None,
    *,
    code: str | None,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Build the public place-card surface_rent_display block.

    States:
      - under_review: config list, clamped, or invalid area — label only, no £
      - hidden: placeholder / not publishable / missing money — no £
      - ok: low/central/high as £ per m² + estimate label (flag must already be on)
    """
    if is_under_review(code, path):
        return _unavailable_payload()
    if row is None or not publicly_served(row):
        return _hidden_payload()
    if row.get("quality") == "placeholder":
        return _hidden_payload()
    money = _money_fields(row)
    if money is None:
        return _hidden_payload()
    if _is_clamped(row, money):
        return _unavailable_payload()
    area_ha = _area_ha(row)
    if area_ha is None:
        # Missing / zero / negative residential_land_ha → estimate unavailable.
        return _unavailable_payload()
    machine = resolve_estimate_label(row)
    return {
        "state": "ok",
        "label": None,
        "estimate_label": visitor_estimate_label(machine),
        "estimate_label_key": machine,
        "low": _per_m2(money["low"], area_ha),
        "central": _per_m2(money["central"], area_ha),
        "high": _per_m2(money["high"], area_ha),
        "rent_rate_wording": rent_rate_wording_card(),
        "unit": UNIT,
        "unit_wording": UNIT_WORDING,
        "central_label": CENTRAL_LABEL,
        "numerator": NUMERATOR_CENTRAL_FIELD,
        "numerator_fields": list(NUMERATOR_FIELDS),
        "denominator": AREA_FIELD,
        "grain": "data_zone",
    }


def public_settings(path: Path | str | None = None) -> dict[str, Any]:
    """Minimal public settings for frontend shells (no zone list required)."""
    cfg = load_gbp_live_config(path)
    enabled = bool(cfg["enabled"])
    return {
        "enabled": enabled,
        "banner": EARLY_ESTIMATES_BANNER if enabled else None,
        "rent_rate_wording": (
            rent_rate_wording_how_it_works() if enabled else None
        ),
        "unit": UNIT if enabled else None,
        "unit_wording": UNIT_WORDING if enabled else None,
    }


_ZONE_ROW_SQL = (
    "SELECT DISTINCT ON (code) code, vintage, measured_rent, uncertainty_low, uncertainty_high, "
    "residential_land_ha, quality, publish_level, publication_status, fill_method, proxy_tags, "
    "value_tier, negative_residual "
    "FROM surface_rent_dz WHERE code = %s AND vintage = %s "
    "ORDER BY code, valuation_date DESC"
)


def fetch_surface_rent_row(code: str, vintage: int) -> dict[str, Any] | None:
    """Latest surface_rent_dz row for a Data Zone, or None if DB unavailable / missing."""
    from georgist import db

    try:
        with db.cursor() as cur:
            cur.execute(_ZONE_ROW_SQL, (code, vintage))
            row = cur.fetchone()
    except db.DatabaseUnavailable:
        return None
    except Exception:
        return None
    return dict(row) if row else None


def surface_rent_display_for_zone(
    code: str | None,
    vintage: int | None,
    *,
    path: Path | str | None = None,
    row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve display for one Data Zone (optional preloaded row for tests)."""
    if is_under_review(code, path):
        return surface_rent_display_for_row(None, code=code, path=path)
    loaded = row
    if loaded is None and code and vintage in (2011, 2022):
        loaded = fetch_surface_rent_row(str(code), int(vintage))
    return surface_rent_display_for_row(loaded, code=code, path=path)


def attach_gbp_live_to_place_card(
    card: dict[str, Any],
    *,
    path: Path | str | None = None,
    row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Mutate/return place card with gbp_live settings + surface_rent_display when enabled.

    When the flag is OFF, only ``gbp_live.enabled: false`` is attached — no money
    fields, no £ characters — so existing publishable guards stay green.
    """
    settings = public_settings(path)
    card["gbp_live"] = {"enabled": settings["enabled"]}
    if not settings["enabled"]:
        return card

    card["gbp_live"]["banner"] = settings["banner"]
    card["gbp_live"]["rent_rate_wording"] = settings["rent_rate_wording"]
    card["gbp_live"]["unit"] = settings["unit"]
    card["gbp_live"]["unit_wording"] = settings["unit_wording"]

    zone = card.get("data_zone") or {}
    # Prefer the card's preferred vintage/code (DZ2022 when present).
    code = zone.get("code")
    vintage = zone.get("vintage")
    zones = zone.get("zones") or []
    for entry in zones:
        if entry.get("vintage") == 2022 and entry.get("code"):
            code = entry["code"]
            vintage = 2022
            break

    display = surface_rent_display_for_zone(code, vintage, path=path, row=row)
    card["surface_rent_display"] = display

    # Surface AGR part: unavailable label only (money stays on surface_rent_display;
    # frontend formats £ so API JSON never needs a currency glyph).
    rows = card.get("agr_rows") or []
    for agr in rows:
        if agr.get("id") != "surface":
            continue
        if display["state"] == "under_review":
            agr["range"] = ESTIMATE_UNAVAILABLE_LABEL
            agr["amount_label"] = ESTIMATE_UNAVAILABLE_LABEL
        elif display["state"] == "ok":
            agr["estimate_label"] = display["estimate_label"]
            agr["amount_label"] = display["estimate_label"]
            agr["rent_rate_wording"] = display["rent_rate_wording"]
        break
    return card
