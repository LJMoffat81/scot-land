"""Build Scotland land/inshore/offshore extent (offline; never in CI).

Sources: UKHO Maritime Limits & Boundaries, SI 1999/1126 lateral limits,
OS Boundary-Line ``country_region`` Scotland. Geometry is noded, flooded,
made disjoint, and simplified in EPSG:27700. Writes ``ref.extent`` /
``ref.extent_sub`` / ``ref.extent_buf50_sub`` and
``data/processed/gis/scotland_extent.27700.geojson``.

Optional Hatton/Faroe shelf is written to
``scotland_ext_shelf_optional.27700.geojson`` (outside the default clip).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from shapely import make_valid
from shapely.errors import GEOSException
from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    box,
    mapping,
    shape,
)
from shapely.ops import unary_union

from etl.extent_geom import (
    SEED_LAT,
    SEED_LON,
    BuiltZones,
    TransformStats,
    area_km2,
    densify_rhumb,
    flood_faces,
    is_art4_tsl_segment,
    load_ostn15_grid,
    make_disjoint_zones,
    make_ukho_transformers,
    polygonize_lines_snapped,
    solway_include_scottish_pockets,
    transform_linestring_ukho,
    transform_ukho,
    _as_multipolygon,
)
from etl.extent_sources import (
    UKHO_ATTRIBUTION,
    ExtentError,
    load_extent_sources,
    load_si_vertices,
)
from layers.catalog_copy import (
    SCOTLAND_EXTENT_LABEL,
    SCOTLAND_EXTENT_LAND_CREDIT,
    SCOTLAND_EXTENT_MARINE_CREDIT,
)

# Kept for etl.adapters.arcgis (and any other callers) that redact query tokens
# from logged URLs. SRC-A no longer fetches NMPi; the helper stays generic.
_TOKEN_RE = re.compile(r"(token=)[^&\s]+", re.IGNORECASE)


def redact(url: str) -> str:
    """Replace ``token=<x>`` with ``token=***`` in every log/receipt/manifest line."""
    return _TOKEN_RE.sub(r"\1***", url)

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = Path(__file__).resolve().parent / "sql"
OUT_PATH = REPO_ROOT / "data" / "processed" / "gis" / "scotland_extent.27700.geojson"
EXT_SHELF_PATH = (
    REPO_ROOT / "data" / "processed" / "gis" / "scotland_ext_shelf_optional.27700.geojson"
)
MANIFEST_PATH = REPO_ROOT / "data" / "processed" / "gis" / "manifest.csv"
DOCS_MANIFEST = REPO_ROOT / "docs" / "processed_data_manifest.md"
SOURCES_YAML = REPO_ROOT / "backend" / "layers" / "extent" / "scotland_extent_sources.yaml"
DEFAULT_SI_PATH = (
    Path("/workspace/scot-land-data/clip1_fetch/si1999_1126_lines.27700.geojson")
)
DEFAULT_UKHO_ZIP = Path("/workspace/scot-land-data/ukho_mlb.zip")
DEFAULT_BDLINE_ZIP = Path("/workspace/scot-land-data/bdline_gpkg_gb.zip")

# Expected zone areas (km²) from the Engineering Lead dry run; ±1% required.
EXPECTED_KM2 = {
    "land": 80_221.0,
    "inshore_0_12nm": 89_034.0,
    "offshore_12_200nm": 364_711.0,
    "union": 533_963.0,
}

ZONES = ("land", "inshore_0_12nm", "offshore_12_200nm")

UKHO_REQUIRED_CLASSES = (
    "Territorial Sea Limit",
    "Exclusive Economic Zone Limit",
    "Median line in absence of agreed maritime boundary",
)

AOI = box(-25.0, 53.5, 10.0, 65.0)
LABEL = (
    "Scotland land and sea area (illustrative; not prejudicial to delimitation). "
    + SCOTLAND_EXTENT_LABEL
)


def _dsn() -> str:
    dsn = (
        os.environ.get("ARCH1_TEST_DSN")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if not dsn:
        print("EXTENT: ARCH1_TEST_DSN or DATABASE_URL not set", flush=True)
        raise SystemExit(2)
    return dsn


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ensure_sql(conn) -> None:
    close_sql = (SQL_DIR / "close_slivers.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(close_sql)
        cur.execute("CREATE SCHEMA IF NOT EXISTS ref")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ref.extent (
              geography text NOT NULL,
              zone text NOT NULL,
              geom geometry(MultiPolygon, 27700) NOT NULL,
              sha256 text NOT NULL,
              built_at timestamptz NOT NULL,
              PRIMARY KEY (geography, zone)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ref.extent_sub (
              geography text NOT NULL,
              zone text NOT NULL,
              geom geometry(MultiPolygon, 27700) NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ref.extent_buf50_sub (
              geography text NOT NULL,
              geom geometry(MultiPolygon, 27700) NOT NULL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS extent_sub_geom_idx "
            "ON ref.extent_sub USING GIST (geom)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS extent_buf50_sub_geom_idx "
            "ON ref.extent_buf50_sub USING GIST (geom)"
        )
    conn.commit()


def _persist_ref_tables(conn, sha: str, built_at: str, zones_geom: dict) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ref.extent WHERE geography = 'scotland'")
        cur.execute("DELETE FROM ref.extent_sub WHERE geography = 'scotland'")
        cur.execute(
            "DELETE FROM ref.extent_buf50_sub WHERE geography = 'scotland'"
        )
        cur.execute("DROP TABLE IF EXISTS tmp_extent_final")
        cur.execute(
            "CREATE TEMP TABLE tmp_extent_final ("
            "zone text PRIMARY KEY, geom geometry(MultiPolygon, 27700) NOT NULL)"
        )
        for zone, geom in zones_geom.items():
            cur.execute(
                """
                INSERT INTO tmp_extent_final (zone, geom)
                VALUES (
                  %s,
                  ST_SetSRID(ST_GeomFromGeoJSON(%s), 27700)
                )
                """,
                (zone, json.dumps(mapping(geom))),
            )
        for zone in ZONES:
            cur.execute(
                """
                INSERT INTO ref.extent (geography, zone, geom, sha256, built_at)
                SELECT 'scotland', zone, geom, %s, %s::timestamptz
                FROM tmp_extent_final WHERE zone = %s
                """,
                (sha, built_at, zone),
            )
        cur.execute(
            """
            INSERT INTO ref.extent_sub (geography, zone, geom)
            SELECT
              'scotland',
              zone,
              ST_Multi((ST_Dump(ST_Subdivide(geom, 256))).geom)
            FROM tmp_extent_final
            """
        )
        cur.execute(
            """
            INSERT INTO ref.extent_buf50_sub (geography, geom)
            SELECT
              'scotland',
              ST_Multi((ST_Dump(ST_Subdivide(ST_Buffer(ST_Union(geom), 50), 256))).geom)
            FROM tmp_extent_final
            """
        )
    conn.commit()


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
            "key": "(zone)",
            "rows": str(rows),
            "sha256": sha256,
            "source_year": "",
        }
    )
    with MANIFEST_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)


def _update_docs_manifest(sha: str, source: str, attribution: str) -> None:
    marker = "scotland_extent.27700.geojson"
    line = (
        f"- `{marker}` (Scotland land/inshore/offshore extent from UKHO + "
        f"SI 1999/1126 + OS Boundary-Line, EPSG:27700; "
        f"sha256={sha}; {source}; licence OGL v3; "
        f"attribution: {attribution})\n"
    )
    if not DOCS_MANIFEST.is_file():
        return
    text = DOCS_MANIFEST.read_text(encoding="utf-8")
    if marker in text:
        lines = []
        for existing in text.splitlines(True):
            if marker in existing:
                lines.append(line)
            else:
                lines.append(existing)
        DOCS_MANIFEST.write_text("".join(lines), encoding="utf-8")
    else:
        DOCS_MANIFEST.write_text(text.rstrip() + "\n\n" + line, encoding="utf-8")
    # Optional shelf file row.
    shelf_marker = "scotland_ext_shelf_optional.27700.geojson"
    if EXT_SHELF_PATH.is_file():
        shelf_sha = _sha256_file(EXT_SHELF_PATH)
        shelf_line = (
            f"- `{shelf_marker}` (optional UK continental shelf beyond EEZ "
            f"next to Scottish waters — Hatton/Faroe; not in default clip; "
            f"sha256={shelf_sha}; licence OGL v3; attribution: {attribution})\n"
        )
        text = DOCS_MANIFEST.read_text(encoding="utf-8")
        if shelf_marker in text:
            lines = []
            for existing in text.splitlines(True):
                if shelf_marker in existing:
                    lines.append(shelf_line)
                else:
                    lines.append(existing)
            DOCS_MANIFEST.write_text("".join(lines), encoding="utf-8")
        else:
            DOCS_MANIFEST.write_text(
                text.rstrip() + "\n" + shelf_line, encoding="utf-8"
            )


def _manifest_sha_for(path: Path) -> str | None:
    if not MANIFEST_PATH.is_file():
        return None
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row.get("file") or "") == path.name:
                return (row.get("sha256") or "").lower() or None
    return None


def load_only(geojson_path: Path) -> dict:
    """Load a committed extent GeoJSON into ``ref.*`` (sha checked; no repair)."""
    path = geojson_path.resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise ExtentError(f"CLIP: extent file empty: {path}")

    raw = path.read_bytes()
    if not raw.strip():
        raise ExtentError(f"CLIP: extent file empty: {path}")

    actual = hashlib.sha256(raw).hexdigest()
    expected = _manifest_sha_for(path)
    if expected is None or actual != expected:
        raise ExtentError("CLIP: extent sha256 mismatch")

    try:
        collection = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ExtentError(f"CLIP: extent file not GeoJSON: {path}") from exc

    features = collection.get("features") or []
    if not features:
        raise ExtentError(f"CLIP: extent file empty: {path}")

    conn = psycopg2.connect(_dsn())
    try:
        _ensure_sql(conn)
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS tmp_extent_final")
            cur.execute(
                "CREATE TEMP TABLE tmp_extent_final ("
                "zone text PRIMARY KEY, geom geometry(MultiPolygon, 27700) NOT NULL)"
            )
            for feature in features:
                zone = (feature.get("properties") or {}).get("zone")
                if zone not in ZONES:
                    raise ExtentError(f"CLIP: zone {zone} invalid: unknown zone")
                geom_json = json.dumps(feature["geometry"])
                cur.execute(
                    """
                    SELECT ST_IsValid(g), ST_IsValidReason(g),
                           ST_Multi(ST_CollectionExtract(g, 3))
                    FROM (
                      SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), 27700) AS g
                    ) s
                    """,
                    (geom_json,),
                )
                ok, reason, multi = cur.fetchone()
                if not ok:
                    raise ExtentError(f"CLIP: zone {zone} invalid: {reason}")
                cur.execute(
                    "INSERT INTO tmp_extent_final (zone, geom) VALUES (%s, %s)",
                    (zone, multi),
                )
            built_at = datetime.now(timezone.utc).isoformat()
            # Persist via shared helper expecting shapely dict — rebuild from DB.
            zones_geom = {}
            for zone in ZONES:
                cur.execute(
                    "SELECT ST_AsGeoJSON(geom) FROM tmp_extent_final WHERE zone = %s",
                    (zone,),
                )
                zones_geom[zone] = shape(json.loads(cur.fetchone()[0]))
        conn.commit()
        _persist_ref_tables(conn, actual, built_at, zones_geom)
    finally:
        conn.close()
    return {"path": str(path), "sha256": actual}


def _load_land(bdline_zip: Path, expected_sha: str) -> MultiPolygon:
    # Fiona is offline-build-only; keep import lazy so CI test collection
    # (load_only / redact / ExtentError) does not require it.
    import fiona

    if _sha256_file(bdline_zip) != expected_sha:
        raise ExtentError("EXTENT: Boundary-Line sha256 mismatch")
    path = f"/vsizip/{bdline_zip.as_posix()}/Data/bdline_gb.gpkg"
    parts = []
    with fiona.open(path, layer="country_region") as src:
        for feature in src:
            props = dict(feature["properties"] or {})
            name = props.get("Name") or props.get("name") or props.get("NAME")
            if name != "Scotland":
                continue
            parts.append(shape(feature["geometry"]))
    if not parts:
        raise ExtentError("EXTENT: Boundary-Line Scotland missing")
    land = _as_multipolygon(unary_union(parts))
    # Simplify-preserve-topology to 25 m for noding only (dry-run land).
    return _as_multipolygon(land.simplify(25.0, preserve_topology=True))


def _ukho_lines_from_shape(shp_shape) -> list[LineString]:
    """Convert a pyshp polyline shape into shapely LineStrings (WGS 84)."""
    points = list(shp_shape.points or [])
    if len(points) < 2:
        return []
    parts = list(shp_shape.parts or [0])
    lines: list[LineString] = []
    for i, start in enumerate(parts):
        end = parts[i + 1] if i + 1 < len(parts) else len(points)
        coords = points[start:end]
        if len(coords) >= 2:
            lines.append(LineString(coords))
    return lines


def _load_ukho(
    ukho_zip: Path,
    *,
    expected_sha: str,
    ostn,
    helmert,
    stats: TransformStats,
) -> dict[str, list[LineString]]:
    # pyshp is in requirements.txt so T7/T8 can drive this loader in CI.
    import shapefile

    if _sha256_file(ukho_zip) != expected_sha:
        raise ExtentError("EXTENT: UKHO sha256 mismatch")
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(ukho_zip) as zf:
            zf.extractall(tmp)
        shp = next(Path(tmp).rglob("*.shp"))
        buckets: dict[str, list[LineString]] = {
            "tsl": [],
            "eez": [],
            "median": [],
            "iom": [],
            "art4": [],
            "continental_shelf": [],
            "boundary_faroe_ireland": [],
        }
        with shapefile.Reader(str(shp)) as reader:
            fields = [f[0] for f in reader.fields[1:]]
            for sr in reader.iterShapeRecords():
                props = dict(zip(fields, sr.record, strict=False))
                line_geoms = _ukho_lines_from_shape(sr.shape)
                if not line_geoms:
                    continue
                geom = (
                    line_geoms[0]
                    if len(line_geoms) == 1
                    else MultiLineString(line_geoms)
                )
                if not geom.intersects(AOI):
                    continue
                state = props.get("State")
                feat = props.get("Feature") or ""
                boundary = props.get("Boundary") or ""
                transformed = []
                for lg in line_geoms:
                    if lg.is_empty:
                        continue
                    transformed.append(
                        transform_linestring_ukho(
                            list(lg.coords),
                            ostn=ostn,
                            helmert=helmert,
                            stats=stats,
                        )
                    )
                if not transformed:
                    continue
                line = (
                    transformed[0]
                    if len(transformed) == 1
                    else LineString(
                        [c for t in transformed for c in t.coords]
                    )
                )

                if is_art4_tsl_segment(geom, props):
                    buckets["art4"].append(
                        transform_linestring_ukho(
                            list(geom.coords)
                            if geom.geom_type == "LineString"
                            else list(line_geoms[0].coords),
                            ostn=ostn,
                            helmert=helmert,
                            stats=stats,
                        )
                    )
                    continue

                if feat == "Territorial Sea Limit" and state == "United Kingdom":
                    buckets["tsl"].append(line)
                elif feat == "Exclusive Economic Zone Limit" and state == "United Kingdom":
                    buckets["eez"].append(line)
                elif feat.startswith("Median line") and state == "United Kingdom":
                    buckets["median"].append(line)
                elif state == "Isle of Man" and feat in (
                    "Territorial Sea Limit",
                    "National Limit",
                ):
                    buckets["iom"].append(line)
                elif feat == "Continental Shelf" and state == "United Kingdom":
                    buckets["continental_shelf"].append(line)
                elif feat == "Boundary" and boundary in (
                    "Faroe Islands",
                    "Ireland",
                    "Norway",
                ):
                    # Included for noding only — not flood barriers (§3.5).
                    buckets["boundary_faroe_ireland"].append(line)

        if not buckets["eez"]:
            raise ExtentError(
                "EXTENT: UKHO class missing: Exclusive Economic Zone Limit"
            )
        if not buckets["tsl"]:
            raise ExtentError("EXTENT: UKHO class missing: Territorial Sea Limit")
        if not buckets["median"]:
            raise ExtentError(
                "EXTENT: UKHO class missing: Median line in absence of agreed "
                "maritime boundary"
            )
        return buckets


def _seed_xy_27700(ostn, helmert, stats: TransformStats) -> tuple[float, float]:
    return transform_ukho(SEED_LON, SEED_LAT, ostn=ostn, helmert=helmert, stats=stats)


def build_geometry(
    *,
    sources_yaml: Path = SOURCES_YAML,
    si_path: Path = DEFAULT_SI_PATH,
    ukho_zip: Path = DEFAULT_UKHO_ZIP,
    bdline_zip: Path = DEFAULT_BDLINE_ZIP,
    ostn15_grid: Path | None = None,
) -> BuiltZones:
    cfg = load_extent_sources(sources_yaml)
    ukho_src = cfg.get("ukho-mlb")
    si_src = cfg.get("si-1999-1126")
    os_src = cfg.get("os-boundary-line")
    ostn_src = cfg.get("ostn15")

    grid_path = ostn15_grid
    if grid_path is None:
        env = os.environ.get("PROJ_DATA")
        if env:
            candidate = Path(env) / "uk_os_OSTN15_NTv2_OSGBtoETRS.tif"
            if candidate.is_file():
                grid_path = candidate
        if grid_path is None:
            grid_path = Path("/workspace/scot-land-data/uk_os_OSTN15_NTv2_OSGBtoETRS.tif")
    grid_path = load_ostn15_grid(grid_path, expected_sha256=ostn_src.sha256)
    ostn, helmert = make_ukho_transformers(grid_path)
    stats = TransformStats()

    si_parts = load_si_vertices(si_path, expected_sha256=si_src.sha256)
    densified: dict[str, LineString] = {}
    for part, verts in si_parts.items():
        dens = densify_rhumb(verts, step_m=cfg.densify_max_m)
        densified[part] = LineString(dens)

    land = _load_land(bdline_zip, os_src.sha256)
    ukho = _load_ukho(
        ukho_zip,
        expected_sha=ukho_src.sha256,
        ostn=ostn,
        helmert=helmert,
        stats=stats,
    )

    # Coast for noding (land exterior rings).
    coast_lines: list[LineString] = []
    for poly in land.geoms if land.geom_type == "MultiPolygon" else [land]:
        coast_lines.append(LineString(poly.exterior.coords))
        for ring in poly.interiors:
            coast_lines.append(LineString(ring.coords))

    barrier_lines: list[LineString] = []
    for line in densified.values():
        barrier_lines.append(line)
    for line in ukho["eez"] + ukho["median"] + ukho["iom"] + ukho["art4"]:
        barrier_lines.append(line)

    # Full node set: barriers + UK TSL + coast + Faroe/Ireland/Norway Boundary
    # + continental shelf (noding / optional zone). Boundary lines are NOT flood
    # barriers (§3.5).
    node_lines = (
        list(barrier_lines)
        + list(ukho["tsl"])
        + list(ukho["boundary_faroe_ireland"])
        + list(ukho["continental_shelf"])
        + coast_lines
    )
    faces, snap_count, snap_max = polygonize_lines_snapped(
        node_lines, snap_m=cfg.snap_m
    )

    seed_xy = _seed_xy_27700(ostn, helmert, TransformStats())
    seed_face, other_faces = flood_faces(
        faces,
        barrier_lines=barrier_lines,
        land=land,
        seed_xy=seed_xy,
    )

    inshore_raw = _as_multipolygon(unary_union(other_faces)) if other_faces else MultiPolygon([])
    offshore_raw = _as_multipolygon(seed_face)

    # Remove land from sea faces.
    inshore_raw = _as_multipolygon(make_valid(inshore_raw.difference(land)))
    offshore_raw = _as_multipolygon(make_valid(offshore_raw.difference(land)))

    land_z, inshore_z, offshore_z = make_disjoint_zones(
        land, inshore_raw, offshore_raw, simplify_m=25.0
    )

    # §3.7 Upper Solway: Scottish-side faces along densified s1 (no land cut).
    inshore_z = solway_include_scottish_pockets(
        land=land_z,
        inshore=inshore_z,
        offshore=offshore_z,
        si_s1=densified["sch1_pt2_s1"],
        s1_vertices=si_parts["sch1_pt2_s1"],
        aoi_bounds=cfg.solway.aoi,
        corridor_m=cfg.solway.corridor_m,
    )
    inshore_z = _as_multipolygon(make_valid(inshore_z.difference(land_z)))
    # Keep zones disjoint after the Solway add.
    offshore_z = _as_multipolygon(
        make_valid(offshore_z.difference(unary_union([land_z, inshore_z])))
    )

    # Optional ext shelf: Hatton + Faroe strip beyond EEZ.
    ext_shelf = _build_ext_shelf(
        faces=faces,
        land=land_z,
        inshore=inshore_z,
        offshore=offshore_z,
        eez=ukho["eez"],
        continental_shelf=ukho["continental_shelf"],
        boundary_lines=ukho["boundary_faroe_ireland"],
        seed_face=seed_face,
    )

    return BuiltZones(
        land=land_z,
        inshore_0_12nm=inshore_z,
        offshore_12_200nm=offshore_z,
        ext_shelf_optional=ext_shelf,
        helmert_fallback=stats.helmert_fallback,
        snap_count=snap_count,
        snap_max_m=snap_max,
        sources=[ukho_src.id, si_src.id, os_src.id],
        source_dates={
            ukho_src.id: ukho_src.published,
            si_src.id: si_src.published,
            os_src.id: os_src.published,
        },
    )


def _build_ext_shelf(
    *,
    faces: list,
    land,
    inshore,
    offshore,
    eez: list[LineString],
    continental_shelf: list[LineString],
    boundary_lines: list[LineString],
    seed_face,
) -> MultiPolygon | None:
    """Hatton face + Faroe shelf strips outside the default Scottish waters."""
    scottish = make_valid(unary_union([land, inshore, offshore]))
    eez_u = unary_union(eez) if eez else None
    cs_u = unary_union(continental_shelf) if continental_shelf else None
    if eez_u is None or cs_u is None:
        return None
    candidates = []
    for face in faces:
        face = make_valid(face)
        if face.is_empty or face.area < 1e6:  # < 1 km²
            continue
        try:
            overlap = face.intersection(scottish).area
        except GEOSException:
            continue
        if overlap > face.area * 0.5:
            continue
        # Outside default clip, touching EEZ and continental shelf.
        if face.distance(eez_u) < 50.0 and face.distance(cs_u) < 50.0:
            candidates.append(face)
    if not candidates:
        return None
    return _as_multipolygon(unary_union([make_valid(c) for c in candidates]))


def _write_extent_geojson(built: BuiltZones, built_at: str) -> tuple[str, int]:
    features = []
    for zone, geom in (
        ("land", built.land),
        ("inshore_0_12nm", built.inshore_0_12nm),
        ("offshore_12_200nm", built.offshore_12_200nm),
    ):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "zone": zone,
                    "label": LABEL,
                    "sources": list(built.sources),
                    "source_dates": dict(built.source_dates),
                    "built_at": built_at,
                },
                "geometry": mapping(geom),
            }
        )
    collection = {
        "type": "FeatureCollection",
        "name": "scotland_extent",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::27700"},
        },
        "features": features,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(collection, separators=(",", ":"))
    OUT_PATH.write_text(body, encoding="utf-8")
    size = OUT_PATH.stat().st_size
    sha = hashlib.sha256(OUT_PATH.read_bytes()).hexdigest()
    if size >= 8 * 1024 * 1024:
        raise ExtentError("EXTENT: GeoJSON >= 8 MB")
    print(f"EXTENT: wrote {OUT_PATH} bytes={size} sha256={sha}")
    return sha, size


def _write_ext_shelf(built: BuiltZones, built_at: str) -> str | None:
    if built.ext_shelf_optional is None or built.ext_shelf_optional.is_empty:
        return None
    features = []
    geom = built.ext_shelf_optional
    polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    for poly in polys:
        # Drop numerical dust faces (< 0.001 km²) left by noding.
        if poly.is_empty or poly.area < 1_000.0:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "zone": "ext_shelf_optional",
                    "label": LABEL,
                    "note": (
                        "Seabed rights only; not Scottish waters; "
                        "outside the default clip"
                    ),
                    "sources": list(built.sources),
                    "source_dates": dict(built.source_dates),
                    "built_at": built_at,
                },
                "geometry": mapping(poly),
            }
        )
    if not features:
        return None
    collection = {
        "type": "FeatureCollection",
        "name": "scotland_ext_shelf_optional",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::27700"},
        },
        "features": features,
    }
    body = json.dumps(collection, separators=(",", ":"))
    EXT_SHELF_PATH.write_text(body, encoding="utf-8")
    sha = hashlib.sha256(EXT_SHELF_PATH.read_bytes()).hexdigest()
    print(f"EXTENT: wrote {EXT_SHELF_PATH} sha256={sha}")
    return sha


def build(
    *,
    sources_yaml: Path = SOURCES_YAML,
    si_path: Path = DEFAULT_SI_PATH,
    ukho_zip: Path = DEFAULT_UKHO_ZIP,
    bdline_zip: Path = DEFAULT_BDLINE_ZIP,
    ostn15_grid: Path | None = None,
    write_db: bool = True,
) -> dict:
    built_at = datetime.now(timezone.utc).isoformat()
    built = build_geometry(
        sources_yaml=sources_yaml,
        si_path=si_path,
        ukho_zip=ukho_zip,
        bdline_zip=bdline_zip,
        ostn15_grid=ostn15_grid,
    )
    stats = {
        "land": {"km2": area_km2(built.land)},
        "inshore_0_12nm": {"km2": area_km2(built.inshore_0_12nm)},
        "offshore_12_200nm": {"km2": area_km2(built.offshore_12_200nm)},
        "union": {
            "km2": area_km2(
                unary_union(
                    [built.land, built.inshore_0_12nm, built.offshore_12_200nm]
                )
            )
        },
    }
    for zone, expected in EXPECTED_KM2.items():
        got = stats[zone]["km2"]
        lo, hi = expected * 0.99, expected * 1.01
        print(
            f"EXTENT: zone={zone} km2={got:.1f} "
            f"(expected {expected} ±1%)"
        )
        if not (lo <= got <= hi):
            raise ExtentError(
                f"EXTENT: {zone} area {got:.1f} outside expected ±1%"
            )
    sha, size = _write_extent_geojson(built, built_at)
    shelf_sha = _write_ext_shelf(built, built_at)

    cfg = load_extent_sources(sources_yaml)
    ukho_src = cfg.get("ukho-mlb")
    si_src = cfg.get("si-1999-1126")
    os_src = cfg.get("os-boundary-line")
    attribution = f"{SCOTLAND_EXTENT_MARINE_CREDIT} {SCOTLAND_EXTENT_LAND_CREDIT}"
    source = (
        f"ukho={ukho_src.url} sha256={ukho_src.sha256}; "
        f"si={si_src.url} sha256={si_src.sha256}; "
        f"os={os_src.url} sha256={os_src.sha256}; "
        f"fetched={ukho_src.fetched}"
    )
    _upsert_manifest_row(
        file_name=OUT_PATH.name,
        source=source,
        attribution=attribution,
        rows=3,
        sha256=sha,
    )
    if shelf_sha:
        _upsert_manifest_row(
            file_name=EXT_SHELF_PATH.name,
            source=source,
            attribution=attribution,
            rows=len(json.loads(EXT_SHELF_PATH.read_text())["features"]),
            sha256=shelf_sha,
        )
    _update_docs_manifest(sha, source, attribution)

    if write_db:
        conn = psycopg2.connect(_dsn())
        try:
            _ensure_sql(conn)
            _persist_ref_tables(
                conn,
                sha,
                built_at,
                {
                    "land": built.land,
                    "inshore_0_12nm": built.inshore_0_12nm,
                    "offshore_12_200nm": built.offshore_12_200nm,
                },
            )
        finally:
            conn.close()

    print(
        f"EXTENT: helmert_fallback={built.helmert_fallback} "
        f"snaps={built.snap_count} snap_max_m={built.snap_max_m:.1f}"
    )
    return {
        "path": str(OUT_PATH),
        "sha256": sha,
        "bytes": size,
        "stats": stats,
        "helmert_fallback": built.helmert_fallback,
        "snap_count": built.snap_count,
        "source": source,
        "built": built,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--load-only",
        metavar="GEOJSON",
        help="Load committed GeoJSON into ref.* (sha checked; no repair)",
    )
    parser.add_argument(
        "--sources-yaml",
        type=Path,
        default=SOURCES_YAML,
        help="Path to scotland_extent_sources.yaml",
    )
    parser.add_argument("--si-path", type=Path, default=DEFAULT_SI_PATH)
    parser.add_argument("--ukho-zip", type=Path, default=DEFAULT_UKHO_ZIP)
    parser.add_argument("--bdline-zip", type=Path, default=DEFAULT_BDLINE_ZIP)
    parser.add_argument("--ostn15-grid", type=Path, default=None)
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Build GeoJSON/manifest only (skip PostGIS write)",
    )
    args = parser.parse_args(argv)
    if args.load_only:
        result = load_only(Path(args.load_only))
        print(f"EXTENT: load-only ok sha256={result['sha256']}")
        return
    result = build(
        sources_yaml=args.sources_yaml,
        si_path=args.si_path,
        ukho_zip=args.ukho_zip,
        bdline_zip=args.bdline_zip,
        ostn15_grid=args.ostn15_grid,
        write_db=not args.no_db,
    )
    stats = result["stats"]
    print(
        "EXTENT: ok "
        f"union_km2={stats['union']['km2']:.1f} bytes={result['bytes']} "
        f"sha256={result['sha256']} helmert={result['helmert_fallback']}"
    )


if __name__ == "__main__":
    main()
