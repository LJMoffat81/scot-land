"""Rebuild data/processed/sg_urban_rural_2022_urban_20m.geojson from the pinned SG release.

Usage: python build_urban_rural.py <SG_UrbanRural_2022.zip> <out_dir>

Source: Scottish Government Urban Rural Classification 2022,
https://maps.gov.scot/ATOM/shapefiles/SG_UrbanRural_2022.zip (Open Government Licence v3.0).
Keeps UR6 classes 1-4 (settlements; any land outside them is countryside), simplifies each
polygon to 20 m (topology-preserving), keeps British National Grid (EPSG:27700) rounded to
whole metres. The zip and shapefile are never committed.

Needs: Python 3.11+ (tested on 3.13.5), pyshp==3.1.6, shapely==2.1.2 (pip install pyshp==3.1.6 shapely==2.1.2).
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import shapefile  # pyshp
from shapely.geometry import mapping, shape

PINNED_SHA256 = "1b18bce2d4201d5f99dfd3bdacbf9fb5bc7a966294cee94262165e2c398d85a9"
OUT_NAME = "sg_urban_rural_2022_urban_20m.geojson"
TOLERANCE_M = 20


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _round(coords):
    if isinstance(coords[0], (list, tuple)):
        return [_round(c) for c in coords]
    return [round(coords[0]), round(coords[1])]


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    zip_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    got = _sha256(zip_path)
    if got != PINNED_SHA256:
        print(f"REFUSING: zip sha256 {got} does not match pinned {PINNED_SHA256}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        shp = next(Path(tmp).rglob("SG_UrbanRural_2022.shp"))
        reader = shapefile.Reader(str(shp))
        features = []
        for rec in reader.iterShapeRecords():
            cls = int(rec.record["UR6Class"])
            if cls > 4:
                continue
            geom = shape(rec.shape.__geo_interface__).simplify(TOLERANCE_M, preserve_topology=True)
            gj = mapping(geom)
            features.append(
                {
                    "type": "Feature",
                    "properties": {"UR6Class": cls},
                    "geometry": {"type": gj["type"], "coordinates": _round(gj["coordinates"])},
                }
            )
        reader.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / OUT_NAME
    with out.open("w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, separators=(",", ":"))
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(features)} features)")
    print(f"sha256 {_sha256(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
