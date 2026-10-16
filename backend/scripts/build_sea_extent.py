#!/usr/bin/env python3
"""Build the Scotland land and seas context boundaries (SEA-EXTENT-1 PR-1).

Fetches three open inputs, dissolves them, and writes static GeoJSON.
Nothing here is a value, a rent, or a tax figure. Hydrographic Office
products are not fetched.

Inputs (Open Government Licence v3):
  * OS Boundary-Line country_region, Scotland, mean high water
  * Scottish Marine Regions (Marine_Scotland_FishDAC_1609), 11 areas
  * Scottish and offshore marine regions
    (spatialdata record Marine_Scotland_FishDAC_12185)

Outputs (EPSG:4326) under data/static/sea_extent/:
  land.geojson, inshore_12nm.geojson, scottish_waters.geojson, manifest.json

Land is clipped out of the 12 nautical mile area. The outer limit is the
union of the offshore regions and that 12 nautical mile area. The three
pieces are polygonized so their borders are shared arcs, then simplified
together with mapshaper (Douglas-Peucker, 300 m in EPSG:27700). Parts
under 5 km² are dropped so the three GeoJSON files stay within 500 KB.
300 m is the coarsest step inside the 50–300 m band that meets that cap.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import ssl
import subprocess
import sys
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import shapefile
import shapely
from pyproj import Transformer
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import polygonize, transform, unary_union

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "data" / "static" / "sea_extent"
DEFAULT_CACHE = REPO_ROOT / "data" / "cache" / "sea_extent"
BUNDLED_SECTIGO = Path(__file__).resolve().parent / "sectigo_public_server_auth_dv_r36.pem"

OGL_V3 = "OGL v3"
OGL_V3_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
SG_ATTRIBUTION = (
    "Contains information from Scottish Government "
    "licensed under the Open Government Licence v3.0."
)

OS_DOWNLOAD = (
    "https://api.os.uk/downloads/v1/products/BoundaryLine/downloads"
    "?area=GB&format=ESRI%C2%AE+Shapefile&redirect"
)
SMR_RECORD = (
    "https://spatialdata.gov.scot/geonetwork/srv/api/records/"
    "Marine_Scotland_FishDAC_1609/formatters/xml"
)
OMR_RECORD = (
    "https://spatialdata.gov.scot/geonetwork/srv/api/records/"
    "Marine_Scotland_FishDAC_12185/formatters/xml"
)
USER_AGENT = "scot-land-sea-extent/1.0"

# Source dissolve uses 50 m so the overlay is tractable. The shared-arc
# pass below is the resolution of the published files.
PRE_SIMPLIFY_M = 50
SHARED_SIMPLIFY_M = 300
MIN_PART_M2 = 5_000_000
COORD_DECIMALS = 4
MAX_FILE_BYTES = 300_000
MAX_TOTAL_BYTES = 500_000

# Spec points. Latitude first in the brief; GeoJSON order is longitude, latitude.
EDINBURGH = Point(-3.1883, 55.9533)
CARLISLE = Point(-2.9382, 54.8951)
MINCH = Point(-6.05, 58.42)
NORTH_OF_12NM = Point(-1.0, 61.5)

TO_BNG = Transformer.from_crs(4326, 27700, always_xy=True)
TO_WGS = Transformer.from_crs(27700, 4326, always_xy=True)

SHAPE_ZIP = re.compile(
    r"https://[^\"'<\s]*outputFormat=shape-zip[^\"'<\s]*",
    re.IGNORECASE,
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def os_attribution(year: str) -> str:
    return f"Contains OS data © Crown copyright and database right {year}"


def ssl_context() -> ssl.SSLContext:
    """System trust store plus the bundled public Sectigo intermediate.

    The Marine Scotland feature service omits that intermediate, so a
    default handshake cannot build the chain. crt.sectigo.com does not
    complete a TLS handshake here, so the public intermediate is bundled
    rather than fetched.
    """
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(BUNDLED_SECTIGO))
    return context


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300, context=ssl_context()) as response:
        return response.read()


def cached_download(url: str, dest: Path, reuse: bool) -> tuple[bytes, str]:
    if reuse and dest.exists() and dest.stat().st_size > 0:
        data = dest.read_bytes()
        fetched = datetime.fromtimestamp(dest.stat().st_mtime, timezone.utc).date().isoformat()
        return data, fetched
    data = fetch_bytes(url)
    dest.write_bytes(data)
    return data, date.today().isoformat()


def shape_zip_url(record_xml: str, type_name: str) -> str:
    found = [match.replace("&amp;", "&") for match in SHAPE_ZIP.findall(record_xml)]
    # The line layer name contains the polygon type name as a prefix, so match the
    # parameter boundary rather than a substring.
    polygon = [
        url
        for url in found
        if f"typeName={type_name}&" in url or url.endswith(f"typeName={type_name}")
    ]
    if len(polygon) != 1:
        raise RuntimeError(f"expected one shape-zip link for {type_name}, found {len(polygon)}")
    return polygon[0]


def read_shapefile(path: Path):
    reader = shapefile.Reader(str(path), encoding="latin-1", encodingErrors="replace")
    try:
        return [shape(record.shape.__geo_interface__) for record in reader.iterShapeRecords()]
    finally:
        reader.close()


def scotland_land(shp_path: Path):
    reader = shapefile.Reader(str(shp_path), encoding="latin-1", encodingErrors="replace")
    try:
        parts = [
            shape(record.shape.__geo_interface__)
            for record in reader.iterShapeRecords()
            if record.record["NAME"] == "Scotland"
        ]
    finally:
        reader.close()
    if len(parts) < 100:
        raise RuntimeError(f"expected the Scotland country_region parts, found {len(parts)}")
    return parts


def extract_zip(data: bytes, dest: Path, name_contains: str | None = None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = [
            info
            for info in archive.infolist()
            if not info.is_dir() and (name_contains is None or name_contains in info.filename)
        ]
        if not members:
            raise RuntimeError(f"no zip members matching {name_contains!r}")
        archive.extractall(dest, members)


def polygonal(geometry):
    geometry = shapely.make_valid(geometry)
    parts = []

    def take(piece) -> None:
        if piece.is_empty:
            return
        if piece.geom_type == "Polygon" and piece.area > 0:
            parts.append(piece)
        elif piece.geom_type in {"MultiPolygon", "GeometryCollection"}:
            for child in piece.geoms:
                take(child)

    take(geometry)
    if not parts:
        raise RuntimeError("geometry has no polygons")
    if len(parts) == 1:
        return parts[0]
    return shapely.MultiPolygon(parts)


def dissolve(geometries):
    return polygonal(unary_union(geometries).simplify(PRE_SIMPLIFY_M, preserve_topology=True))


def mosaic(land, inshore, offshore):
    """Node the three borders and assign each face so arcs are shared.

    Coastal gaps between land and the 12 nautical mile area are given to
    the 12 nautical mile area. Other gaps are given to the offshore part.
    """
    lines = unary_union([land.boundary, inshore.boundary, offshore.boundary])
    faces = list(polygonize(lines))
    shapely.prepare(land)
    shapely.prepare(inshore)
    shapely.prepare(offshore)
    buckets = {"land": [], "inshore": [], "offshore": [], "gap": []}
    for face in faces:
        point = face.representative_point()
        if land.covers(point):
            buckets["land"].append(face)
        elif inshore.covers(point):
            buckets["inshore"].append(face)
        elif offshore.covers(point):
            buckets["offshore"].append(face)
        else:
            buckets["gap"].append(face)
    for gap in buckets["gap"]:
        if land.intersects(gap):
            buckets["inshore"].append(gap)
        else:
            buckets["offshore"].append(gap)
    return (
        polygonal(unary_union(buckets["land"])),
        polygonal(unary_union(buckets["inshore"])),
        polygonal(unary_union(buckets["offshore"])),
    )


def find_mapshaper(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which("mapshaper")
    if found:
        return found
    raise RuntimeError("mapshaper is required (install it, or pass --mapshaper)")


def shared_simplify(land, inshore, offshore, mapshaper: str, work: Path):
    """Simplify the three layers together so shared borders stay one arc."""
    work.mkdir(parents=True, exist_ok=True)
    source = work / "mosaic.geojson"
    output = work / "mosaic_simplified.geojson"
    collection = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"layer": name}, "geometry": mapping(geometry)}
            for name, geometry in (
                ("land", land),
                ("inshore", inshore),
                ("offshore", offshore),
            )
        ],
    }
    source.write_text(json.dumps(collection, separators=(",", ":")), encoding="utf-8")
    completed = subprocess.run(
        [
            mapshaper,
            str(source),
            "-simplify",
            "dp",
            f"interval={SHARED_SIMPLIFY_M}",
            "planar",
            "-o",
            "format=geojson",
            "precision=1",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr[-2000:] or completed.stdout[-2000:])
    simplified = json.loads(output.read_text(encoding="utf-8"))
    by_layer = {
        feature["properties"]["layer"]: polygonal(shape(feature["geometry"]))
        for feature in simplified["features"]
    }
    return by_layer["land"], by_layer["inshore"], by_layer["offshore"]


def keep_large_land(land):
    kept = [part for part in _polygons(land) if part.area >= MIN_PART_M2]
    return polygonal(unary_union(kept))


def _polygons(geometry):
    geometry = shapely.make_valid(geometry)
    parts = []

    def take(piece) -> None:
        if piece.is_empty:
            return
        if piece.geom_type == "Polygon" and piece.area > 0:
            parts.append(piece)
        elif piece.geom_type in {"MultiPolygon", "GeometryCollection"}:
            for child in piece.geoms:
                take(child)

    take(geometry)
    return parts


def fill_holes_without_land(geometry, land):
    """Drop interior rings that do not sit on a kept land part."""
    shapely.prepare(land)
    cleaned = []
    for part in _polygons(geometry):
        holes = []
        for ring in part.interiors:
            hole = Polygon(ring)
            if hole.area > 0 and land.covers(hole.representative_point()):
                holes.append(ring)
        cleaned.append(Polygon(part.exterior, holes))
    return polygonal(unary_union(cleaned))


def to_wgs_feature(geometry, feature_name: str) -> dict:
    def round_xy(x, y, z=None):
        return (round(float(x), COORD_DECIMALS), round(float(y), COORD_DECIMALS))

    projected = transform(TO_WGS.transform, geometry)
    rounded = polygonal(transform(round_xy, projected))
    return {
        "type": "Feature",
        "properties": {"name": feature_name},
        "geometry": mapping(rounded),
    }


def feature_collection(feature: dict) -> dict:
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": [feature],
    }


def assert_geography(land, inshore, waters) -> None:
    if not land.contains(EDINBURGH):
        raise RuntimeError("land does not contain Edinburgh")
    if land.contains(CARLISLE):
        raise RuntimeError("land contains Carlisle")
    if not inshore.contains(MINCH):
        raise RuntimeError("inshore does not contain 58.42 N, 6.05 W")
    if inshore.contains(NORTH_OF_12NM):
        raise RuntimeError("inshore contains 61.5 N, 1.0 W")
    if not waters.contains(NORTH_OF_12NM):
        raise RuntimeError("scottish waters do not contain 61.5 N, 1.0 W")


def write_json(path: Path, payload: dict) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    data = text.encode("utf-8")
    if "£" in text:
        raise RuntimeError(f"{path.name} contains a pound sign")
    path.write_bytes(data)
    return data


def build(cache: Path, out: Path, reuse: bool, mapshaper: str) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    os_zip, os_fetched = cached_download(OS_DOWNLOAD, cache / "os_boundary_line.zip", reuse)
    smr_xml = fetch_bytes(SMR_RECORD).decode("utf-8", errors="replace")
    omr_xml = fetch_bytes(OMR_RECORD).decode("utf-8", errors="replace")
    smr_url = shape_zip_url(smr_xml, "nmpwfs:administrative_units_scottish_marine_regions")
    omr_url = shape_zip_url(
        omr_xml, "nmpwfs:area_management_scottish_assessment_areas_marine_regions"
    )
    smr_zip, smr_fetched = cached_download(smr_url, cache / "scottish_marine_regions.zip", reuse)
    omr_zip, omr_fetched = cached_download(
        omr_url, cache / "scottish_offshore_marine_regions.zip", reuse
    )

    os_dir = cache / "os_boundary_line"
    smr_dir = cache / "smr"
    omr_dir = cache / "omr"
    extract_zip(os_zip, os_dir, "country_region")
    extract_zip(smr_zip, smr_dir)
    extract_zip(omr_zip, omr_dir)

    country = next(os_dir.rglob("country_region.shp"))
    smr_shp = next(smr_dir.glob("*.shp"))
    omr_shp = next(omr_dir.glob("*.shp"))
    land_parts = scotland_land(country)
    smr_parts = read_shapefile(smr_shp)
    omr_parts = read_shapefile(omr_shp)
    if len(smr_parts) != 11:
        raise RuntimeError(f"Scottish Marine Regions must be 11 areas, found {len(smr_parts)}")
    if len(omr_parts) < 11:
        raise RuntimeError(f"expected the offshore marine regions, found {len(omr_parts)}")

    # Boundary-Line country_region is already EPSG:27700. Marine downloads are EPSG:4326.
    land_bng = dissolve(land_parts)
    smr_bng = dissolve([transform(TO_BNG.transform, part) for part in smr_parts])
    omr_bng = dissolve([transform(TO_BNG.transform, part) for part in omr_parts])
    inshore_bng = polygonal(smr_bng.difference(land_bng))
    offshore_bng = polygonal(omr_bng.difference(smr_bng))
    land_bng, inshore_bng, offshore_bng = mosaic(land_bng, inshore_bng, offshore_bng)
    land_bng, inshore_bng, offshore_bng = shared_simplify(
        land_bng, inshore_bng, offshore_bng, mapshaper, cache / "work"
    )
    land_bng = keep_large_land(land_bng)
    inshore_bng = fill_holes_without_land(inshore_bng, land_bng)
    offshore_bng = fill_holes_without_land(offshore_bng, land_bng)
    waters_bng = polygonal(unary_union([offshore_bng, inshore_bng]))
    waters_bng = fill_holes_without_land(waters_bng, land_bng)

    land_feature = to_wgs_feature(land_bng, "Scotland")
    inshore_feature = to_wgs_feature(inshore_bng, "12 nautical mile line")
    waters_feature = to_wgs_feature(waters_bng, "Scottish waters")
    land = shape(land_feature["geometry"])
    inshore = shape(inshore_feature["geometry"])
    waters = shape(waters_feature["geometry"])
    assert_geography(land, inshore, waters)

    outputs = {
        "land.geojson": (feature_collection(land_feature), [os_attribution(os_fetched[:4])]),
        "inshore_12nm.geojson": (
            feature_collection(inshore_feature),
            [os_attribution(os_fetched[:4]), SG_ATTRIBUTION],
        ),
        "scottish_waters.geojson": (
            feature_collection(waters_feature),
            [os_attribution(os_fetched[:4]), SG_ATTRIBUTION],
        ),
    }
    written = {name: write_json(out / name, payload) for name, (payload, _credit) in outputs.items()}
    sizes = {name: len(data) for name, data in written.items()}
    if any(size > MAX_FILE_BYTES for size in sizes.values()):
        raise RuntimeError(f"a GeoJSON file exceeds 300 KB: {sizes}")
    if sum(sizes.values()) > MAX_TOTAL_BYTES:
        raise RuntimeError(f"GeoJSON total exceeds 500 KB: {sizes}")

    os_credit = os_attribution(os_fetched[:4])
    manifest = {
        "name": "sea_extent",
        "fetch_date": max(os_fetched, smr_fetched, omr_fetched),
        "licence": OGL_V3,
        "licence_url": OGL_V3_URL,
        "crs": "EPSG:4326",
        "simplify_m": SHARED_SIMPLIFY_M,
        "method": "mapshaper shared-arc Douglas-Peucker",
        "min_part_m2": MIN_PART_M2,
        "attribution": [os_credit, SG_ATTRIBUTION],
        "inputs": [
            {
                "id": "os_boundary_line_country_region",
                "source_url": OS_DOWNLOAD,
                "fetch_date": os_fetched,
                "licence": OGL_V3,
                "sha256": sha256_bytes(os_zip),
                "attribution": os_credit,
                "note": "OS Boundary-Line country_region, Scotland, mean high water",
            },
            {
                "id": "scottish_marine_regions",
                "dataset_id": "Marine_Scotland_FishDAC_1609",
                "source_url": SMR_RECORD,
                "download_url": smr_url,
                "fetch_date": smr_fetched,
                "licence": OGL_V3,
                "sha256": sha256_bytes(smr_zip),
                "attribution": SG_ATTRIBUTION,
                "note": "11 Scottish Marine Regions; outer edge is the 12 nautical mile line",
            },
            {
                "id": "scottish_offshore_marine_regions",
                "dataset_id": "Marine_Scotland_FishDAC_12185",
                "source_url": OMR_RECORD,
                "download_url": omr_url,
                "fetch_date": omr_fetched,
                "licence": OGL_V3,
                "sha256": sha256_bytes(omr_zip),
                "attribution": SG_ATTRIBUTION,
                "note": "Offshore regions fetched from spatialdata record Marine_Scotland_FishDAC_12185",
            },
        ],
        "outputs": [
            {
                "file": name,
                "sha256": sha256_bytes(data),
                "bytes": len(data),
                "licence": OGL_V3,
                "attribution": outputs[name][1],
            }
            for name, data in written.items()
        ],
    }
    write_json(out / "manifest.json", manifest)
    print(json.dumps({"wrote": str(out), "bytes": sizes}, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build data/static/sea_extent boundaries")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--mapshaper", default=None, help="Path to the mapshaper executable")
    parser.add_argument(
        "--reuse-cache",
        action="store_true",
        help="Reuse zip files already in the cache instead of downloading them again",
    )
    args = parser.parse_args(argv)
    build(args.cache, args.out, args.reuse_cache, find_mapshaper(args.mapshaper))
    return 0


if __name__ == "__main__":
    sys.exit(main())
