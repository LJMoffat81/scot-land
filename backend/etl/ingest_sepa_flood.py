"""Ingest SEPA Flood Maps polygons into PostGIS (sepa_flood).

Source is the OGL download at www2.sepa.org.uk/flooddata only — never
MapServer / viewer / live query services.

Repeatable path (FileGDB → GeoJSON → PostGIS), keeping polygons from mixed
geometries and simplifying ~2 m in British National Grid:

  # Unzip River + Coastal v3.0 GDBs under data/external/sepa/
  python -m etl.ingest_sepa_flood --from-gdb --replace

Or load a pre-exported FeatureCollection:

  python -m etl.ingest_sepa_flood \\
    --input ../data/external/sepa/flood_medium_river_coastal.geojson \\
    --replace

Vintage defaults to the SEPA Flood Maps v3.0 release-notes date
(25 February 2025), not a placeholder. See scripts/data/README-sepa.md.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import psycopg2
from shapely.geometry import MultiPolygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("ingest_sepa_flood")

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE = "sepa_flood"
DEFAULT_DIR = REPO_ROOT / "data" / "external" / "sepa"
DEFAULT_INPUT = DEFAULT_DIR / "flood_medium_river_coastal.geojson"

# SEPA Flood Map Version 3.0 Release Notes — 25 February 2025
# https://www.sepa.org.uk/media/htpldzvk/flood-map-version-3_0-release-notes.pdf
RELEASE_NOTES_DATE = "2025-02-25"
RELEASE_NOTES_URL = (
    "https://www.sepa.org.uk/media/htpldzvk/flood-map-version-3_0-release-notes.pdf"
)
FLOODDATA_URL = "https://www2.sepa.org.uk/flooddata/"
# Atom zip links published on the flooddata download page (OGL product, not MapServer query).
DOWNLOAD_ZIPS = {
    "river": "https://map.sepa.org.uk/atom/flood/SEPA_River_Flood_Maps_v3_0.zip",
    "coastal": "https://map.sepa.org.uk/atom/flood/SEPA_Coastal_Flood_Maps_v3_0.zip",
}

# Medium-likelihood (1:200) present-day extent layers inside the v3.0 FileGDBs.
GDB_LAYERS = {
    "river": {
        "layer_name": "FRM_FH_RIVER_EXTENT_M",
        "layer_id": 1,
        "gdb_glob": "*River*Flood*Hazard*.gdb",
        "expected_rows": 47_093,
    },
    "coastal": {
        "layer_name": "FRM_FH_COASTAL_EXTENT_M",
        "layer_id": 7,
        "gdb_glob": "*Coastal*Flood*Hazard*.gdb",
        "expected_rows": 16,
    },
}
SIMPLIFY_METRES = 2.0
COUNT_TOLERANCE = 0.001  # ~0.1% vs #57 / release load

SOURCE_FROM_LAYER = {1: "River", 4: "Surface Water", 7: "Coastal"}


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
    sql = (REPO_ROOT / "backend" / "db" / "schema" / "007_sepa_flood.sql").read_text(
        encoding="utf-8"
    )
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def keep_polygons(geom: BaseGeometry) -> dict[str, Any] | None:
    """Keep polygon parts from mixed geometries; drop lines/points."""
    if geom.is_empty:
        return None
    if geom.geom_type == "Polygon":
        return mapping(MultiPolygon([geom]))
    if geom.geom_type == "MultiPolygon":
        return mapping(geom)
    if geom.geom_type == "GeometryCollection":
        parts = [
            g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty
        ]
        if not parts:
            return None
        return keep_polygons(unary_union(parts))
    return None


# Back-compat alias used by tests / callers.
_as_multipolygon = keep_polygons


def _layer_id(props: dict[str, Any]) -> int:
    raw = props.get("layer_id") or props.get("LAYER_ID")
    if raw is not None and str(raw).strip() != "":
        return int(raw)
    source = str(props.get("SOURCE") or props.get("source") or "").lower()
    if "coast" in source:
        return 7
    if "surface" in source:
        return 4
    return 1


def _object_id(props: dict[str, Any], feature: dict[str, Any], index: int) -> int:
    for key in ("OBJECTID", "object_id", "FID", "fid"):
        raw = props.get(key)
        if raw is not None and str(raw).strip() != "":
            return int(raw)
    fid = feature.get("id")
    if fid is not None and str(fid).strip() != "":
        # GeoJSON id may be "FRM_FH_COASTAL_EXTENT_M.12"
        text = str(fid)
        if "." in text:
            text = text.rsplit(".", 1)[-1]
        try:
            return int(text)
        except ValueError:
            pass
    return index + 1


def _require_ogr2ogr() -> str:
    path = shutil.which("ogr2ogr")
    if not path:
        raise SystemExit(
            "ogr2ogr not found on PATH. Install GDAL (gdal-bin) to export SEPA "
            "FileGDBs, or pass a pre-built GeoJSON with --input."
        )
    return path


def find_gdb(root: Path, kind: str) -> Path:
    """Locate the River or Coastal hazard FileGDB under data/external/sepa/."""
    spec = GDB_LAYERS[kind]
    matches = sorted(root.rglob(spec["gdb_glob"]))
    # rglob with case-insensitive fallback
    if not matches:
        needle = "river" if kind == "river" else "coastal"
        matches = [
            p
            for p in root.rglob("*.gdb")
            if p.is_dir() and needle in p.name.lower()
        ]
    if not matches:
        raise SystemExit(
            f"No {kind} FileGDB found under {root}. Download the SEPA {kind} "
            f"Flood Maps v3.0 zip from {FLOODDATA_URL} and unzip into "
            f"data/external/sepa/ (gitignored)."
        )
    return matches[0]


def export_gdb_layer(
    gdb: Path,
    layer_name: str,
    out_path: Path,
    *,
    simplify_metres: float = SIMPLIFY_METRES,
) -> Path:
    """Export one FileGDB layer to WGS84 GeoJSON; ~2 m simplify in source metres."""
    ogr2ogr = _require_ogr2ogr()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    cmd = [
        ogr2ogr,
        "-f",
        "GeoJSON",
        "-t_srs",
        "EPSG:4326",
        "-nlt",
        "PROMOTE_TO_MULTI",
        "-simplify",
        str(simplify_metres),
        "-lco",
        "RFC7946=YES",
        str(out_path),
        str(gdb),
        layer_name,
    ]
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not out_path.is_file():
        raise SystemExit(
            f"ogr2ogr failed for {gdb.name}:{layer_name}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return out_path


def merge_feature_collections(
    parts: list[tuple[dict[str, Any], int]],
) -> dict[str, Any]:
    """Merge GeoJSON FeatureCollections, stamping properties.layer_id."""
    features: list[dict[str, Any]] = []
    for payload, layer_id in parts:
        for feature in payload.get("features") or []:
            if not isinstance(feature, dict):
                continue
            props = dict(feature.get("properties") or {})
            props["layer_id"] = layer_id
            features.append({**feature, "properties": props})
    return {"type": "FeatureCollection", "features": features}


def export_medium_from_gdb(
    sepa_dir: Path,
    out_path: Path,
    *,
    simplify_metres: float = SIMPLIFY_METRES,
) -> tuple[Path, dict[str, int]]:
    """Export river + coastal medium extents and write a combined GeoJSON."""
    counts: dict[str, int] = {}
    merged_parts: list[tuple[dict[str, Any], int]] = []
    with tempfile.TemporaryDirectory(prefix="sepa_flood_export_") as tmp:
        tmp_dir = Path(tmp)
        for kind, spec in GDB_LAYERS.items():
            gdb = find_gdb(sepa_dir, kind)
            layer_name = spec["layer_name"]
            part_path = tmp_dir / f"{kind}_medium.geojson"
            export_gdb_layer(
                gdb, layer_name, part_path, simplify_metres=simplify_metres
            )
            payload = json.loads(part_path.read_text(encoding="utf-8"))
            n = len(payload.get("features") or [])
            counts[kind] = n
            logger.info(
                "Exported %s %s features from %s:%s",
                n,
                kind,
                gdb.name,
                layer_name,
            )
            merged_parts.append((payload, int(spec["layer_id"])))
    combined = merge_feature_collections(merged_parts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(combined), encoding="utf-8")
    logger.info("Wrote combined GeoJSON (%s features) → %s", len(combined["features"]), out_path)
    return out_path, counts


def check_counts(counts: dict[str, int], *, tolerance: float = COUNT_TOLERANCE) -> None:
    """Accept when each layer is within ~0.1% of the #57 / release baseline."""
    problems: list[str] = []
    for kind, spec in GDB_LAYERS.items():
        expected = int(spec["expected_rows"])
        actual = int(counts.get(kind, -1))
        if actual < 0:
            problems.append(f"{kind}: missing count")
            continue
        delta = abs(actual - expected) / expected if expected else abs(actual - expected)
        if delta > tolerance:
            problems.append(
                f"{kind}: got {actual:,}, expected {expected:,} "
                f"(Δ {delta:.4%} > {tolerance:.1%})"
            )
        else:
            logger.info(
                "Count check OK %s: %s (expected %s, Δ %.4f%%)",
                kind,
                f"{actual:,}",
                f"{expected:,}",
                delta * 100,
            )
    if problems:
        raise SystemExit("Flood row-count check failed:\n  - " + "\n  - ".join(problems))


