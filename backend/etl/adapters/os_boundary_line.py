"""Fetch OS Boundary-Line GeoPackage zip and emit Scotland GeoJSON (27700).

Uses stdlib ``sqlite3`` + GeoPackage binary header strip — no GDAL/Fiona.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from shapely import wkb as shapely_wkb
from shapely.geometry import mapping

_ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def gpkg_blob_to_wkb(blob: bytes) -> bytes:
    """Strip a GeoPackageBinary header (envelopes 0–4) and return WKB."""
    if not isinstance(blob, (bytes, bytearray)) or len(blob) < 8:
        raise RuntimeError("geometry blob is not GeoPackage (GP) encoded")
    if bytes(blob[:2]) != b"GP":
        raise RuntimeError("geometry blob is not GeoPackage (GP) encoded")
    flags = blob[3]
    envelope_type = (flags >> 1) & 0x07
    if envelope_type not in _ENVELOPE_BYTES:
        raise RuntimeError(
            f"geometry blob GeoPackage envelope type {envelope_type} unsupported"
        )
    header_len = 8 + _ENVELOPE_BYTES[envelope_type]
    if len(blob) < header_len:
        raise RuntimeError("geometry blob GeoPackage header truncated")
    return bytes(blob[header_len:])


def _redact_url(url: str) -> str:
    """Drop the query string (and fragment) from a download URL."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_path(cache_dir: Path, sha256: str) -> Path:
    return Path(cache_dir) / f"os_boundary_line_{sha256[:12]}.zip"


def _download_zip(
    client: httpx.Client,
    url: str,
    dest: Path,
    *,
    download_max_mb: float,
) -> None:
    budget = int(float(download_max_mb) * 1024 * 1024)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            total = 0
            with tmp.open("wb") as out:
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > budget:
                        raise RuntimeError("budget exceeded: download_mb")
                    out.write(chunk)
        tmp.replace(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        raise


def _read_features_from_zip(
    zip_path: Path,
    *,
    layer: str,
    code_field: str,
    name_field: str,
    code_prefix: str,
) -> list[dict[str, Any]]:
    with zipfile.ZipFile(zip_path) as zf:
        gpkg_names = [n for n in zf.namelist() if n.lower().endswith(".gpkg")]
        if len(gpkg_names) != 1:
            raise RuntimeError(
                f"Boundary-Line zip must contain exactly one .gpkg, got {len(gpkg_names)}"
            )
        gpkg_bytes = zf.read(gpkg_names[0])

    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
        tmp.write(gpkg_bytes)
        gpkg_path = Path(tmp.name)
    try:
        conn = sqlite3.connect(f"file:{gpkg_path.as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute(
                """
                SELECT srs_id, column_name
                FROM gpkg_geometry_columns
                WHERE table_name = ?
                LIMIT 1
                """,
                (layer,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Boundary-Line layer {layer} missing")
            srs_id, geom_col = int(row[0]), str(row[1])
            if srs_id != 27700:
                raise RuntimeError(
                    f"Boundary-Line layer {layer} srs_id {srs_id} != 27700"
                )
            # Identifiers come from registry YAML (validated); quote by doubling.
            def q(ident: str) -> str:
                if not ident or not all(
                    ch.isalnum() or ch == "_" for ch in ident
                ):
                    raise RuntimeError(f"unsafe gpkg identifier {ident!r}")
                return '"' + ident.replace('"', '""') + '"'

            sql = (
                f"SELECT {q(geom_col)}, {q(code_field)}, {q(name_field)} "
                f"FROM {q(layer)}"
            )
            features: list[dict[str, Any]] = []
            for geom_blob, code_raw, name_raw in conn.execute(sql):
                code = str(code_raw or "")
                if not code.startswith(code_prefix):
                    continue
                wkb = gpkg_blob_to_wkb(bytes(geom_blob))
                geom = shapely_wkb.loads(wkb)
                name = str(name_raw or "")
                features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "id": code,
                            "code": code,
                            "name": name,
                        },
                        "geometry": mapping(geom),
                    }
                )
            return features
        finally:
            conn.close()
    finally:
        gpkg_path.unlink(missing_ok=True)


def fetch_os_boundary_line(
    url: str,
    sha256: str,
    layer: str,
    code_field: str,
    name_field: str,
    code_prefix: str,
    expected_count: int,
    download_max_mb: float,
    cache_dir: Path,
    max_mb: float | None = None,
    client: httpx.Client | None = None,
) -> tuple[dict[str, Any], bytes, str]:
    """Download (or reuse) Boundary-Line zip → Scotland FeatureCollection.

    Returns ``(collection, raw_geojson_bytes, redacted_url)``. Raises
    ``RuntimeError`` with ``INGEST:``-ready messages (no layer id prefix).
    """
    expected = str(sha256).lower()
    cache = _cache_path(cache_dir, expected)
    redacted = _redact_url(url)
    owns_client = client is None
    http = client or httpx.Client(
        timeout=httpx.Timeout(600.0, connect=30.0),
        follow_redirects=True,
    )
    try:
        reuse = False
        if cache.is_file():
            actual = _sha256_file(cache)
            if actual == expected:
                reuse = True
            else:
                cache.unlink(missing_ok=True)
        if not reuse:
            _download_zip(
                http, url, cache, download_max_mb=float(download_max_mb)
            )
            actual = _sha256_file(cache)
            if actual != expected:
                cache.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Boundary-Line sha256 mismatch: expected {expected}, "
                    f"got {actual}"
                )

        features = _read_features_from_zip(
            cache,
            layer=layer,
            code_field=code_field,
            name_field=name_field,
            code_prefix=code_prefix,
        )
        if len(features) != int(expected_count):
            raise RuntimeError(
                f"expected {int(expected_count)} features with "
                f"{code_field} {code_prefix}*, got {len(features)}"
            )
        collection: dict[str, Any] = {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG::27700"},
            },
            "features": features,
        }
        raw = json.dumps(collection, separators=(",", ":")).encode("utf-8")
        if max_mb is not None and len(raw) > float(max_mb) * 1024 * 1024:
            raise RuntimeError("budget exceeded: mb")
        return collection, raw, redacted
    finally:
        if owns_client:
            http.close()
