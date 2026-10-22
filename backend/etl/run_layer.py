"""Shared ingest → clip → check → swap for registry layers (ARCH-1b).

Usage::

    python -m etl.run_layer <id> [--from-file <geojson>]

Never serves unclipped data (D9). Request path reads ``layers.<id>`` only (D8).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import psycopg2
import psycopg2.extras

from etl.adapters.arcgis import fetch_arcgis
from etl.adapters.geojson_file import fetch_geojson_file
from etl.build_scotland_extent import ExtentError
from layers.registry.loader import LayerEntry, RegistryError, registry

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = Path(__file__).resolve().parent / "sql"
RECEIPT_DIR = REPO_ROOT / "data" / "processed" / "layers"

CLIP_ZONES: dict[str, tuple[str, ...]] = {
    "land": ("land",),
    "sea": ("inshore_0_12nm", "offshore_12_200nm"),
    "land+sea": ("land", "inshore_0_12nm", "offshore_12_200nm"),
}

_GEOM_DIM: dict[str, int] = {
    "point": 1,
    "line": 2,
    "polygon": 3,
}


class LayerPipelineError(Exception):
    """Base class for ARCH-1 ingest / clip / check failures."""


class IngestError(LayerPipelineError):
    """Fetch / load budget or payload failure (``INGEST:`` prefix)."""


class CheckError(LayerPipelineError):
    """Post-clip boundary check failure (``CHECK:`` prefix)."""


def _dsn() -> str:
    dsn = (
        os.environ.get("ARCH1_TEST_DSN")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if not dsn:
        raise IngestError("INGEST: ARCH1_TEST_DSN or DATABASE_URL not set")
    return dsn


def _q_ident(name: str) -> str:
    """Quote a SQL identifier; hyphens allowed inside double quotes."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise IngestError(f"INGEST: unsafe identifier {name!r}")
    return '"' + name.replace('"', "") + '"'


def _table(schema: str, name: str) -> str:
    if schema not in {"stage", "layers", "ref"}:
        raise IngestError(f"INGEST: unsafe schema {schema!r}")
    return f"{schema}.{_q_ident(name)}"