def load_geojson(path: Path, conn, *, replace: bool) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features") or []
    if not isinstance(features, list):
        raise ValueError(f"{path} must be a FeatureCollection")

    with conn.cursor() as cur:
        if replace:
            cur.execute(f"TRUNCATE {TABLE}")
        inserted = 0
        for index, feature in enumerate(features):
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties") or {}
            geometry = feature.get("geometry")
            if not geometry:
                continue
            try:
                geom = shape(geometry)
            except Exception:
                logger.warning("Skip feature %s: bad geometry", index)
                continue
            multi = keep_polygons(geom)
            if multi is None:
                continue
            layer_id = _layer_id(props)
            object_id = _object_id(props, feature, index)
            source = (
                props.get("SOURCE")
                or props.get("source")
                or SOURCE_FROM_LAYER.get(layer_id)
                or "Unknown"
            )
            probability = props.get("PROB") or props.get("probability") or "M"
            cur.execute(
                f"""
                INSERT INTO {TABLE}
                    (object_id, layer_id, source, probability, scenario,
                     map_type, reference, version, geom)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s,
                     ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                ON CONFLICT (layer_id, object_id) DO UPDATE SET
                    source = EXCLUDED.source,
                    probability = EXCLUDED.probability,
                    scenario = EXCLUDED.scenario,
                    map_type = EXCLUDED.map_type,
                    reference = EXCLUDED.reference,
                    version = EXCLUDED.version,
                    geom = EXCLUDED.geom
                """,
                (
                    object_id,
                    layer_id,
                    str(source),
                    str(probability),
                    props.get("SCENARIO") or props.get("scenario") or "Present Day",
                    props.get("MAP_TYPE") or props.get("map_type"),
                    props.get("REFERENCE") or props.get("reference"),
                    props.get("VERSION") or props.get("version"),
                    json.dumps(multi),
                ),
            )
            inserted += 1
    conn.commit()
    return inserted


