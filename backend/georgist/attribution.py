"""Licence + attribution that public views must carry for the datasets they are built from.

Source of truth: the `attribution` column of data/processed/<dataset>/manifest.csv (with
`licence` and `publish_level` from the same row). The loader requires it for every
public_* file. There is no README scraping and no pinned copy: if the manifest row or its
attribution is missing, AttributionMissing is raised and the public endpoint answers 503
`attribution_missing` instead of serving figures without their credit.

  surface_rent  always: gis/epc_dz_rollup.csv (Valuation's rebuild mix and floor area) and
                gis/dz_detached_plot_bands.csv (estate/one-off rebuild split; RoS credit, OGL v3).
                when used: gis/dz_residential_land.csv (per residential hectare),
                datazones/dwellings_by_year.csv (per dwelling) and
                datazones/zone_spine.csv (per resident).
"""

from __future__ import annotations

import csv
import functools
from pathlib import Path
from typing import Any, Iterable

from paths import PROCESSED_DIR

EPC_ROLLUP = ("gis", "epc_dz_rollup.csv")
DZ_DWELLINGS = ("datazones", "dwellings_by_year.csv")
DZ_SPINE = ("datazones", "zone_spine.csv")
GIS_RESIDENTIAL_LAND = ("gis", "dz_residential_land.csv")
GIS_PLOT_BANDS = ("gis", "dz_detached_plot_bands.csv")  # Valuation's estate/one-off split (RoS parcels, OGL v3)

# Datasets every figure of a public layer is built from.
LAYER_DATASETS: dict[str, tuple[tuple[str, str], ...]] = {"surface_rent": (EPC_ROLLUP, GIS_PLOT_BANDS)}
# Display views -> dataset whose count they divide by (credited only when the view is shown).
VIEW_DATASETS: dict[str, tuple[str, str]] = {
    "per_residential_hectare": GIS_RESIDENTIAL_LAND,  # RoS parcel-based area (RoS/OS attribution)
    "per_dwelling": DZ_DWELLINGS,
    "per_resident": DZ_SPINE,
}
# View statuses that put a figure on screen (and so need the denominator's credit).
SHOWN_STATUSES = ("ok", "interim_rough")

NON_COMMERCIAL = "Non-commercial research use only; licence check needed before any commercial use."


class AttributionMissing(RuntimeError):
    def __init__(self, datasets: list[str], reason: str):
        self.datasets = datasets
        super().__init__(f"{', '.join(datasets)}: {reason}; refusing to serve it publicly")


@functools.lru_cache(maxsize=None)
def dataset_attribution(dataset: str, file: str, root: str | None = None) -> dict[str, Any]:
    label = f"{dataset}/{file}"
    manifest = Path(root or PROCESSED_DIR) / dataset / "manifest.csv"
    if not manifest.is_file():
        raise AttributionMissing([label], f"no {dataset}/manifest.csv")
    with open(manifest, encoding="utf-8-sig", newline="") as fh:
        row = next((r for r in csv.DictReader(fh) if (r.get("file") or "").strip() == file), None)
    if row is None:
        raise AttributionMissing([label], "not listed in its manifest")
    licence = (row.get("licence") or "").strip()
    attribution = (row.get("attribution") or "").strip()
    if not licence or not attribution:
        raise AttributionMissing([label], "manifest licence or attribution is empty")
    out = {"dataset": label, "licence": licence, "attribution": attribution,
           "publish_level": (row.get("publish_level") or "").strip(), "source": "manifest"}
    if "non-commercial" in licence.lower():
        out["use_restriction"] = NON_COMMERCIAL
    return out


def attributions_for(layer: str, views_shown: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Credits for a public layer plus the count datasets of the views actually shown."""
    datasets = list(LAYER_DATASETS.get(layer, ()))
    datasets += [VIEW_DATASETS[v] for v in dict.fromkeys(views_shown) if v in VIEW_DATASETS]
    out, missing = [], []
    for ds in datasets:
        try:
            out.append(dataset_attribution(*ds))
        except AttributionMissing as exc:
            missing += exc.datasets
    if missing:
        raise AttributionMissing(missing, "no manifest attribution")
    return out
