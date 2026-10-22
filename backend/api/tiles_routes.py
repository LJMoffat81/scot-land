"""ARCH-2a-2: serve versioned MVT tiles from local PMTiles (read-only).

No DB, no tippecanoe, no clip — only the manifest and immutable tile files.
"""

from __future__ import annotations

import json
import logging
import re
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pmtiles.reader import MmapSource, Reader

from layers.registry.loader import RegistryError, registry
from tiles.storage import StorageError, load_storage

logger = logging.getLogger("scot_land.api.tiles")

router = APIRouter(tags=["tiles"])

_VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.[0-9a-f]{8}$")
_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
_MANIFEST_CACHE = "public, max-age=60"
_READER_CACHE_MAX = 8

# path -> (open file handle, Reader); files are immutable by name.
_reader_cache: OrderedDict[str, tuple[Any, Reader]] = OrderedDict()
_reader_lock = Lock()


def _tiles_root() -> Path | None:
    """Return TILES_DIR root, or None when storage is unset / invalid."""
    try:
        return load_storage().root
    except StorageError:
        return None


def _read_manifest(root: Path) -> tuple[dict[str, Any], str | None]:
    """Load manifest.json.

    Returns (payload, note). note is set when the file is missing or unreadable;
    payload always has schema + tilesets dict.
    """
    path = root / "manifest.json"
    if not path.is_file():
        return {"schema": 1, "tilesets": {}, "ok": False, "note": "no tiles built"}, "no tiles built"
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.error("TILES: manifest unreadable: %s: %s", path, exc)
        return (
            {"schema": 1, "tilesets": {}, "ok": False, "note": "tiles manifest unreadable"},
            "tiles manifest unreadable",
        )
    if not isinstance(data, dict):
        logger.error("TILES: manifest unreadable: %s: not an object", path)
        return (
            {"schema": 1, "tilesets": {}, "ok": False, "note": "tiles manifest unreadable"},
            "tiles manifest unreadable",
        )
    tilesets = data.get("tilesets")
    if not isinstance(tilesets, dict):
        logger.error("TILES: manifest unreadable: %s: tilesets not an object", path)
        return (
            {"schema": 1, "tilesets": {}, "ok": False, "note": "tiles manifest unreadable"},
            "tiles manifest unreadable",
        )
    data.setdefault("schema", 1)
    return data, None


def _is_gated(layer_id: str) -> bool:
    try:
        entries = registry()
    except RegistryError:
        return True
    entry = entries.get(layer_id)
    if entry is None:
        return True
    return bool(entry.raw.get("gated_by"))


def _in_registry(layer_id: str) -> bool:
    try:
        entries = registry()
    except RegistryError:
        return False
    return layer_id in entries


def _public_manifest(data: dict[str, Any]) -> dict[str, Any]:
    """Copy manifest for clients: drop gated ids, add tiles URL template."""
    out_sets: dict[str, Any] = {}
    for layer_id, entry in (data.get("tilesets") or {}).items():
        if not isinstance(entry, dict):
            continue
        if not _in_registry(layer_id) or _is_gated(layer_id):
            continue
        version = entry.get("version")
        if not isinstance(version, str):
            continue
        row = dict(entry)
        row["tiles"] = f"/v1/tiles/{layer_id}/{version}/{{z}}/{{x}}/{{y}}.mvt"
        out_sets[layer_id] = row
    result = {"schema": int(data.get("schema") or 1), "tilesets": out_sets}
    if data.get("ok") is False:
        result["ok"] = False
    if "note" in data:
        result["note"] = data["note"]
    return result


def _get_reader(path: Path) -> Reader:
    key = str(path.resolve())
    with _reader_lock:
        cached = _reader_cache.get(key)
        if cached is not None:
            _reader_cache.move_to_end(key)
            return cached[1]
        fh = path.open("rb")
        reader = Reader(MmapSource(fh))
        _reader_cache[key] = (fh, reader)
        while len(_reader_cache) > _READER_CACHE_MAX:
            _old_key, (old_fh, _old_reader) = _reader_cache.popitem(last=False)
            try:
                old_fh.close()
            except OSError:
                pass
        return reader


