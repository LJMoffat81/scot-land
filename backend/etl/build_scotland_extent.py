"""Build Scotland land/inshore/offshore extent in PostGIS (offline; never in CI).

Sources: 32 councils (or optional dz2011), 21 NMPi assessment areas (11 SMR +
10 OMR). Geometry is closed, unioned, made disjoint, and simplified inside
PostGIS. Writes ``ref.extent`` / ``ref.extent_sub`` / ``ref.extent_buf50_sub``
and ``data/processed/gis/scotland_extent.27700.geojson``.

Token: env ``NMPI_WFS_TOKEN`` only. Every logged URL uses ``token=***``.
OS Boundary-Line is documented but not used.
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
from urllib.parse import urlencode

import certifi
import httpx
import psycopg2
import psycopg2.extras

REPO_ROOT = Path(__file__).resolve().parents[2]


class ExtentError(Exception):
    """Scotland extent load failure (message prefix ``CLIP: ``)."""

SQL_DIR = Path(__file__).resolve().parent / "sql"
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

# Expected zone areas (km²) from the Engineering Lead dry run; ±1% required.
EXPECTED_KM2 = {
    "land": 80_227.0,
    "inshore_0_12nm": 87_407.0,
    "offshore_12_200nm": 532_889.0,
    "union": 700_511.0,
}
EXPECTED_VERTICES_TOL = 0.10
EXPECTED_PARTS_TOL = 0.10

_TOKEN_RE = re.compile(r"(token=)[^&\s]+", re.IGNORECASE)
ZONES = ("land", "inshore_0_12nm", "offshore_12_200nm")


def redact(url: str) -> str:
    """Replace ``token=<x>`` with ``token=***`` in every log/receipt/manifest line."""
    return _TOKEN_RE.sub(r"\1***", url)


def _ssl_verify() -> str:
    if not EXTRA_CA.is_file():
        print(f"EXTENT: missing CA file {EXTRA_CA}", file=sys.stderr)
        sys.exit(2)
    bundle = Path("/tmp/scot_land_nmpi_ca_bundle.pem")
    bundle.write_bytes(Path(certifi.where()).read_bytes() + b"\n" + EXTRA_CA.read_bytes())
    ssl.create_default_context(cafile=str(bundle))
    return str(bundle)


def _require_token() -> str:
    token = os.environ.get("NMPI_WFS_TOKEN")
    if not token:
        print("EXTENT: NMPI_WFS_TOKEN not set", file=sys.stderr)
        sys.exit(2)
    return token


def _dsn() -> str:
    dsn = (
        os.environ.get("ARCH1_TEST_DSN")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if not dsn:
        print("EXTENT: ARCH1_TEST_DSN or DATABASE_URL not set", file=sys.stderr)
        sys.exit(2)
    return dsn


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


def _wfs_geojson(
    client: httpx.Client, type_name: str, token: str
) -> tuple[list[dict], str]:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": type_name,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "token": token,
    }
    logged = redact(f"{NMPI_WFS}?{urlencode(params)}")
    response = client.get(NMPI_WFS, params=params)
    if response.status_code != 200:
        print(f"EXTENT: WFS {response.status_code} for {logged}", file=sys.stderr)
        response.raise_for_status()
    payload = response.json()
    return list(payload.get("features") or []), logged


def _zone_for_area(props: dict, smr_names: set[str]) -> str:
    name = ""
    for key in ("name", "NAME", "Name", "objnam", "area_name"):
        if props.get(key):
            name = str(props[key]).strip()
            break
    smr_lower = {n.lower() for n in smr_names}
    if name in smr_names or name.lower() in smr_lower:
        return "inshore_0_12nm"
    return "offshore_12_200nm"


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


def _insert_parts(conn, rows: list[tuple[str, str]]) -> None:
    """rows: (zone, geojson_geometry_text in 27700)."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS tmp_extent_parts")
        cur.execute(
            "CREATE TEMP TABLE tmp_extent_parts ("
            "zone text NOT NULL, geom geometry(Geometry, 27700) NOT NULL)"
        )
        psycopg2.extras.execute_batch(
            cur,
            """
            INSERT INTO tmp_extent_parts (zone, geom)
            VALUES (
              %s,
              ST_SetSRID(ST_GeomFromGeoJSON(%s), 27700)
            )
            """,
            rows,
            page_size=100,
        )
    conn.commit()


