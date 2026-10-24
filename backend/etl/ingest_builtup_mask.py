"""Deprecated by SRC-B-SETTLEMENTS; tables kept pending Laurie.

Ingest UX10-2 built-up display mask into PostGIS.

DISPLAY ONLY — never changes any figure. Loads delivery GeoJSON (EPSG:4326):
  map_builtup_mask.4326.geojson  → table map_builtup_mask (one Polygon row per part)
  dz2022_masked.4326.geojson     → table dz2022_masked (code PK, MultiPolygon)

Large blobs stay out of git. Resolve paths from, in order:
  --mask / --masked-dz CLI flags
  BUILTUP_MASK_DIR env
  DATA_DIR/external/builtup/ (default DATA_DIR = repo data/)

Usage:
  export DATABASE_URL=postgresql://...
  export BUILTUP_MASK_DIR=/path/to/mask-ux10-2
  python -m etl.ingest_builtup_mask --allow-deprecated --replace
  # or CI fixture:
  python -m etl.ingest_builtup_mask --allow-deprecated --fixture --replace
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from etl.receipt_write import write_receipt
from georgist.db import connect
from paths import DATA_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = REPO_ROOT / "backend" / "db" / "schema" / "025_map_builtup_mask.sql"
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "builtup_mask"
DEFAULT_DIR = DATA_DIR / "external" / "builtup"
EXPECTED_DZ = 7392
CODE_RE = re.compile(r"^S01[0-9]{6}$")
VISITOR_ATTRIBUTION = "Built-up areas: NRS Settlements 2022. Copyright National Records of Scotland, contains Ordnance Survey data © Crown copyright and database right 2026 (OGL v3)"


def ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()


def _resolve_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    env = (os.getenv("BUILTUP_MASK_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_DIR.resolve()


def _load_fc(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Input not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise SystemExit(f"{path}: must be a GeoJSON FeatureCollection")
    return payload


def _geometry_parts(geometry: dict[str, Any]) -> list[dict[str, Any]]:
    """Return Polygon GeoJSON dicts (dump MultiPolygon)."""
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon":
        return [geometry]
    if gtype == "MultiPolygon":
        return [{"type": "Polygon", "coordinates": ring} for ring in coords or []]
    raise SystemExit(f"Unsupported geometry type for map_builtup_mask: {gtype}")


def load_mask(conn, payload: dict[str, Any], replace: bool) -> int:
    features = payload.get("features") or []
    with conn.cursor() as cur:
        if replace:
            cur.execute("TRUNCATE TABLE map_builtup_mask RESTART IDENTITY;")
        inserted = 0
        for feature in features:
            geometry = feature.get("geometry")
            if not geometry:
                continue
            for part in _geometry_parts(geometry):
                cur.execute(
                    """
                    INSERT INTO map_builtup_mask (geom)
                    VALUES (
                        ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
                    )
                    """,
                    (json.dumps(part),),
                )
                inserted += 1
    conn.commit()
    return inserted


def load_masked_dz(conn, payload: dict[str, Any], replace: bool) -> int:
    features = payload.get("features") or []
    with conn.cursor() as cur:
        if replace:
            cur.execute("TRUNCATE TABLE dz2022_masked;")
        inserted = 0
        seen: set[str] = set()
        for feature in features:
            geometry = feature.get("geometry")
            props = dict(feature.get("properties") or {})
            code = str(props.get("code") or "").strip()
            if not geometry or not code:
                continue
            if not CODE_RE.match(code):
                raise SystemExit(f"Invalid DZ2022 code in mask delivery: {code!r}")
            if code in seen:
                raise SystemExit(f"Duplicate dz2022_masked code: {code}")
            seen.add(code)
            gtype = geometry.get("type")
            if gtype == "Polygon":
                geometry = {
                    "type": "MultiPolygon",
                    "coordinates": [geometry["coordinates"]],
                }
            elif gtype != "MultiPolygon":
                raise SystemExit(f"Unsupported geometry for {code}: {gtype}")
            cur.execute(
                """
                INSERT INTO dz2022_masked (code, geom)
                VALUES (
                    %s,
                    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                )
                ON CONFLICT (code) DO UPDATE SET
                    geom = EXCLUDED.geom,
                    updated_at = now();
                """,
                (code, json.dumps(geometry)),
            )
            inserted += 1
    conn.commit()
    return inserted


def assert_full_qa(conn, qa_path: Path | None) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT code) FROM dz2022_masked")
        rows, distinct = cur.fetchone()
    if rows != EXPECTED_DZ or distinct != EXPECTED_DZ:
        raise SystemExit(
            f"dz2022_masked QA fail: rows={rows} distinct={distinct} "
            f"(expected {EXPECTED_DZ})"
        )
    if qa_path is not None and qa_path.is_file():
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        if float(qa.get("uprn_inside_mask_pct", 0)) != 100.0:
            raise SystemExit(
                f"QA json uprn_inside_mask_pct={qa.get('uprn_inside_mask_pct')} "
                "(expected 100.0)"
            )
        if int(qa.get("dz2022_masked_rows", 0)) != EXPECTED_DZ:
            raise SystemExit(
                f"QA json dz2022_masked_rows={qa.get('dz2022_masked_rows')} "
                f"(expected {EXPECTED_DZ})"
            )
        missing = qa.get("dz_with_uprn_missing_masked_geom") or []
        if missing:
            raise SystemExit(f"QA json lists missing masked geoms: {missing[:5]}…")
    logger.info(
        "QA OK: dz2022_masked=%s codes 1:1; visitor attribution=%r",
        EXPECTED_DZ,
        VISITOR_ATTRIBUTION,
    )


def write_stamp(path: Path, mask_parts: int, dz_rows: int) -> Path | None:
    """Write builtup_mask.ingest.json; non-fatal when /app/data is read-only."""
    stamp = {
        "layer": "map_builtup_mask",
        "licence": "OGL-3.0",
        "attribution": VISITOR_ATTRIBUTION,
        "map_builtup_mask_parts": mask_parts,
        "dz2022_masked_rows": dz_rows,
        "expected_dz2022_masked": EXPECTED_DZ,
        "ingested_on": date.today().isoformat(),
        "note": (
            "Local stamp only — raw geometry stays out of git "
            "(data/external/builtup/ or BUILTUP_MASK_DIR)."
        ),
    }
    return write_receipt(
        path,
        stamp,
        fallback_name="builtup_mask.ingest.json",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-deprecated",
        action="store_true",
        help="Acknowledge SRC-B-SETTLEMENTS deprecation and run anyway",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="Directory with *.4326.geojson (default BUILTUP_MASK_DIR or DATA_DIR/external/builtup)",
    )
    parser.add_argument(
        "--mask",
        type=Path,
        default=None,
        help="Path to map_builtup_mask.4326.geojson",
    )
    parser.add_argument(
        "--masked-dz",
        type=Path,
        default=None,
        help="Path to dz2022_masked.4326.geojson",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Load tiny CI fixtures from backend/tests/fixtures/builtup_mask/",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="TRUNCATE tables before load",
    )
    parser.add_argument(
        "--assert-full-qa",
        action="store_true",
        help="Require 7392 unique dz2022_masked rows (and QA json if present)",
    )
    parser.add_argument(
        "--qa-json",
        type=Path,
        default=None,
        help="Optional qa_builtup_mask.json to verify when --assert-full-qa",
    )
    args = parser.parse_args(argv)
    if not args.allow_deprecated:
        raise RuntimeError(
            "ingest_builtup_mask is deprecated (SRC-B-SETTLEMENTS); pass --allow-deprecated"
        )

    if not (os.getenv("DATABASE_URL") or "").strip() and not (
        os.getenv("PGHOST", "").strip() and os.getenv("PGDATABASE", "").strip()
    ):
        raise SystemExit("Set DATABASE_URL or PGHOST+PGDATABASE before ingest.")

    if args.fixture:
        mask_path = FIXTURE_DIR / "map_builtup_mask.4326.geojson"
        dz_path = FIXTURE_DIR / "dz2022_masked.4326.geojson"
        qa_path = FIXTURE_DIR / "qa_builtup_mask.json"
    else:
        base = _resolve_dir(args.dir)
        mask_path = (args.mask or base / "map_builtup_mask.4326.geojson").resolve()
        dz_path = (args.masked_dz or base / "dz2022_masked.4326.geojson").resolve()
        qa_path = args.qa_json or (base / "qa_builtup_mask.json")

    for path in (mask_path, dz_path):
        resolved = path.resolve()
        if "data/processed" in str(resolved).replace("\\", "/"):
            raise SystemExit(
                "Refuse to read built-up mask geometry from data/processed/. "
                "Keep extracts under data/external/builtup/ or BUILTUP_MASK_DIR."
            )

    conn = connect()
    try:
        ensure_tables(conn)
        mask_fc = _load_fc(mask_path)
        dz_fc = _load_fc(dz_path)
        mask_n = load_mask(conn, mask_fc, replace=args.replace)
        dz_n = load_masked_dz(conn, dz_fc, replace=args.replace)
        logger.info("Loaded %s polygon parts into map_builtup_mask", mask_n)
        logger.info("Loaded %s rows into dz2022_masked", dz_n)
        if args.assert_full_qa:
            assert_full_qa(conn, qa_path if isinstance(qa_path, Path) else None)
        stamp_dir = DEFAULT_DIR if not args.fixture else FIXTURE_DIR
        write_stamp(stamp_dir / "builtup_mask.ingest.json", mask_n, dz_n)
    finally:
        conn.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
