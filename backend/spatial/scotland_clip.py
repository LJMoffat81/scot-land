"""Scotland-only clip for context layers (EPSG:27700).

One committed extent file. Callers fail closed when it is missing or the
sha256 does not match the GIS manifest row.
"""

from __future__ import annotations

import csv
import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely import segmentize, set_precision
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform
from shapely.validation import make_valid

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTENT_PATH = (
    REPO_ROOT / "data" / "processed" / "gis" / "scotland_extent.27700.geojson"
)
DEFAULT_MANIFEST_PATH = REPO_ROOT / "data" / "processed" / "gis" / "manifest.csv"

_to_bng = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
_to_wgs = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)

_extent_lock = threading.Lock()
_extent_cache: Any = None
_extent_error: Exception | None = None


class ScotlandClipError(Exception):
    """Fail-closed clip / extent error."""


@dataclass(frozen=True)
class ScotlandExtent:
    """Union of the three zone polygons in EPSG:27700, plus the file sha."""

    geom: BaseGeometry
    zones: dict[str, BaseGeometry]
    sha256: str
    path: Path

    def envelope_wgs84(self) -> tuple[float, float, float, float]:
        """Return (xmin, ymin, xmax, ymax) in EPSG:4326 for NSTA pre-filter."""
        minx, miny, maxx, maxy = self.geom.bounds
        corners = [
            _to_wgs.transform(minx, miny),
            _to_wgs.transform(minx, maxy),
            _to_wgs.transform(maxx, miny),
            _to_wgs.transform(maxx, maxy),
        ]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        return (min(xs), min(ys), max(xs), max(ys))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_sha256(manifest: Path, relative_file: str) -> str:
    with manifest.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row.get("file") or "").strip() == relative_file:
                return (row.get("sha256") or "").strip().lower()
    raise ScotlandClipError(f"CLIP: extent sha256 mismatch")


def load_extent(
    path: Path | str | None = None,
    *,
    manifest: Path | str | None = None,
) -> ScotlandExtent:
    """Load the Scotland extent and check its sha256 against the manifest."""
    extent_path = Path(path) if path is not None else DEFAULT_EXTENT_PATH
    manifest_path = Path(manifest) if manifest is not None else DEFAULT_MANIFEST_PATH
    if not extent_path.is_file():
        raise ScotlandClipError(f"CLIP: extent file missing: {extent_path}")
    actual = _sha256_file(extent_path)
    expected = _manifest_sha256(manifest_path, extent_path.name)
    if actual != expected:
        raise ScotlandClipError("CLIP: extent sha256 mismatch")

    import json

    payload = json.loads(extent_path.read_text(encoding="utf-8"))
    zones: dict[str, BaseGeometry] = {}
    parts: list[BaseGeometry] = []
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        zone = str(props.get("zone") or "")
        geom = shape(feature["geometry"])
        if geom.is_empty:
            continue
        if not geom.is_valid:
            geom = make_valid(geom)
        zones[zone] = geom
        parts.append(geom)
    if not parts:
        raise ScotlandClipError("CLIP: extent sha256 mismatch")
    from shapely.ops import unary_union

    unioned = unary_union(parts)
    if not unioned.is_valid:
        unioned = make_valid(unioned)
    return ScotlandExtent(geom=unioned, zones=zones, sha256=actual, path=extent_path)


def get_process_extent() -> ScotlandExtent:
    """Load once per process (lock-guarded). Re-raises the first failure."""
    global _extent_cache, _extent_error
    with _extent_lock:
        if _extent_cache is not None:
            return _extent_cache
        if _extent_error is not None:
            raise _extent_error
        try:
            _extent_cache = load_extent()
            return _extent_cache
        except Exception as exc:  # noqa: BLE001 — cache the fail-closed reason
            _extent_error = exc
            raise


def reset_process_extent() -> None:
    """Test helper: clear the module-level extent cache."""
    global _extent_cache, _extent_error
    with _extent_lock:
        _extent_cache = None
        _extent_error = None


def _project(geom: BaseGeometry, transformer: Transformer) -> BaseGeometry:
    return shapely_transform(transformer.transform, geom)


def _is_pointish(geom: BaseGeometry) -> bool:
    return geom.geom_type in ("Point", "MultiPoint")


def _is_empty_result(geom: BaseGeometry) -> bool:
    if geom is None or geom.is_empty:
        return True
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom.area <= 0.0
    if geom.geom_type in ("LineString", "MultiLineString"):
        return geom.length <= 0.0
    return False


