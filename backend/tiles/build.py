"""Build versioned PMTiles from clipped ``layers.<id>`` tables (ARCH-2a-1).

Usage::

    python -m tiles.build <id>
    python -m tiles.build --all
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

from layers.registry.loader import RegistryError, registry
from tiles.measure import measure_pmtiles
from tiles.profiles import ProfileError, tippecanoe_flags
from tiles.storage import LocalStorage, StorageError, load_storage

_VERSION_RE = re.compile(r"^(.+)@(\d{4}-\d{2}-\d{2})-([0-9a-f]{8})$")


class TilesError(Exception):
    """Tile build failure (``TILES:`` prefix)."""


def _dsn() -> str:
    dsn = (
        os.environ.get("ARCH1_TEST_DSN")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if not dsn:
        raise TilesError("TILES: ARCH1_TEST_DSN or DATABASE_URL not set")
    return dsn


def _q_ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise TilesError(f"TILES: unsafe identifier {name!r}")
    return '"' + name.replace('"', "") + '"'


def _parse_dataset_version(dataset_version: str) -> tuple[str, str]:
    match = _VERSION_RE.fullmatch(dataset_version)
    if not match:
        raise TilesError(f"TILES: bad dataset_version {dataset_version!r}")
    return match.group(2), match.group(3)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    # fsync the directory entry
    dir_fd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema": 1, "tilesets": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": 1, "tilesets": {}}
    if not isinstance(data, dict):
        return {"schema": 1, "tilesets": {}}
    tilesets = data.get("tilesets")
    if not isinstance(tilesets, dict):
        data["tilesets"] = {}
    data.setdefault("schema", 1)
    return data


def _export_geojsonseq(
    conn,
    layer_id: str,
    *,
    keep_fields: list[str],
    precision_dp: int,
    dest: Path,
) -> int:
    """Stream GeoJSONSeq (EPSG:4326) with feature_id + keep_fields only."""
    table = f"layers.{_q_ident(layer_id)}"
    field_exprs: list[str] = ["feature_id"]
    for field in keep_fields:
        # props keys are exact; quote as JSON path literal
        safe = field.replace("'", "''")
        field_exprs.append(f"props ->> '{safe}' AS {_q_ident(field)}")
    select_cols = ", ".join(field_exprs)
    geom_expr = f"ST_AsGeoJSON(ST_Transform(geom, 4326), {int(precision_dp)})"
    sql = f"SELECT {select_cols}, {geom_expr} AS geojson FROM {table}"
    count = 0
    # Unnamed cursor: named (server-side) cursors cannot run with autocommit.
    with dest.open("w", encoding="utf-8") as out, conn.cursor() as cur:
        cur.execute(sql)
        for row in cur:
            *values, geojson = row
            if geojson is None:
                continue
            props: dict[str, Any] = {"feature_id": values[0]}
            for name, value in zip(keep_fields, values[1:]):
                if value is not None:
                    props[name] = value
            feature = {
                "type": "Feature",
                "properties": props,
                "geometry": json.loads(geojson),
            }
            out.write(json.dumps(feature, separators=(",", ":")))
            out.write("\n")
            count += 1
    return count


def _run_tippecanoe(
    *,
    layer_id: str,
    geojsonseq: Path,
    out_pmtiles: Path,
    zoom_max: int,
    low_zoom: str,
    keep_fields: list[str],
) -> None:
    tippecanoe = shutil.which("tippecanoe")
    if not tippecanoe:
        raise TilesError("TILES: tippecanoe not found")
    try:
        profile = tippecanoe_flags(
            low_zoom, zoom_max=zoom_max, keep_fields=keep_fields
        )
    except ProfileError as exc:
        raise TilesError(f"TILES: {layer_id}: {exc}") from exc

    cmd = [
        tippecanoe,
        "-q",
        "-f",
        "-Z0",
        f"-z{zoom_max}",
        "-l",
        layer_id,
        "-o",
        str(out_pmtiles),
        *profile,
        str(geojsonseq),
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise TilesError(
            f"TILES: {layer_id}: tippecanoe exit {result.returncode}"
        )


def build_tileset(
    layer_id: str,
    *,
    conn=None,
    storage_path: Path | None = None,
    low_zoom_override: str | None = None,
    force_keep_all_check: bool = False,
) -> dict[str, Any]:
    """Build one tileset. Fail-closed: previous file + manifest untouched on error.

    ``force_keep_all_check`` is test-only (B-13): run the keep_all z5 coverage
    check even when tippecanoe used a different profile.
    """
    entries = registry()
    if layer_id not in entries:
        raise TilesError(f"TILES: unknown layer {layer_id}")
    entry = entries[layer_id]
    raw = entry.raw
    if "tiles" not in raw:
        raise TilesError(f"TILES: {layer_id}: no tiles block")
    gated = raw.get("gated_by")
    if gated:
        raise TilesError(f"TILES: {layer_id}: gated by {gated}")

    budget = (raw.get("tiles") or {}).get("budget") or {}
    tile_kb = int(budget["tile_kb"])
    z0_7_mb = float(budget["z0_7_mb"])
    total_mb = float(budget["total_mb"])
    keep_fields = list(raw.get("keep_fields") or [])
    zoom = raw.get("zoom") or {}
    zoom_max = int(zoom.get("max") or 14)
    low_zoom = low_zoom_override or str(zoom.get("low_zoom") or "simplify")
    precision_dp = int((raw.get("serve") or {}).get("precision_dp") or 6)
    attribution = str(raw.get("attribution") or "")
    check_keep_all = force_keep_all_check or (low_zoom == "keep_all")

    config = load_storage(storage_path)
    storage = LocalStorage(config)
    tiles_dir = config.root
    tmp_dir = tiles_dir / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    owns_conn = conn is None
    connection = conn or psycopg2.connect(_dsn())
    connection.autocommit = True
    tmp_geo: Path | None = None
    tmp_pmtiles: Path | None = None
    try:
        table_name = layer_id
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.tables
                  WHERE table_schema='layers' AND table_name=%s
                )
                """,
                (table_name,),
            )
            if not cur.fetchone()[0]:
                raise TilesError(f"TILES: {layer_id}: layer not built")

            cur.execute(
                f'SELECT count(*) FROM layers.{_q_ident(layer_id)}'
            )
            n_features = int(cur.fetchone()[0])
            if n_features == 0:
                raise TilesError(f"TILES: {layer_id}: 0 features")

            cur.execute(
                f"""
                SELECT DISTINCT dataset_version, as_of::text
                FROM layers.{_q_ident(layer_id)}
                """
            )
            versions = cur.fetchall()
            if len(versions) != 1:
                raise TilesError(f"TILES: {layer_id}: mixed dataset_version")
            dataset_version, as_of_col = versions[0]
            dataset_version = str(dataset_version)

            # keep_fields must exist as keys in props on at least one row
            for field in keep_fields:
                cur.execute(
                    f"""
                    SELECT EXISTS (
                      SELECT 1 FROM layers.{_q_ident(layer_id)}
                      WHERE props ? %s
                    )
                    """,
                    (field,),
                )
                if not cur.fetchone()[0]:
                    raise TilesError(
                        f"TILES: {layer_id}: keep_field {field} not in layer properties"
                    )

        as_of, sha8 = _parse_dataset_version(dataset_version)
        version = f"{as_of}.{sha8}"

        tmp_geo = Path(
            tempfile.mkstemp(prefix=f"{layer_id}.", suffix=".geojsonl", dir=tmp_dir)[1]
        )
        tmp_pmtiles = Path(
            tempfile.mkstemp(prefix=f"{layer_id}.", suffix=".pmtiles", dir=tmp_dir)[1]
        )
        # mkstemp creates empty files; tippecanoe needs a clean -o path sometimes
        tmp_pmtiles.unlink(missing_ok=True)

        _export_geojsonseq(
            connection,
            layer_id,
            keep_fields=keep_fields,
            precision_dp=precision_dp,
            dest=tmp_geo,
        )
        _run_tippecanoe(
            layer_id=layer_id,
            geojsonseq=tmp_geo,
            out_pmtiles=tmp_pmtiles,
            zoom_max=zoom_max,
            low_zoom=low_zoom,
            keep_fields=keep_fields,
        )

        try:
            measurements = measure_pmtiles(
                tmp_pmtiles,
                layer_id=layer_id,
                tile_kb=tile_kb,
                z0_7_mb=z0_7_mb,
                total_mb=total_mb,
                keep_all=check_keep_all,
                expected_count=n_features if check_keep_all else None,
            )
        except RuntimeError as exc:
            raise TilesError(f"TILES: {layer_id}: {exc}") from exc

        # Publish only after checks pass (D4).
        final_path = storage.publish(tmp_pmtiles, layer_id, version)
        tmp_pmtiles = None  # owned by publish

        manifest_path = tiles_dir / "manifest.json"
        manifest = _load_manifest(manifest_path)
        entry_payload: dict[str, Any] = {
            "version": version,
            "dataset_version": dataset_version,
            "as_of": as_of,
            "file": final_path.name,
            "bytes": measurements.bytes,
            "sha256": measurements.sha256,
            "minzoom": 0,
            "maxzoom": zoom_max,
            "layer": layer_id,
            "z0_7_bytes": measurements.z0_7_bytes,
            "max_tile_gz_bytes": measurements.max_tile_gz_bytes,
            "max_tile_zoom": measurements.max_tile_zoom,
            "attribution": attribution,
            "built_at": datetime.now(timezone.utc).isoformat(),
        }
        if measurements.distinct_z5 is not None:
            entry_payload["distinct_z5"] = measurements.distinct_z5
        manifest.setdefault("tilesets", {})[layer_id] = entry_payload
        _atomic_write_json(manifest_path, manifest)

        storage.prune(layer_id, config.keep_versions)
        return entry_payload
    finally:
        if tmp_geo is not None:
            tmp_geo.unlink(missing_ok=True)
        if tmp_pmtiles is not None:
            tmp_pmtiles.unlink(missing_ok=True)
        # Clear leftover empties in .tmp for this id
        if tmp_dir.is_dir():
            for leftover in tmp_dir.glob(f"{layer_id}.*"):
                leftover.unlink(missing_ok=True)
        if owns_conn:
            connection.close()


def build_all(*, conn=None, storage_path: Path | None = None) -> list[str]:
    """Build every registry entry that has a ``tiles`` block, sorted by id."""
    entries = registry()
    ids = sorted(
        eid for eid, entry in entries.items() if "tiles" in entry.raw
    )
    for layer_id in ids:
        build_tileset(layer_id, conn=conn, storage_path=storage_path)
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layer_id", nargs="?", help="Registry layer id to tile")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Build every registry entry with a tiles block",
    )
    args = parser.parse_args(argv)
    try:
        if args.all:
            build_all()
            return 0
        if not args.layer_id:
            parser.error("layer_id or --all required")
        build_tileset(args.layer_id)
        return 0
    except TilesError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except StorageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except RegistryError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
