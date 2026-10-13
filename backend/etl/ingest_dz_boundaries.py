"""Ingest Scottish Government Data Zone boundaries (2011 / 2022) into PostGIS.

Downloads the official ATOM shapefile zips (OGL v3.0), reprojects to
EPSG:27700, loads ``dz_boundaries``, and records provenance (URL, vintage,
sha256) in ``dz_boundaries_meta``. Fails loudly on wrong national counts or
invalid codes.

Self-fetch uses a temp directory only — never writes ``data/external/``.
CI uses ``--fixture`` with a small synthetic GeoJSON (not real SG polygons).

Usage:
  export DATABASE_URL=postgresql://...
  python -m etl.ingest_dz_boundaries --fetch --replace
  python -m etl.ingest_dz_boundaries --fixture --replace
  python -m etl.ingest_dz_boundaries --vintage 2011 --input /path/to.zip

No £ rent figures are loaded or published.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import httpx
import psycopg2
import shapefile
import yaml
from pyproj import CRS, Transformer
from shapely import wkb
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import transform as shp_transform

from georgist.dz_lookup import vintage_for_code

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("etl.ingest_dz_boundaries")

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
SCHEMA_BOUNDS = REPO_ROOT / "backend" / "db" / "schema" / "002_dz_boundaries.sql"
SCHEMA_META = REPO_ROOT / "backend" / "db" / "schema" / "022_dz_boundaries_meta.sql"
FIXTURE_PATH = (
    REPO_ROOT / "backend" / "tests" / "fixtures" / "dz_boundaries_sample.geojson"
)

TABLE = "dz_boundaries"
META_TABLE = "dz_boundaries_meta"
TARGET_EPSG = 27700

OGL_LICENCE = "OGL-3.0"
OGL_LICENCE_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)
ATTRIBUTION = (
    "Contains public sector information licensed under the Open Government "
    "Licence v3.0. © Scottish Government, contains OS data © Crown copyright "
    "and database right."
)

# Published national zone counts (Scottish Government / NRS).
EXPECTED_COUNTS = {2011: 6976, 2022: 7392}

DEFAULT_URLS = {
    2011: "https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip",
    2022: "https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2022.zip",
}

CODE_FIELDS = (
    "DataZone",
    "datazone",
    "DZ",
    "dzcode",
    "DZCode",
    "code",
    "CODE",
)
NAME_FIELDS = (
    "Name",
    "name",
    "DZName",
    "dzname",
    "DZNAME",
    "datazone_name",
    "DataZoneName",
)


class IngestError(RuntimeError):
    """Loud failure for download, CRS, count, or code problems."""


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


def _cfg() -> dict[str, Any]:
    if not SOURCES_PATH.is_file():
        return {}
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        return (yaml.safe_load(handle) or {}).get("data_zone_boundaries") or {}


def source_url(vintage: int) -> str:
    cfg = _cfg()
    vintages = cfg.get("vintages") or {}
    entry = vintages.get(vintage) or vintages.get(str(vintage)) or {}
    return str(entry.get("url") or DEFAULT_URLS[vintage])


def pinned_sha256(vintage: int) -> str | None:
    cfg = _cfg()
    vintages = cfg.get("vintages") or {}
    entry = vintages.get(vintage) or vintages.get(str(vintage)) or {}
    digest = entry.get("sha256")
    return str(digest).lower() if digest else None


def ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        cur.execute(SCHEMA_BOUNDS.read_text(encoding="utf-8"))
        cur.execute(SCHEMA_META.read_text(encoding="utf-8"))
    conn.commit()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _refuse_external_write(path: Path) -> None:
    as_posix = str(path.resolve()).replace("\\", "/")
    if "/data/external" in as_posix:
        raise IngestError(
            "Refuse to download into data/external/. "
            "Self-fetch uses a temp directory only."
        )


def download_zip(url: str, dest: Path) -> bytes:
    _refuse_external_write(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s", url)
    with httpx.Client(
        timeout=httpx.Timeout(300.0, connect=30.0),
        follow_redirects=True,
        headers={"User-Agent": "scot-land/0.8 (research; dz-boundaries ingest)"},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        data = response.content
    if not data:
        raise IngestError(f"Empty download from {url}")
    dest.write_bytes(data)
    return data


def _pick_shapefile(extract_dir: Path) -> Path:
    matches = sorted(extract_dir.rglob("*.shp"))
    if not matches:
        raise IngestError(f"No .shp inside {extract_dir}")
    # Prefer the canonical SG DataZone boundary shapefile name when present.
    preferred = [
        p
        for p in matches
        if "datazone" in p.name.lower() and "bdry" in p.name.lower()
    ]
    return preferred[0] if preferred else matches[0]


def _crs_from_prj(shp_path: Path) -> CRS:
    prj = shp_path.with_suffix(".prj")
    if prj.is_file():
        try:
            return CRS.from_wkt(prj.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001 — loud re-raise with path
            raise IngestError(f"Unreadable .prj at {prj}: {exc}") from exc
    # SG ATOM packs are British National Grid when .prj is absent.
    logger.warning("%s: no .prj; assuming EPSG:%s", shp_path, TARGET_EPSG)
    return CRS.from_epsg(TARGET_EPSG)


def _to_multipolygon(geom) -> MultiPolygon | None:
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    parts: list[Polygon] = []
    for part in getattr(geom, "geoms", []):
        if isinstance(part, Polygon):
            parts.append(part)
        elif isinstance(part, MultiPolygon):
            parts.extend(list(part.geoms))
    if not parts:
        return None
    return MultiPolygon(parts)


def _field(props: dict[str, Any], candidates: Iterable[str]) -> Any:
    lower = {str(k).lower(): v for k, v in props.items()}
    for key in candidates:
        if key.lower() in lower and lower[key.lower()] not in (None, ""):
            return lower[key.lower()]
    return None


def iter_shapefile_rows(shp_path: Path, vintage: int) -> list[tuple[str, str | None, Any]]:
    """Return [(code, name, shapely MultiPolygon in EPSG:27700)]."""
    reader = shapefile.Reader(str(shp_path))
    field_names = [f[0] for f in reader.fields[1:]]
    source_crs = _crs_from_prj(shp_path)
    transformer = None
    if source_crs.to_epsg() != TARGET_EPSG:
        transformer = Transformer.from_crs(
            source_crs, CRS.from_epsg(TARGET_EPSG), always_xy=True
        ).transform

    rows: list[tuple[str, str | None, Any]] = []
    refused = 0
    for shape_rec in reader.iterShapeRecords():
        props = dict(zip(field_names, shape_rec.record))
        code = str(_field(props, CODE_FIELDS) or "").strip()
        if vintage_for_code(code) != vintage:
            refused += 1
            continue
        geom = shape(shape_rec.shape.__geo_interface__)
        if transformer is not None:
            geom = shp_transform(transformer, geom)
        multi = _to_multipolygon(geom)
        if multi is None:
            refused += 1
            continue
        if not multi.is_valid:
            multi = _to_multipolygon(multi.buffer(0))
            if multi is None:
                refused += 1
                continue
        name_raw = _field(props, NAME_FIELDS)
        name = str(name_raw).strip() if name_raw not in (None, "") else None
        rows.append((code, name, multi))
    if refused:
        logger.warning(
            "%s: refused %d features without a valid %s polygon/code",
            shp_path.name,
            refused,
            vintage,
        )
    if not rows:
        raise IngestError(f"{shp_path}: no valid {vintage} Data Zone polygons")
    return rows


def iter_geojson_rows(path: Path, vintage: int) -> list[tuple[str, str | None, Any]]:
    """Fixture / offline GeoJSON → EPSG:27700 MultiPolygons."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise IngestError(f"{path}: must be a GeoJSON FeatureCollection")
    crs_name = str(
        ((payload.get("crs") or {}).get("properties") or {}).get("name", "")
    )
    is_27700 = "27700" in crs_name
    to_bng = None
    if not is_27700:
        to_bng = Transformer.from_crs(4326, TARGET_EPSG, always_xy=True).transform

    rows: list[tuple[str, str | None, Any]] = []
    for feature in payload.get("features") or []:
        props = dict(feature.get("properties") or {})
        feat_vintage = props.get("vintage")
        if feat_vintage is not None and int(feat_vintage) != vintage:
            continue
        code = str(_field(props, CODE_FIELDS) or "").strip()
        if vintage_for_code(code) != vintage:
            continue
        geometry = feature.get("geometry")
        if not geometry:
            continue
        geom = shape(geometry)
        if to_bng is not None:
            geom = shp_transform(to_bng, geom)
        multi = _to_multipolygon(geom)
        if multi is None:
            continue
        name_raw = _field(props, NAME_FIELDS)
        name = str(name_raw).strip() if name_raw not in (None, "") else None
        rows.append((code, name, multi))
    if not rows:
        raise IngestError(f"{path}: no valid {vintage} features")
    return rows


