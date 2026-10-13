"""Ingest RoS INSPIRE Index Polygons into PostGIS (inspire_parcels).

Self-fetches per-registration-county shapefile zips from the RoS INSPIRE
download service (MapCloud API; catalogue https://ros.locationcentre.co.uk/inspire/).
Downloads go to a temp directory — **never** under data/external/.

One-command usage (from backend/, with DATABASE_URL set):

  # Pilot — Edinburgh (Midlothian/MID) + Fife
  python -m etl.ingest_inspire_parcels --pilot --replace

  # All 33 RoS registration counties
  python -m etl.ingest_inspire_parcels --all --replace

  # CI synthetic fixture (not real RoS titles)
  python -m etl.ingest_inspire_parcels --fixture --replace

Optional local GeoJSON (gitignored path; not created by this loader):

  python -m etl.ingest_inspire_parcels --input /path/to/index_polygons.geojson --replace
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import tempfile
import time
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import httpx
import psycopg2
import shapefile
import yaml
from psycopg2 import extras
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform as shp_transform

from etl.inspire_counties import (
    BY_CODE,
    CATALOGUE_URL,
    DOWNLOAD_BASE,
    PILOT_CODES,
    REGISTRATION_COUNTIES,
    SERVICE_HOME,
    resolve_codes,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
TABLE = "inspire_parcels"
META_TABLE = "inspire_parcels_meta"
DEFAULT_INPUT = REPO_ROOT / "data" / "external" / "inspire" / "index_polygons.geojson"
DEFAULT_FIXTURE = (
    BACKEND_ROOT / "tests" / "fixtures" / "cadastral_index_polygons.geojson"
)

PRODUCTION_LICENCE = "OGL-3.0"
PRODUCTION_SOURCE_URL = "https://www.ros.gov.uk/open-data"
PRODUCTION_PRODUCT = "ROS INSPIRE Index Polygons (CP.CadastralParcel)"

_BNG_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


def _db_config() -> dict[str, Any]:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        return {"dsn": url}
    return {
        "dbname": os.getenv("WEALTH_DB_NAME", "scotland_wealth"),
        "user": os.getenv("WEALTH_DB_USER", "wealth_user"),
        "password": os.getenv("WEALTH_DB_PASSWORD", ""),
        "host": os.getenv("WEALTH_DB_HOST", "localhost"),
        "port": os.getenv("WEALTH_DB_PORT", "5432"),
    }


def connect():
    cfg = _db_config()
    if "dsn" in cfg:
        return psycopg2.connect(cfg["dsn"])
    return psycopg2.connect(**cfg)


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                inspire_id TEXT PRIMARY KEY,
                national_reference TEXT,
                label TEXT,
                area_sqm DOUBLE PRECISION,
                county TEXT,
                geom GEOMETRY(MultiPolygon, 4326) NOT NULL
            );
            """
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_geom "
            f"ON {TABLE} USING GIST (geom);"
        )
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {META_TABLE} (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
    conn.commit()


def _props(feature: dict[str, Any]) -> dict[str, Any]:
    return dict(feature.get("properties") or {})


def _inspire_id(props: dict[str, Any], feature: dict[str, Any], index: int) -> str:
    for key in ("inspireid", "inspire_id", "INSPIREID", "id"):
        value = props.get(key)
        if value:
            return str(value)
    fid = feature.get("id")
    if fid:
        return str(fid)
    return f"row-{index}"


def _download_base() -> str:
    """Prefer sources.yaml download_api; fall back to the MapCloud endpoint."""
    try:
        with SOURCES_PATH.open(encoding="utf-8") as handle:
            sources = yaml.safe_load(handle) or {}
        parcels = sources.get("parcels") or {}
        api = (parcels.get("download_api") or "").strip().rstrip("/")
        if api and "{code}" in api:
            return api.replace("/{code}", "").replace("{code}", "").rstrip("/")
        if api:
            return api
    except OSError:
        pass
    return DOWNLOAD_BASE


def download_county_zip(
    code: str,
    dest: Path,
    *,
    attempts: int = 5,
    base_delay: float = 1.0,
    client: httpx.Client | None = None,
) -> Path:
    """Download one registration-county zip with exponential backoff."""
    code = code.upper()
    if code not in BY_CODE:
        raise SystemExit(f"Unknown county code: {code}")
    base = _download_base()
    url = f"{base}/{code}"
    owns_client = client is None
    if owns_client:
        client = httpx.Client(
            timeout=httpx.Timeout(180.0, connect=30.0),
            follow_redirects=True,
            headers={"User-Agent": "scot-land/0.8 (research; inspire ingest)"},
        )
    assert client is not None
    last_exc: Exception | None = None
    try:
        for attempt in range(1, attempts + 1):
            try:
                logger.info(
                    "Downloading %s (%s) attempt %s/%s → %s",
                    code,
                    BY_CODE[code]["title"],
                    attempt,
                    attempts,
                    url,
                )
                response = client.get(url)
                if response.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"retryable {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                if not response.content.startswith(b"PK"):
                    raise ValueError(
                        f"Download for {code} is not a zip "
                        f"(content-type={response.headers.get('content-type')!r})"
                    )
                dest.write_bytes(response.content)
                logger.info("Saved %s (%s bytes)", dest.name, len(response.content))
                return dest
            except (httpx.HTTPError, ValueError, OSError) as exc:
                last_exc = exc
                if attempt >= attempts:
                    break
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "Download %s failed (%s); retry in %.1fs",
                    code,
                    exc,
                    delay,
                )
                time.sleep(delay)
    finally:
        if owns_client:
            client.close()
    raise SystemExit(f"Failed to download {code} after {attempts} attempts: {last_exc}")


