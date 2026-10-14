"""Experimental label + market/proxy/shadow tags for AGR / Wealth Engine responses.

Kept out of api/main.py so publication status messaging lives with the AGR
router modules. Every JSON response from those surfaces should carry the
experimental label; rent-bearing payloads also expose the three value-tier tags.
"""

from __future__ import annotations

from typing import Any, Mapping

EXPERIMENTAL_LABEL = "experimental"
EXPERIMENTAL_STATUS = "experimental_research_estimate"
DISCLAIMER = "Experimental research estimate. Not an official valuation or tax bill."
VALUE_TIER_TAGS: tuple[str, str, str] = ("market", "proxy", "shadow")

# Health / router status copy for the mounted internal AGR router (not main.py).
AGR_INTERNAL_ROUTER_NOTE = (
    "INTERNAL Wealth Engine place + residual diagnostics; "
    "publication_status=blocked until yield calibration"
)


def experimental_fields(*, value_tier: str | None = None) -> dict[str, Any]:
    """Common labels attached to every AGR / Wealth Engine JSON body."""
    body: dict[str, Any] = {
        "label": EXPERIMENTAL_LABEL,
        "estimate_status": EXPERIMENTAL_STATUS,
        "disclaimer": DISCLAIMER,
        "value_tier_tags": list(VALUE_TIER_TAGS),
    }
    if value_tier is not None:
        if value_tier not in VALUE_TIER_TAGS:
            raise ValueError(f"bad value_tier {value_tier!r}")
        body["value_tier"] = value_tier
    return body


def stamp_experimental(
    payload: Mapping[str, Any] | dict[str, Any],
    *,
    value_tier: str | None = None,
) -> dict[str, Any]:
    """Return a shallow copy of payload with experimental + tier tags applied."""
    body = dict(payload)
    body.update(experimental_fields(value_tier=value_tier))
    return body
