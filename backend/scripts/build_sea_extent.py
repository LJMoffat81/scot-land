#!/usr/bin/env python3
"""Build the Scotland land and seas context boundaries (SEA-EXTENT-1 PR-1).

Fetches three open inputs, dissolves them, and writes static GeoJSON.
Nothing here is a value, a rent, or a tax figure. Hydrographic Office
products are not fetched.

Inputs (Open Government Licence v3):
  * OS Boundary-Line country_region, Scotland, mean high water
  * Scottish Marine Regions (Marine_Scotland_FishDAC_1609), 11 areas
  * Scottish and offshore marine regions
    (data.gov.uk 750aafeb-1653-4661-be35-c95f7da308bc)

Outputs (EPSG:4326) under data/static/sea_extent/:
  land.geojson, inshore_12nm.geojson, scottish_waters.geojson, manifest.json

inshore_12nm is the dissolved Scottish Marine Regions. Its outer edge is
the 12 nautical mile line, including the 1999 Adjacent Waters line.
scottish_waters is the dissolved Scottish and offshore marine regions.

Geometries are dissolved and simplified by 50 m in EPSG:27700. That
simplify alone is several megabytes. The same spec caps each file at
300 KB and the three GeoJSON files at 500 KB, so coordinates are then
snapped to a 1 800 m grid in EPSG:27700 (the finest grid, on a 200 m
step, that met both caps and the published point checks) and simplified
by 50 m again.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import ssl
import sys
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import shapefile
import shapely
from pyproj import Transformer
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform, unary_union

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "data" / "static" / "sea_extent"
DEFAULT_CACHE = REPO_ROOT / "data" / "cache" / "sea_extent"

OGL_V3 = "OGL v3"
OGL_V3_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
OS_ATTRIBUTION = "Contains OS data © Crown copyright and database right 2026"
SG_ATTRIBUTION = (
    "Contains information from the Scottish Government "
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
OMR_DATA_GOV = (
    "https://www.data.gov.uk/dataset/750aafeb-1653-4661-be35-c95f7da308bc/"
    "area-management-scottish-assessment-areas-scottish-marine-regions-"
    "and-offshore-marine-regions"
)
SECTIGO_DV_R36 = "http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt"
USER_AGENT = "scot-land-sea-extent/1.0"

SIMPLIFY_M = 50
VERTEX_GRID_M = 1800
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


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def ssl_context(cache: Path) -> ssl.SSLContext:
    """System trust store plus the public Sectigo intermediate.

    The Marine Scotland feature service omits that intermediate, so a
    default handshake cannot build the chain. The intermediate is the
    public AIA certificate, not a private authority.
    """
    pem_path = cache / "sectigo-public-server-auth-dv-r36.pem"
    if not pem_path.exists():
        request = urllib.request.Request(SECTIGO_DV_R36, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
        if b"BEGIN CERTIFICATE" in body:
            pem = body
        else:
            pem = ssl.DER_cert_to_PEM_cert(body).encode("ascii")
        pem_path.write_bytes(pem)
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(pem_path))
    return context


def fetch_bytes(url: str, cache: Path) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300, context=ssl_context(cache)) as response:
        return response.read()


def cached_download(url: str, dest: Path, cache: Path, reuse: bool) -> tuple[bytes, str]:
    if reuse and dest.exists() and dest.stat().st_size > 0:
        data = dest.read_bytes()
        fetched = datetime.fromtimestamp(dest.stat().st_mtime, timezone.utc).date().isoformat()
        return data, fetched
    data = fetch_bytes(url, cache)
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
        if piece.geom_type == "Polygon":
            if piece.area > 0:
                parts.append(piece)
        elif piece.geom_type == "MultiPolygon":
            for child in piece.geoms:
                take(child)
        elif piece.geom_type == "GeometryCollection":
            for child in piece.geoms:
                take(child)

    take(geometry)
    if not parts:
        raise RuntimeError("generalised geometry has no polygons")
    if len(parts) == 1:
        return parts[0]
    return shapely.MultiPolygon(parts)


def snap_grid(geometry, grid_m: float):
    def quantise(x, y, z=None):
        return (round(x / grid_m) * grid_m, round(y / grid_m) * grid_m)

    return shapely.make_valid(transform(quantise, geometry))


def generalise(geometries):
    """Dissolve, simplify ~50 m, snap to the size-cap grid, simplify 50 m."""
    dissolved = unary_union(geometries)
    simplified = dissolved.simplify(SIMPLIFY_M, preserve_topology=True)
    snapped = snap_grid(simplified, VERTEX_GRID_M)
    return polygonal(snapped.simplify(SIMPLIFY_M, preserve_topology=True))


def to_wgs_feature(geometry, name: str) -> dict:
    def round_xy(x, y, z=None):
        return (round(float(x), COORD_DECIMALS), round(float(y), COORD_DECIMALS))

    projected = transform(TO_WGS.transform, geometry)
    rounded = polygonal(transform(round_xy, projected))
    return {
        "type": "Feature",
        "properties": {"name": name},
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


def build(cache: Path, out: Path, reuse: bool) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    os_zip, os_fetched = cached_download(
        OS_DOWNLOAD, cache / "os_boundary_line.zip", cache, reuse
    )
    smr_xml = fetch_bytes(SMR_RECORD, cache).decode("utf-8", errors="replace")
    omr_xml = fetch_bytes(OMR_RECORD, cache).decode("utf-8", errors="replace")
    smr_url = shape_zip_url(smr_xml, "nmpwfs:administrative_units_scottish_marine_regions")
    omr_url = shape_zip_url(
        omr_xml, "nmpwfs:area_management_scottish_assessment_areas_marine_regions"
    )
    smr_zip, smr_fetched = cached_download(smr_url, cache / "scottish_marine_regions.zip", cache, reuse)
    omr_zip, omr_fetched = cached_download(
        omr_url, cache / "scottish_offshore_marine_regions.zip", cache, reuse
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
    land_bng = generalise(land_parts)
    inshore_bng = generalise([transform(TO_BNG.transform, part) for part in smr_parts])
    waters_bng = generalise([transform(TO_BNG.transform, part) for part in omr_parts])

    land_feature = to_wgs_feature(land_bng, "Scotland")
    inshore_feature = to_wgs_feature(inshore_bng, "Scottish marine regions")
    waters_feature = to_wgs_feature(waters_bng, "Scottish waters")
    land = shape(land_feature["geometry"])
    inshore = shape(inshore_feature["geometry"])
    waters = shape(waters_feature["geometry"])
    assert_geography(land, inshore, waters)

    outputs = {
        "land.geojson": (
            feature_collection(land_feature),
            [OS_ATTRIBUTION],
        ),
        "inshore_12nm.geojson": (
            feature_collection(inshore_feature),
            [OS_ATTRIBUTION, SG_ATTRIBUTION],
        ),
        "scottish_waters.geojson": (
            feature_collection(waters_feature),
            [OS_ATTRIBUTION, SG_ATTRIBUTION],
        ),
    }
    written = {name: write_json(out / name, payload) for name, (payload, _credit) in outputs.items()}
    sizes = {name: len(data) for name, data in written.items()}
    if any(size > MAX_FILE_BYTES for size in sizes.values()):
        raise RuntimeError(f"a GeoJSON file exceeds 300 KB: {sizes}")
    if sum(sizes.values()) > MAX_TOTAL_BYTES:
        raise RuntimeError(f"GeoJSON total exceeds 500 KB: {sizes}")

    manifest = {
        "name": "sea_extent",
        "fetch_date": max(os_fetched, smr_fetched, omr_fetched),
        "licence": OGL_V3,
        "licence_url": OGL_V3_URL,
        "crs": "EPSG:4326",
        "simplify_m": SIMPLIFY_M,
        "vertex_grid_m": VERTEX_GRID_M,
        "attribution": [OS_ATTRIBUTION, SG_ATTRIBUTION],
        "inputs": [
            {
                "id": "os_boundary_line_country_region",
                "source_url": OS_DOWNLOAD,
                "fetch_date": os_fetched,
                "licence": OGL_V3,
                "sha256": sha256_bytes(os_zip),
                "attribution": OS_ATTRIBUTION,
                "note": "OS Boundary-Line country_region, Scotland, mean high water",
            },
            {
                "id": "scottish_marine_regions",
                "dataset_id": "Marine_Scotland_FishDAC_1609",
                "source_url": "https://spatialdata.gov.scot/geonetwork/srv/api/records/Marine_Scotland_FishDAC_1609",
                "fetch_date": smr_fetched,
                "licence": OGL_V3,
                "sha256": sha256_bytes(smr_zip),
                "attribution": SG_ATTRIBUTION,
                "note": "11 Scottish Marine Regions; outer edge is the 12 nautical mile line",
            },
            {
                "id": "scottish_offshore_marine_regions",
                "dataset_id": "750aafeb-1653-4661-be35-c95f7da308bc",
                "source_url": OMR_DATA_GOV,
                "fetch_date": omr_fetched,
                "licence": OGL_V3,
                "sha256": sha256_bytes(omr_zip),
                "attribution": SG_ATTRIBUTION,
                "note": "Scottish marine regions and offshore marine regions",
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
    parser.add_argument(
        "--reuse-cache",
        action="store_true",
        help="Reuse zip files already in the cache instead of downloading them again",
    )
    args = parser.parse_args(argv)
    build(args.cache, args.out, args.reuse_cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
