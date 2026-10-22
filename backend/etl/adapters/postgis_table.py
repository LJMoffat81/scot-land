"""Read a clipped-ready PostGIS table as a FeatureCollection (ARCH-2a)."""

from __future__ import annotations

import json
import re
from typing import Any

import psycopg2
from psycopg2 import sql

_TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$")
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _split_table(table: str) -> tuple[str | None, str]:
    if not _TABLE_RE.fullmatch(table):
        raise RuntimeError(f"unsafe table identifier {table!r}")
    if "." in table:
        schema, name = table.split(".", 1)
        return schema, name
    return None, table


def _quote_table(table: str) -> sql.Composed:
    schema, name = _split_table(table)
    if schema is None:
        return sql.Identifier(name)
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(name))


def fetch_postgis_table(
    conn,
    table: str,
    id_field: str,
    where: str,
    keep_fields: list[str],
    *,
    max_mb: float | None = None,
) -> tuple[dict[str, Any], bytes, str]:
    """Return ``(FeatureCollection, content_hash_bytes, redacted_url)``.

    Geometry is already EPSG:27700. ``content_hash_bytes`` concatenates the
    ordered ``(feature_id, ST_AsBinary(geom), props)`` rows for
    ``dataset_version`` hashing. Budget is summed WKB bytes vs ``max_mb``.
    """
    if not _IDENT_RE.fullmatch(id_field):
        raise RuntimeError(f"unsafe id_field {id_field!r}")
    for field in keep_fields:
        if not isinstance(field, str) or not field:
            raise RuntimeError(f"unsafe keep_field {field!r}")

    table_sql = _quote_table(table)
    id_sql = sql.Identifier(id_field)

    if keep_fields:
        build_pairs: list[sql.Composable] = []
        for field in keep_fields:
            build_pairs.append(sql.Literal(field))
            build_pairs.append(sql.Identifier(field))
        props_expr = sql.SQL("jsonb_build_object({})").format(
            sql.SQL(", ").join(build_pairs)
        )
    else:
        props_expr = sql.SQL("'{}'::jsonb")

    query = sql.SQL(
        """
        SELECT
          {id_field}::text AS feature_id,
          {props} AS props,
          ST_AsBinary(ST_Multi(geom)) AS wkb,
          ST_AsGeoJSON(ST_Multi(geom)) AS geojson
        FROM {table}
        WHERE {where}
        ORDER BY {id_field}::text
        """
    ).format(
        id_field=id_sql,
        props=props_expr,
        table=table_sql,
        where=sql.SQL(where),
    )

    features: list[dict[str, Any]] = []
    hash_parts: list[bytes] = []
    total_wkb = 0
    with conn.cursor() as cur:
        try:
            cur.execute(query)
        except psycopg2.Error as exc:
            raise RuntimeError(str(exc)) from exc
        rows = cur.fetchall()

    for feature_id, props, wkb, geojson in rows:
        if wkb is None:
            continue
        wkb_bytes = bytes(wkb)
        total_wkb += len(wkb_bytes)
        props_obj = props if isinstance(props, dict) else json.loads(props or "{}")
        props_bytes = json.dumps(
            props_obj, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        fid = str(feature_id)
        hash_parts.append(fid.encode("utf-8"))
        hash_parts.append(wkb_bytes)
        hash_parts.append(props_bytes)
        geom = json.loads(geojson)
        # ``id`` is read by run_layer._feature_id; keep_fields alone go in props.
        features.append(
            {
                "type": "Feature",
                "properties": {"id": fid, **props_obj},
                "geometry": geom,
            }
        )

    if max_mb is not None and total_wkb > float(max_mb) * 1024 * 1024:
        raise RuntimeError("budget exceeded: mb")

    collection: dict[str, Any] = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::27700"},
        },
        "features": features,
    }
    content_bytes = b"\0".join(hash_parts)
    redacted = f"postgis://{table}"
    return collection, content_bytes, redacted