def _shape_rings_bng(shp_shape: shapefile.Shape) -> list[list[tuple[float, float]]]:
    points = shp_shape.points or []
    if len(points) < 4:
        return []
    parts = list(shp_shape.parts or [0]) + [len(points)]
    rings: list[list[tuple[float, float]]] = []
    for i in range(len(parts) - 1):
        ring = [(float(x), float(y)) for x, y in points[parts[i] : parts[i + 1]]]
        if len(ring) >= 4:
            rings.append(ring)
    return rings


def _bng_rings_to_wgs84_multipolygon(
    rings: list[list[tuple[float, float]]],
) -> MultiPolygon | Polygon | None:
    if not rings:
        return None
    polys: list[Polygon] = []
    for ring in rings:
        try:
            poly = Polygon(ring)
        except Exception:
            continue
        if poly.is_empty:
            continue
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            continue
        if isinstance(poly, MultiPolygon):
            polys.extend(p for p in poly.geoms if not p.is_empty)
        elif isinstance(poly, Polygon):
            polys.append(poly)
    if not polys:
        return None
    geom_bng: Polygon | MultiPolygon = (
        polys[0] if len(polys) == 1 else MultiPolygon(polys)
    )

    def _project(x: float, y: float, z: float | None = None):
        return _BNG_TO_WGS84.transform(x, y)

    return shp_transform(_project, geom_bng)


def _pick_shapefile(extract_dir: Path, code: str) -> Path:
    """Prefer *_bng.shp (coordinates are OSGB36/BNG even when etrs89 is mislabelled)."""
    preferred = extract_dir / f"{code}_bng.shp"
    if preferred.is_file():
        return preferred
    matches = sorted(extract_dir.rglob("*.shp"))
    if not matches:
        raise FileNotFoundError(f"No .shp in extract for {code}")
    bng = [p for p in matches if p.name.lower().endswith("_bng.shp")]
    return bng[0] if bng else matches[0]