def _insert_rows(
    conn,
    vintage: int,
    rows: list[tuple[str, str | None, Any]],
    *,
    replace: bool,
    source_id: str,
    licence: str,
) -> int:
    with conn.cursor() as cur:
        if replace:
            cur.execute(f"DELETE FROM {TABLE} WHERE vintage = %s", (vintage,))
        for code, name, geom in rows:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (code, vintage, name, geom, source_id, licence)
                VALUES (
                    %s, %s, %s,
                    ST_SetSRID(ST_GeomFromWKB(%s), {TARGET_EPSG}),
                    %s, %s
                )
                ON CONFLICT (code, vintage) DO UPDATE SET
                    name = EXCLUDED.name,
                    geom = EXCLUDED.geom,
                    source_id = EXCLUDED.source_id,
                    licence = EXCLUDED.licence,
                    updated_at = now()
                """,
                (code, vintage, name, wkb.dumps(geom), source_id, licence),
            )
        cur.execute(
            f"SELECT COUNT(*) FROM {TABLE} WHERE vintage = %s", (vintage,)
        )
        count = int(cur.fetchone()[0])
    conn.commit()
    return count


def write_provenance(
    conn,
    *,
    vintage: int,
    source_url: str,
    sha256: str,
    row_count: int,
    load_scope: str,
    licence: str = OGL_LICENCE,
    licence_url: str = OGL_LICENCE_URL,
    attribution: str = ATTRIBUTION,
) -> None:
    digest = sha256.lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise IngestError(f"sha256 must be 64-char hex, got {sha256!r}")
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO {META_TABLE} (
                vintage, source_url, sha256, row_count, licence, licence_url,
                attribution, load_scope, retrieved_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (vintage) DO UPDATE SET
                source_url = EXCLUDED.source_url,
                sha256 = EXCLUDED.sha256,
                row_count = EXCLUDED.row_count,
                licence = EXCLUDED.licence,
                licence_url = EXCLUDED.licence_url,
                attribution = EXCLUDED.attribution,
                load_scope = EXCLUDED.load_scope,
                retrieved_at = EXCLUDED.retrieved_at,
                updated_at = now()
            """,
            (
                vintage,
                source_url,
                digest,
                row_count,
                licence,
                licence_url,
                attribution,
                load_scope,
                date.today().isoformat(),
            ),
        )
    conn.commit()


