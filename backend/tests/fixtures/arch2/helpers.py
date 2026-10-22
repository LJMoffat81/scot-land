"""Shared helpers for ARCH-2a-1 tests (synthetic fixtures only)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import pytest
import yaml

from etl.build_scotland_extent import load_only
from layers.registry.loader import LayerEntry

ARCH1_FIXTURES = Path(__file__).resolve().parents[1] / "arch1"
EXTENT_TINY = ARCH1_FIXTURES / "extent_tiny.27700.geojson"
ARCH2_BIN = Path(__file__).resolve().parent / "bin"


def require_dsn() -> str:
    dsn = os.environ.get("ARCH1_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("ARCH1_TEST_DSN not set")
    return dsn


def connect() -> Any:
    connection = psycopg2.connect(require_dsn())
    connection.autocommit = True
    with connection.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    return connection


def load_tiny_extent(conn, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARCH1_TEST_DSN", require_dsn())
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS ref")
        cur.execute("CREATE SCHEMA IF NOT EXISTS stage")
        cur.execute("CREATE SCHEMA IF NOT EXISTS layers")
        for table in ("extent_buf50_sub", "extent_sub", "extent"):
            cur.execute(f"DROP TABLE IF EXISTS ref.{table} CASCADE")

    gis = tmp_path / "gis"
    gis.mkdir(exist_ok=True)
    dest = gis / "scotland_extent.27700.geojson"
    dest.write_bytes(EXTENT_TINY.read_bytes())
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    (gis / "manifest.csv").write_text(
        f"file,sha256\nscotland_extent.27700.geojson,{sha}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "etl.build_scotland_extent.MANIFEST_PATH", gis / "manifest.csv"
    )
    load_only(dest)


def drop_layer_tables(conn, *layer_ids: str) -> None:
    with conn.cursor() as cur:
        for layer_id in layer_ids:
            for suffix in ("", "_prev", "__new"):
                cur.execute(
                    f'DROP TABLE IF EXISTS layers."{layer_id}{suffix}" CASCADE'
                )
                cur.execute(
                    f'DROP TABLE IF EXISTS stage."{layer_id}{suffix}" CASCADE'
                )


def drop_dz_boundaries(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS public.dz_boundaries CASCADE")


def seed_dz_grid(conn) -> None:
    """9×1 km vintage 2022 + 9×2011 + one edge straddler (synthetic)."""
    drop_dz_boundaries(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE public.dz_boundaries (
              code text NOT NULL,
              name text NOT NULL,
              vintage integer NOT NULL,
              geom geometry(MultiPolygon, 27700) NOT NULL
            )
            """
        )
        rows: list[tuple[Any, ...]] = []
        # 3×3 grid of 1 km squares inside land (0–10000), origin (1000,1000)
        codes_2022 = [f"S010134{n}" for n in range(482, 491)]  # S01013482–S01013490
        for idx, code in enumerate(codes_2022):
            col, row = idx % 3, idx // 3
            x0 = 1000 + col * 1000
            y0 = 1000 + row * 1000
            rows.append(
                (
                    code,
                    f"DZ {code}",
                    2022,
                    x0,
                    y0,
                    x0 + 1000,
                    y0 + 1000,
                )
            )
        # 2011 vintage — shifted east so codes don't collide
        for idx in range(9):
            col, row = idx % 3, idx // 3
            x0 = 5000 + col * 1000
            y0 = 1000 + row * 1000
            code = f"S0101201{idx}"
            rows.append(
                (
                    code,
                    f"DZ2011 {code}",
                    2011,
                    x0,
                    y0,
                    x0 + 1000,
                    y0 + 1000,
                )
            )
        # Straddler: half outside north edge of extent (y=10000)
        rows.append(
            (
                "S01013491",
                "DZ straddle",
                2022,
                2000,
                9500,
                3000,
                10500,
            )
        )
        for code, name, vintage, x0, y0, x1, y1 in rows:
            cur.execute(
                """
                INSERT INTO public.dz_boundaries (code, name, vintage, geom)
                VALUES (
                  %s, %s, %s,
                  ST_Multi(ST_SetSRID(ST_MakeEnvelope(%s, %s, %s, %s), 27700))
                )
                """,
                (code, name, vintage, x0, y0, x1, y1),
            )


def seed_layer_table(
    conn,
    layer_id: str,
    features: list[dict[str, Any]],
    *,
    dataset_version: str | None = None,
    as_of: str = "2026-10-22",
    keep_field_props: dict[str, Any] | None = None,
) -> str:
    """Insert rows into layers.\"<id>\" matching run_layer stage schema."""
    drop_layer_tables(conn, layer_id)
    if dataset_version is None:
        dataset_version = f"{layer_id}@{as_of}-abcd1234"
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS layers")
        cur.execute(
            f"""
            CREATE TABLE layers."{layer_id}" (
              feature_id text NOT NULL,
              props jsonb NOT NULL,
              geom geometry(Geometry, 27700) NOT NULL,
              source_layer_ids text[] NOT NULL,
              dataset_version text NOT NULL,
              as_of date NOT NULL,
              method text NOT NULL,
              child_unit_ids text[] NULL
            )
            """
        )
        rows: list[tuple[Any, ...]] = []
        for index, feature in enumerate(features):
            fid = str(feature.get("id", index + 1))
            props = dict(feature.get("properties") or {})
            if keep_field_props:
                props.update(keep_field_props)
            geom = feature["geometry"]
            version = feature.get("dataset_version", dataset_version)
            rows.append(
                (
                    fid,
                    json.dumps(props),
                    json.dumps(geom),
                    [layer_id],
                    version,
                    as_of,
                )
            )
        if rows:
            psycopg2.extras.execute_batch(
                cur,
                f"""
                INSERT INTO layers."{layer_id}" (
                  feature_id, props, geom,
                  source_layer_ids, dataset_version, as_of, method, child_unit_ids
                )
                VALUES (
                  %s, %s::jsonb,
                  ST_SetSRID(ST_GeomFromGeoJSON(%s), 27700),
                  %s, %s, %s::date, 'source', NULL
                )
                """,
                rows,
                page_size=500,
            )
    return dataset_version


