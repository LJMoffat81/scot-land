"""Layer admission test (charter v2 §4, M1).

Runs on the committed registry at import (via ``registry()``) and in CI.
Every failure raises ``AdmissionError`` with an ``ADMISSION:`` message.
"""

from __future__ import annotations

from typing import Any, Mapping

from layers.registry.loader import LayerEntry, RegistryError

CONTEXT_CAP = 6
NON_COMMERCIAL_LICENCES = frozenset({"NSTA-OGL"})
SUMMING_METHODS = frozenset({"sum", "area_weighted", "pop_weighted"})
# Layers on main before M1 that may carry ``admission_gaps``. Literal ids, no
# globs; a new layer must pass the test in full.
GRANDFATHERED_GAPS = frozenset(
    {
        "councils",
        "dz2022",
        "oil-fields",
        "pipelines",
        "platforms",
        "scotland-extent",
        "settlements-2022",
    }
)
_REQUIRED = ("policy_question", "shows", "value_layer")


class AdmissionError(RegistryError):
    """Raised when a registry entry fails the charter v2 §4 admission test."""


def _gaps(raw: Mapping[str, Any]) -> set[str]:
    found: set[str] = set()
    vintage = raw.get("vintage")
    if not isinstance(vintage, str) or not vintage.strip():
        found.add("vintage")
    return found


def _check_entry(entry_id: str, raw: Mapping[str, Any]) -> None:
    for key in _REQUIRED:
        if key not in raw:
            raise AdmissionError(f"ADMISSION: {entry_id}: $.{key}: required")
    questions = raw["policy_question"]
    shows = raw["shows"]
    if shows == "context":
        if questions:
            raise AdmissionError(
                f"ADMISSION: {entry_id}: $.policy_question: must be empty for a context layer"
            )
    elif not questions:
        raise AdmissionError(
            f"ADMISSION: {entry_id}: $.policy_question: name at least one of Q1-Q6"
        )

    licence = raw.get("licence")
    non_commercial = raw.get("non_commercial", False)
    if licence in NON_COMMERCIAL_LICENCES and non_commercial is not True:
        raise AdmissionError(
            f"ADMISSION: {entry_id}: $.non_commercial: must be true for licence {licence}"
        )
    if licence not in NON_COMMERCIAL_LICENCES and non_commercial is True:
        raise AdmissionError(
            f"ADMISSION: {entry_id}: $.non_commercial: licence {licence} is not non-commercial"
        )

    value = raw["value_layer"]
    if value:
        if shows == "context":
            raise AdmissionError(
                f"ADMISSION: {entry_id}: $.value_layer: a context layer cannot be a value layer"
            )
        for key in ("net_of", "overlaps_with"):
            if key not in raw:
                raise AdmissionError(
                    f"ADMISSION: {entry_id}: $.{key}: required for a value layer"
                )
    else:
        for key in ("net_of", "overlaps_with"):
            if key in raw:
                raise AdmissionError(
                    f"ADMISSION: {entry_id}: $.{key}: only allowed on a value layer"
                )

    declared = set(raw.get("admission_gaps") or [])
    actual = _gaps(raw)
    if declared and entry_id not in GRANDFATHERED_GAPS:
        raise AdmissionError(
            f"ADMISSION: {entry_id}: $.admission_gaps: only pre-M1 layers may declare gaps"
        )
    missing = sorted(actual - declared)
    if missing:
        raise AdmissionError(
            f"ADMISSION: {entry_id}: $.{missing[0]}: required (charter v2 §4.5)"
        )
    stale = sorted(declared - actual)
    if stale:
        raise AdmissionError(
            f"ADMISSION: {entry_id}: $.admission_gaps: stale gap {stale[0]!r}"
        )


def _check_overlaps(entries: Mapping[str, LayerEntry]) -> None:
    for entry_id, entry in entries.items():
        for other in entry.raw.get("overlaps_with") or []:
            if other == entry_id:
                raise AdmissionError(
                    f"ADMISSION: {entry_id}: $.overlaps_with: lists itself"
                )
            target = entries.get(other)
            if target is None:
                raise AdmissionError(
                    f"ADMISSION: {entry_id}: $.overlaps_with: unknown layer {other}"
                )
            if not target.raw.get("value_layer"):
                raise AdmissionError(
                    f"ADMISSION: {entry_id}: $.overlaps_with: {other} is not a value layer"
                )
            if entry_id not in (target.raw.get("overlaps_with") or []):
                raise AdmissionError(
                    f"ADMISSION: {entry_id}: $.overlaps_with: {other} does not list {entry_id}"
                )


def _check_double_counting(entries: Mapping[str, LayerEntry]) -> None:
    for entry_id, entry in entries.items():
        lineage = entry.raw.get("lineage") or {}
        if lineage.get("method") not in SUMMING_METHODS:
            continue
        parents = [
            p
            for p in lineage.get("derived_from") or []
            if p in entries and entries[p].raw.get("value_layer")
        ]
        for i, a in enumerate(parents):
            for b in parents[i + 1 :]:
                if b in (entries[a].raw.get("overlaps_with") or []):
                    raise AdmissionError(
                        f"ADMISSION: {entry_id}: $.lineage.derived_from: "
                        f"sums overlapping value layers {a} + {b}"
                    )


def _check_context_cap(entries: Mapping[str, LayerEntry]) -> None:
    context = sorted(
        eid for eid, e in entries.items() if e.raw.get("shows") == "context"
    )
    if len(context) > CONTEXT_CAP:
        raise AdmissionError(
            f"ADMISSION: context layers {len(context)} > cap {CONTEXT_CAP}: "
            + ", ".join(context)
        )


def check_admission(entries: Mapping[str, LayerEntry]) -> None:
    """Apply charter v2 §4 to a loaded registry; raise on the first failure."""
    for entry_id in sorted(entries):
        _check_entry(entry_id, entries[entry_id].raw)
    _check_overlaps(entries)
    _check_double_counting(entries)
    _check_context_cap(entries)