def iter_county_rows(zip_path: Path, code: str) -> Iterable[tuple]:
    """Yield DB row tuples from a county zip (BNG shapefile → WGS84)."""
    code = code.upper()
    with tempfile.TemporaryDirectory(prefix=f"inspire_{code}_") as tmp:
        work = Path(tmp)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(work)
        shp_path = _pick_shapefile(work, code)
        reader = shapefile.Reader(str(shp_path))
        field_names = [field[0] for field in reader.fields[1:]]
        for index, (record, shp_shape) in enumerate(
            zip(reader.iterRecords(), reader.iterShapes())
        ):
            props = dict(zip(field_names, record))
            rings = _shape_rings_bng(shp_shape)
            geom = _bng_rings_to_wgs84_multipolygon(rings)
            if geom is None or geom.is_empty:
                continue
            # Area in m² from BNG rings (before transform).
            area_sqm = None
            try:
                bng_polys = [Polygon(r) for r in rings if len(r) >= 4]
                area_sqm = float(sum(p.area for p in bng_polys if not p.is_empty))
            except Exception:
                area_sqm = None
            inspire_id = str(
                props.get("inspireid") or props.get("INSPIREID") or f"{code}-{index}"
            )
            national = str(
                props.get("nationalca")
                or props.get("nationalcadastralreference")
                or props.get("label")
                or ""
            )
            label = str(props.get("label") or national or inspire_id)
            county = str(props.get("county") or code)
            # Force MultiPolygon for the PostGIS column.
            if geom.geom_type == "Polygon":
                geom = MultiPolygon([geom])
            geojson = json.dumps(mapping(geom))
            yield (
                inspire_id,
                national or None,
                label,
                area_sqm,
                county,
                geojson,
            )


def _insert_rows(conn, rows: Iterable[tuple], *, replace: bool) -> int:
    with conn.cursor() as cur:
        if replace:
            cur.execute(f"TRUNCATE TABLE {TABLE};")
        sql = f"""
            INSERT INTO {TABLE}
                (inspire_id, national_reference, label, area_sqm, county, geom)
            VALUES (
                %s, %s, %s, %s, %s,
                ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
            )
            ON CONFLICT (inspire_id) DO UPDATE SET
                national_reference = EXCLUDED.national_reference,
                label = EXCLUDED.label,
                area_sqm = EXCLUDED.area_sqm,
                county = EXCLUDED.county,
                geom = EXCLUDED.geom;
        """
        batch: list[tuple] = []
        inserted = 0
        for row in rows:
            batch.append(row)
            if len(batch) >= 500:
                extras.execute_batch(cur, sql, batch, page_size=500)
                inserted += len(batch)
                batch.clear()
        if batch:
            extras.execute_batch(cur, sql, batch, page_size=500)
            inserted += len(batch)
    conn.commit()
    return inserted


def load_geojson(path: Path, conn, replace: bool) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise SystemExit("Input must be a GeoJSON FeatureCollection")
    features = payload.get("features") or []

    def _rows() -> Iterable[tuple]:
        for index, feature in enumerate(features):
            geometry = feature.get("geometry")
            if not geometry:
                continue
            props = _props(feature)
            inspire_id = _inspire_id(props, feature, index)
            national = str(
                props.get("nationalcadastralreference")
                or props.get("national_reference")
                or props.get("label")
                or ""
            )
            label = str(props.get("label") or national or inspire_id)
            area = props.get("area_sqm") or props.get("area") or props.get("AREA_SQM")
            county = props.get("county")
            # Normalise to MultiPolygon via shapely when possible.
            try:
                geom = shape(geometry)
                if geom.geom_type == "Polygon":
                    geom = MultiPolygon([geom])
                geojson = json.dumps(mapping(geom))
            except Exception:
                geojson = json.dumps(geometry)
            yield (
                inspire_id,
                national or None,
                label,
                float(area) if area is not None else None,
                str(county) if county is not None else None,
                geojson,
            )

    return _insert_rows(conn, _rows(), replace=replace)


