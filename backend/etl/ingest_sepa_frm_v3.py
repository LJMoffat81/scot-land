"""Data Zone shares from SEPA Flood Maps v3.0 medium-likelihood extents.

Reads files already downloaded under data/external/sepa_frm_v3/ (gitignored).
Uses only present-day medium-likelihood extent layers (`_M`). Rejects
`_M_CC`, high-likelihood, depth, and velocity files. Checks each file's
licence statement and aborts unless it says Open Government Licence 3.0.

Reprojects to EPSG:27700, intersects the 2022 Data Zones, and stores one
row per zone: data_zone, pct_area_river, pct_area_coastal, pct_area_surface
(nearest 1%, 0 to 100), source_version. No flood polygons are stored.

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

from pyproj import Transformer
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("ingest_sepa_frm_v3")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / "data" / "external" / "sepa_frm_v3"
TABLE = "sepa_flood_dz"
SOURCE_VERSION = "v3.0"
LICENCE_PHRASE = b"Open Government Licence 3.0"
KINDS = ("river", "coastal", "surface")
ZONE_FILES = {"dz.geojson", "data_zones.geojson"}
GDB_MEDIUM_LAYERS = {
    "river": "FRM_FH_RIVER_EXTENT_M",
    "coastal": "FRM_FH_COASTAL_EXTENT_M",
    "surface": "FRM_FH_SURFACE_WATER_EXTENT_M",
}
_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)


class RejectedFloodSource(Exception):
    """File is not a present-day medium-likelihood extent."""


class LicenceError(Exception):
    """Licence statement is missing or is not Open Government Licence 3.0."""


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


def kind_from_name(name: str) -> str:
    low = name.lower()
    if "coast" in low:
        return "coastal"
    if "surface" in low:
        return "surface"
    if "river" in low:
        return "river"
    raise RejectedFloodSource(name)


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
    if is_rejected_name(path.name):
        raise RejectedFloodSource(path.name)
    if path.suffix.lower() == ".zip":
        return "zip"
    if path.is_dir() and path.suffix.lower() == ".gdb":
        return "gdb"
    low = path.name.lower()
    if "extent_m" not in low and path.suffix.lower() not in {".geojson", ".json", ".gpkg"}:
        raise RejectedFloodSource(path.name)
    return kind_from_name(path.name)


def assert_licence(root: Path, data_path: Path) -> None:
    """Abort unless a statement shipped beside the file says Open Government Licence 3.0."""
    folders = []
    for folder in (data_path.parent, root):
        if folder.is_dir() and folder not in folders:
            folders.append(folder)
    for folder in folders:
        for candidate in sorted(folder.iterdir()):
            if not _is_licence_sidecar(candidate):
                continue
            blob = candidate.read_bytes()
            if LICENCE_PHRASE in blob:
                return
    raise LicenceError(
        f"{data_path.name}: licence statement must say Open Government Licence 3.0"
    )


def _as_bng(geom: BaseGeometry) -> BaseGeometry:
    minx, miny, maxx, maxy = geom.bounds
    if max(abs(minx), abs(maxx), abs(miny), abs(maxy)) <= 180:
        return transform(_TO_BNG.transform, geom)
    return geom


def _geoms_from_collection(payload: dict[str, Any]) -> list[BaseGeometry]:
    features = payload.get("features") or []
    geoms: list[BaseGeometry] = []
    for feature in features:
        raw = feature.get("geometry")
        if not raw:
            continue
        geom = _as_bng(shape(raw))
        if geom.is_empty:
            continue
        geoms.append(geom)
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
    zones: list[tuple[str, BaseGeometry]] = []
    for feature in read_geojson(path).get("features") or []:
        raw = feature.get("geometry")
        if not raw:
            continue
        zones.append((_zone_code(dict(feature.get("properties") or {})), _as_bng(shape(raw))))
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
    """Share of each zone covered by the flood polygons, nearest 1%."""
    if not zones:
        return {}
    codes = [code for code, _geom in zones]
    geoms = [geom for _code, geom in zones]
    parts: dict[str, list[BaseGeometry]] = {code: [] for code in codes}
    if floods:
        tree = STRtree(geoms)
        for flood in floods:
            if flood.is_empty:
                continue
            for idx in tree.query(flood):
                zone_geom = geoms[int(idx)]
                inter = zone_geom.intersection(flood)
                if inter.is_empty or inter.area <= 0:
                    continue
                parts[codes[int(idx)]].append(inter)
    out: dict[str, int] = {}
    for code, geom in zones:
        pieces = parts[code]
        covered = 0.0 if not pieces else unary_union(pieces).area
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


def _gdb_medium_layers(gdb: Path) -> list[tuple[str, str]]:
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
    chosen: list[tuple[str, str]] = []
    for layer_name in names:
        if is_rejected_name(layer_name):
            continue
        if not layer_name.endswith("_EXTENT_M") and "EXTENT_M" not in layer_name:
            continue
        if layer_name.endswith("_M_CC") or "_M_CC" in layer_name:
            continue
        chosen.append((kind_from_name(layer_name), layer_name))
    if not chosen:
        for kind, layer_name in GDB_MEDIUM_LAYERS.items():
            chosen.append((kind, layer_name))
    return chosen


def _geoms_from_gdb(gdb: Path) -> dict[str, list[BaseGeometry]]:
    floods: dict[str, list[BaseGeometry]] = {kind: [] for kind in KINDS}
    for kind, layer_name in _gdb_medium_layers(gdb):
        dest = gdb.parent / f".{gdb.stem}_{layer_name}.geojson"
        try:
            subprocess.run(
                [
                    "ogr2ogr",
                    "-f",
                    "GeoJSON",
                    str(dest),
                    str(gdb),
                    layer_name,
                    "-t_srs",
                    "EPSG:27700",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SystemExit(f"ogr2ogr failed for {layer_name}: {exc}") from exc
        floods[kind].extend(_geoms_from_collection(read_geojson(dest)))
        dest.unlink(missing_ok=True)
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
        assert_licence(root, path)
        if screened == "zip":
            saw_zip = True
            continue
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
    zones: list[tuple[str, BaseGeometry]] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT code, ST_AsGeoJSON(geom)
            FROM dz_boundaries
            WHERE vintage = 2022
            """
        )
        for code, geojson in cur.fetchall():
            zones.append((str(code).strip(), shape(json.loads(geojson))))
    if not zones:
        raise SystemExit("2022 Data Zones are not loaded in dz_boundaries")
    return zones


def floods_from_directory(root: Path) -> dict[str, list[BaseGeometry]]:
    """Licence-checked medium extents. Raises on a rejected file."""
    floods: dict[str, list[BaseGeometry]] = {kind: [] for kind in KINDS}
    saw_zip = False
    for path in iter_inputs(root):
        screened = screen_input(path)
        assert_licence(root, path)
        if screened == "zip":
            saw_zip = True
            continue
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
