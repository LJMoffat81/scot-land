"""SVDLS site valuation — ECONOMIC_RULES §7 (best permitted use − remediation).

Room rules (follow-up to the SVDLS map layer):

1. Value each site at **best permitted use minus remediation cost**, never £0
   for hectares that remain on the SVDLS layer after overlap handling.
2. Where a site overlaps housing land supply, **HLS owns the overlap**;
   SVDLS values only the non-overlap hectares (``excl_hls`` /
   ``ha_register_excl_hls_dup``).

Data-zone join (for zone rent and rollups — not reimplemented here):

* GIS footprint allocation writes ``data/processed/gis/dz_svdls_rollup.csv``
  keyed ``(code, vintage)`` with ``crosswalk_method=footprint_area``
  (``etl/gis/build_svdls_hls.py``; code ranges checked in ``etl/gis/zone_rules.py``).
* Runtime zone identity uses ``georgist.dz_lookup.require_vintage`` /
  ``vintage_for_code`` (integer 2011|2022 only).

Live map geometry still requests ArcGIS ``outSR=4326`` (see ``layers.vdl``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from paths import CONFIG_DIR

CONFIG_PATH = CONFIG_DIR / "svdls_valuation.yaml"

# Coarse previous-use → config bucket (SVDLS register / Spatial Hub strings).
_PREVIOUS_USE_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("agriculture", ("agricultur", "farm", "horticultur", "forestry", "woodland")),
    ("residential", ("resident", "housing", "dwelling")),
    ("manufacturing", ("manufactur", "industrial", "factory", "works", "warehouse")),
    ("mineral", ("mineral", "quarry", "mine", "coal")),
    ("landfill", ("landfill", "waste", "tip")),
    ("utilities", ("utilit", "gas", "electric", "water", "sewage", "rail", "transport")),
    ("commercial", ("commercial", "retail", "office", "hotel", "leisure")),
)


@dataclass(frozen=True)
class HectareSplit:
    """HLS owns overlap; SVDLS values only ``svdls_ha``."""

    ha_register: float
    ha_dup_hls: float
    svdls_ha: float
    hls_owned_ha: float

    @property
    def fully_owned_by_hls(self) -> bool:
        return self.ha_register > 0 and self.svdls_ha <= 0


@dataclass(frozen=True)
class SiteValuation:
    """Annual rent for the SVDLS share of a site (research estimate)."""

    annual_rent_gbp: float
    best_permitted_gbp: float
    remediation_gbp: float
    valued_ha: float
    hls_owned_ha: float
    use_basis: str
    previous_use_bucket: str
    flags: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "annual_rent_gbp": self.annual_rent_gbp,
            "best_permitted_gbp": self.best_permitted_gbp,
            "remediation_gbp": self.remediation_gbp,
            "valued_ha": self.valued_ha,
            "hls_owned_ha": self.hls_owned_ha,
            "use_basis": self.use_basis,
            "previous_use_bucket": self.previous_use_bucket,
            "flags": list(self.flags),
            "notes": list(self.notes),
            "disclaimer": (
                "Research estimate. Best permitted use minus remediation. "
                "Not an official valuation or tax bill."
            ),
        }


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or CONFIG_PATH
    with cfg_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"svdls valuation config must be a mapping: {cfg_path}")
    return data


def previous_use_bucket(previous_use: str | None) -> str:
    """Map a free-text SVDLS previous-use string to a remediation bucket."""
    if previous_use is None or str(previous_use).strip() == "":
        return "unknown"
    text = str(previous_use).strip().lower()
    for bucket, needles in _PREVIOUS_USE_BUCKETS:
        if any(n in text for n in needles):
            return bucket
    return "unknown"


def remediation_capital_per_ha(
    previous_use: str | None,
    config: Mapping[str, Any] | None = None,
) -> float:
    cfg = config or load_config()
    table = cfg.get("remediation_gbp_per_ha_capital") or {}
    by_use = table.get("by_previous_use") or {}
    bucket = previous_use_bucket(previous_use)
    raw = by_use.get(bucket, table.get("default", 0))
    return max(0.0, float(raw))


def annual_remediation_per_ha(
    previous_use: str | None,
    config: Mapping[str, Any] | None = None,
) -> float:
    """Capital remediation × land_yield → £/ha/year (same unit as rent)."""
    cfg = config or load_config()
    yield_rate = float(cfg.get("land_yield") or 0.05)
    if yield_rate <= 0:
        raise ValueError("land_yield must be positive")
    return remediation_capital_per_ha(previous_use, cfg) * yield_rate


def split_hectares_hls_owns_overlap(
    ha_register: float,
    ha_dup_hls: float = 0.0,
) -> HectareSplit:
    """Housing land owns the overlap; SVDLS keeps only excl_hls hectares."""
    register = max(0.0, float(ha_register))
    overlap = max(0.0, min(float(ha_dup_hls), register))
    svdls_ha = register - overlap
    return HectareSplit(
        ha_register=register,
        ha_dup_hls=overlap,
        svdls_ha=svdls_ha,
        hls_owned_ha=overlap,
    )


def value_svdls_site(
    *,
    ha_register: float,
    rent_per_ha_gbp: float,
    ha_dup_hls: float = 0.0,
    previous_use: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> SiteValuation:
    """Best permitted use − remediation on SVDLS-owned hectares; never £0 when ha > 0.

    ``rent_per_ha_gbp`` is the caller's zone (or site-context) best-permitted
    annual rent per hectare — not invented here. Overlap hectares are excluded
    so HLS can value them once.
    """
    cfg = dict(config or load_config())
    split = split_hectares_hls_owns_overlap(ha_register, ha_dup_hls)
    bucket = previous_use_bucket(previous_use)
    use_basis = str(cfg.get("use_basis") or "best_permitted_use")
    flags: list[str] = []
    notes: list[str] = [
        "Best permitted use minus remediation (ECONOMIC_RULES §7).",
        "HLS owns SVDLS∩housing-land overlap; SVDLS values excl_hls only.",
    ]

    if split.fully_owned_by_hls:
        flags.append("fully_owned_by_hls")
        notes.append("All register hectares overlap HLS — valued on the housing land layer.")
        return SiteValuation(
            annual_rent_gbp=0.0,
            best_permitted_gbp=0.0,
            remediation_gbp=0.0,
            valued_ha=0.0,
            hls_owned_ha=split.hls_owned_ha,
            use_basis=use_basis,
            previous_use_bucket=bucket,
            flags=tuple(flags),
            notes=tuple(notes),
        )

    if split.svdls_ha <= 0:
        # No register land — nothing to value (missing site, not the idle-land trap).
        flags.append("no_register_hectares")
        return SiteValuation(
            annual_rent_gbp=0.0,
            best_permitted_gbp=0.0,
            remediation_gbp=0.0,
            valued_ha=0.0,
            hls_owned_ha=split.hls_owned_ha,
            use_basis=use_basis,
            previous_use_bucket=bucket,
            flags=tuple(flags),
            notes=tuple(notes),
        )

    rent_per_ha = float(rent_per_ha_gbp)
    if rent_per_ha < 0:
        raise ValueError("rent_per_ha_gbp must be >= 0")
    if rent_per_ha == 0:
        flags.append("zone_rent_missing")
        notes.append("Caller supplied £0/ha zone rent — flagged; never treat as idle £0 without review.")

    rem_per_ha = annual_remediation_per_ha(previous_use, cfg)
    best = split.svdls_ha * rent_per_ha
    remediation = split.svdls_ha * rem_per_ha
    raw = best - remediation

    never_zero = cfg.get("never_zero") or {}
    floor_per_ha = float(never_zero.get("minimum_rent_gbp_per_ha_year") or 1.0)
    floor = split.svdls_ha * floor_per_ha
    floor_flag = str(never_zero.get("flag") or "remediation_floor_applied")

    if raw < floor:
        annual = floor
        flags.append(floor_flag)
        notes.append(
            f"Net rent floored to {floor_per_ha:g} £/ha/year so SVDLS land is never published as £0."
        )
    else:
        annual = raw

    if split.hls_owned_ha > 0:
        flags.append("hls_owns_overlap")

    # Guaranteed: valued hectares on this layer never publish as zero.
    if split.svdls_ha > 0 and annual <= 0:
        annual = floor
        if floor_flag not in flags:
            flags.append(floor_flag)

    return SiteValuation(
        annual_rent_gbp=round(annual, 2),
        best_permitted_gbp=round(best, 2),
        remediation_gbp=round(remediation, 2),
        valued_ha=round(split.svdls_ha, 6),
        hls_owned_ha=round(split.hls_owned_ha, 6),
        use_basis=use_basis,
        previous_use_bucket=bucket,
        flags=tuple(flags),
        notes=tuple(notes),
    )


def value_hls_overlap_handoff(
    *,
    ha_dup_hls: float,
    rent_per_ha_gbp: float,
    previous_use: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> SiteValuation:
    """Value the overlap hectares for the housing land layer (HLS owns them).

    Same best-use − remediation formula; caller attributes the result to HLS,
    not SVDLS, so the overlap is never double-counted.
    """
    cfg = dict(config or load_config())
    overlap = max(0.0, float(ha_dup_hls))
    # Treat as a pure HLS parcel: no further SVDLS/HLS split.
    return value_svdls_site(
        ha_register=overlap,
        ha_dup_hls=0.0,
        rent_per_ha_gbp=rent_per_ha_gbp,
        previous_use=previous_use,
        config=cfg,
    )
