"""Ingest NatureScot Carbon and Peatland 2016 into PostGIS (carbon_peatland).

Pinned source (GPKG, not WMS/WFS):
  https://gis-downloads.nature.scot/CPM2016_SCOTLAND_GPKG_27700.zip
CRS EPSG:27700; class field IMPORTANCE.

Two entry points:
  --fixture   CI/tests: load the eight-class stub GeoJSON only
  --national  Laurie's PC: refuse until pins exist; before-INSERT raw count

National zip stays under data/external/ (gitignored). Do not download in CI.
After a successful raw load, callers may ``run_layer("carbon-peatland")`` for
repair/clip via the shared pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import psycopg2
from shapely import wkb as shapely_wkb
from shapely.geometry import MultiPolygon, mapping, shape

from etl.adapters.os_boundary_line import gpkg_blob_to_wkb
from etl import cpm2016_provenance as prov
from georgist.cpm2016_rules import (
    ALLOWED_IMPORTANCE,
    CRS,
    FIELD,
    GPKG_FEATURE_COUNT,
    GPKG_LAYER,
    GPKG_SHA256,
    SOURCE_URL,
    normalize_importance,
    Cpm2016RuleError,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE = "carbon_peatland"
EXTERNAL_DIR = REPO_ROOT / "data" / "external"
DEFAULT_NATIONAL = EXTERNAL_DIR / "CPM2016_SCOTLAND_GPKG_27700.zip"
FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "cpm2016_importance_stub.geojson"
)
SCHEMA_SQL = (
    Path(__file__).resolve().parents[1] / "db" / "schema" / "028_carbon_peatland.sql"
)
INGEST_PREFIX = "CPM2016-INGEST: REFUSED: "
EPSG_27700_NAMES = frozenset(
    {
        "EPSG:27700",
        "urn:ogc:def:crs:EPSG::27700",
        "urn:ogc:def:crs:EPSG:27700",
    }
)


class Cpm2016IngestError(RuntimeError):
    """National/fixture ingest refusal (``CPM2016-INGEST: REFUSED:`` prefix)."""


def _refuse(message: str) -> Cpm2016IngestError:
    return Cpm2016IngestError(f"{INGEST_PREFIX}{message}")


def _dsn() -> str:
    dsn = (
        os.environ.get("ARCH1_TEST_DSN")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if not dsn:
        raise Cpm2016IngestError(
            "CPM2016-INGEST: REFUSED: DATABASE_URL/ARCH1_TEST_DSN missing"
        )
    return dsn


def connect():
    connection = psycopg2.connect(_dsn())
    connection.autocommit = True
    return connection


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collection_crs_name(collection: dict[str, Any]) -> str | None:
    crs = collection.get("crs") or {}
    props = crs.get("properties") or {}
    name = props.get("name")
    return str(name) if name else None


def _require_27700(collection: dict[str, Any]) -> None:
    name = _collection_crs_name(collection)
    if name is None or name not in EPSG_27700_NAMES:
        actual = name if name is not None else "absent"
        raise _refuse(f"CRS: expected EPSG:27700, got {actual}")


def _importance_from_props(props: dict[str, Any]) -> int:
    if "IMPORTANCE" in props:
        raw = props.get("IMPORTANCE")
    elif "importance" in props:
        raw = props.get("importance")
    else:
        raise _refuse(
            "IMPORTANCE: expected integer code in "
            f"{sorted(ALLOWED_IMPORTANCE)}, got None"
        )
    try:
        return normalize_importance(raw)
    except Cpm2016RuleError as exc:
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            raise _refuse(
                "IMPORTANCE: expected integer code in "
                f"{sorted(ALLOWED_IMPORTANCE)}, got None"
            ) from exc
        # Out-of-domain integer (e.g. 6) — keep the locked R6 wording.
        try:
            code = int(raw) if not isinstance(raw, bool) else raw
        except (TypeError, ValueError):
            code = raw
        if isinstance(code, int) and code not in ALLOWED_IMPORTANCE:
            raise _refuse(
                f"IMPORTANCE {code} is outside the official class set "
                f"{sorted(ALLOWED_IMPORTANCE)}"
            ) from exc
        raise _refuse(
            "IMPORTANCE: expected integer code in "
            f"{sorted(ALLOWED_IMPORTANCE)}, got {raw!r}"
        ) from exc


def _as_multipolygon_geojson(geom_obj: dict[str, Any]) -> str:
    geom = shape(geom_obj)
    if geom.is_empty:
        raise _refuse("geometry: expected non-empty polygon, got empty")
    if geom.geom_type == "Polygon":
        geom = MultiPolygon([geom])
    elif geom.geom_type != "MultiPolygon":
        raise _refuse(
            f"geometry: expected Polygon/MultiPolygon, got {geom.geom_type}"
        )
    return json.dumps(mapping(geom))


def _row_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema='public' AND table_name=%s
            )
            """,
            (TABLE,),
        )
        if not cur.fetchone()[0]:
            return 0
        cur.execute(f"SELECT count(*) FROM {TABLE}")
        return int(cur.fetchone()[0])


