"""Point -> data zone (code, vintage). PostGIS first, then a local boundary file, else unavailable.

1. PostGIS `dz_boundaries` (MultiPolygon, EPSG:27700): the WGS84 point is
   transformed to 27700 in SQL and tested with ST_Intersects.
2. If the DB is not configured/reachable, or holds no boundaries, local files
   under DATA_DIR/processed are used if present (GeoJSON; RFC 7946 WGS84, or a
   named EPSG:27700 `crs`). None ship with the repo today: the old lookup
   (c6adad0, spatial/context_tiles.py) queried the maps.gov.scot ArcGIS service.
3. Otherwise `BoundariesUnavailable` (-> HTTP 503 with reasons).

Never returns 'unknown': a miss is an empty list; every returned code is
checked against the NRS code range for its vintage.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from georgist import db
from paths import PROCESSED_DIR
from pyproj import Transformer

logger = logging.getLogger(__name__)

DZ_CODE_RE = re.compile(r"^S01\d{6}$")
# Vintage standard (Scot-LAND Data Zones owns zone identity): `vintage` is the INTEGER
# 2011 or 2022 everywhere: schema, API, loader, frontend. Text labels such as 'DZ2011'
# are refused, never mapped, so a mislabelled source fails loudly instead of joining nothing.
DZ_RANGES = {2011: (6506, 13481), 2022: (13482, 20873)}
VINTAGES = tuple(DZ_RANGES)

BOUNDARY_FILES = {
    2011: "dz2011_boundaries.geojson",
    2022: "dz2022_boundaries.geojson",
}
CODE_FIELDS = ("code", "datazone", "datazone2011", "datazone2022", "dz2011_code", "dz2022_code",
               "dzcode", "dz_code", "dz2011", "dz2022")
NAME_FIELDS = ("name", "dzname", "dz_name", "datazone_name")


class BoundariesUnavailable(RuntimeError):
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


class VintageError(ValueError):
    """A vintage that is not the integer 2011 or 2022 (e.g. the text 'DZ2011')."""


def require_vintage(value: Any, where: str = "vintage") -> int:
    """The integer vintage, or VintageError. Accepts int 2011/2022 only (not bool, not text)."""
    if isinstance(value, bool) or not isinstance(value, int) or value not in DZ_RANGES:
        hint = " (text labels like 'DZ2011' are not accepted; use 2011 or 2022)" if isinstance(value, str) else ""
        raise VintageError(f"{where} must be the integer 2011 or 2022, got {value!r}{hint}")
    return value


def vintage_for_code(code: str) -> int | None:
    if not isinstance(code, str) or not DZ_CODE_RE.match(code):
        return None
    n = int(code[3:])
    for vintage, (lo, hi) in DZ_RANGES.items():
        if lo <= n <= hi:
            return vintage
    return None


@dataclass
class Lookup:
    source: str
    vintages_loaded: list[int]
    zones: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        by_vintage = {z["vintage"]: z for z in self.zones}
        # Default public grain is DZ2022; 2011 only when that vintage alone is present.
        primary = by_vintage.get(2022) or by_vintage.get(2011)
        return {
            # Back-compat with the old /layers/context/data-zones/at shape:
            "code": primary["code"] if primary else None,
            "name": primary["name"] if primary else None,
            "vintage": primary["vintage"] if primary else None,
            "zones": self.zones,
            "dz2011": by_vintage.get(2011),
            "dz2022": by_vintage.get(2022),
            "source": self.source,
            "vintages_loaded": self.vintages_loaded,
        }


def _zone(code: str, vintage: int, name: str | None, hits: int) -> dict[str, Any] | None:
    if vintage_for_code(code) != vintage:
        logger.error("Boundary source returned %r for %s; refused", code, vintage)
        return None
    return {"code": code, "vintage": vintage, "name": (name or None), "on_boundary": hits > 1}


# --------------------------------------------------------------------------- PostGIS

_PG_LOADED = """
    SELECT v.vintage FROM (VALUES (2011::smallint), (2022::smallint)) AS v(vintage)
    WHERE EXISTS (SELECT 1 FROM dz_boundaries b WHERE b.vintage = v.vintage)
