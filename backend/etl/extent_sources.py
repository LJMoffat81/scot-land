"""Load and validate Scotland extent source YAML and SI vertex GeoJSON."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


class ExtentError(Exception):
    """Scotland extent failure (message prefixes ``CLIP:``, ``EXTENT-``…)."""


UKHO_ATTRIBUTION = (
    "Contains public sector information, licensed under the Open Government "
    "Licence v3.0, from UK Hydrographic Office."
)

REQUIRED_SOURCE_IDS = ("ukho-mlb", "si-1999-1126", "os-boundary-line", "ostn15")
SI_PARTS = ("sch1_pt1_east", "sch1_pt2_s1", "sch1_pt2_s2", "sch2")
SI_VERTEX_COUNTS = {
    "sch1_pt1_east": 7,
    "sch1_pt2_s1": 33,
    "sch1_pt2_s2": 118,
    "sch2": 21,
}
# British National Grid practical bounds (metres).
BNG_BOUNDS = (-100_000.0, 700_000.0, -100_000.0, 1_400_000.0)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


@dataclass(frozen=True)
class ExtentSource:
    id: str
    publisher: str
    url: str
    licence: str
    attribution: str
    published: str
    fetched: str
    sha256: str
    crs: int


@dataclass(frozen=True)
class SolwayConfig:
    """§3.7 Upper Solway AOI (EPSG:27700) and corridor buffer (metres)."""

    aoi: tuple[float, float, float, float]  # minx, miny, maxx, maxy
    corridor_m: float


@dataclass(frozen=True)
class ExtentSourcesConfig:
    snap_m: float
    densify_max_m: float
    sources: dict[str, ExtentSource]
    solway: SolwayConfig
    # sha256 of data/reference/sea/ukho_tsl_scotland.27700.geojson
    tsl_reference_sha256: str

    def get(self, source_id: str) -> ExtentSource:
        return self.sources[source_id]

    def reference_sha256_manifest(self) -> dict[str, str]:
        """Filename → sha256 for C5/K7 committed reference inputs."""
        return {
            "si1999_1126_vertices.27700.geojson": self.get("si-1999-1126").sha256,
            "ukho_tsl_scotland.27700.geojson": self.tsl_reference_sha256,
        }


def _as_date_str(value: Any, *, source_id: str, key: str) -> str:
    if isinstance(value, bool):
        raise ExtentError(f"EXTENT-SRC: {source_id} {key} must be a date")
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        raise ExtentError(f"EXTENT-SRC: {source_id} {key} must be a date")
    if not _DATE_RE.fullmatch(value):
        raise ExtentError(f"EXTENT-SRC: {source_id} {key} invalid date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ExtentError(f"EXTENT-SRC: {source_id} {key} invalid date") from exc
    return value


def _require_str(entry: dict[str, Any], source_id: str, key: str) -> str:
    if key not in entry:
        raise ExtentError(f"EXTENT-SRC: {source_id} missing key {key}")
    value = entry[key]
    if not isinstance(value, str):
        if key == "sha256":
            raise ExtentError(f"EXTENT-SRC: {source_id} sha256 must be a string")
        raise ExtentError(f"EXTENT-SRC: {source_id} missing key {key}")
    return value


def _parse_source(entry: Any) -> ExtentSource:
    if not isinstance(entry, dict):
        raise ExtentError("EXTENT-SRC: sources root must be a mapping")
    source_id = entry.get("id")
    if not isinstance(source_id, str) or not source_id:
        raise ExtentError("EXTENT-SRC: missing key sources")
    for key in (
        "publisher",
        "url",
        "licence",
        "attribution",
        "published",
        "fetched",
        "sha256",
        "crs",
    ):
        if key not in entry:
            raise ExtentError(f"EXTENT-SRC: {source_id} missing key {key}")

    sha = entry["sha256"]
    if not isinstance(sha, str):
        raise ExtentError(f"EXTENT-SRC: {source_id} sha256 must be a string")
    if not _SHA256_RE.fullmatch(sha):
        raise ExtentError(f"EXTENT-SRC: {source_id} sha256 invalid")

    url = _require_str(entry, source_id, "url")
    if not url.startswith("https://"):
        raise ExtentError(f"EXTENT-SRC: {source_id} url must be https")

    licence = _require_str(entry, source_id, "licence")
    if licence != "OGL-3.0":
        raise ExtentError(f"EXTENT-SRC: {source_id} licence must be OGL-3.0")

    attribution = _require_str(entry, source_id, "attribution")
    if source_id == "ukho-mlb" and attribution != UKHO_ATTRIBUTION:
        raise ExtentError(f"EXTENT-SRC: {source_id} attribution mismatch")

    published = _as_date_str(entry["published"], source_id=source_id, key="published")
    fetched = _as_date_str(entry["fetched"], source_id=source_id, key="fetched")

    crs = entry["crs"]
    if isinstance(crs, bool) or not isinstance(crs, int):
        raise ExtentError(f"EXTENT-SRC: {source_id} crs must be an integer")

    return ExtentSource(
        id=source_id,
        publisher=_require_str(entry, source_id, "publisher"),
        url=url,
        licence=licence,
        attribution=attribution,
        published=published,
        fetched=fetched,
        sha256=sha,
        crs=crs,
    )


def _parse_number(value: Any, *, key: str, lo_exclusive: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExtentError(f"EXTENT-SRC: {key} must be a number")
    number = float(value)
    if not (lo_exclusive < number <= hi):
        raise ExtentError(f"EXTENT-SRC: {key} out of range")
    return number


def load_extent_sources(path: Path | str) -> ExtentSourcesConfig:
    """Load and validate ``scotland_extent_sources.yaml`` (only entry point)."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ExtentError(f"EXTENT-SRC: sources file missing: {file_path}")
    raw = file_path.read_bytes()
    if not raw.strip():
        raise ExtentError(f"EXTENT-SRC: sources file empty: {file_path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExtentError(f"EXTENT-SRC: sources file not YAML: {file_path}") from exc
    if not text.strip():
        raise ExtentError(f"EXTENT-SRC: sources file empty: {file_path}")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ExtentError(f"EXTENT-SRC: sources file not YAML: {file_path}") from exc

    if isinstance(data, list):
        raise ExtentError("EXTENT-SRC: sources root must be a mapping")
    if not isinstance(data, dict):
        raise ExtentError("EXTENT-SRC: sources root must be a mapping")

    allowed = {
        "snap_m",
        "densify_max_m",
        "sources",
        "solway",
        "tsl_reference_sha256",
    }
    for key in data:
        if key not in allowed:
            raise ExtentError(f"EXTENT-SRC: unknown key {key}")

    if "sources" not in data:
        raise ExtentError("EXTENT-SRC: missing key sources")
    if "snap_m" not in data:
        raise ExtentError("EXTENT-SRC: missing key sources")
    if "densify_max_m" not in data:
        raise ExtentError("EXTENT-SRC: missing key sources")
    if "solway" not in data:
        raise ExtentError("EXTENT-SRC: missing key solway")
    if "tsl_reference_sha256" not in data:
        raise ExtentError("EXTENT-SRC: missing key tsl_reference_sha256")

    snap_m = _parse_number(data["snap_m"], key="snap_m", lo_exclusive=0.0, hi=150.0)
    densify_max_m = _parse_number(
        data["densify_max_m"], key="densify_max_m", lo_exclusive=0.0, hi=1000.0
    )
    solway = _parse_solway(data["solway"])
    tsl_sha = data["tsl_reference_sha256"]
    if not isinstance(tsl_sha, str):
        raise ExtentError("EXTENT-SRC: tsl_reference_sha256 must be a string")
    if not _SHA256_RE.fullmatch(tsl_sha):
        raise ExtentError("EXTENT-SRC: tsl_reference_sha256 invalid")

    entries = data["sources"]
    if not isinstance(entries, list):
        raise ExtentError("EXTENT-SRC: sources root must be a mapping")

    sources: dict[str, ExtentSource] = {}
    for entry in entries:
        parsed = _parse_source(entry)
        if parsed.id in sources:
            raise ExtentError(f"EXTENT-SRC: duplicate source {parsed.id}")
        sources[parsed.id] = parsed

    for required in REQUIRED_SOURCE_IDS:
        if required not in sources:
            raise ExtentError(f"EXTENT-SRC: missing source {required}")

    return ExtentSourcesConfig(
        snap_m=snap_m,
        densify_max_m=densify_max_m,
        sources=sources,
        solway=solway,
        tsl_reference_sha256=tsl_sha,
    )


def _parse_solway(value: Any) -> SolwayConfig:
    if not isinstance(value, dict):
        raise ExtentError("EXTENT-SRC: solway must be a mapping")
    allowed = {"aoi", "corridor_m"}
    for key in value:
        if key not in allowed:
            raise ExtentError(f"EXTENT-SRC: unknown key solway.{key}")
    if "aoi" not in value:
        raise ExtentError("EXTENT-SRC: solway missing key aoi")
    if "corridor_m" not in value:
        raise ExtentError("EXTENT-SRC: solway missing key corridor_m")
    aoi = value["aoi"]
    if not isinstance(aoi, list) or len(aoi) != 4:
        raise ExtentError("EXTENT-SRC: solway aoi must be [minx, miny, maxx, maxy]")
    coords: list[float] = []
    for item in aoi:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ExtentError("EXTENT-SRC: solway aoi must be [minx, miny, maxx, maxy]")
        coords.append(float(item))
    minx, miny, maxx, maxy = coords
    if not (minx < maxx and miny < maxy):
        raise ExtentError("EXTENT-SRC: solway aoi must be [minx, miny, maxx, maxy]")
    corridor_m = _parse_number(
        value["corridor_m"], key="solway.corridor_m", lo_exclusive=0.0, hi=10_000.0
    )
    return SolwayConfig(aoi=(minx, miny, maxx, maxy), corridor_m=corridor_m)


def load_si_vertices(
    path: Path | str, *, expected_sha256: str | None = None
) -> dict[str, list[tuple[float, float]]]:
    """Load densify-ready SI LineStrings in EPSG:27700."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ExtentError(f"EXTENT-SI: file missing: {file_path}")
    raw = file_path.read_bytes()
    if not raw.strip():
        raise ExtentError(f"EXTENT-SI: file empty: {file_path}")
    if expected_sha256 is not None:
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected_sha256:
            raise ExtentError("EXTENT-SI: sha256 mismatch")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExtentError(f"EXTENT-SI: file not GeoJSON: {file_path}") from exc

    if isinstance(payload, list) or not isinstance(payload, dict):
        raise ExtentError("EXTENT-SI: root must be a FeatureCollection")
    if payload.get("type") != "FeatureCollection":
        raise ExtentError("EXTENT-SI: root must be a FeatureCollection")

    features = payload.get("features") or []
    parts: dict[str, list[tuple[float, float]]] = {}
    for feature in features:
        props = feature.get("properties") or {}
        part = props.get("part")
        geom = feature.get("geometry") or {}
        if part not in SI_PARTS:
            continue
        if geom.get("type") != "LineString":
            raise ExtentError(f"EXTENT-SI: {part} must be a LineString")
        coords = geom.get("coordinates") or []
        vertices: list[tuple[float, float]] = []
        for i, coord in enumerate(coords):
            if (
                not isinstance(coord, (list, tuple))
                or len(coord) < 2
                or isinstance(coord[0], bool)
                or isinstance(coord[1], bool)
                or not isinstance(coord[0], (int, float))
                or not isinstance(coord[1], (int, float))
            ):
                raise ExtentError(f"EXTENT-SI: {part} vertex {i} not numeric")
            x, y = float(coord[0]), float(coord[1])
            minx, maxx, miny, maxy = BNG_BOUNDS
            if not (minx <= x <= maxx and miny <= y <= maxy):
                raise ExtentError(
                    f"EXTENT-SI: {part} vertex {i} outside EPSG:27700 bounds"
                )
            vertices.append((x, y))
        expected_n = SI_VERTEX_COUNTS[part]
        if len(vertices) != expected_n:
            raise ExtentError(
                f"EXTENT-SI: {part} has {len(vertices)} vertices, expected {expected_n}"
            )
        parts[part] = vertices

    missing = [p for p in SI_PARTS if p not in parts]
    if missing:
        raise ExtentError(
            "EXTENT-SI: parts must be sch1_pt1_east,sch1_pt2_s1,sch1_pt2_s2,sch2"
        )
    return parts