def count_by_layer(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              SUM(CASE WHEN layer_id = 1 THEN 1 ELSE 0 END) AS river,
              SUM(CASE WHEN layer_id = 7 THEN 1 ELSE 0 END) AS coastal
            FROM {TABLE}
            """
        )
        row = cur.fetchone() or (0, 0)
    return {"river": int(row[0] or 0), "coastal": int(row[1] or 0)}


def write_local_stamp(input_path: Path, count: int, vintage: str, extra: dict[str, Any] | None = None) -> Path:
    stamp_path = input_path.with_suffix(input_path.suffix + ".ingest.json")
    stamp: dict[str, Any] = {
        "layer": "sepa_flood",
        "product": "SEPA Flood Maps v3.0",
        "licence": "OGL-3.0",
        "source_url": FLOODDATA_URL,
        "release_notes_url": RELEASE_NOTES_URL,
        "input": str(input_path),
        "row_count": count,
        "vintage": vintage,
        "simplify_metres": SIMPLIFY_METRES,
        "ingested_on": date.today().isoformat(),
        "note": "Local stamp only — raw geometry stays out of git (data/external/).",
    }
    if extra:
        stamp.update(extra)
    stamp_path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    return stamp_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="GeoJSON FeatureCollection (default after --from-gdb: flood_medium_river_coastal.geojson)",
    )
    parser.add_argument(
        "--from-gdb",
        action="store_true",
        help=(
            "Export FRM_FH_RIVER_EXTENT_M + FRM_FH_COASTAL_EXTENT_M from FileGDBs "
            f"under data/external/sepa/ (simplify {SIMPLIFY_METRES:g} m) then load"
        ),
    )
    parser.add_argument(
        "--sepa-dir",
        type=Path,
        default=DEFAULT_DIR,
        help="Directory holding unzipped SEPA FileGDBs (default: data/external/sepa)",
    )
    parser.add_argument(
        "--export-geojson",
        type=Path,
        default=DEFAULT_INPUT,
        help="Where --from-gdb writes the combined GeoJSON",
    )
    parser.add_argument(
        "--vintage",
        default=RELEASE_NOTES_DATE,
        help=(
            f"Product vintage (default: {RELEASE_NOTES_DATE} from SEPA v3.0 release notes; "
            "do not use a 2025-01-01 placeholder)"
        ),
    )
    parser.add_argument("--replace", action="store_true")
    parser.add_argument(
        "--check-counts",
        action="store_true",
        help="Fail unless river/coastal row counts match the #57 baseline within ~0.1%",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="With --from-gdb, write GeoJSON and exit without loading PostGIS",
    )
    args = parser.parse_args()

    export_counts: dict[str, int] | None = None
    input_path = args.input
    if args.from_gdb:
        input_path, export_counts = export_medium_from_gdb(
            args.sepa_dir, args.export_geojson
        )
        if args.check_counts:
            check_counts(export_counts)
        if args.export_only:
            logger.info("Export-only complete: %s", input_path)
            return
    elif input_path is None:
        input_path = DEFAULT_INPUT

    if not input_path.is_file():
        raise SystemExit(
            f"Input not found: {input_path}\n"
            f"Download SEPA Flood Maps (OGL) from {FLOODDATA_URL} into "
            "data/external/sepa/ (gitignored), unzip the River + Coastal v3.0 "
            "FileGDBs, then re-run with --from-gdb. Do not use MapServer / viewer / "
            "web services."
        )
    resolved = input_path.resolve()
    if "data/processed" in str(resolved).replace("\\", "/"):
        raise SystemExit(
            "Refuse to read flood geometry from data/processed/. "
            "Keep raw extracts under data/external/ (gitignored)."
        )

    conn = connect()
    try:
        ensure_table(conn)
        count = load_geojson(input_path, conn, replace=args.replace)
        by_layer = count_by_layer(conn)
    finally:
        conn.close()

    if args.check_counts:
        check_counts(by_layer if by_layer["river"] or by_layer["coastal"] else (export_counts or {}))

    stamp = write_local_stamp(
        input_path,
        count,
        args.vintage,
        extra={"by_layer": by_layer, "release_notes_date": RELEASE_NOTES_DATE},
    )
    logger.info(
        "Loaded %s flood polygons into %s (river=%s coastal=%s vintage=%s). Stamp: %s",
        count,
        TABLE,
        by_layer.get("river"),
        by_layer.get("coastal"),
        args.vintage,
        stamp,
    )


if __name__ == "__main__":
    main()
