"""Data Zone shares from SEPA Flood Maps v3.0 medium-likelihood extents.

Reads files already downloaded under data/external/sepa_frm_v3/ (gitignored).
Uses only present-day medium-likelihood extent layers whose names contain
``extent_m`` (not ``extent_m_cc``). Rejects other names, including GeoPackage
files, which this loader does not read. Checks the licence statement in each
dataset folder and aborts unless it matches an Open Government Licence or OGL
statement with an optional "version" before 3.0.

Reprojects to EPSG:27700 using the CRS named in the file, intersects the 2022
Data Zones, and stores one row per zone: data_zone, pct_area_river,
pct_area_coastal, pct_area_surface (nearest 1%, 0 to 100), source_version.
The denominator is the full Data Zone area, land and water. No flood polygons
are stored.

  python -m etl.ingest_sepa_frm_v3 --replace
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import psycopg2
from pyproj import CRS, Transformer
from shapely import make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("ingest_sepa_frm_v3")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / "data" / "external" / "sepa_frm_v3"
TABLE = "sepa_flood_dz"
SOURCE_VERSION = "v3.0"
TARGET_EPSG = 27700
DZ2022_VINTAGE = 2022
DZ2022_COUNT = 7392
# Pinned sha256 of SG_DataZoneBdry_2022.zip (data/config/sources.yaml).
DZ2022_SHA256 = "421c648480c7d51e32934de9f1b9f6cbbf86c6d8d382aab30a7bb4d2049ef0ec"
LICENCE_RE = re.compile(
    rb"(?i)(?:open\s+government\s+licen[cs]e|\bogl\b)\s*(?:(?:version|v)\s*)?3(?:\.0)?"
)
EXTENT_M_RE = re.compile(r"extent_m(?!_cc)(?![a-z0-9])")
KINDS = ("river", "coastal", "surface")
ZONE_FILES = {"dz.geojson", "data_zones.geojson"}
TARGET_CRS = CRS.from_epsg(TARGET_EPSG)


class RejectedFloodSource(Exception):
    """File is not a present-day medium-likelihood extent."""


class LicenceError(Exception):
    """Licence statement is missing or is not an Open Government Licence 3.0 form."""


def round_percent(covered: float, total: float) -> int:
    """Nearest 1%, clamped to 0..100. Halves round away from zero."""
    if total <= 0:
        return 0
    pct = 100.0 * covered / total
    if pct < 0:
        pct = 0.0
    if pct > 100:
        pct = 100.0
    return int(math.floor(pct + 0.5))


def is_rejected_name(name: str) -> bool:
    low = name.lower()
    if "_m_cc" in low or "m_cc" in low:
        return True
    if "high-likelihood" in low or "high_likelihood" in low or "high likelihood" in low:
        return True
    if "depth" in low or "velocity" in low:
        return True
    if re.search(r"extent_h(\.|_|$)", low):
        return True
    if re.search(r"extent_l(\.|_|$)", low):
        return True
    return False


def has_extent_m(name: str) -> bool:
    """True when ``extent_m`` is present and not followed by ``_cc``."""
    return EXTENT_M_RE.search(name.lower()) is not None


def kind_from_name(name: str) -> str:
    low = name.lower()
    if "coast" in low:
        return "coastal"
    if "surface" in low:
        return "surface"
    if "river" in low:
        return "river"
    raise RejectedFloodSource(name)


def select_medium_layers(names: list[str]) -> list[tuple[str, str]]:
    """Allowlist extent_m layer names. Refuse a set with none."""
    chosen: list[tuple[str, str]] = []
    for layer_name in names:
        if is_rejected_name(layer_name) or not has_extent_m(layer_name):
            continue
        chosen.append((kind_from_name(layer_name), layer_name))
    if not chosen:
        raise RejectedFloodSource("no medium-likelihood extent_m layer")
    return chosen


def _is_zone_file(path: Path) -> bool:
    return path.name.lower() in ZONE_FILES


def _is_licence_sidecar(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() in {".txt", ".pdf", ".html", ".md"}:
        return True
    return "licen" in path.name.lower()


def iter_inputs(root: Path) -> list[Path]:
    """Data files and FileGDBs. Licence sidecars and zone outlines are separate."""
    found: list[Path] = []
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("*")):
        if path.name.startswith("."):
            continue
        if _is_zone_file(path) or _is_licence_sidecar(path):
            continue
        if path.is_dir() and path.suffix.lower() == ".gdb":
            found.append(path)
            continue
        if path.is_file() and path.suffix.lower() in {".geojson", ".json", ".zip", ".gpkg"}:
            found.append(path)
    return found


def screen_input(path: Path) -> str:
    """Return 'zip', 'gdb', or a kind. Raise when the file is not a medium extent."""
    if path.suffix.lower() == ".gpkg":
        raise RejectedFloodSource(path.name)
    if is_rejected_name(path.name):
        raise RejectedFloodSource(path.name)
    if path.suffix.lower() == ".zip":
        return "zip"
    if path.is_dir() and path.suffix.lower() == ".gdb":
        return "gdb"
    if not has_extent_m(path.name):
        raise RejectedFloodSource(path.name)
    return kind_from_name(path.name)


def assert_licence(root: Path, data_path: Path) -> None:
    """Abort unless this dataset folder's own statement matches OGL 3.0.

    A statement that only sits in ``root`` does not cover a file in a subfolder.
    """
    folder = data_path.parent
    if folder.is_dir():
        for candidate in sorted(folder.iterdir()):
            if not _is_licence_sidecar(candidate):
                continue
            if candidate.resolve() == data_path.resolve():
                continue
            if LICENCE_RE.search(candidate.read_bytes()):
                return
    raise LicenceError(
        f"{data_path.name}: licence statement in {folder} "
        f"(download root {root.name} does not count for a subfolder) must match "
        "Open Government Licence / OGL 3.0"
    )


def crs_from_geojson(payload: dict[str, Any]) -> CRS:
    """Read the CRS the file itself names. Do not infer one from coordinate size."""
    raw = payload.get("crs")
    if not isinstance(raw, dict):
        raise SystemExit(f"GeoJSON has no CRS; name EPSG:{TARGET_EPSG} or another CRS")
    props = raw.get("properties") or {}
    name = props.get("name")
    code = props.get("code")
    if name:
        return CRS.from_user_input(str(name))
    if code:
        return CRS.from_user_input(f"EPSG:{code}")
    raise SystemExit("GeoJSON CRS has no name")


def reproject_to_bng(geom: BaseGeometry, source: CRS) -> BaseGeometry:
    """Reproject to EPSG:27700 and assert that is the CRS of the result."""
    target = CRS.from_epsg(TARGET_EPSG)
    if target.to_epsg() != TARGET_EPSG:
        raise SystemExit(f"reprojection target EPSG:{target.to_epsg()} is not EPSG:27700")
    if source.to_epsg() != TARGET_EPSG:
        transformer = Transformer.from_crs(source, target, always_xy=True)
        geom = transform(transformer.transform, geom)
    out = target.to_epsg()
    if out != TARGET_EPSG:
        raise SystemExit(f"geometry CRS EPSG:{out} is not EPSG:27700")
    return geom


def _polygon_parts(geom: BaseGeometry) -> list[BaseGeometry]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [] if geom.area <= 0 else [geom]
    if isinstance(geom, MultiPolygon):
        return [part for part in geom.geoms if isinstance(part, Polygon) and part.area > 0]
    if isinstance(geom, GeometryCollection):
        parts: list[BaseGeometry] = []
        for part in geom.geoms:
            parts.extend(_polygon_parts(part))
        return parts
    return []


def prepare_polygon(geom: BaseGeometry) -> BaseGeometry | None:
    """make_valid, then keep only polygonal parts."""
    parts = _polygon_parts(make_valid(geom))
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return MultiPolygon(parts)


def _geoms_from_collection(payload: dict[str, Any]) -> list[BaseGeometry]:
    source = crs_from_geojson(payload)
    features = payload.get("features") or []
    geoms: list[BaseGeometry] = []
    for feature in features:
        raw = feature.get("geometry")
        if not raw:
            continue
        prepared = prepare_polygon(reproject_to_bng(shape(raw), source))
        if prepared is None or prepared.is_empty:
            continue
        geoms.append(prepared)
    return geoms


def read_geojson(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise SystemExit(f"{path.name}: expected a GeoJSON FeatureCollection")
    return payload


def _zone_code(props: dict[str, Any]) -> str:
    for key in ("data_zone", "code", "dz_code", "DataZone", "DZCode"):
        raw = props.get(key)
        if raw:
            return str(raw).strip()
    raise SystemExit("Data Zone feature is missing data_zone")


def zones_from_geojson(path: Path) -> list[tuple[str, BaseGeometry]]:
    payload = read_geojson(path)
    source = crs_from_geojson(payload)
    zones: list[tuple[str, BaseGeometry]] = []
    for feature in payload.get("features") or []:
        raw = feature.get("geometry")
        if not raw:
            continue
        prepared = prepare_polygon(reproject_to_bng(shape(raw), source))
        zones.append(
            (
                _zone_code(dict(feature.get("properties") or {})),
                prepared if prepared is not None else Polygon(),
            )
        )
    return zones


def _find_zone_file(root: Path) -> Path | None:
    for name in sorted(ZONE_FILES):
        for path in root.rglob(name):
            return path
    return None


def coverage_by_zone(
    zones: list[tuple[str, BaseGeometry]],
    floods: list[BaseGeometry],
) -> dict[str, int]:
    """Share of each zone covered by the flood polygons, nearest 1%.

    The denominator is the full Data Zone area, land and water.
    """
    if not zones:
        return {}
    prepared_zones: list[tuple[str, BaseGeometry]] = []
    for code, geom in zones:
        prepared = prepare_polygon(geom)
        prepared_zones.append((code, prepared if prepared is not None else Polygon()))
    codes = [code for code, _geom in prepared_zones]
    geoms = [geom for _code, geom in prepared_zones]
    parts: dict[str, list[BaseGeometry]] = {code: [] for code in codes}
    if floods:
        tree = STRtree(geoms)
        for flood in floods:
            flood_geom = prepare_polygon(flood)
            if flood_geom is None or flood_geom.is_empty:
                continue
            for idx in tree.query(flood_geom):
                # make_valid both sides, then keep only polygons after intersection.
                inter_parts = _polygon_parts(
                    make_valid(geoms[int(idx)].intersection(flood_geom))
                )
                if inter_parts:
                    parts[codes[int(idx)]].extend(inter_parts)
    out: dict[str, int] = {}
    for code, geom in prepared_zones:
        pieces = parts[code]
        covered = 0.0 if not pieces else unary_union(pieces).area
        # Denominator is the full Data Zone area (land and water).
        out[code] = round_percent(covered, geom.area)
    return out


def rows_from_zones(
    zones: list[tuple[str, BaseGeometry]],
    floods_by_kind: dict[str, list[BaseGeometry]],
    *,
    source_version: str = SOURCE_VERSION,
) -> list[dict[str, Any]]:
    shares = {
        kind: coverage_by_zone(zones, floods_by_kind.get(kind) or [])
        for kind in KINDS
    }
    rows = []
    for code, _geom in zones:
        rows.append(
            {
                "data_zone": code,
                "pct_area_river": shares["river"].get(code, 0),
                "pct_area_coastal": shares["coastal"].get(code, 0),
                "pct_area_surface": shares["surface"].get(code, 0),
                "source_version": source_version,
            }
        )
    return rows


def _gdb_layer_names(gdb: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["ogrinfo", "-q", str(gdb)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"ogrinfo failed for {gdb.name}: {exc}") from exc
    names: list[str] = []
    for line in proc.stdout.splitlines():
        if ":" not in line:
            continue
        names.append(line.split(":", 1)[1].strip().split(" ")[0])
    return names


def _crs_from_ogr_payload(payload: dict[str, Any]) -> CRS:
    layers = payload.get("layers") or [payload]
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        for field in layer.get("geometryFields") or []:
            cs = field.get("coordinateSystem") or {}
            wkt = cs.get("wkt")
            if wkt:
                return CRS.from_wkt(wkt)
        wkt = layer.get("srs") or layer.get("wkt")
        if isinstance(wkt, str) and wkt.strip():
            return CRS.from_wkt(wkt)
    raise SystemExit("FileGDB layer has no CRS")


def _read_gdb_layer_crs(gdb: Path, layer_name: str) -> CRS:
    try:
        proc = subprocess.run(
            ["ogrinfo", "-json", "-so", str(gdb), layer_name],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"ogrinfo could not read the CRS for {layer_name}: {exc}") from exc
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{layer_name}: ogrinfo did not return a CRS") from exc
    return _crs_from_ogr_payload(payload)


def _geoms_from_gdb(gdb: Path) -> dict[str, list[BaseGeometry]]:
    floods: dict[str, list[BaseGeometry]] = {kind: [] for kind in KINDS}
    for kind, layer_name in select_medium_layers(_gdb_layer_names(gdb)):
        # Read the file CRS before converting. ogr2ogr then writes EPSG:27700.
        _read_gdb_layer_crs(gdb, layer_name)
        dest = gdb.parent / f".{gdb.stem}_{layer_name}.geojson"
        try:
            subprocess.run(
                [
                    "ogr2ogr",
                    "-f",
                    "GeoJSON",
                    "-t_srs",
                    f"EPSG:{TARGET_EPSG}",
                    "-lco",
                    "RFC7946=NO",
                    str(dest),
                    str(gdb),
                    layer_name,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SystemExit(f"ogr2ogr failed for {layer_name}: {exc}") from exc
        payload = read_geojson(dest)
        dest.unlink(missing_ok=True)
        written = crs_from_geojson(payload)
        if written.to_epsg() != TARGET_EPSG:
            raise SystemExit(
                f"{layer_name}: reprojected CRS EPSG:{written.to_epsg()} is not EPSG:27700"
            )
        floods[kind].extend(_geoms_from_collection(payload))
    return floods


def aggregate_directory(root: Path) -> list[dict[str, Any]]:
    """Screen files, require the OGL statement, and return zone share rows."""
    root = root.resolve()
    inputs = iter_inputs(root)
    if not inputs:
        raise SystemExit(f"No SEPA Flood Maps files in {root}")
    floods: dict[str, list[BaseGeometry]] = {kind: [] for kind in KINDS}
    saw_zip = False
    for path in inputs:
        screened = screen_input(path)
        if screened == "zip":
            saw_zip = True
            continue
        assert_licence(root, path)
        if screened == "gdb":
            for kind, geoms in _geoms_from_gdb(path).items():
                floods[kind].extend(geoms)
            continue
        floods[screened].extend(_geoms_from_collection(read_geojson(path)))
    zone_file = _find_zone_file(root)
    if zone_file is None:
        if saw_zip and not any(floods.values()):
            raise SystemExit(
                "Unzip the medium-likelihood present-day extent archives "
                "in data/external/sepa_frm_v3/ before --replace"
            )
        raise SystemExit("No Data Zone outlines in the folder and no zone file")
    return rows_from_zones(zones_from_geojson(zone_file), floods)


def connect():
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        dbname=os.getenv("WEALTH_DB_NAME", "scotland_wealth"),
        user=os.getenv("WEALTH_DB_USER", "wealth_user"),
        password=os.getenv("WEALTH_DB_PASSWORD", ""),
        host=os.getenv("WEALTH_DB_HOST", "localhost"),
        port=os.getenv("WEALTH_DB_PORT", "5432"),
    )


def ensure_table(conn) -> None:
    sql = (REPO_ROOT / "backend" / "db" / "schema" / "027_sepa_flood_dz.sql").read_text(
        encoding="utf-8"
    )
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def load_zones_postgis(conn) -> list[tuple[str, BaseGeometry]]:
    """2022 Data Zones, after the pinned sha, SRID 27700, and the 7,392 count."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sha256
            FROM dz_boundaries_meta
            WHERE vintage = %s AND load_scope = 'production'
            """,
            (DZ2022_VINTAGE,),
        )
        found = cur.fetchone()
        digest = str(found[0]).lower() if found and found[0] else ""
        if digest != DZ2022_SHA256:
            raise SystemExit(
                "DZ2022 source sha256 does not match the pinned SG_DataZoneBdry_2022 file"
            )
        cur.execute(
            """
            SELECT code, ST_AsGeoJSON(geom), ST_SRID(geom)
            FROM dz_boundaries
            WHERE vintage = %s
            """,
            (DZ2022_VINTAGE,),
        )
        zones: list[tuple[str, BaseGeometry]] = []
        for code, geojson, srid in cur.fetchall():
            if int(srid) != TARGET_EPSG:
                raise SystemExit(f"dz_boundaries SRID {srid} is not EPSG:27700")
            prepared = prepare_polygon(shape(json.loads(geojson)))
            zones.append((str(code).strip(), prepared if prepared is not None else Polygon()))
    if len(zones) != DZ2022_COUNT:
        raise SystemExit(
            f"expected {DZ2022_COUNT} Data Zones for 2022 before writing, got {len(zones)}"
        )
    return zones


def floods_from_directory(root: Path) -> dict[str, list[BaseGeometry]]:
    """Licence-checked medium extents. Raises on a rejected file."""
    floods: dict[str, list[BaseGeometry]] = {kind: [] for kind in KINDS}
    saw_zip = False
    for path in iter_inputs(root):
        screened = screen_input(path)
        if screened == "zip":
            saw_zip = True
            continue
        assert_licence(root, path)
        if screened == "gdb":
            for kind, geoms in _geoms_from_gdb(path).items():
                floods[kind].extend(geoms)
            continue
        floods[screened].extend(_geoms_from_collection(read_geojson(path)))
    if saw_zip and not any(floods.values()):
        raise SystemExit(
            "Unzip the medium-likelihood present-day extent archives "
            "in data/external/sepa_frm_v3/ before --replace"
        )
    if not any(floods.values()):
        raise SystemExit(f"No medium-likelihood extent files in {root}")
    return floods


def write_rows(conn, rows: list[dict[str, Any]]) -> int:
    ensure_table(conn)
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {TABLE}")
        for row in rows:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    data_zone, pct_area_river, pct_area_coastal,
                    pct_area_surface, source_version
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    row["data_zone"],
                    int(row["pct_area_river"]),
                    int(row["pct_area_coastal"]),
                    int(row["pct_area_surface"]),
                    row["source_version"],
                ),
            )
    conn.commit()
    return len(rows)


def load_replace(root: Path) -> int:
    """Replace sepa_flood_dz from the download folder and PostGIS Data Zones."""
    floods = floods_from_directory(root)
    conn = connect()
    try:
        zones = load_zones_postgis(conn)
        rows = rows_from_zones(zones, floods)
        return write_rows(conn, rows)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace sepa_flood_dz with shares from data/external/sepa_frm_v3/",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DIR,
        help="Download folder (default data/external/sepa_frm_v3)",
    )
    args = parser.parse_args()
    if not args.replace:
        raise SystemExit("Refusing to load without --replace")
    count = load_replace(args.dir)
    logger.info("Wrote %s Data Zone rows to %s", count, TABLE)


if __name__ == "__main__":
    main()
