"""Manual-drop harvesters for Improvement Service layers (L8).

These modules must not import HTTP clients or reference Spatial Hub auth,
login pages, or click-through acceptance flows. Laurie places extracts under
data/external/<id>/.
"""

from __future__ import annotations

from harvesters.base import HarvesterResult, load_manual_drop

# Acquisition = manual_drop for all of these (LAYERS-ADD-1 + licence 1a).
MANUAL_DROP_LAYER_IDS = (
    "vdl",
    "green_belt",
    "school_catchments",
    "contaminated_land",
    "ldp_allocations",
    "housing_land_supply",
    "sepa_frm_maps",
)


def harvest(layer_id: str) -> HarvesterResult:
    if layer_id not in MANUAL_DROP_LAYER_IDS:
        raise ValueError(f"{layer_id} is not a manual_drop layer")
    if layer_id == "sepa_frm_maps":
        return HarvesterResult(
            layer_id=layer_id,
            ok=True,
            skipped=True,
            reason="prohibited — never ingested",
        )
    return load_manual_drop(layer_id)