def _build_zones_in_db(conn) -> None:
    # Keep temp tables for the rest of the connection (no ON COMMIT DROP).
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS tmp_extent_union")
        cur.execute("DROP TABLE IF EXISTS tmp_extent_disjoint")
        cur.execute("DROP TABLE IF EXISTS tmp_extent_final")
        cur.execute(
            """
            CREATE TEMP TABLE tmp_extent_union AS
            SELECT
              zone,
              ST_Multi(
                ST_CollectionExtract(
                  ST_MakeValid(ST_Union(ref.close_slivers(geom))),
                  3
                )
              ) AS geom
            FROM tmp_extent_parts
            GROUP BY zone
            """
        )
        cur.execute(
            """
            CREATE TEMP TABLE tmp_extent_disjoint AS
            WITH land AS (
              SELECT geom FROM tmp_extent_union WHERE zone = 'land'
            ),
            inshore_raw AS (
              SELECT geom FROM tmp_extent_union WHERE zone = 'inshore_0_12nm'
            ),
            offshore_raw AS (
              SELECT geom FROM tmp_extent_union WHERE zone = 'offshore_12_200nm'
            ),
            inshore AS (
              SELECT ST_Multi(
                ST_CollectionExtract(
                  ST_MakeValid(ST_Difference(i.geom, l.geom)),
                  3
                )
              ) AS geom
              FROM inshore_raw i, land l
            ),
            offshore AS (
              SELECT ST_Multi(
                ST_CollectionExtract(
                  ST_MakeValid(
                    ST_Difference(o.geom, ST_Union(l.geom, i.geom))
                  ),
                  3
                )
              ) AS geom
              FROM offshore_raw o, land l, inshore i
            )
            SELECT 'land'::text AS zone, geom FROM land
            UNION ALL
            SELECT 'inshore_0_12nm', geom FROM inshore
            UNION ALL
            SELECT 'offshore_12_200nm', geom FROM offshore
            """
        )
        cur.execute(
            """
            CREATE TEMP TABLE tmp_extent_final AS
            SELECT
              zone,
              ST_Multi(
                ST_CollectionExtract(
                  ST_MakeValid(ST_SimplifyPreserveTopology(geom, 25.0)),
                  3
                )
              ) AS geom
            FROM tmp_extent_disjoint
            """
        )
        for zone in ZONES:
            cur.execute(
                "SELECT ST_IsValid(geom), ST_IsValidReason(geom) "
                "FROM tmp_extent_final WHERE zone = %s",
                (zone,),
            )
            row = cur.fetchone()
            if row is None:
                print(f"EXTENT: zone {zone} missing after build", file=sys.stderr)
                sys.exit(3)
            ok, reason = row
            if not ok:
                print(
                    f"EXTENT: zone {zone} invalid after build: {reason}",
                    file=sys.stderr,
                )
                sys.exit(3)


def _zone_stats(conn) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    with conn.cursor() as cur:
        for zone in ZONES:
            cur.execute(
                """
                SELECT
                  ST_Area(geom) / 1e6,
                  ST_NPoints(geom),
                  ST_NumGeometries(geom)
                FROM tmp_extent_final WHERE zone = %s
                """,
                (zone,),
            )
            area, verts, parts = cur.fetchone()
            stats[zone] = {
                "km2": float(area),
                "vertices": float(verts or 0),
                "parts": float(parts or 0),
            }
        cur.execute(
            "SELECT ST_Area(ST_Union(geom)) / 1e6 FROM tmp_extent_final"
        )
        stats["union"] = {"km2": float(cur.fetchone()[0])}
    return stats


def _assert_areas(stats: dict[str, dict[str, float]]) -> None:
    for zone, expected in EXPECTED_KM2.items():
        got = stats[zone]["km2"]
        lo, hi = expected * 0.99, expected * 1.01
        if not (lo <= got <= hi):
            print(
                f"EXTENT: {zone} area {got:.1f} outside expected",
                file=sys.stderr,
            )
            sys.exit(4)
        print(
            f"EXTENT: zone={zone} km2={got:.1f} "
            f"vertices={stats[zone].get('vertices', 0):.0f} "
            f"parts={stats[zone].get('parts', 0):.0f} valid=true"
        )