def load_county_zips(
    codes: list[str],
    conn,
    *,
    replace: bool,
    work_dir: Path,
    attempts: int = 5,
) -> tuple[int, dict[str, int]]:
    """Download and load one or more county zips. Never writes under data/external.

    Returns (total_rows, per_county_counts). Source shapefiles are EPSG:27700
    (BNG); rows are stored as WGS84 for the map bbox contract.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    # Refuse accidental data/external targets.
    as_posix = str(work_dir.resolve()).replace("\\", "/")
    if "/data/external" in as_posix:
        raise SystemExit(
            "Refuse to download into data/external/. "
            "Self-fetch uses a temp directory only."
        )

    total = 0
    county_counts: dict[str, int] = {}
    first = True
    with httpx.Client(
        timeout=httpx.Timeout(180.0, connect=30.0),
        follow_redirects=True,
        headers={"User-Agent": "scot-land/0.8 (research; inspire ingest)"},
    ) as client:
        for code in codes:
            zip_path = work_dir / f"{code}.zip"
            download_county_zip(
                code, zip_path, attempts=attempts, client=client
            )
            count = _insert_rows(
                conn,
                iter_county_rows(zip_path, code),
                replace=(replace and first),
            )
            first = False
            total += count
            county_counts[code] = count
            logger.info("Loaded %s parcels from %s", count, code)
    return total, county_counts


def _harvest_year(vintage: str) -> int:
    match = re.search(r"(20\d{2})", str(vintage or ""))
    if match:
        return int(match.group(1))
    return date.today().year


def _county_counts_from_table(conn) -> dict[str, int]:
    """Per-county row counts after a GeoJSON / county load."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT COALESCE(county, 'unknown') AS county, COUNT(*)
            FROM {TABLE}
            GROUP BY 1
            ORDER BY 1
            """
        )
        return {str(code): int(n) for code, n in cur.fetchall()}


def write_load_meta(
    conn,
    *,
    count: int,
    vintage: str,
    load_scope: str,
    licence: str,
    source_url: str,
    input_path: Path | str,
    counties: str = "",
    county_counts: dict[str, int] | None = None,
) -> None:
    """Persist load provenance for the API (fixture vs production extract)."""
    year = _harvest_year(vintage)
    rows = {
        "load_scope": load_scope,
        "licence": licence,
        "source_url": source_url,
        "product": PRODUCTION_PRODUCT,
        "vintage": vintage,
        "harvest_year": str(year),
        "row_count": str(count),
        "input": str(input_path),
        "ingested_on": date.today().isoformat(),
        "counties": counties,
        "catalogue_url": CATALOGUE_URL,
        "service_home": SERVICE_HOME,
        "crs_source": "EPSG:27700",
        "publication_status": "ok" if load_scope != "fixture" else "fixture",
        "tagged": "live" if load_scope in ("production", "pilot", "subset") else load_scope,
    }
    if county_counts is not None:
        rows["county_counts"] = json.dumps(
            {str(k): int(v) for k, v in sorted(county_counts.items())},
            separators=(",", ":"),
        )
    with conn.cursor() as cur:
        extras.execute_batch(
            cur,
            f"""
            INSERT INTO {META_TABLE} (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
            """,
            list(rows.items()),
        )
    conn.commit()


def write_local_stamp(
    input_path: Path,
    count: int,
    vintage: str,
    *,
    load_scope: str,
    licence: str,
    source_url: str,
) -> Path:
    stamp_path = input_path.with_suffix(input_path.suffix + ".ingest.json")
    stamp = {
        "layer": "inspire_parcels",
        "product": PRODUCTION_PRODUCT,
        "licence": licence,
        "source_url": source_url,
        "load_scope": load_scope,
        "input": str(input_path),
        "row_count": count,
        "vintage": vintage,
        "ingested_on": date.today().isoformat(),
        "note": (
            "Local stamp only — raw geometry stays out of git. "
            "Self-fetch uses temp dirs (never data/external/). "
            "Synthetic fixtures must not be shown as real RoS titles."
        ),
    }
    stamp_path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    return stamp_path


def _assert_allowed_input(path: Path) -> None:
    resolved = path.resolve()
    as_posix = str(resolved).replace("\\", "/")
    if "data/processed" in as_posix:
        raise SystemExit(
            "Refuse to read cadastral geometry from data/processed/. "
            "Use --pilot / --all (self-fetch), --fixture, or a local --input."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--pilot",
        action="store_true",
        help=(
            "Download + load Edinburgh (Midlothian/MID) and Fife (FFE). "
            "One command; temp download only."
        ),
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help=(
            f"Download + load all {len(REGISTRATION_COUNTIES)} RoS registration "
            "counties. One command; temp download only."
        ),
    )
    mode.add_argument(
        "--fixture",
        action="store_true",
        help=(
            "Load the committed synthetic CI fixture "
            f"({DEFAULT_FIXTURE.relative_to(REPO_ROOT)}). "
            "Marks load_scope=fixture — not real RoS titles."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Local GeoJSON FeatureCollection (optional; not created by this loader)",
    )
    parser.add_argument(
        "--counties",
        nargs="+",
        default=None,
        help="Optional subset of titles/codes (with --pilot/--all unused; standalone)",
    )
    parser.add_argument(
        "--vintage",
        default=date.today().isoformat(),
        help="Dataset vintage date (YYYY-MM-DD) recorded in meta",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="TRUNCATE inspire_parcels before load",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=5,
        help="Download retry attempts per county (default 5)",
    )
    args = parser.parse_args()

    mode_flags = [
        args.pilot,
        args.all,
        args.fixture,
        args.input is not None,
        bool(args.counties),
    ]
    if sum(bool(x) for x in mode_flags) != 1:
        raise SystemExit(
            "Choose exactly one: --pilot | --all | --fixture | --input PATH | "
            "--counties …\nSee scripts/data/README-inspire.md."
        )

    conn = connect()
    tmp_root: Path | None = None
    try:
        ensure_table(conn)

        county_counts: dict[str, int] | None = None
        if args.fixture:
            input_path = DEFAULT_FIXTURE
            if not input_path.is_file():
                raise SystemExit(f"Fixture not found: {input_path}")
            _assert_allowed_input(input_path)
            count = load_geojson(input_path, conn, replace=args.replace)
            load_scope = "fixture"
            licence = "synthetic-test-only"
            source_url = str(DEFAULT_FIXTURE.relative_to(REPO_ROOT))
            counties = ""
            county_counts = _county_counts_from_table(conn)
            stamp = write_local_stamp(
                input_path,
                count,
                args.vintage,
                load_scope=load_scope,
                licence=licence,
                source_url=source_url,
            )
        elif args.input is not None:
            input_path = args.input
            if not input_path.is_file():
                raise SystemExit(f"Input not found: {input_path}")
            _assert_allowed_input(input_path)
            count = load_geojson(input_path, conn, replace=args.replace)
            load_scope = "production"
            licence = PRODUCTION_LICENCE
            source_url = PRODUCTION_SOURCE_URL
            counties = ""
            county_counts = _county_counts_from_table(conn)
            stamp = write_local_stamp(
                input_path,
                count,
                args.vintage,
                load_scope=load_scope,
                licence=licence,
                source_url=source_url,
            )
        else:
            if args.pilot:
                codes = list(PILOT_CODES)
                load_scope = "pilot"
            elif args.all:
                codes = resolve_codes(None)
                load_scope = "production"
            else:
                codes = resolve_codes(args.counties)
                load_scope = "production" if len(codes) >= len(REGISTRATION_COUNTIES) else "subset"
            tmp_root = Path(tempfile.mkdtemp(prefix="inspire_fetch_"))
            count, county_counts = load_county_zips(
                codes,
                conn,
                replace=args.replace,
                work_dir=tmp_root,
                attempts=max(1, int(args.attempts)),
            )
            licence = PRODUCTION_LICENCE
            source_url = PRODUCTION_SOURCE_URL
            counties = ",".join(codes)
            stamp = tmp_root / "ingest.json"
            stamp.write_text(
                json.dumps(
                    {
                        "layer": "inspire_parcels",
                        "load_scope": load_scope,
                        "counties": codes,
                        "county_counts": county_counts,
                        "row_count": count,
                        "licence": licence,
                        "catalogue_url": CATALOGUE_URL,
                        "download_api": _download_base() + "/{code}",
                        "vintage": args.vintage,
                        "harvest_year": _harvest_year(args.vintage),
                        "crs_source": "EPSG:27700",
                        "tagged": "live",
                        "ingested_on": date.today().isoformat(),
                        "note": "Temp fetch dir — deleted after load; never data/external.",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            input_path = stamp

        write_load_meta(
            conn,
            count=count,
            vintage=args.vintage,
            load_scope=load_scope,
            licence=licence,
            source_url=source_url,
            input_path=input_path,
            counties=counties,
            county_counts=county_counts,
        )
    finally:
        conn.close()
        if tmp_root is not None:
            shutil.rmtree(tmp_root, ignore_errors=True)

    logger.info(
        "Loaded %s parcels into %s (scope=%s). Stamp/meta written.",
        count,
        TABLE,
        load_scope,
    )


if __name__ == "__main__":
    main()