def _assert_count(vintage: int, count: int, *, load_scope: str) -> None:
    if load_scope == "fixture":
        if count < 1:
            raise IngestError(f"fixture vintage {vintage}: expected ≥1 row, got {count}")
        return
    expected = EXPECTED_COUNTS[vintage]
    if count != expected:
        raise IngestError(
            f"vintage {vintage}: loaded {count} zones, expected published "
            f"count {expected}"
        )


def load_zip(
    conn,
    zip_path: Path,
    vintage: int,
    *,
    replace: bool,
    source_url: str,
    sha256: str,
    load_scope: str = "production",
) -> int:
    work = Path(tempfile.mkdtemp(prefix=f"dz{vintage}_"))
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(work)
        shp = _pick_shapefile(work)
        rows = iter_shapefile_rows(shp, vintage)
        count = _insert_rows(
            conn,
            vintage,
            rows,
            replace=replace,
            source_id=f"sg-dz-{vintage}@{sha256[:12]}",
            licence=OGL_LICENCE,
        )
        _assert_count(vintage, count, load_scope=load_scope)
        write_provenance(
            conn,
            vintage=vintage,
            source_url=source_url,
            sha256=sha256,
            row_count=count,
            load_scope=load_scope,
        )
        return count
    finally:
        shutil.rmtree(work, ignore_errors=True)


def load_fixture(conn, path: Path, *, replace: bool) -> dict[int, int]:
    digest = sha256_file(path)
    loaded: dict[int, int] = {}
    for vintage in (2011, 2022):
        try:
            rows = iter_geojson_rows(path, vintage)
        except IngestError:
            continue
        count = _insert_rows(
            conn,
            vintage,
            rows,
            replace=replace,
            source_id=f"fixture@{digest[:12]}",
            licence="synthetic-test-only",
        )
        _assert_count(vintage, count, load_scope="fixture")
        write_provenance(
            conn,
            vintage=vintage,
            source_url=str(path),
            sha256=digest,
            row_count=count,
            load_scope="fixture",
            licence="synthetic-test-only",
            licence_url="https://example.invalid/synthetic-test-only",
            attribution="Synthetic CI fixture — not Scottish Government data.",
        )
        loaded[vintage] = count
    if not loaded:
        raise IngestError(f"{path}: fixture contained no 2011/2022 zones")
    return loaded


