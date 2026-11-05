"""Ingest NatureScot Carbon and Peatland 2016 into PostGIS (carbon_peatland).

Pinned source (GPKG, not WMS/WFS):
  https://gis-downloads.nature.scot/CPM2016_SCOTLAND_GPKG_27700.zip
CRS EPSG:27700; class field IMPORTANCE. National zip stays under
data/external/ (gitignored) and is loaded on Laurie's PC. CI uses the
eight-class stub fixture.
"""

from __future__ import annotations

from pathlib import Path

TABLE = "carbon_peatland"
SOURCE_URL = "https://gis-downloads.nature.scot/CPM2016_SCOTLAND_GPKG_27700.zip"
FIELD = "IMPORTANCE"
CRS = "EPSG:27700"
FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "cpm2016_importance_stub.geojson"
)


def main() -> None:
    raise SystemExit(
        "ingest_cpm2016: national GPKG load runs on Laurie's PC "
        f"(table {TABLE}, {CRS}, field {FIELD}, {SOURCE_URL}). "
        f"CI fixture: {FIXTURE}"
    )


if __name__ == "__main__":
    main()
