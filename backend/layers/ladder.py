"""Places ladder: DZ2022 containment checks and committed nest report.

A Data Zone is *crossed* by a feature when the intersection area sits strictly
between the tolerance bands around empty and full coverage:

    tol_m * perimeter(dz) < area(dz ∩ f) < area(dz) - tol_m * perimeter(dz)

``nests: true`` means zero crossings against the DZ2022 frame.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from layers.registry.loader import LayerEntry, load_registry

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPO_ROOT / "data" / "processed" / "gis" / "ladder_report.json"
EXTENT_PATH = REPO_ROOT / "data" / "processed" / "gis" / "scotland_extent.27700.geojson"

# SRC-B-SETTLEMENTS: offline EPSG:27700 GeoJSON pin (outSR=27700).
SETTLEMENTS_2022_SHA256 = (
    "b35e990b14ca07650a08a6991f64bac87a74412a9c6d351a66aa05c017995689"
)
# Crossings computed once against DZ2022 at 1 m; nests stays false.
PINNED_LADDER_LAYERS: dict[str, dict[str, Any]] = {
    "settlements-2022": {
        "ladder_level": "settlement",
        "nests": False,
        "crossings": 277,
    },
}


class LadderError(Exception):
    """Raised when a nests claim or report pin fails."""


def check_nesting(
    features: Sequence[BaseGeometry],
    dz: Sequence[BaseGeometry],
    tol_m: float = 1.0,
) -> list[int]:
    """Return indices of DZ polygons crossed by any feature.

    ``tol_m`` is metres when geometries are in a projected CRS (EPSG:27700).
    """
    if not dz:
        return []
    feat_list = [g for g in features if g is not None and not g.is_empty]
    if not feat_list:
        return []
    tree = STRtree(feat_list)
    crossed: list[int] = []
    for index, zone in enumerate(dz):
        if zone is None or zone.is_empty:
            continue
        zone_area = float(zone.area)
        band = float(tol_m) * float(zone.length)
        if zone_area <= 0 or band < 0:
            continue
        # shapely 2 STRtree.query returns ndarray of indices into feat_list
        hits = tree.query(zone)
        for hit in hits:
            feat = feat_list[int(hit)]
            inter = float(zone.intersection(feat).area)
            if band < inter < (zone_area - band):
                crossed.append(index)
                break
    return crossed


def assert_nests(
    layer_id: str,
    features: Sequence[BaseGeometry],
    dz: Sequence[BaseGeometry],
    *,
    nests: bool,
    tol_m: float = 1.0,
) -> int:
    """Raise if ``nests`` claim disagrees with ``check_nesting``."""
    crossed = check_nesting(features, dz, tol_m=tol_m)
    n = len(crossed)
    if nests and n:
        raise LadderError(
            f"ladder: layer {layer_id!r} marked nests: true but crosses "
            f"{n} dz2022 zones"
        )
    return n


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_dz2022(shp_zip: Path) -> tuple[list[BaseGeometry], str]:
    import fiona

    sha = _sha256_file(shp_zip)
    # Find the .shp member
    import zipfile

    with zipfile.ZipFile(shp_zip) as zf:
        shp_names = [n for n in zf.namelist() if n.lower().endswith(".shp")]
        if not shp_names:
            raise LadderError("ladder: DZ2022 zip has no .shp")
        shp_member = shp_names[0]
    path = f"/vsizip/{shp_zip.as_posix()}/{shp_member}"
    geoms: list[BaseGeometry] = []
    with fiona.open(path) as src:
        for feature in src:
            geoms.append(shape(feature["geometry"]))
    return geoms, sha


def _load_councils_27700(bdline_zip: Path) -> tuple[list[BaseGeometry], str]:
    import fiona

    sha = _sha256_file(bdline_zip)
    path = f"/vsizip/{bdline_zip.as_posix()}/Data/bdline_gb.gpkg"
    geoms: list[BaseGeometry] = []
    with fiona.open(path, layer="district_borough_unitary") as src:
        for feature in src:
            props = dict(feature["properties"] or {})
            code = str(props.get("Census_Code") or "")
            if not code.startswith("S12"):
                continue
            geoms.append(shape(feature["geometry"]))
    return geoms, sha


def _load_extent_land(path: Path) -> list[BaseGeometry]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[BaseGeometry] = []
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        if props.get("zone") == "land":
            out.append(shape(feature["geometry"]))
        elif not props.get("zone"):
            out.append(shape(feature["geometry"]))
    if not out:
        # Whole collection is the extent
        out = [shape(f["geometry"]) for f in payload.get("features") or []]
    return out


def _ladder_entries(entries: dict[str, LayerEntry]) -> dict[str, LayerEntry]:
    out: dict[str, LayerEntry] = {}
    for eid, entry in entries.items():
        raw = entry.raw
        if raw.get("geometry") != "polygon":
            continue
        if "ladder_level" not in raw or "nests" not in raw:
            continue
        out[eid] = entry
    return out


def build_report(
    *,
    dz_zip: Path,
    bdline_zip: Path,
    extent_path: Path = EXTENT_PATH,
    registry_dir: Path | None = None,
    tol_m: float = 1.0,
) -> dict[str, Any]:
    """Compute nests flags for every registry polygon layer with ladder fields."""
    entries = _ladder_entries(load_registry(registry_dir))
    dz_geoms, dz_sha = _load_dz2022(dz_zip)
    extent_geoms = _load_extent_land(extent_path)
    extent_sha = _sha256_file(extent_path)
    council_geoms, bl_sha = _load_councils_27700(bdline_zip)

    layer_geoms: dict[str, list[BaseGeometry]] = {
        "dz2022": dz_geoms,
        "scotland-extent": extent_geoms,
        "councils": council_geoms,
    }

    layers_out: dict[str, Any] = {}
    for eid, entry in sorted(entries.items()):
        if eid in PINNED_LADDER_LAYERS:
            pinned = dict(PINNED_LADDER_LAYERS[eid])
            # Keep ladder_level from registry when present.
            pinned["ladder_level"] = entry.raw["ladder_level"]
            layers_out[eid] = pinned
            continue
        geoms = layer_geoms.get(eid)
        if geoms is None:
            raise LadderError(f"ladder: no geometry source for registry layer {eid!r}")
        crossed = check_nesting(geoms, dz_geoms, tol_m=tol_m)
        nests = len(crossed) == 0
        layers_out[eid] = {
            "ladder_level": entry.raw["ladder_level"],
            "nests": nests,
            "crossings": len(crossed),
        }

    return {
        "tol_m": tol_m,
        "layers": layers_out,
        "inputs": {
            "dz2022_sha256": dz_sha,
            "scotland_extent_sha256": extent_sha,
            "os_boundary_line_sha256": bl_sha,
            "settlements_2022_sha256": SETTLEMENTS_2022_SHA256,
        },
    }


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def load_report(path: Path = REPORT_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_registry_matches_report(
    *,
    registry_dir: Path | None = None,
    report_path: Path = REPORT_PATH,
) -> None:
    """CI pin: each registry ``nests`` equals the committed report."""
    report = load_report(report_path)
    layers = report.get("layers") or {}
    entries = _ladder_entries(load_registry(registry_dir))
    for eid, entry in sorted(entries.items()):
        if eid not in layers:
            raise LadderError(f"ladder report missing layer {eid!r}")
        reported = bool(layers[eid]["nests"])
        claimed = bool(entry.raw["nests"])
        if claimed != reported:
            raise LadderError(
                f"ladder report mismatch for {eid!r}: registry nests="
                f"{str(claimed).lower()}, report={str(reported).lower()}"
            )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="store_true",
        help=f"Write {REPORT_PATH.relative_to(REPO_ROOT)}",
    )
    parser.add_argument(
        "--dz-zip",
        type=Path,
        help="SG DataZoneBdry 2022 shapefile zip",
    )
    parser.add_argument(
        "--bdline-zip",
        type=Path,
        help="OS Boundary-Line GeoPackage zip (SRC-A pin)",
    )
    parser.add_argument(
        "--tol-m",
        type=float,
        default=1.0,
        help="Crossing tolerance in metres (default 1.0)",
    )
    args = parser.parse_args(argv)
    if not args.report:
        parser.error("pass --report")
    if args.dz_zip is None or args.bdline_zip is None:
        parser.error("--report requires --dz-zip and --bdline-zip")
    report = build_report(
        dz_zip=args.dz_zip,
        bdline_zip=args.bdline_zip,
        tol_m=args.tol_m,
    )
    path = write_report(report)
    print(json.dumps({"wrote": str(path), "layers": report["layers"]}, indent=2))


if __name__ == "__main__":
    main()