def _write_geojson(conn) -> tuple[str, int]:
    features = []
    with conn.cursor() as cur:
        for zone in ZONES:
            cur.execute(
                """
                SELECT ST_AsGeoJSON(
                  ST_SnapToGrid(geom, 1.0),
                  0,
                  0
                )
                FROM tmp_extent_final WHERE zone = %s
                """,
                (zone,),
            )
            geom_json = cur.fetchone()[0]
            features.append(
                {
                    "type": "Feature",
                    "properties": {"zone": zone},
                    "geometry": json.loads(geom_json),
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
        print("EXTENT: GeoJSON >= 8 MB", file=sys.stderr)
        sys.exit(2)
    print(f"EXTENT: wrote {OUT_PATH} bytes={size} sha256={sha}")
    return sha, size


def _persist_ref_tables(conn, sha: str, built_at: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ref.extent WHERE geography = 'scotland'")
        cur.execute("DELETE FROM ref.extent_sub WHERE geography = 'scotland'")
        cur.execute(
            "DELETE FROM ref.extent_buf50_sub WHERE geography = 'scotland'"
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


def _update_docs_manifest(sha: str, source: str) -> None:
    marker = "scotland_extent.27700.geojson"
    line = (
        f"- `{marker}` (ARCH-1 Scotland land/inshore/offshore extent, EPSG:27700; "
        f"sha256={sha}; {source}; licence OGL-3.0; "
        f"attribution: {MARINE_ATTR} {LAND_ATTR})\n"
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


def _feature_to_27700_geojson(feature: dict, *, already_27700: bool) -> str:
    geom = feature.get("geometry")
    if geom is None:
        raise RuntimeError("feature missing geometry")
    if already_27700:
        return json.dumps(geom)
    # Reproject 4326 → 27700 inside PostGIS when inserting.
    return json.dumps(geom)


def build(*, land_source: str = "councils") -> dict:
    token = _require_token()
    fetch_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    built_at = datetime.now(timezone.utc).isoformat()

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
            print(
                f"EXTENT: expected 21 SMR+OMR areas, got {len(areas)}",
                file=sys.stderr,
            )
            sys.exit(2)
        if len(smr) != 11:
            print(f"EXTENT: expected 11 SMR, got {len(smr)}", file=sys.stderr)
            sys.exit(2)

    smr_names: set[str] = set()
    for feature in smr:
        props = feature.get("properties") or {}
        for key in ("objnam", "name", "NAME", "Name", "nmp_name"):
            if props.get(key):
                smr_names.add(str(props[key]).strip())
                break
    if len(smr_names) != 11:
        print(f"EXTENT: expected 11 SMR names, got {len(smr_names)}", file=sys.stderr)
        sys.exit(2)

    part_rows: list[tuple[str, str]] = []
    for feature in land_features:
        part_rows.append(
            ("land", _feature_to_27700_geojson(feature, already_27700=True))
        )

    inshore_n = offshore_n = 0
    for feature in areas:
        props = feature.get("properties") or {}
        zone = _zone_for_area(props, smr_names)
        if zone == "inshore_0_12nm":
            inshore_n += 1
        else:
            offshore_n += 1
        # Sea features arrive in 4326; transform on insert.
        part_rows.append((zone, json.dumps(feature["geometry"])))

    if inshore_n != 11 or offshore_n != 10:
        print(
            f"EXTENT: zone split inshore={inshore_n} offshore={offshore_n} "
            f"(expected 11/10)",
            file=sys.stderr,
        )
        sys.exit(2)

    conn = psycopg2.connect(_dsn())
    try:
        _ensure_sql(conn)
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS tmp_extent_parts")
            cur.execute(
                "CREATE TEMP TABLE tmp_extent_parts ("
                "zone text NOT NULL, geom geometry NOT NULL)"
            )
            for zone, geojson in part_rows:
                if zone == "land":
                    cur.execute(
                        """
                        INSERT INTO tmp_extent_parts (zone, geom)
                        VALUES (
                          %s,
                          ST_SetSRID(ST_GeomFromGeoJSON(%s), 27700)
                        )
                        """,
                        (zone, geojson),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO tmp_extent_parts (zone, geom)
                        VALUES (
                          %s,
                          ST_Transform(
                            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                            27700
                          )
                        )
                        """,
                        (zone, geojson),
                    )
        conn.commit()
        print("EXTENT: +1/-1 m per part via ref.close_slivers, then union…")
        _build_zones_in_db(conn)
        stats = _zone_stats(conn)
        _assert_areas(stats)
        sha, size = _write_geojson(conn)
        _persist_ref_tables(conn, sha, built_at)
    finally:
        conn.close()

    source = (
        f"land={redact(land_url)}; areas={areas_url}; smr={smr_url}; "
        f"fetched={fetch_time}"
    )
    attribution = f"{MARINE_ATTR} {LAND_ATTR}"
    _upsert_manifest_row(
        file_name=OUT_PATH.name,
        source=source,
        attribution=attribution,
        rows=3,
        sha256=sha,
    )
    _update_docs_manifest(sha, source)
    return {
        "path": str(OUT_PATH),
        "sha256": sha,
        "bytes": size,
        "stats": stats,
        "councils": 32 if land_source == "councils" else len(land_features),
        "areas": 21,
        "smr": 11,
        "source": source,
    }


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
    # Fail-closed: missing manifest row/file is the same class of error as a mismatch.
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
                # No make_valid on load — invalid files must fail closed.
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
        conn.commit()
        _persist_ref_tables(conn, actual, built_at)
    finally:
        conn.close()
    return {"path": str(path), "sha256": actual}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--land-source",
        choices=("councils", "dz2011"),
        default="councils",
        help="councils (default, 32 LA) or dz2011 dissolve",
    )
    parser.add_argument(
        "--load-only",
        metavar="GEOJSON",
        help="Load committed GeoJSON into ref.* (sha checked; no repair)",
    )
    args = parser.parse_args(argv)
    if args.load_only:
        result = load_only(Path(args.load_only))
        print(f"EXTENT: load-only ok sha256={result['sha256']}")
        return
    result = build(land_source=args.land_source)
    stats = result["stats"]
    print(
        "EXTENT: ok "
        f"councils={result['councils']} areas={result['areas']} smr={result['smr']} "
        f"union_km2={stats['union']['km2']:.1f} bytes={result['bytes']} "
        f"sha256={result['sha256']}"
    )


if __name__ == "__main__":
    main()