"""
_PG_HITS = """
    SELECT vintage, code, name, count(*) OVER (PARTITION BY vintage) AS hits
    FROM dz_boundaries
    WHERE ST_Intersects(geom, ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 27700))
    ORDER BY vintage, code
"""
_PG_POINT = """
    SELECT code, name, vintage,
           ST_Y(ST_Transform(ST_PointOnSurface(geom), 4326)) AS lat,
           ST_X(ST_Transform(ST_PointOnSurface(geom), 4326)) AS lng
    FROM dz_boundaries
    WHERE code = %s AND vintage = %s
    LIMIT 1
"""


def lookup_postgis(lat: float, lon: float) -> Lookup:
    """Raises db.DatabaseUnavailable; returns vintages_loaded=[] when the table is empty."""
    with db.cursor() as cur:
        cur.execute(_PG_LOADED)
        loaded = [r["vintage"] for r in cur.fetchall()]
        zones: list[dict[str, Any]] = []
        if loaded:
            cur.execute(_PG_HITS, (lon, lat))
            seen: set[str] = set()
            for r in cur.fetchall():
                if r["vintage"] in seen:
                    continue
                seen.add(r["vintage"])
                z = _zone(r["code"], r["vintage"], r["name"], int(r["hits"]))
                if z:
                    zones.append(z)
    return Lookup("postgis:dz_boundaries", loaded, zones)


# --------------------------------------------------------------------------- local file

_file_cache: dict[str, tuple[float, Any, list[tuple[str, str | None]], list[Any]]] = {}
_file_lock = threading.Lock()
_bng_to_wgs84: Transformer | None = None


def _wgs84_from_bng(x: float, y: float) -> tuple[float, float]:
    """Reuse one BNG→WGS84 transformer across zone lookups."""
    global _bng_to_wgs84
    transformer = _bng_to_wgs84
    if transformer is None:
        with _file_lock:
            transformer = _bng_to_wgs84
            if transformer is None:
                transformer = Transformer.from_crs(27700, 4326, always_xy=True)
                _bng_to_wgs84 = transformer
    lng, lat = transformer.transform(x, y)
    return lng, lat


def _field(props: dict, candidates: Iterable[str]) -> Any:
    lower = {str(k).lower(): v for k, v in props.items()}
    for c in candidates:
        if c in lower and lower[c] not in (None, ""):
            return lower[c]
    return None


def _is_27700(collection: dict) -> bool:
    name = str(((collection.get("crs") or {}).get("properties") or {}).get("name", ""))
    return "27700" in name


def read_boundary_file(path: Path, vintage: int) -> list[tuple[str, str | None, Any]]:
    """[(code, name, shapely geometry in EPSG:27700)]. Rows with bad codes are refused (logged)."""
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform

    collection = json.loads(Path(path).read_text(encoding="utf-8"))
    to_bng = None if _is_27700(collection) else Transformer.from_crs(4326, 27700, always_xy=True).transform
    out, refused = [], 0
    for feat in collection.get("features", []):
        props = feat.get("properties") or {}
        code = str(_field(props, CODE_FIELDS) or "").strip()
        if vintage_for_code(code) != vintage:
            refused += 1
            continue
        geom = shape(feat["geometry"])
        if to_bng is not None:
            geom = transform(to_bng, geom)
        name = _field(props, NAME_FIELDS)
        out.append((code, str(name).strip() if name else None, geom))
    if refused:
        logger.warning("%s: refused %d features without a valid %s code", path, refused, vintage)
    return out


def _file_index(vintage: int):
    path = PROCESSED_DIR / BOUNDARY_FILES[vintage]
    if not path.is_file():
        return None
    from shapely.strtree import STRtree

    key, mtime = str(path), path.stat().st_mtime
    with _file_lock:
        cached = _file_cache.get(key)
        if cached is None or cached[0] != mtime:
            rows = read_boundary_file(path, vintage)
            tree = STRtree([g for _, _, g in rows])
            cached = (
                mtime,
                tree,
                [(c, n) for c, n, _ in rows],
                [g for _, _, g in rows],
            )
            _file_cache[key] = cached
    return cached[1], cached[2], cached[3]


def lookup_file(lat: float, lon: float) -> Lookup:
    from pyproj import Transformer
    from shapely.geometry import Point

    x, y = Transformer.from_crs(4326, 27700, always_xy=True).transform(lon, lat)
    pt = Point(x, y)
    loaded, zones, names = [], [], []
    for vintage in VINTAGES:
        index = _file_index(vintage)
        if index is None:
            continue
        tree, meta = index[0], index[1]
        loaded.append(vintage)
        names.append(BOUNDARY_FILES[vintage])
        hits = sorted(int(i) for i in tree.query(pt, predicate="intersects"))
        if hits:
            code, name = meta[hits[0]]
            z = _zone(code, vintage, name, len(hits))
            if z:
                zones.append(z)
    if not loaded:
        raise BoundariesUnavailable([f"no boundary file in {PROCESSED_DIR} ({', '.join(BOUNDARY_FILES.values())})"])
    return Lookup("file:" + ",".join(names), loaded, zones)


# --------------------------------------------------------------------------- orchestration


def _point_payload(code: str, vintage: int, name: str | None, lat: float, lng: float) -> dict[str, Any] | None:
    if vintage_for_code(code) != vintage:
        return None
    if not (isinstance(lat, (int, float)) and isinstance(lng, (int, float))):
        return None
    lat_f, lng_f = float(lat), float(lng)
    if not math.isfinite(lat_f) or not math.isfinite(lng_f):
        return None
    return {
        "code": code,
        "name": name or None,
        "vintage": vintage,
        "lat": lat_f,
        "lng": lng_f,
    }


def _point_postgis(code: str, vintage: int) -> dict[str, Any] | None:
    with db.cursor() as cur:
        cur.execute(_PG_POINT, (code, vintage))
        row = cur.fetchone()
    if not row:
        return None
    return _point_payload(row["code"], int(row["vintage"]), row["name"], row["lat"], row["lng"])


def _point_file(code: str, vintage: int) -> dict[str, Any] | None:
    index = _file_index(vintage)
    if index is None:
        raise BoundariesUnavailable(
            [f"no boundary file in {PROCESSED_DIR} ({BOUNDARY_FILES[vintage]})"]
        )
    _tree, meta, geoms = index
    for i, (zone_code, name) in enumerate(meta):
        if zone_code != code:
            continue
        pt = geoms[i].representative_point()
        lng, lat = _wgs84_from_bng(pt.x, pt.y)
        return _point_payload(code, vintage, name, lat, lng)
    return None


def representative_point(code: str) -> dict[str, Any] | None:
    """A point inside the Data Zone polygon, for restoring that zone by code.

    PostGIS first (ST_PointOnSurface), then a local boundary file.
    ``None`` when the source is loaded and the code is absent.
    ``BoundariesUnavailable`` when no boundary source is available.
    """
    vintage = vintage_for_code(code)
    if vintage is None:
        raise ValueError(f"not a data zone code: {code!r}")
    reasons: list[str] = []
    if db.database_configured():
        try:
            found = _point_postgis(code, vintage)
            if found is not None:
                return found
            reasons.append("db: code not in dz_boundaries")
        except db.DatabaseUnavailable as exc:
            reasons.append(f"db: {exc.reason}")
    else:
        reasons.append("db: not_configured")
    try:
        return _point_file(code, vintage)
    except BoundariesUnavailable as exc:
        raise BoundariesUnavailable(reasons + exc.reasons) from None


def lookup(lat: float, lon: float) -> Lookup:
    reasons: list[str] = []
    if db.database_configured():
        try:
            result = lookup_postgis(lat, lon)
            if result.vintages_loaded:
                return result
            reasons.append("db: dz_boundaries is empty")
        except db.DatabaseUnavailable as exc:
            reasons.append(f"db: {exc.reason}")
    else:
        reasons.append("db: not_configured")
    try:
        return lookup_file(lat, lon)
    except BoundariesUnavailable as exc:
        raise BoundariesUnavailable(reasons + exc.reasons) from None
