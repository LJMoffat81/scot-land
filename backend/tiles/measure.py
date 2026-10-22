"""Measure a built PMTiles file against registry budgets (ARCH-2a)."""

from __future__ import annotations

import gzip
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mapbox_vector_tile
from pmtiles.reader import MmapSource, Reader, all_tiles


@dataclass(frozen=True)
class TileMeasurements:
    bytes: int
    sha256: str
    minzoom: int
    maxzoom: int
    z0_7_bytes: int
    max_tile_gz_bytes: int
    max_tile_zoom: int
    max_tile_x: int
    max_tile_y: int
    distinct_z5: int | None


def _gunzip_if_needed(data: bytes) -> bytes:
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        return gzip.decompress(data)
    return data


def _feature_ids_in_tile(data: bytes, layer_name: str) -> set[str]:
    decoded = mapbox_vector_tile.decode(_gunzip_if_needed(data))
    layer = decoded.get(layer_name) or {}
    ids: set[str] = set()
    for feat in layer.get("features") or []:
        props = feat.get("properties") or {}
        if "feature_id" in props:
            ids.add(str(props["feature_id"]))
    return ids


def measure_pmtiles(
    path: Path,
    *,
    layer_id: str,
    tile_kb: int,
    z0_7_mb: float,
    total_mb: float,
    keep_all: bool,
    expected_count: int | None = None,
) -> TileMeasurements:
    """Decode ``path`` and enforce size / coverage budgets.

    Raises ``RuntimeError`` with a ``TILES:``-ready message (no prefix).
    """
    raw = path.read_bytes()
    file_bytes = len(raw)
    sha = hashlib.sha256(raw).hexdigest()
    if file_bytes > float(total_mb) * 1024 * 1024:
        mb = file_bytes / (1024 * 1024)
        raise RuntimeError(
            f"budget exceeded: total {mb:.2f} MB > {total_mb} MB"
        )

    with path.open("rb") as fh:
        get_bytes = MmapSource(fh)
        reader = Reader(get_bytes)
        header = reader.header()
        minzoom = int(header["min_zoom"])
        maxzoom = int(header["max_zoom"])
        if minzoom != 0:
            raise RuntimeError(f"minzoom {minzoom} != 0")

        z0_7 = 0
        max_gz = 0
        max_z = 0
        max_x = 0
        max_y = 0
        distinct_z5: set[str] = set()
        limit_bytes = int(tile_kb) * 1024

        for (z, x, y), tile_bytes in all_tiles(get_bytes):
            if tile_bytes is None:
                continue
            n = len(tile_bytes)
            if n > limit_bytes:
                kb = n / 1024
                raise RuntimeError(
                    f"budget exceeded: tile {z}/{x}/{y} {kb:.0f} KB > {tile_kb} KB"
                )
            if z <= 7:
                z0_7 += n
            if n > max_gz:
                max_gz = n
                max_z, max_x, max_y = z, x, y
            if keep_all and z == 5:
                distinct_z5 |= _feature_ids_in_tile(tile_bytes, layer_id)

    if z0_7 > float(z0_7_mb) * 1024 * 1024:
        mb = z0_7 / (1024 * 1024)
        raise RuntimeError(
            f"budget exceeded: z0-7 {mb:.2f} MB > {z0_7_mb} MB"
        )

    distinct_count: int | None = None
    if keep_all:
        distinct_count = len(distinct_z5)
        if expected_count is not None and distinct_count != expected_count:
            raise RuntimeError(
                f"z5 shows {distinct_count} of {expected_count} features (keep_all)"
            )

    return TileMeasurements(
        bytes=file_bytes,
        sha256=sha,
        minzoom=minzoom,
        maxzoom=maxzoom,
        z0_7_bytes=z0_7,
        max_tile_gz_bytes=max_gz,
        max_tile_zoom=max_z,
        max_tile_x=max_x,
        max_tile_y=max_y,
        distinct_z5=distinct_count,
    )


def decode_tile_properties(
    path: Path, *, layer_id: str, z: int, x: int, y: int
) -> list[dict[str, Any]]:
    """Return property dicts for features in one tile (for B-15)."""
    with path.open("rb") as fh:
        reader = Reader(MmapSource(fh))
        data = reader.get(z, x, y)
    if data is None:
        return []
    decoded = mapbox_vector_tile.decode(_gunzip_if_needed(data))
    layer = decoded.get(layer_id) or {}
    return [dict(f.get("properties") or {}) for f in (layer.get("features") or [])]


def distinct_ids_at_zoom(path: Path, *, layer_id: str, zoom: int) -> set[str]:
    """Collect distinct ``feature_id`` values at a single zoom."""
    ids: set[str] = set()
    with path.open("rb") as fh:
        get_bytes = MmapSource(fh)
        for (z, _x, _y), tile_bytes in all_tiles(get_bytes):
            if z != zoom or tile_bytes is None:
                continue
            ids |= _feature_ids_in_tile(tile_bytes, layer_id)
    return ids