def fetch_and_load(
    conn,
    *,
    vintages: Iterable[int] = (2011, 2022),
    replace: bool = True,
) -> dict[int, int]:
    tmp = Path(tempfile.mkdtemp(prefix="dz_boundaries_"))
    _refuse_external_write(tmp)
    loaded: dict[int, int] = {}
    try:
        for vintage in vintages:
            url = source_url(int(vintage))
            zip_path = tmp / f"SG_DataZoneBdry_{vintage}.zip"
            data = download_zip(url, zip_path)
            digest = sha256_bytes(data)
            pinned = pinned_sha256(int(vintage))
            if pinned and digest != pinned:
                raise IngestError(
                    f"vintage {vintage}: sha256 {digest} != pinned {pinned}"
                )
            count = load_zip(
                conn,
                zip_path,
                int(vintage),
                replace=replace,
                source_url=url,
                sha256=digest,
                load_scope="production",
            )
            loaded[int(vintage)] = count
            logger.info(
                "Loaded %s Data Zones for %s (sha256=%s…)",
                count,
                vintage,
                digest[:12],
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--fetch",
        action="store_true",
        help="Download SG ATOM shapefile zips for 2011 and 2022 (temp only)",
    )
    mode.add_argument(
        "--fixture",
        action="store_true",
        help="Load the small synthetic CI fixture (not real SG polygons)",
    )
    mode.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Local zip or .shp for a single --vintage (offline reload)",
    )
    parser.add_argument(
        "--vintage",
        type=int,
        choices=(2011, 2022),
        default=None,
        help="Required with --input; optional filter with --fetch",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        default=True,
        help="Replace rows for each loaded vintage (default)",
    )
    parser.add_argument(
        "--no-replace",
        action="store_false",
        dest="replace",
    )
    args = parser.parse_args(argv)

    conn = connect()
    try:
        ensure_tables(conn)
        if args.fixture:
            path = FIXTURE_PATH
            if not path.is_file():
                raise SystemExit(f"Fixture missing: {path}")
            loaded = load_fixture(conn, path, replace=args.replace)
            print(json.dumps({"mode": "fixture", "loaded": loaded}, indent=2))
            return 0

        if args.fetch:
            vintages = (args.vintage,) if args.vintage else (2011, 2022)
            loaded = fetch_and_load(conn, vintages=vintages, replace=args.replace)
            print(
                json.dumps(
                    {
                        "mode": "fetch",
                        "loaded": loaded,
                        "expected": {str(k): v for k, v in EXPECTED_COUNTS.items()
                                     if k in loaded},
                        "licence": OGL_LICENCE,
                        "epsg": TARGET_EPSG,
                    },
                    indent=2,
                )
            )
            return 0

        if args.input is None or args.vintage is None:
            raise SystemExit("--input requires --vintage 2011|2022")
        path = args.input.resolve()
        if not path.exists():
            raise SystemExit(f"Input not found: {path}")
        as_posix = str(path).replace("\\", "/")
        if "/data/processed" in as_posix:
            raise SystemExit(
                "Refuse to read Data Zone geometry from data/processed/. "
                "Use --fetch, --fixture, or a local zip/.shp."
            )
        if path.suffix.lower() == ".geojson":
            rows = iter_geojson_rows(path, args.vintage)
            digest = sha256_file(path)
            count = _insert_rows(
                conn,
                args.vintage,
                rows,
                replace=args.replace,
                source_id=f"local-geojson@{digest[:12]}",
                licence=OGL_LICENCE,
            )
            _assert_count(args.vintage, count, load_scope="production")
            write_provenance(
                conn,
                vintage=args.vintage,
                source_url=str(path),
                sha256=digest,
                row_count=count,
                load_scope="production",
            )
        elif path.suffix.lower() == ".zip":
            digest = sha256_file(path)
            count = load_zip(
                conn,
                path,
                args.vintage,
                replace=args.replace,
                source_url=str(path),
                sha256=digest,
            )
        elif path.suffix.lower() == ".shp":
            rows = iter_shapefile_rows(path, args.vintage)
            digest = sha256_file(path)
            count = _insert_rows(
                conn,
                args.vintage,
                rows,
                replace=args.replace,
                source_id=f"local-shp@{digest[:12]}",
                licence=OGL_LICENCE,
            )
            _assert_count(args.vintage, count, load_scope="production")
            write_provenance(
                conn,
                vintage=args.vintage,
                source_url=str(path),
                sha256=digest,
                row_count=count,
                load_scope="production",
            )
        else:
            raise SystemExit("Input must be .zip, .shp, or .geojson")
        print(
            json.dumps(
                {
                    "mode": "input",
                    "vintage": args.vintage,
                    "loaded": count,
                    "licence": OGL_LICENCE,
                    "epsg": TARGET_EPSG,
                },
                indent=2,
            )
        )
        return 0
    except IngestError as exc:
        raise SystemExit(f"ingest_dz_boundaries: {exc}") from exc
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
