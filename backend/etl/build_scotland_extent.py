"""Build data/processed/gis/scotland_extent.27700.geojson (offline; never in CI).

Land: 32 councils from maps.gov.scot AdministrativeElectoral/2.
Sea: NMPi WFS assessment areas (11 SMR + 10 OMR) plus SMR name list.

Token: env NMPI_WFS_TOKEN only. Never defaulted, never logged in clear.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import certifi
import httpx
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union
from shapely.validation import make_valid

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "processed" / "gis" / "scotland_extent.27700.geojson"
MANIFEST_PATH = REPO_ROOT / "data" / "processed" / "gis" / "manifest.csv"
DOCS_MANIFEST = REPO_ROOT / "docs" / "processed_data_manifest.md"
EXTRA_CA = (
    Path(__file__).resolve().parent.parent
    / "certs"
    / "sectigo-public-server-auth-ca-dv-r36.pem"
)

COUNCILS_URL = (
    "https://maps.gov.scot/server/rest/services/ScotGov/AdministrativeElectoral/"
    "MapServer/2/query"
)
DZ2011_URL = (
    "https://maps.gov.scot/server/rest/services/ScotGov/StatisticalUnits/"
    "MapServer/2/query"
)
NMPI_WFS = "https://msmap1.atkinsgeospatial.com/geoserver/nmpwfs/ows"
AREAS_TYPE = "nmpwfs:area_management_scottish_assessment_areas_marine_regions"
SMR_TYPE = "nmpwfs:administrative_units_scottish_marine_regions"

MARINE_ATTR = (
    "Contains information from the Scottish Government (Marine Scotland) "
    "licensed under the Open Government Licence v3.0."
)
LAND_ATTR = (
    "Copyright Scottish Government, contains Ordnance Survey data "
    "© Crown copyright and database right 2026."
)

_TOKEN_RE = re.compile(r"(token=)[^&\s]+", re.IGNORECASE)
_to_bng = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)


def redact_url(url: str) -> str:
    """Replace token=… with token=*** in any logged or receipt URL."""
    return _TOKEN_RE.sub(r"\1***", url)


def _ssl_verify() -> str:
    """certifi roots plus the Sectigo R36 intermediate (host omits it)."""
    if not EXTRA_CA.is_file():
        print(f"EXTENT: missing CA file {EXTRA_CA}", file=sys.stderr)
        sys.exit(2)
    bundle = Path("/tmp/scot_land_nmpi_ca_bundle.pem")
    bundle.write_bytes(Path(certifi.where()).read_bytes() + b"\n" + EXTRA_CA.read_bytes())
    # Prove the bundle loads; insecure TLS modes are banned.
    ssl.create_default_context(cafile=str(bundle))
    return str(bundle)


def _require_token() -> str:
    token = os.environ.get("NMPI_WFS_TOKEN")
    if not token:
        print("EXTENT: NMPI_WFS_TOKEN not set", file=sys.stderr)
        sys.exit(2)
    return token


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(300.0, connect=30.0),
        follow_redirects=True,
        verify=_ssl_verify(),
        headers={"User-Agent": "scot-land/extent-build"},
    )


def _arcgis_geojson(client: httpx.Client, url: str) -> list[dict]:
    features: list[dict] = []
    offset = 0
    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "f": "geojson",
            "outSR": "27700",
            "resultRecordCount": "1000",
            "resultOffset": str(offset),
        }
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("features") or []
        features.extend(batch)
        props = payload.get("properties") or {}
        exceeded = bool(payload.get("exceededTransferLimit")) or bool(
            isinstance(props, dict) and props.get("exceededTransferLimit")
        )
        if not batch or (not exceeded and len(batch) < 1000):
            break
        offset += len(batch)
    return features


def _wfs_geojson(client: httpx.Client, type_name: str, token: str) -> tuple[list[dict], str]:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": type_name,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "token": token,
    }
    # Build URL for redacted logging only.
    logged = redact_url(f"{NMPI_WFS}?{urlencode(params)}")
    response = client.get(NMPI_WFS, params=params)
    if response.status_code != 200:
        print(f"EXTENT: WFS {response.status_code} for {logged}", file=sys.stderr)
        response.raise_for_status()
    payload = response.json()
    return list(payload.get("features") or []), logged


def _to_27700(geom):
    if geom.geom_type == "GeometryCollection":
        # WFS may return 4326; reproject each part.
        pass
    return shapely_transform(_to_bng.transform, geom)


def _prepare_part(geom):
    if not geom.is_valid:
        geom = make_valid(geom)
    # Close slivers between council coast and SMR inner edge before union.
    geom = geom.buffer(1.0).buffer(-1.0)
    if not geom.is_valid:
        geom = make_valid(geom)
    return geom


def _zone_for_area(props: dict, smr_names: set[str]) -> str:
    """Map an assessment-area feature to inshore vs offshore via SMR name list."""
    name = ""
    for key in ("name", "NAME", "Name", "objnam", "area_name"):
        if props.get(key):
            name = str(props[key]).strip()
            break
    smr_lower = {n.lower() for n in smr_names}
    if name in smr_names or name.lower() in smr_lower:
        return "inshore_0_12nm"
    return "offshore_12_200nm"


def build(*, land_source: str = "councils") -> dict:
    token = _require_token()
    fetch_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _client() as client:
        if land_source == "dz2011":
            land_url = DZ2011_URL
            land_features = _arcgis_geojson(client, land_url)
            print(f"EXTENT: land source dz2011 features={len(land_features)}")
        else:
            land_url = COUNCILS_URL
            land_features = _arcgis_geojson(client, land_url)
            if len(land_features) != 32:
                print(
                    f"EXTENT: expected 32 councils, got {len(land_features)}",
                    file=sys.stderr,
                )
                sys.exit(2)
            print(f"EXTENT: councils={len(land_features)}")

        areas, areas_url = _wfs_geojson(client, AREAS_TYPE, token)
        smr, smr_url = _wfs_geojson(client, SMR_TYPE, token)
        print(f"EXTENT: assessment areas={len(areas)} url={areas_url}")
        print(f"EXTENT: SMR={len(smr)} url={smr_url}")
        if len(areas) != 21:
            print(f"EXTENT: expected 21 SMR+OMR areas, got {len(areas)}", file=sys.stderr)
            sys.exit(2)
        if len(smr) != 11:
            print(f"EXTENT: expected 11 SMR, got {len(smr)}", file=sys.stderr)
            sys.exit(2)

    smr_names: set[str] = set()
    for feature in smr:
        props = feature.get("properties") or {}
        # NMPi SMR layer uses INSPIRE objnam for the English region name.
        for key in ("objnam", "name", "NAME", "Name", "nmp_name"):
            if props.get(key):
                smr_names.add(str(props[key]).strip())
                break
    if len(smr_names) != 11:
        print(f"EXTENT: expected 11 SMR names, got {len(smr_names)}", file=sys.stderr)
        sys.exit(2)

    land_parts = []
    for feature in land_features:
        geom = shape(feature["geometry"])
        # Already in 27700 from outSR.
        land_parts.append(_prepare_part(geom))
    land_union = unary_union(land_parts)

    inshore_parts = []
    offshore_parts = []
    for feature in areas:
        props = feature.get("properties") or {}
        geom = _to_27700(shape(feature["geometry"]))
        geom = _prepare_part(geom)
        zone = _zone_for_area(props, smr_names)
        if zone == "inshore_0_12nm":
            inshore_parts.append(geom)
        else:
            offshore_parts.append(geom)

    if len(inshore_parts) != 11 or len(offshore_parts) != 10:
        print(
            f"EXTENT: zone split inshore={len(inshore_parts)} offshore={len(offshore_parts)} "
            f"(expected 11/10); smr_names={len(smr_names)}",
            file=sys.stderr,
        )
        sys.exit(2)

    inshore = unary_union(inshore_parts)
    offshore = unary_union(offshore_parts)

    def _quantize_coords(coords):
        # 1 m integer metres keep the GeoJSON under the 8 MB D1 cap.
        if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
            return [int(round(coords[0])), int(round(coords[1]))]
        return [_quantize_coords(part) for part in coords]

    def _as_polygon_geom(geom):
        """Drop non-areal parts from make_valid GeometryCollections."""
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            return geom
        if geom.geom_type == "GeometryCollection":
            polys = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
            if not polys:
                return geom
            return unary_union(polys)
        return geom

    def _quantized_mapping(geom):
        geom = _as_polygon_geom(geom)
        geo = mapping(geom)
        if "coordinates" in geo:
            geo["coordinates"] = _quantize_coords(geo["coordinates"])
            quantized = shape(geo)
            if not quantized.is_valid:
                quantized = _as_polygon_geom(make_valid(quantized))
                geo = mapping(quantized)
                if "coordinates" in geo:
                    geo["coordinates"] = _quantize_coords(geo["coordinates"])
        return geo

    features_out = []
    for zone, geom in (
        ("land", land_union),
        ("inshore_0_12nm", inshore),
        ("offshore_12_200nm", offshore),
    ):
        if not geom.is_valid:
            geom = make_valid(geom)
        simple = geom.simplify(25.0, preserve_topology=True)
        if not simple.is_valid:
            simple = make_valid(simple)
        geo = _quantized_mapping(simple)
        features_out.append(
            {
                "type": "Feature",
                "properties": {"zone": zone},
                "geometry": geo,
            }
        )

    collection = {
        "type": "FeatureCollection",
        "name": "scotland_extent",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::27700"}},
        "features": features_out,
    }

    parts_out = []
    for feature in features_out:
        part = shape(feature["geometry"])
        if not part.is_valid:
            part = make_valid(part)
        part = _as_polygon_geom(part)
        parts_out.append(part)
    total = make_valid(unary_union(parts_out))
    area_km2 = total.area / 1_000_000.0
    print(f"EXTENT: area_km2={area_km2:.1f}")
    if not (690_000.0 <= area_km2 <= 710_000.0):
        print(
            f"EXTENT: area {area_km2:.1f} km² outside 690000–710000",
            file=sys.stderr,
        )
        sys.exit(2)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(collection, separators=(",", ":"))
    OUT_PATH.write_text(body, encoding="utf-8")
    size = OUT_PATH.stat().st_size
    sha = hashlib.sha256(OUT_PATH.read_bytes()).hexdigest()
    print(f"EXTENT: wrote {OUT_PATH} bytes={size} sha256={sha}")
    if size >= 8 * 1024 * 1024:
        print("EXTENT: GeoJSON >= 8 MB; consider FlatGeobuf (D1)", file=sys.stderr)
        sys.exit(2)

    source = (
        f"land={redact_url(land_url)}; "
        f"areas={areas_url}; smr={smr_url}; fetched={fetch_time}"
    )
    attribution = f"{MARINE_ATTR} {LAND_ATTR}"
    _upsert_manifest_row(
        file_name=OUT_PATH.name,
        source=source,
        attribution=attribution,
        rows=3,
        sha256=sha,
    )
    return {
        "path": str(OUT_PATH),
        "sha256": sha,
        "bytes": size,
        "area_km2": area_km2,
        "councils": 32 if land_source == "councils" else len(land_features),
        "areas": 21,
        "smr": 11,
        "source": source,
    }


def _upsert_manifest_row(
    *,
    file_name: str,
    source: str,
    attribution: str,
    rows: int,
    sha256: str,
) -> None:
    fieldnames = [
        "file",
        "owner",
        "source",
        "licence",
        "attribution",
        "publish_level",
        "zone_vintage",
        "key",
        "rows",
        "sha256",
        "source_year",
    ]
    existing: list[dict] = []
    if MANIFEST_PATH.is_file():
        with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
            existing = list(csv.DictReader(handle))
    existing = [r for r in existing if (r.get("file") or "") != file_name]
    existing.append(
        {
            "file": file_name,
            "owner": "gis",
            "source": source,
            "licence": "OGL-3.0",
            "attribution": attribution,
            "publish_level": "public_zone",
            "zone_vintage": "2011;2022",
            "key": "(code, vintage)",
            "rows": str(rows),
            "sha256": sha256,
            "source_year": "",
        }
    )
    with MANIFEST_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--land-source",
        choices=("councils", "dz2011"),
        default="councils",
        help="councils (default, 32 LA) or dz2011 dissolve",
    )
    args = parser.parse_args(argv)
    # OS Boundary-Line country_region is documented but not used.
    result = build(land_source=args.land_source)
    print(
        "EXTENT: ok "
        f"councils={result['councils']} areas={result['areas']} smr={result['smr']} "
        f"area_km2={result['area_km2']:.1f} bytes={result['bytes']} "
        f"sha256={result['sha256']}"
    )


if __name__ == "__main__":
    main()
