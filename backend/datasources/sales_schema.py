"""Canonical sales transaction schema for Scot-LAND assessments.

Designed for Registers of Scotland (and other *licensed*) extracts.
Not for scraped portal listings.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Literal


SourceSystem = Literal[
    "ros",
    "licensed_partner",
    "fixture_synthetic",
    "unknown",
]

LicenceCode = Literal[
    "OGL-3.0",
    "ROS-research",
    "ROS-commercial",
    "partner-licence",
    "synthetic-test-only",
    "unknown",
]


@dataclass(frozen=True)
class SalesProvenance:
    source_system: SourceSystem
    licence: LicenceCode
    retrieved_at: str  # ISO date or datetime
    source_record_id: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_synthetic(self) -> bool:
        return self.licence == "synthetic-test-only" or self.source_system == "fixture_synthetic"

    def is_production_eligible(self) -> bool:
        """Synthetic data must never feed public 'real market' claims."""
        return not self.is_synthetic() and self.licence not in ("unknown",)


@dataclass(frozen=True)
class SalesTransaction:
    """One completed property transaction (arms-length preferred)."""

    transaction_id: str
    price_gbp: int
    transfer_date: str  # ISO date YYYY-MM-DD
    lat: float | None
    lng: float | None
    postcode: str | None
    property_type: str | None  # e.g. D/S/T/F or free text
    new_build: bool | None
    floor_area_sqm: float | None
    plot_area_sqm: float | None
    tenure: str | None
    council_code: str | None
    provenance: SalesProvenance
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> SalesTransaction:
        prov = payload.get("provenance") or {}
        provenance = SalesProvenance(
            source_system=prov.get("source_system", "unknown"),
            licence=prov.get("licence", "unknown"),
            retrieved_at=prov.get("retrieved_at", ""),
            source_record_id=prov.get("source_record_id"),
            notes=prov.get("notes"),
        )
        return SalesTransaction(
            transaction_id=str(payload["transaction_id"]),
            price_gbp=int(payload["price_gbp"]),
            transfer_date=str(payload["transfer_date"]),
            lat=float(payload["lat"]) if payload.get("lat") is not None else None,
            lng=float(payload["lng"]) if payload.get("lng") is not None else None,
            postcode=payload.get("postcode"),
            property_type=payload.get("property_type"),
            new_build=payload.get("new_build"),
            floor_area_sqm=(
                float(payload["floor_area_sqm"])
                if payload.get("floor_area_sqm") is not None
                else None
            ),
            plot_area_sqm=(
                float(payload["plot_area_sqm"])
                if payload.get("plot_area_sqm") is not None
                else None
            ),
            tenure=payload.get("tenure"),
            council_code=payload.get("council_code"),
            provenance=provenance,
            raw=dict(payload.get("raw") or {}),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.price_gbp <= 0:
            errors.append("price_gbp must be positive")
        try:
            date.fromisoformat(self.transfer_date[:10])
        except ValueError:
            errors.append("transfer_date must be ISO date")
        if self.lat is None and not self.postcode:
            errors.append("require lat/lng or postcode")
        if not self.provenance.retrieved_at:
            errors.append("provenance.retrieved_at required")
        if self.provenance.licence == "unknown":
            errors.append("provenance.licence must not be unknown for ingest")
        return errors