def clip_features(
    features: list[dict],
    extent: ScotlandExtent,
    *,
    crs: str = "EPSG:4326",
) -> tuple[list[dict], dict[str, Any]]:
    """Clip features to the Scotland extent. Work is in EPSG:27700."""
    if crs != "EPSG:4326":
        raise ScotlandClipError(f"CLIP: unsupported crs {crs}")
    report: dict[str, Any] = {
        "in": len(features),
        "kept": 0,
        "clipped": 0,
        "dropped_outside": 0,
        "invalid": 0,
        "extent_sha256": extent.sha256,
    }
    if not features:
        return [], report

    kept: list[dict] = []
    for feature in features:
        raw_geom = feature.get("geometry")
        if raw_geom is None:
            report["invalid"] += 1
            continue
        if _raw_ring_unclosed(raw_geom):
            report["invalid"] += 1
            continue
        try:
            geom = shape(raw_geom)
        except Exception:
            report["invalid"] += 1
            continue
        if not geom.is_valid:
            geom = make_valid(geom)
        if geom is None or geom.is_empty or not geom.is_valid:
            report["invalid"] += 1
            continue

        projected = _project(geom, _to_bng)
        if not projected.is_valid:
            projected = make_valid(projected)
        if projected is None or projected.is_empty or not projected.is_valid:
            report["invalid"] += 1
            continue
        # Snap to 1 m so WGS84 round-trips do not bleed into clip area (C3).
        projected = set_precision(projected, grid_size=1.0)
        if projected is None or projected.is_empty:
            report["invalid"] += 1
            continue

        out_feature = {"type": "Feature"}
        if "properties" in feature:
            out_feature["properties"] = feature["properties"]

        if _is_pointish(projected):
            # Keep if the centroid is within the extent; geometry unchanged.
            if not extent.geom.contains(projected.centroid) and not extent.geom.covers(
                projected.centroid
            ):
                report["dropped_outside"] += 1
                continue
            out_feature["geometry"] = feature["geometry"]
            kept.append(out_feature)
            report["kept"] += 1
            continue

        if not projected.intersects(extent.geom):
            report["dropped_outside"] += 1
            continue
        clipped = projected.intersection(extent.geom)
        if not clipped.is_valid:
            clipped = make_valid(clipped)
        clipped = set_precision(clipped, grid_size=1.0)
        if _is_empty_result(clipped):
            report["dropped_outside"] += 1
            continue
        changed = not projected.equals(clipped)
        if not changed:
            # Fully inside: keep caller geometry byte-identical (C1 / C9).
            out_feature["geometry"] = feature["geometry"]
        else:
            # Densify before WGS84 so metric area survives the round-trip (C3).
            dense = segmentize(clipped, max_segment_length=50.0)
            out_feature["geometry"] = mapping(_project(dense, _to_wgs))
            report["clipped"] += 1
        kept.append(out_feature)
        report["kept"] += 1
    return kept, report


def _raw_ring_unclosed(raw_geom: dict) -> bool:
    """True when a Polygon / MultiPolygon ring is not closed in the JSON."""
    if not isinstance(raw_geom, dict):
        return False
    gtype = raw_geom.get("type")
    coords = raw_geom.get("coordinates")
    if gtype == "Polygon":
        rings = coords or []
        return any(_ring_open(ring) for ring in rings)
    if gtype == "MultiPolygon":
        polys = coords or []
        return any(_ring_open(ring) for poly in polys for ring in poly)
    return False


def _ring_open(ring: list) -> bool:
    if not ring or len(ring) < 3:
        return True
    return list(ring[0]) != list(ring[-1])


def assert_inside(
    features: list[dict],
    extent: ScotlandExtent,
    *,
    layer: str = "layer",
    tol_m: float = 50.0,
    crs: str = "EPSG:4326",
) -> None:
    """Raise if any feature falls outside extent buffered by tol_m metres."""
    if crs != "EPSG:4326":
        raise ScotlandClipError(f"CLIP: unsupported crs {crs}")
    buffered = extent.geom.buffer(tol_m)
    outside = 0
    first_id: Any = None
    for feature in features:
        raw_geom = feature.get("geometry")
        if raw_geom is None:
            continue
        try:
            geom = shape(raw_geom)
        except Exception:
            continue
        if not geom.is_valid:
            geom = make_valid(geom)
        projected = _project(geom, _to_bng)
        if not projected.is_valid:
            projected = make_valid(projected)
        # ST_IsEmpty(ST_Difference(geom, ST_Buffer(extent, tol)))
        diff = projected.difference(buffered)
        if diff is not None and not diff.is_empty:
            outside += 1
            if first_id is None:
                props = feature.get("properties") or {}
                first_id = props.get("id", props.get("name", "?"))
    if outside:
        raise ScotlandClipError(
            f"CLIP: {layer}: {outside} feature(s) outside Scotland, first id {first_id}"
        )
