"""Provisional Georgist yield band for INTERNAL AGR / residual rents.

v3 (result hash 4654e513) supersedes v2 (b3442d47). Public publication stays
blocked. Surface Rent (la-calc) is a separate lens — see data/config/surface.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


# Georgist INTERNAL provisional sign-off v3 (carry in config / PR / responses).
YIELD_VERSION = 3
YIELD_RESULT_HASH = "4654e513"
YIELD_SUPERSEDES_HASH = "b3442d47"  # v2
YIELD_CENTRAL = 0.04499  # central_at_cap (4.5% cap)
YIELD_BAND_LOW = 0.0398
YIELD_BAND_HIGH = 0.0450  # band_clipped_outer at the 4.5% cap
YIELD_HIGH_CLIPPED_AT_CAP = True
# Calibration QA counts (document; fill of 727 stays with PR #18).
FALLBACK_RENT_ZONE_COUNT = 390
MODEL_FILL_ZONE_COUNT_KEEP_NULL = 727


@dataclass(frozen=True)
class YieldBand:
    """Configured land-yield band for rentalising residual site capital."""

    central: float
    low: float
    high: float
    high_clipped_at_cap: bool
    result_hash: str
    version: int
    central_at_cap: bool
    band_clipped_outer: bool
    bed_mapping_sensitive: bool
    value_basis: str
    publication_status: str
    fallback_rent_zone_count: int
    model_fill_zone_count_keep_null: int
    supersedes_hash: str = YIELD_SUPERSEDES_HASH


def _calibration_block(config: Mapping[str, Any]) -> Mapping[str, Any]:
    return config.get("yield_calibration") or {}


def yield_band_from_config(config: Mapping[str, Any]) -> YieldBand:
    """Read valuer_roll yield + yield_calibration sign-off from agr.yaml."""
    valuer = config.get("valuer_roll") or {}
    valuation = config.get("valuation") or {}
    calib = _calibration_block(config)
    band = valuer.get("yield_band") or calib.get("band") or {}
    flags = calib.get("flags") or {}

    central = float(valuer.get("yield_rate", valuation.get("yield_rate", YIELD_CENTRAL)))
    low = float(band.get("low", YIELD_BAND_LOW))
    high = float(band.get("high", YIELD_BAND_HIGH))
    clipped = bool(band.get("high_clipped_at_cap", YIELD_HIGH_CLIPPED_AT_CAP))
    result_hash = str(calib.get("result_hash") or YIELD_RESULT_HASH)
    fallback = calib.get("fallback_rent_zones") or {}
    model_fill = calib.get("model_fill_zones") or {}

    return YieldBand(
        central=central,
        low=low,
        high=high,
        high_clipped_at_cap=clipped,
        result_hash=result_hash,
        version=int(calib.get("version", YIELD_VERSION)),
        central_at_cap=bool(flags.get("central_at_cap", True)),
        band_clipped_outer=bool(flags.get("band_clipped_outer", True)),
        bed_mapping_sensitive=bool(flags.get("bed_mapping_sensitive", True)),
        value_basis=str(flags.get("value_basis") or "proxy"),
        publication_status=str(calib.get("publication_status") or "blocked"),
        fallback_rent_zone_count=int(
            fallback.get("count", FALLBACK_RENT_ZONE_COUNT)
        ),
        model_fill_zone_count_keep_null=int(
            model_fill.get("count", MODEL_FILL_ZONE_COUNT_KEEP_NULL)
        ),
        supersedes_hash=str(calib.get("supersedes_hash") or YIELD_SUPERSEDES_HASH),
    )


def scale_rent(central_rent: float | None, band: YieldBand) -> tuple[float | None, float | None]:
    """Map a rent computed at central yield onto the configured yield band."""
    if central_rent is None:
        return None, None
    if band.central <= 0:
        raise ValueError("central yield must be positive")
    factor_lo = band.low / band.central
    factor_hi = band.high / band.central
    return round(central_rent * factor_lo, 2), round(central_rent * factor_hi, 2)


def yield_signoff_payload(band: YieldBand) -> dict[str, Any]:
    """INTERNAL metadata for API responses / diagnostics."""
    return {
        "status": "internal_provisional",
        "version": band.version,
        "publication_status": band.publication_status,
        "result_hash": band.result_hash,
        "supersedes_hash": band.supersedes_hash,
        "yield_land": band.central,
        "yield_band": {
            "low": band.low,
            "high": band.high,
            "high_clipped_at_cap": band.high_clipped_at_cap,
        },
        "flags": {
            "central_at_cap": band.central_at_cap,
            "band_clipped_outer": band.band_clipped_outer,
            "bed_mapping_sensitive": band.bed_mapping_sensitive,
            "value_basis": band.value_basis,
        },
        "value_basis": band.value_basis,
        "bed_mapping_sensitive": band.bed_mapping_sensitive,
        "central_at_cap": band.central_at_cap,
        "band_clipped_outer": band.band_clipped_outer,
        "fallback_rent_zones": {
            "count": band.fallback_rent_zone_count,
            "tag": "yield_fallback:config",
        },
        "model_fill_zones": {
            "count": band.model_fill_zone_count_keep_null,
            "keep_null": True,
            "note": "Do not fill here; owned by PR #18 / separate work.",
        },
        "rent_display": "band",
        "note": (
            f"Georgist yield calibration v{band.version} for INTERNAL use only "
            f"(hash {band.result_hash}; supersedes {band.supersedes_hash}). "
            "Rents shown as a band; publication_status=blocked."
        ),
    }
