"""PLANNING-PUBLISH-1: per-authority publish allow-list for registry layers.

Every check raises ``RegistryError`` with a ``REGISTRY:`` message (load time) or
returns the filtered features plus counts (ingest time). Fail closed: a feature
whose authority is missing, blank, excluded or not allow-listed never reaches
the stage table.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping

from layers.registry.loader import RegistryError

# Layers that must carry a publish block (PL ruling 13 Nov 2026).
PUBLISH_REQUIRED: frozenset[str] = frozenset({"hls-open", "ldp-highland"})
# Authorities that must be excluded, per layer (PL ruling 13 Nov 2026).
HARD_EXCLUDE: Mapping[str, frozenset[str]] = {
    "hls-open": frozenset({"North Lanarkshire"}),
}
# Never-allowed sources: Spatial Hub Premium HLS and the SG ArcGIS HLS copy.
DENY_SOURCE_MARKERS: tuple[str, ...] = (
    "housing_land_supply_premium",
    "sh_hls_premium",
    "ba05ffddfe854d95b6386a7ded516e90",
)

# WUX 13 Nov 2026: a vintage may carry one {date} slot, filled at fetch from the
# ArcGIS layer's editingInfo.dataLastEditDate (epoch ms, UTC) as "6 Oct 2026".
VINTAGE_DATE_SLOT = "{date}"
VINTAGE_FALLBACK: Mapping[str, str] = {
    "ldp-highland": "Highland Council live data, last update date not given",
}
_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def format_last_edit(value: Any) -> str | None:
    """Epoch ms -> "6 Oct 2026" (UTC). None if missing, zero, negative or non-numeric."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    try:
        when = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return f"{when.day} {_MONTHS[when.month - 1]} {when.year}"


def fill_vintage(entry_id: str, template: str, last_edit: Any) -> str:
    """Fill the {date} slot, or return the layer's fixed fallback string."""
    if VINTAGE_DATE_SLOT not in template:
        return template
    day = format_last_edit(last_edit)
    if day is None:
        return VINTAGE_FALLBACK[entry_id]
    return template.replace(VINTAGE_DATE_SLOT, day)


def _public_vintage(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and "{" not in value
        and "}" not in value
        and "dataLastEditDate" not in value
    )