def _max_feature_id(conn) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema='public' AND table_name=%s
            )
            """,
            (TABLE,),
        )
        if not cur.fetchone()[0]:
            return None
        cur.execute(f"SELECT max(feature_id) FROM {TABLE}")
        row = cur.fetchone()
        return None if row is None else row[0]


def _clear_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {TABLE}")


def _insert_features(conn, features: list[dict[str, Any]]) -> int:
    ensure_table(conn)
    _clear_table(conn)
    inserted = 0
    with conn.cursor() as cur:
        for index, feature in enumerate(features):
            props = dict(feature.get("properties") or {})
            importance = _importance_from_props(props)
            geom = feature.get("geometry")
            if not isinstance(geom, dict):
                raise _refuse("geometry: expected GeoJSON geometry, got absent")
            geojson = _as_multipolygon_geojson(geom)
            feature_id = f"cpm2016-{importance}-{index}"
            cur.execute(
                f"""
                INSERT INTO {TABLE} (feature_id, importance, geom)
                VALUES (
                  %s,
                  %s,
                  ST_Multi(
                    ST_CollectionExtract(
                      ST_MakeValid(
                        ST_SetSRID(ST_GeomFromGeoJSON(%s), 27700)
                      ),
                      3
                    )
                  )
                )
                """,
                (feature_id, importance, geojson),
            )
            inserted += 1
    return inserted


def load_fixture(
    conn,
    *,
    path: Path | None = None,
    replace: bool = True,
) -> int:
    """Fixture path: read the eight-class stub (or a synthetic GeoJSON)."""
    fixture_path = path or FIXTURE
    collection = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise _refuse("source: expected FeatureCollection")
    _require_27700(collection)
    features = list(collection.get("features") or [])
    if not features:
        raise _refuse("source: expected at least 1 feature, got 0")
    # Validate every IMPORTANCE before any write.
    for feature in features:
        _importance_from_props(dict(feature.get("properties") or {}))
    if not replace and _row_count(conn) > 0:
        raise _refuse(f"table {TABLE}: expected empty for non-replace load")
    before = _row_count(conn)
    before_max = _max_feature_id(conn)
    # Invalidate any national provenance before raw replacement (AMENDMENT-2).
    prov.invalidate_national_provenance()
    try:
        n = _insert_features(conn, features)
    except Exception:
        # Guaranteed by DELETE+INSERT in one autocommit connection only if we
        # validate first; re-raise after callers can still compare counts on
        # refusal paths that never call insert.
        _ = (before, before_max)
        raise
    prov.write_fixture_provenance(conn, rows=n)
    return n


def _open_gpkg_connection(source: Path) -> tuple[sqlite3.Connection, Path | None]:
    """Return (sqlite conn, temp_path_to_cleanup_or_None)."""
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".gpkg")]
            if len(names) != 1:
                raise _refuse(
                    f"source: expected exactly one .gpkg in zip, got {len(names)}"
                )
            raw = zf.read(names[0])
        tmp = tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False)
        try:
            tmp.write(raw)
            tmp.close()
            gpkg_path = Path(tmp.name)
            conn = sqlite3.connect(f"file:{gpkg_path.as_posix()}?mode=ro", uri=True)
            return conn, gpkg_path
        except Exception:
            Path(tmp.name).unlink(missing_ok=True)
            raise
    if source.suffix.lower() != ".gpkg":
        raise _refuse(
            f"source: expected .gpkg or .zip under data/external/, got {source.suffix}"
        )
    conn = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    return conn, None


def _quote_ident(ident: str) -> str:
    if not ident or not all(ch.isalnum() or ch == "_" for ch in ident):
        raise _refuse(f"GPKG_LAYER: unsafe identifier {ident!r}")
    return '"' + ident.replace('"', '""') + '"'


def count_gpkg_features(source: Path, layer: str) -> int:
    gpkg, tmp = _open_gpkg_connection(source)
    try:
        row = gpkg.execute(
            """
            SELECT 1 FROM gpkg_contents WHERE table_name = ? LIMIT 1
            """,
            (layer,),
        ).fetchone()
        if row is None:
            raise _refuse(f"GPKG_LAYER: expected pinned inner layer name, got absent")
        q = _quote_ident(layer)
        return int(gpkg.execute(f"SELECT count(*) FROM {q}").fetchone()[0])
    finally:
        gpkg.close()
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def _read_gpkg_features(source: Path, layer: str) -> list[dict[str, Any]]:
    gpkg, tmp = _open_gpkg_connection(source)
    try:
        meta = gpkg.execute(
            """
            SELECT srs_id, column_name
            FROM gpkg_geometry_columns
            WHERE table_name = ?
            LIMIT 1
            """,
            (layer,),
        ).fetchone()
        if meta is None:
            raise _refuse(f"GPKG_LAYER: expected pinned inner layer name, got absent")
        srs_id, geom_col = int(meta[0]), str(meta[1])
        if srs_id != 27700:
            raise _refuse(f"CRS: expected EPSG:27700, got EPSG:{srs_id}")

        # Prefer IMPORTANCE / importance column when present.
        cols = {
            r[1].lower(): r[1]
            for r in gpkg.execute(f"PRAGMA table_info({_quote_ident(layer)})")
        }
        importance_col = None
        for candidate in ("importance", "IMPORTANCE"):
            if candidate.lower() in cols:
                importance_col = cols[candidate.lower()]
                break
        if importance_col is None:
            raise _refuse(
                "IMPORTANCE: expected integer code in "
                f"{sorted(ALLOWED_IMPORTANCE)}, got None"
            )

        sql = (
            f"SELECT {_quote_ident(geom_col)}, {_quote_ident(importance_col)} "
            f"FROM {_quote_ident(layer)}"
        )
        features: list[dict[str, Any]] = []
        for geom_blob, importance_raw in gpkg.execute(sql):
            if geom_blob is None:
                continue
            wkb = gpkg_blob_to_wkb(bytes(geom_blob))
            geom = shapely_wkb.loads(wkb)
            if geom.is_empty:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {"IMPORTANCE": importance_raw},
                    "geometry": mapping(geom),
                }
            )
        return features
    finally:
        gpkg.close()
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def load_national(
    conn,
    *,
    source: Path | None = None,
    replace: bool = True,
) -> int:
    """National path: refuse without pins; before-INSERT raw-count match."""
    if GPKG_SHA256 is None or GPKG_SHA256 == "":
        raise _refuse("GPKG_SHA256: expected pinned sha256, got None")
    if GPKG_LAYER is None or GPKG_LAYER == "":
        raise _refuse("GPKG_LAYER: expected pinned inner layer name, got None")
    if GPKG_FEATURE_COUNT is None or (
        not isinstance(GPKG_FEATURE_COUNT, int) or GPKG_FEATURE_COUNT <= 0
    ):
        raise _refuse("GPKG_FEATURE_COUNT: expected pinned integer, got None")

    path = source or DEFAULT_NATIONAL
    if not path.is_file():
        raise _refuse(
            "source: expected pinned GPKG at data/external/, got absent"
        )

    actual_sha = _sha256_file(path)
    if actual_sha != GPKG_SHA256:
        raise _refuse(
            f"GPKG_SHA256: expected {GPKG_SHA256}, got {actual_sha}"
        )

    before = _row_count(conn)
    before_max = _max_feature_id(conn)

    actual_count = count_gpkg_features(path, GPKG_LAYER)
    if actual_count != int(GPKG_FEATURE_COUNT):
        # Prove no write: leave table untouched.
        if _row_count(conn) != before or _max_feature_id(conn) != before_max:
            raise RuntimeError("carbon_peatland mutated before INSERT refusal")
        raise _refuse(
            f"GPKG_FEATURE_COUNT: expected {GPKG_FEATURE_COUNT}, got {actual_count}"
        )

    features = _read_gpkg_features(path, GPKG_LAYER)
    # CRS already checked via srs_id; re-validate IMPORTANCE before write.
    for feature in features:
        _importance_from_props(dict(feature.get("properties") or {}))
    if len(features) != int(GPKG_FEATURE_COUNT):
        raise _refuse(
            f"GPKG_FEATURE_COUNT: expected {GPKG_FEATURE_COUNT}, got {len(features)}"
        )

    if not replace and before > 0:
        raise _refuse(f"table {TABLE}: expected empty for non-replace load")
    # Replacement started: drop any prior national receipt (AMENDMENT-2).
    prov.invalidate_national_provenance()
    try:
        n = _insert_features(conn, features)
    except Exception:
        # Do not write a national receipt; prior national stays invalid.
        raise
    prov.write_national_provenance(
        conn,
        rows=n,
        gpkg_sha256=GPKG_SHA256,
        gpkg_layer=GPKG_LAYER,
        gpkg_feature_count=GPKG_FEATURE_COUNT,
    )
    return n


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--fixture",
        action="store_true",
        help="Load the CI eight-class stub into carbon_peatland",
    )
    group.add_argument(
        "--national",
        action="store_true",
        help="Load the pinned national GPKG (refuses until pins exist)",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Override fixture GeoJSON or national zip/gpkg path",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        default=True,
        help="Replace existing carbon_peatland rows (default)",
    )
    args = parser.parse_args(argv)
    conn = connect()
    try:
        ensure_table(conn)
        if args.fixture:
            n = load_fixture(conn, path=args.input, replace=True)
            print(json.dumps({"path": "fixture", "rows": n, "table": TABLE}))
            return
        n = load_national(conn, source=args.input, replace=True)
        print(
            json.dumps(
                {
                    "path": "national",
                    "rows": n,
                    "table": TABLE,
                    "source_url": SOURCE_URL,
                    "field": FIELD,
                    "crs": CRS,
                }
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
