"""SVDLS site geometry precedence (Scot-LAND room decision).

When more than one geometry exists for a register site, pick in this order
(highest first) and tag the site with the chosen ``geometry_source``:

1. ``spatialhub_survey`` — Spatial Hub VDL survey polygon (includes Spatial Hub
   buffer circles drawn around the grid reference)
2. ``ros_title_outline`` — RoS INSPIRE title outline containing the register
   grid reference (internal until OS / RoS end-user terms are cleared for
   public publication)
3. ``point`` — circle at the register grid reference sized to published hectares

The live open map overlay currently serves Spatial Hub survey polygons only
and tags each feature ``spatialhub_survey``. RoS title outlines stay off the
public layer until licence clearance; the precedence rule still applies to
GIS site assembly and any future multi-source ingest.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

GEOMETRY_SOURCE_SPATIALHUB_SURVEY = "spatialhub_survey"
GEOMETRY_SOURCE_ROS_TITLE_OUTLINE = "ros_title_outline"
GEOMETRY_SOURCE_POINT = "point"

GEOMETRY_PRECEDENCE: tuple[str, ...] = (
    GEOMETRY_SOURCE_SPATIALHUB_SURVEY,
    GEOMETRY_SOURCE_ROS_TITLE_OUTLINE,
    GEOMETRY_SOURCE_POINT,
)

# Fine GIS pipeline tags (build_svdls_hls / README_svdls_hls) → room tags.
GIS_PROVENANCE_TO_SOURCE: dict[str, str] = {
    "spatialhub_polygon": GEOMETRY_SOURCE_SPATIALHUB_SURVEY,
    "spatialhub_buffer": GEOMETRY_SOURCE_SPATIALHUB_SURVEY,
    "ros_inspire_outline": GEOMETRY_SOURCE_ROS_TITLE_OUTLINE,
    "point_sized": GEOMETRY_SOURCE_POINT,
}

# Open-layer publication: RoS title outlines remain internal until cleared.
PUBLIC_GEOMETRY_SOURCES: frozenset[str] = frozenset(
    {
        GEOMETRY_SOURCE_SPATIALHUB_SURVEY,
        GEOMETRY_SOURCE_POINT,
    }
)

GEOMETRY_SOURCE_LABELS: dict[str, str] = {
    GEOMETRY_SOURCE_SPATIALHUB_SURVEY: "Spatial Hub survey",
    GEOMETRY_SOURCE_ROS_TITLE_OUTLINE: "RoS title outline",
    GEOMETRY_SOURCE_POINT: "Point (register hectares)",
}


def normalize_geometry_source(raw: str | None) -> str | None:
    """Map a GIS provenance tag or room tag to a room ``geometry_source``."""
    if raw is None or raw == "":
        return None
    if raw in GEOMETRY_PRECEDENCE:
        return raw
    return GIS_PROVENANCE_TO_SOURCE.get(raw)


def pick_geometry_source(available: Iterable[str | None]) -> str | None:
    """Return the highest-precedence geometry source present in ``available``."""
    present = {normalize_geometry_source(item) for item in available}
    present.discard(None)
    for source in GEOMETRY_PRECEDENCE:
        if source in present:
            return source
    return None


def resolve_site_geometry(
    candidates: Mapping[str, Any],
) -> tuple[Any, str] | tuple[None, None]:
    """Pick geometry by room precedence.

    ``candidates`` maps a geometry_source (or GIS provenance alias) to a
    geometry object. Empty / None values are ignored. Returns
    ``(geometry, geometry_source)`` or ``(None, None)`` when nothing usable.
    """
    usable: dict[str, Any] = {}
    for key, geom in candidates.items():
        source = normalize_geometry_source(key)
        if source is None or geom is None:
            continue
        # Keep the first candidate for a source; precedence chooses among sources.
        usable.setdefault(source, geom)
    chosen = pick_geometry_source(usable.keys())
    if chosen is None:
        return None, None
    return usable[chosen], chosen


def is_public_geometry_source(source: str | None) -> bool:
    """Whether the chosen source may appear on the open public VDL layer."""
    return normalize_geometry_source(source) in PUBLIC_GEOMETRY_SOURCES
