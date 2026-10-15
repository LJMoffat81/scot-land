"""GBP-LIVE-V1 — public £ surface rent display behind one config flag (default OFF).

Reads ``data/config/gbp_live.yaml``. When disabled, place card / legend / How it
works stay pre-£ (existing publishable guards). When enabled, Data Zone surface
rent may show a low–central–high range and an estimate label; zones listed in
``under_review_zones`` show under-review with no £. Placeholders never show £.
Totals stay off; nothing finer than Data Zone.
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

UNDER_REVIEW_LABEL = "Under review"
EARLY_ESTIMATES_BANNER = "Early estimates; ranges are wide and will change."
# Yield high of the signed-off band (surface.yaml) — visitor wording uses "up to".
YIELD_UP_TO_PCT = 4.50


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


def yield_up_to_wording(pct: float = YIELD_UP_TO_PCT) -> str:
    """Visitor yield line — always 'up to' (never a bare central %)."""
    rendered = f"{pct:.2f}".rstrip("0").rstrip(".")
    return f"up to {rendered}%"


def _money_fields(row: Mapping[str, Any]) -> dict[str, float] | None:
    """Return low/central/high when all three are finite numbers; else None."""
    try:
        low = float(row["uncertainty_low"])
        central = float(row["measured_rent"])
        high = float(row["uncertainty_high"])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(map(_finite, (low, central, high))):
        return None
    return {"low": low, "central": central, "high": high}


def _finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


def surface_rent_display_for_row(
    row: Mapping[str, Any] | None,
    *,
    code: str | None,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Build the public place-card surface_rent_display block.

    States:
      - under_review: zone in config list — label only, no £
      - hidden: placeholder / not publishable / missing money — no £
      - ok: low/central/high + estimate label (flag must already be on)
    """
    if is_under_review(code, path):
        return {
            "state": "under_review",
            "label": UNDER_REVIEW_LABEL,
            "estimate_label": None,
            "low": None,
            "central": None,
            "high": None,
            "yield_wording": None,
        }
    if row is None or not publicly_served(row):
        return {
            "state": "hidden",
            "label": None,
            "estimate_label": None,
            "low": None,
            "central": None,
            "high": None,
            "yield_wording": None,
        }
    if row.get("quality") == "placeholder":
        return {
            "state": "hidden",
            "label": None,
            "estimate_label": None,
            "low": None,
            "central": None,
            "high": None,
            "yield_wording": None,
        }
    money = _money_fields(row)
    if money is None:
        return {
            "state": "hidden",
            "label": None,
            "estimate_label": None,
            "low": None,
            "central": None,
            "high": None,
            "yield_wording": None,
        }
    machine = resolve_estimate_label(row)
    return {
        "state": "ok",
        "label": None,
        "estimate_label": visitor_estimate_label(machine),
        "estimate_label_key": machine,
        "low": money["low"],
        "central": money["central"],
        "high": money["high"],
        "yield_wording": yield_up_to_wording(),
        "grain": "data_zone",
    }


def public_settings(path: Path | str | None = None) -> dict[str, Any]:
    """Minimal public settings for frontend shells (no zone list required)."""
    cfg = load_gbp_live_config(path)
    return {
        "enabled": bool(cfg["enabled"]),
        "banner": EARLY_ESTIMATES_BANNER if cfg["enabled"] else None,
        "yield_wording": yield_up_to_wording() if cfg["enabled"] else None,
    }


_ZONE_ROW_SQL = (
    "SELECT DISTINCT ON (code) code, vintage, measured_rent, uncertainty_low, uncertainty_high, "
    "quality, publish_level, publication_status, fill_method, proxy_tags, value_tier "
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
    card["gbp_live"]["yield_wording"] = settings["yield_wording"]

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

    # Surface AGR part: under-review label only (money stays on surface_rent_display;
    # frontend formats £ so API JSON never needs a currency glyph).
    rows = card.get("agr_rows") or []
    for agr in rows:
        if agr.get("id") != "surface":
            continue
        if display["state"] == "under_review":
            agr["range"] = UNDER_REVIEW_LABEL
            agr["amount_label"] = UNDER_REVIEW_LABEL
        elif display["state"] == "ok":
            agr["estimate_label"] = display["estimate_label"]
            agr["amount_label"] = display["estimate_label"]
            agr["yield_wording"] = display["yield_wording"]
        break
    return card