def _resolve_tile_path(
    root: Path, layer_id: str, version: str, manifest_entry: dict[str, Any] | None
) -> Path | None:
    """Resolve a tile file path from the manifest current version or a kept file.

    Paths are built only from validated id + version (or the manifest ``file``
    basename); user input never walks the filesystem.
    """
    if manifest_entry is not None and manifest_entry.get("version") == version:
        file_name = manifest_entry.get("file")
        if isinstance(file_name, str) and file_name and "/" not in file_name and "\\" not in file_name:
            candidate = root / file_name
            if candidate.is_file():
                return candidate
    # Kept previous version: exact canonical name only.
    candidate = root / f"{layer_id}.{version}.pmtiles"
    if candidate.is_file():
        return candidate
    return None


def _is_gzip(data: bytes) -> bool:
    return len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B


def _etag(version: str, z: int, x: int, y: int) -> str:
    sha8 = version.rsplit(".", 1)[-1]
    return f'"{sha8}-{z}-{x}-{y}"'


@router.get("/v1/tiles/manifest.json")
def tiles_manifest() -> JSONResponse:
    """Current tile manifest with per-tileset ``tiles`` URL templates."""
    root = _tiles_root()
    if root is None:
        body = {"schema": 1, "tilesets": {}, "ok": False, "note": "no tiles built"}
        return JSONResponse(body, headers={"Cache-Control": "no-store"})
    data, note = _read_manifest(root)
    body = _public_manifest(data)
    if note is not None:
        return JSONResponse(body, headers={"Cache-Control": "no-store"})
    return JSONResponse(body, headers={"Cache-Control": _MANIFEST_CACHE})


@router.get("/v1/tiles/{layer_id}/{version}/{z}/{x}/{y}.mvt")
def tiles_mvt(
    layer_id: str,
    version: str,
    z: int,
    x: int,
    y: int,
    request: Request,
) -> Response:
    """Immutable z/x/y MVT from a versioned PMTiles file."""
    root = _tiles_root()
    if root is None:
        raise HTTPException(status_code=404, detail="unknown tileset")

    if not _in_registry(layer_id) or _is_gated(layer_id):
        raise HTTPException(status_code=404, detail="unknown tileset")

    data, note = _read_manifest(root)
    if note is not None and note == "no tiles built":
        raise HTTPException(status_code=404, detail="unknown tileset")
    tilesets = data.get("tilesets") or {}
    manifest_entry = tilesets.get(layer_id)
    if not isinstance(manifest_entry, dict):
        # Allow kept files for an id that left the manifest only if still registered;
        # unknown / never-published ids stay 404.
        raise HTTPException(status_code=404, detail="unknown tileset")

    if not _VERSION_RE.fullmatch(version):
        raise HTTPException(status_code=404, detail="unknown version")

    tile_path = _resolve_tile_path(root, layer_id, version, manifest_entry)
    if tile_path is None:
        raise HTTPException(status_code=404, detail="unknown version")

    maxzoom = int(manifest_entry.get("maxzoom") or 14)
    if z < 0 or z > maxzoom or x < 0 or y < 0 or x >= (1 << z) or y >= (1 << z):
        raise HTTPException(status_code=404, detail="tile out of range")

    etag = _etag(version, z, x, y)
    inm = request.headers.get("if-none-match")
    if inm is not None and inm.strip() == etag:
        return Response(
            status_code=304,
            headers={
                "Cache-Control": _IMMUTABLE_CACHE,
                "ETag": etag,
            },
        )

    reader = _get_reader(tile_path)
    tile_bytes = reader.get(z, x, y)
    headers = {
        "Cache-Control": _IMMUTABLE_CACHE,
        "ETag": etag,
    }
    if tile_bytes is None:
        return Response(status_code=204, headers=headers)

    if _is_gzip(tile_bytes):
        headers["Content-Encoding"] = "gzip"
    return Response(
        content=tile_bytes,
        status_code=200,
        media_type="application/vnd.mapbox-vector-tile",
        headers=headers,
    )