def _ensure_helpers(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS stage")
        cur.execute("CREATE SCHEMA IF NOT EXISTS layers")
        cur.execute("CREATE SCHEMA IF NOT EXISTS ref")
        # Instrumented intersection for C1 / M9 (counts slow-path calls).
        cur.execute(
            """
            CREATE OR REPLACE FUNCTION ref.counted_intersection(a geometry, b geometry)
            RETURNS geometry
            LANGUAGE plpgsql
            AS $$
            BEGIN
              PERFORM set_config(
                'arch1.intersection_calls',
                (
                  COALESCE(
                    NULLIF(current_setting('arch1.intersection_calls', true), ''),
                    '0'
                  )::int
                  + 1
                )::text,
                false
              );
              RETURN ST_Intersection(a, b);
            END;
            $$
            """
        )
    conn.commit()


def reset_intersection_counter(conn) -> None:
    """Reset the session counter used by ``ref.counted_intersection``."""
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('arch1.intersection_calls', '0', false)")
    conn.commit()


def intersection_calls(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE("
            "NULLIF(current_setting('arch1.intersection_calls', true), ''),"
            "'0')::int"
        )
        return int(cur.fetchone()[0])


def _feature_id(feature: dict[str, Any], index: int) -> str:
    props = feature.get("properties") or {}
    for key in ("OBJECTID", "objectid", "ObjectID", "FID", "fid", "id", "ID"):
        if props.get(key) is not None:
            return str(props[key])
    return str(index)


def _as_of_today() -> date:
    return datetime.now(timezone.utc).date()


def _dataset_version(layer_id: str, as_of: date, body: bytes) -> str:
    sha8 = hashlib.sha256(body).hexdigest()[:8]
    return f"{layer_id}@{as_of.isoformat()}-{sha8}"


def _extent_present(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema='ref' AND table_name='extent_sub'
            )
            """
        )
        if not cur.fetchone()[0]:
            return False
        cur.execute(
            "SELECT count(*) FROM ref.extent_sub WHERE geography='scotland'"
        )
        return int(cur.fetchone()[0]) > 0


def _extent_sha(conn) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sha256 FROM ref.extent WHERE geography='scotland' LIMIT 1"
        )
        row = cur.fetchone()
        return row[0] if row else ""


def _collection_is_27700(collection: dict[str, Any]) -> bool:
    """True when the FeatureCollection declares EPSG:27700 (test fixtures)."""
    crs = collection.get("crs") or {}
    props = crs.get("properties") or {}
    name = str(props.get("name") or "")
    return "27700" in name or name.endswith(":27700")


def _load_stage(
    conn,
    layer_id: str,
    features: list[dict[str, Any]],
    *,
    as_of: date,
    dataset_version: str,
    method: str,
    already_27700: bool = False,
) -> int:
    stage = _table("stage", layer_id)
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {stage}")
        cur.execute(
            f"""
            CREATE TABLE {stage} (
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
            geom = feature.get("geometry")
            if geom is None:
                continue
            props = feature.get("properties") or {}
            fid = _feature_id(feature, index)
            rows.append(
                (
                    fid,
                    json.dumps(props),
                    json.dumps(geom),
                    [layer_id],
                    dataset_version,
                    as_of,
                    method,
                    None,
                )
            )
        if rows:
            if already_27700:
                insert_sql = f"""
                INSERT INTO {stage} (
                  feature_id, props, geom,
                  source_layer_ids, dataset_version, as_of, method, child_unit_ids
                )
                VALUES (
                  %s, %s::jsonb,
                  ST_SetSRID(ST_GeomFromGeoJSON(%s), 27700),
                  %s, %s, %s, %s, %s
                )
                """
            else:
                insert_sql = f"""
                INSERT INTO {stage} (
                  feature_id, props, geom,
                  source_layer_ids, dataset_version, as_of, method, child_unit_ids
                )
                VALUES (
                  %s, %s::jsonb,
                  ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 27700),
                  %s, %s, %s, %s, %s
                )
                """
            psycopg2.extras.execute_batch(
                cur, insert_sql, rows, page_size=500
            )
    conn.commit()
    return len(rows)


def _render_sql(
    template: str,
    *,
    src: str,
    dst: str,
    zones: tuple[str, ...],
    dim: int,
    is_point: bool,
) -> str:
    zones_sql = (
        "ARRAY["
        + ",".join("'" + z.replace("'", "''") + "'" for z in zones)
        + "]::text[]"
    )
    return (
        template.replace("__SRC__", src)
        .replace("__DST__", dst)
        .replace("__ZONES__", zones_sql)
        .replace("__DIM__", str(dim))
        .replace("__IS_POINT__", "TRUE" if is_point else "FALSE")
    )


def _clip(
    conn,
    layer_id: str,
    entry: LayerEntry,
    *,
    new_name: str,
) -> int:
    clip = entry.raw.get("clip") or "sea"
    if clip == "none":
        raise IngestError(
            f"INGEST: {layer_id} clip=none not supported for vector ingest"
        )
    zones = CLIP_ZONES.get(clip)
    if not zones:
        raise IngestError(f"INGEST: {layer_id} unknown clip {clip!r}")
    geom_kind = entry.raw.get("geometry") or "polygon"
    dim = _GEOM_DIM.get(geom_kind, 3)
    is_point = geom_kind == "point"
    template = (SQL_DIR / "clip.sql").read_text(encoding="utf-8")
    src = _table("stage", layer_id)
    dst = _table("layers", new_name)
    sql = _render_sql(
        template, src=src, dst=dst, zones=zones, dim=dim, is_point=is_point
    )
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(f"SELECT count(*) FROM {dst}")
        count = int(cur.fetchone()[0])
    conn.commit()
    return count


def _check(conn, layer_id: str, table_name: str) -> int:
    dst = _table("layers", table_name)
    template = (SQL_DIR / "check_outside.sql").read_text(encoding="utf-8")
    sql = template.replace("__DST__", dst)
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {dst}")
        total = int(cur.fetchone()[0])
        if total == 0:
            raise CheckError(f"CHECK: {layer_id}: 0 features after clip")
        cur.execute(sql)
        outside = int(cur.fetchone()[0])
    conn.commit()
    if outside != 0:
        raise CheckError(
            f"CHECK: {layer_id}: {outside} features outside scotland+50m"
        )
    return outside


def _swap_impl(conn, layer_id: str, new_name: str) -> None:
    """Atomic live ↔ new swap; previous live becomes ``_prev`` (D9)."""
    live_q = _q_ident(layer_id)
    prev_q = _q_ident(f"{layer_id}_prev")
    new_q = _q_ident(new_name)
    old_autocommit = conn.autocommit
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.tables
                  WHERE table_schema='layers' AND table_name=%s
                )
                """,
                (layer_id,),
            )
            has_live = bool(cur.fetchone()[0])
            cur.execute(f"DROP TABLE IF EXISTS layers.{prev_q}")
            if has_live:
                cur.execute(f"ALTER TABLE layers.{live_q} RENAME TO {prev_q}")
            cur.execute(f"ALTER TABLE layers.{new_q} RENAME TO {live_q}")
        conn.commit()
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        conn.autocommit = old_autocommit


def _drop_scratch(conn, new_name: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {_table('layers', new_name)}")
    conn.commit()


def _write_receipt(layer_id: str, payload: dict[str, Any]) -> Path:
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = RECEIPT_DIR / f"{layer_id}.receipt.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _fetch_entry(
    entry: LayerEntry,
    *,
    from_file: Path | None,
) -> tuple[dict[str, Any], bytes, str]:
    layer_id = entry.id
    source = entry.raw.get("source") or {}
    refresh = entry.raw.get("refresh") or {}
    max_mb = float(refresh.get("max_mb") or 300)
    max_s = float(refresh.get("max_s") or 600)

    try:
        if from_file is not None:
            return fetch_geojson_file(from_file, max_mb=max_mb)

        src_type = source.get("type")
        if src_type == "arcgis":
            token = None
            token_env = source.get("token_env")
            if token_env:
                token = os.environ.get(str(token_env)) or None
            return fetch_arcgis(
                source["url"],
                where=source.get("where") or "1=1",
                out_fields=source.get("out_fields") or "*",
                page_size=int(source.get("page_size") or 1000),
                max_mb=max_mb,
                max_s=max_s,
                token=token,
            )
        if src_type == "geojson_file":
            return fetch_geojson_file(source["url"], max_mb=max_mb)
        raise IngestError(f"INGEST: {layer_id} unknown source.type {src_type!r}")
    except RuntimeError as exc:
        msg = str(exc)
        if msg.startswith("budget exceeded:"):
            kind = msg.split(":", 1)[1].strip()
            raise IngestError(
                f"INGEST: {layer_id} budget exceeded: {kind}"
            ) from exc
        raise IngestError(f"INGEST: {layer_id} {msg}") from exc
    except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError) as exc:
        raise IngestError(f"INGEST: {layer_id} fetch failed: {exc}") from exc


def run_layer(
    layer_id: str,
    *,
    from_file: Path | None = None,
    conn=None,
) -> dict[str, Any]:
    """Fetch → stage → clip → check → swap. Leaves live table untouched on failure."""
    entries = registry()
    if layer_id not in entries:
        raise RegistryError(f"REGISTRY: unknown layer {layer_id}")
    entry = entries[layer_id]

    owns_conn = conn is None
    connection = conn or psycopg2.connect(_dsn())
    connection.autocommit = True
    new_name = f"{layer_id}__new"
    started = time.monotonic()
    try:
        _ensure_helpers(connection)
        if not _extent_present(connection):
            raise ExtentError("CLIP: Scotland boundary missing")

        fetch_t0 = time.monotonic()
        collection, raw_body, redacted_url = _fetch_entry(
            entry, from_file=from_file
        )
        fetch_s = time.monotonic() - fetch_t0
        features = list(collection.get("features") or [])
        as_of = _as_of_today()
        method = str((entry.raw.get("lineage") or {}).get("method") or "source")
        version = _dataset_version(layer_id, as_of, raw_body)
        already_27700 = _collection_is_27700(collection)

        before = _load_stage(
            connection,
            layer_id,
            features,
            as_of=as_of,
            dataset_version=version,
            method=method,
            already_27700=already_27700,
        )

        reset_intersection_counter(connection)
        clip_t0 = time.monotonic()
        after = _clip(connection, layer_id, entry, new_name=new_name)
        clip_s = time.monotonic() - clip_t0

        outside = _check(connection, layer_id, new_name)
        _swap_impl(connection, layer_id, new_name)

        receipt = {
            "id": layer_id,
            "before": before,
            "after": after,
            "outside": outside,
            "fetch_s": round(fetch_s, 3),
            "clip_s": round(clip_s, 3),
            "total_s": round(time.monotonic() - started, 3),
            "extent_sha256": _extent_sha(connection),
            "url": redacted_url,
            "as_of": as_of.isoformat(),
            "dataset_version": version,
            "method": method,
        }
        _write_receipt(layer_id, receipt)
        return receipt
    except (
        RegistryError,
        ExtentError,
        IngestError,
        CheckError,
        psycopg2.Error,
        OSError,
    ):
        try:
            _drop_scratch(connection, new_name)
        except (psycopg2.Error, OSError, IngestError):
            pass
        raise
    finally:
        if owns_conn:
            connection.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layer_id", help="Registry layer id (e.g. oil-fields)")
    parser.add_argument(
        "--from-file",
        metavar="GEOJSON",
        help="Offline GeoJSON feed (skips upstream fetch)",
    )
    args = parser.parse_args(argv)
    from_file = Path(args.from_file) if args.from_file else None
    receipt = run_layer(args.layer_id, from_file=from_file)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
