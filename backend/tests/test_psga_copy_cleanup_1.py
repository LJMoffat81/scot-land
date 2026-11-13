"""PSGA-COPY-CLEANUP-1 — "roadmap only" wording for HLS / LDP must not come back.

hls-open is live (North Lanarkshire excluded) and ldp-highland is live for
Highland only (PLANNING-PUBLISH-1). Mutation: restore the old catalog note
"SSDI PSGA restriction — flagged OFF; roadmap only (1a)." → C1 fails.
"""
from __future__ import annotations

import re
from pathlib import Path

from layers.layers_add_catalog import layers_add_entries, waiting_for_permission_rows

REPO = Path(__file__).resolve().parents[2]
_ROADMAP_ONLY = re.compile(r"roadmap[\s-]+only", re.IGNORECASE)
_PLANNING_IDS = ("ldp_allocations", "housing_land_supply")
# Backend/docs sites that describe the HLS / LDP layers.
_COPY_SITES = (
    REPO / "backend" / "layers" / "layers_add_catalog.py",
    REPO / "backend" / "layers" / "platform.py",
    REPO / "backend" / "layers" / "ldp.py",
    REPO / "backend" / "layers" / "hla.py",
    REPO / "docs" / "mintlify" / "map-layer-guide.mdx",
    REPO / "docs" / "mintlify" / "api-reference.mdx",
    REPO / "docs" / "DATA_ACQUISITION.md",
    REPO / "docs" / "DATA_LICENSING.md",
)


def test_c1_catalog_rows_never_say_roadmap_only():
    rows = {r["layer_id"]: r for r in layers_add_entries()}
    for layer_id in _PLANNING_IDS:
        row = rows[layer_id]
        for field in ("title", "note", "licence", "caption"):
            text = str(row.get(field) or "")
            assert not _ROADMAP_ONLY.search(text), f"{layer_id}.{field}: {text}"


def test_c2_copy_sites_never_say_roadmap_only():
    for path in _COPY_SITES:
        text = path.read_text(encoding="utf-8")
        hit = _ROADMAP_ONLY.search(text)
        assert hit is None, f"{path.relative_to(REPO)}: {hit.group(0) if hit else ''}"


def test_c3_waiting_rows_do_not_say_waiting_for_live_layers():
    for row in waiting_for_permission_rows():
        if row["layer_id"] == "housing_land_supply":
            # PL 18:15 GMT: the live HLS row can never say "Waiting for permission".
            assert "waiting for permission" not in row["status_label"].lower()
            assert "waiting for permission" not in row["status_label_short"].lower()
            assert "waiting" not in row["status_label"].lower()
            assert "waiting" not in row["status_label_short"].lower()
            assert row["status_label"] == "On the map from open data. North Lanarkshire is not shown."
        if row["layer_id"] == "ldp_allocations":
            assert row["status_label"].startswith("On the map for Highland only.")