def _https(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("https://") and len(value) > 8


def check_publish_block(entry_id: str, data: Mapping[str, Any]) -> None:
    source = data.get("source") or {}
    urls = [("$.source.url", str(source.get("url") or ""))]
    publish = data.get("publish")
    if isinstance(publish, Mapping) and isinstance(publish.get("allow"), list):
        for i, row in enumerate(publish["allow"]):
            if isinstance(row, Mapping):
                urls.append(
                    (
                        f"$.publish.allow[{i}].licence_url",
                        str(row.get("licence_url") or ""),
                    )
                )
    for path, url in urls:
        if any(marker in url.lower() for marker in DENY_SOURCE_MARKERS):
            raise RegistryError(
                f"REGISTRY: {entry_id}: {path}: Premium or SG ArcGIS HLS copy is never allowed"
            )
    vintage = str(data.get("vintage") or "")
    if "{" in vintage or "}" in vintage:
        source_type = (data.get("source") or {}).get("type")
        if (
            vintage.count("{") != 1
            or vintage.count("}") != 1
            or VINTAGE_DATE_SLOT not in vintage
            or entry_id not in VINTAGE_FALLBACK
            or source_type != "arcgis"
        ):
            raise RegistryError(
                f"REGISTRY: {entry_id}: $.vintage: only one {{date}} slot, "
                "on an arcgis layer with a fixed fallback"
            )
    if publish is None:
        if entry_id in PUBLISH_REQUIRED:
            raise RegistryError(f"REGISTRY: {entry_id}: $.publish: required")
        return
    if not isinstance(publish, Mapping):
        raise RegistryError(f"REGISTRY: {entry_id}: $.publish: expected object")
    field = publish.get("authority_field")
    fixed = publish.get("source_authority")
    has_field = isinstance(field, str) and bool(field.strip())
    has_fixed = isinstance(fixed, str) and bool(fixed.strip())
    if has_field == has_fixed:
        raise RegistryError(
            f"REGISTRY: {entry_id}: $.publish: exactly one of authority_field or source_authority"
        )
    allow = publish.get("allow")
    if not isinstance(allow, list) or not allow:
        raise RegistryError(
            f"REGISTRY: {entry_id}: $.publish.allow: must be a non-empty list"
        )
    seen: set[str] = set()
    for i, row in enumerate(allow):
        path = f"$.publish.allow[{i}]"
        if not isinstance(row, Mapping):
            raise RegistryError(f"REGISTRY: {entry_id}: {path}: expected object")
        name = row.get("authority")
        if not isinstance(name, str) or not name.strip():
            raise RegistryError(f"REGISTRY: {entry_id}: {path}.authority: required")
        if "licence_url" not in row or row.get("licence_url") in (None, ""):
            raise RegistryError(
                f"REGISTRY: {entry_id}: {path}.licence_url: required for {name}"
            )
        if not _https(row.get("licence_url")):
            raise RegistryError(
                f"REGISTRY: {entry_id}: {path}.licence_url: must be https:// for {name}"
            )
        if name in seen:
            raise RegistryError(
                f"REGISTRY: {entry_id}: {path}.authority: duplicate {name}"
            )
        seen.add(name)
    excluded: set[str] = set()
    for i, row in enumerate(publish.get("exclude") or []):
        path = f"$.publish.exclude[{i}]"
        name = row.get("authority") if isinstance(row, Mapping) else None
        reason = row.get("reason") if isinstance(row, Mapping) else None
        if not isinstance(name, str) or not name.strip():
            raise RegistryError(f"REGISTRY: {entry_id}: {path}.authority: required")
        if not isinstance(reason, str) or not reason.strip():
            raise RegistryError(
                f"REGISTRY: {entry_id}: {path}.reason: required for {name}"
            )
        if name in seen:
            raise RegistryError(
                f"REGISTRY: {entry_id}: {path}.authority: {name} is both allowed and excluded"
            )
        excluded.add(name)
    for name in sorted(HARD_EXCLUDE.get(entry_id, frozenset())):
        if name in seen:
            raise RegistryError(
                f"REGISTRY: {entry_id}: $.publish.allow: {name} is excluded (PL 13 Nov 2026)"
            )
        if name not in excluded:
            raise RegistryError(
                f"REGISTRY: {entry_id}: $.publish.exclude: must list {name} (PL 13 Nov 2026)"
            )


def apply_publish_filter(
    entry_id: str,
    publish: Mapping[str, Any] | None,
    features: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep only features from allow-listed authorities. No publish block → unchanged.

    ``entry_id`` is the ingest layer id (the caller passes it); the keep/refuse
    decision uses the publish block alone.
    """
    if publish is None:
        return features, {}
    field = publish.get("authority_field")
    fixed = publish.get("source_authority")
    allowed = {str(row["authority"]) for row in publish["allow"]}
    excluded = {str(row["authority"]) for row in publish.get("exclude") or []}
    kept: list[dict[str, Any]] = []
    by_authority: dict[str, int] = {}
    n_excluded = 0
    n_refused = 0
    for feature in features:
        props = feature.get("properties") or {}
        raw = fixed if fixed else props.get(field)
        name = raw.strip() if isinstance(raw, str) else ""
        if name in allowed:
            kept.append(feature)
            by_authority[name] = by_authority.get(name, 0) + 1
        elif name in excluded:
            n_excluded += 1
        else:
            n_refused += 1
    return kept, {
        "kept_by_authority": dict(sorted(by_authority.items())),
        "excluded": n_excluded,
        "refused": n_refused,
    }


def publish_manifest_fields(
    raw: Mapping[str, Any], *, filled_vintage: str | None = None
) -> dict[str, Any]:
    """Extra manifest keys for layers with a publish block; {} otherwise.

    A {date} template is never published: the fetch-time filled vintage is used
    when it is clean, else the layer's fixed fallback.
    """
    publish = raw.get("publish")
    if not isinstance(publish, Mapping):
        return {}
    vintage = str(raw.get("vintage") or "")
    if VINTAGE_DATE_SLOT in vintage:
        vintage = (
            filled_vintage
            if _public_vintage(filled_vintage)
            else VINTAGE_FALLBACK[str(raw.get("id"))]
        )
    return {
        "vintage": vintage,
        "coverage": {
            "included": [
                {"authority": row["authority"], "licence_url": row["licence_url"]}
                for row in publish.get("allow") or []
            ],
            "excluded": [
                {"authority": row["authority"], "reason": row["reason"]}
                for row in publish.get("exclude") or []
            ],
        },
    }