def square(x0: float, y0: float, size: float = 1000.0) -> dict[str, Any]:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [x0, y0],
                [x0 + size, y0],
                [x0 + size, y0 + size],
                [x0, y0 + size],
                [x0, y0],
            ]
        ],
    }


def point(x: float, y: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [x, y]}


def line(coords: list[list[float]]) -> dict[str, Any]:
    return {"type": "LineString", "coordinates": coords}


def dense_features(n: int = 20000, size: float = 20.0) -> list[dict[str, Any]]:
    """n squares of ``size`` m inside the tiny land extent (generated, not committed)."""
    cols = 200  # 200 × 20 m = 4000 m
    features: list[dict[str, Any]] = []
    for i in range(n):
        col, row = i % cols, i // cols
        x0 = 500.0 + col * size
        y0 = 500.0 + row * size
        features.append(
            {
                "id": f"d{i}",
                "properties": {"name": f"c{i}"},
                "geometry": square(x0, y0, size),
            }
        )
    return features


def pts_close_features() -> list[dict[str, Any]]:
    return [
        {
            "id": "p1",
            "properties": {"NAME": "A", "INF_TYPE": "PLATFORM"},
            "geometry": point(1500.0, 1500.0),
        },
        {
            "id": "p2",
            "properties": {"NAME": "B", "INF_TYPE": "PLATFORM"},
            "geometry": point(1505.0, 1500.0),
        },
    ]


def line_features() -> list[dict[str, Any]]:
    return [
        {
            "id": "l1",
            "properties": {
                "PIPE_NAME": "A",
                "FLUID": "oil",
                "DESCRIPTIO": "one",
            },
            "geometry": line([[1000, 1000], [2000, 1000]]),
        },
        {
            "id": "l2",
            "properties": {
                "PIPE_NAME": "B",
                "FLUID": "gas",
                "DESCRIPTIO": "two",
            },
            "geometry": line([[1000, 2000], [2000, 2500]]),
        },
        {
            "id": "l3",
            "properties": {
                "PIPE_NAME": "C",
                "FLUID": "oil",
                "DESCRIPTIO": "three",
            },
            "geometry": line([[3000, 1000], [3000, 3000]]),
        },
    ]


def dz_grid_layer_features_from_db(conn) -> list[dict[str, Any]]:
    """Read vintage=2022 (+straddler after clip is separate); for direct layer seed."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT code, name, ST_AsGeoJSON(geom)
            FROM public.dz_boundaries
            WHERE vintage = 2022
            ORDER BY code
            """
        )
        out: list[dict[str, Any]] = []
        for code, name, geojson in cur.fetchall():
            out.append(
                {
                    "id": code,
                    "properties": {"name": name},
                    "geometry": json.loads(geojson),
                }
            )
        return out


def write_storage_yaml(
    path: Path, *, keep_versions: int = 3, root_env: str = "TILES_DIR"
) -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "storage": "local",
                "root_env": root_env,
                "keep_versions": keep_versions,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def make_entry(entry_id: str, **over: Any) -> LayerEntry:
    """Valid dz2022-like tiled entry for build tests (id ``x`` by default)."""
    raw: dict[str, Any] = {
        "id": entry_id,
        "title": entry_id,
        "geography": "scotland",
        "clip": "land+sea",
        "unit": "dz2022",
        "licence": "OGL-3.0",
        "attribution": "Test attribution",
        "source": {
            "type": "postgis_table",
            "table": "dz_boundaries",
            "id_field": "code",
            "where": "vintage = 2022",
        },
        "geometry": "polygon",
        "refresh": {"cron": "0 5 1 * *", "max_mb": 300, "max_s": 600},
        "serve": {
            "mode": "pmtiles",
            "simplify_m": 0,
            "precision_dp": 6,
            "max_mb": 15,
        },
        "zoom": {"min": 0, "max": 14, "low_zoom": "keep_all"},
        "style": {},
        "legend": [],
        "lineage": {
            "derived_from": [],
            "method": "source",
            "roll_up_to": ["council", "scotland"],
        },
        "keep_fields": ["name"],
        "tiles": {
            "budget": {"total_mb": 60, "tile_kb": 500, "z0_7_mb": 4}
        },
    }
    for key, value in over.items():
        if (
            key in raw
            and isinstance(raw[key], dict)
            and isinstance(value, dict)
            and key not in ("style",)
        ):
            merged = dict(raw[key])
            merged.update(value)
            raw[key] = merged
        else:
            raw[key] = value
    return LayerEntry(id=entry_id, raw=raw)
