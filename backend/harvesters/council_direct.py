"""Council-direct ArcGIS items for LAYERS-ADD-2.

Reads licenseInfo from item metadata before any feature is kept. No form
posting and no network calls live in this module: the caller supplies the
metadata it has already fetched.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def licence_status_from_license_info(license_info: str | None) -> str:
    """Map an ArcGIS licenseInfo string onto a catalog status."""
    text = (license_info or "").strip().lower()
    if "all rights reserved" in text or "no reuse" in text:
        return "prohibited"
    if "open government licence" in text:
        return "ogl"
    return "open_other"


def latest_vintage(features: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Keep only the newest vintage. Older vintages must not be summed."""
    if not features:
        return []
    newest = max(str(feature["vintage"]) for feature in features)
    return [feature for feature in features if str(feature["vintage"]) == newest]


def ingest_council_features(
    metadata: Mapping[str, Any],
    features: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Load features only after licenseInfo is read. Prohibited items stay empty."""
    status = licence_status_from_license_info(metadata.get("licenseInfo"))
    if status == "prohibited":
        return {"loaded": False, "licence_status": status, "features": []}
    kept = latest_vintage(features)
    return {"loaded": True, "licence_status": status, "features": kept}
