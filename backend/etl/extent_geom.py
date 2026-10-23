"""Geometry helpers for official Scotland sea extent (densify, OSTN15, flood)."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from pyproj import CRS, Transformer
from shapely import make_valid
from shapely import node as shapely_node
from shapely import set_precision
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
    box,
    mapping,
    shape,
)
from shapely.ops import linemerge, nearest_points, polygonize, snap, unary_union

from etl.extent_sources import ExtentError

# C1b pinned SI vertices strictly inside committed land (after 25 m simplify).
# Values are documentation distances (m) to the land-zone boundary; the check
# enforces membership + ≤350 m only.
IN_LAND_SI: dict[tuple[str, int], float] = {
    ("sch1_pt2_s1", 3): 322.3,
    ("sch1_pt2_s1", 4): 242.8,
}

# OSTN15 NTv2 grid coverage (degrees, WGS 84).
OSTN15_WEST = -9.008
OSTN15_EAST = 2.008
OSTN15_SOUTH = 48.996
OSTN15_NORTH = 61.004

SEED_LON = 0.0
SEED_LAT = 58.5

ART4_POINT = Point(-6.743333333333333, 55.415)  # 6°44'36"W 55°24'54"N


@dataclass
class TransformStats:
    helmert_fallback: int = 0


@dataclass
class BuiltZones:
    land: MultiPolygon
    inshore_0_12nm: MultiPolygon
    offshore_12_200nm: MultiPolygon
    ext_shelf_optional: MultiPolygon | None
    helmert_fallback: int
    snap_count: int
    snap_max_m: float
    sources: list[str] = field(default_factory=list)
    source_dates: dict[str, str] = field(default_factory=dict)


def _require_number(value: object, *, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExtentError(f"EXTENT: {what} must be a number")
    return float(value)


def densify_rhumb(
    coords: Sequence[tuple[float, float]],
    *,
    step_m: float,
    from_crs: str = "EPSG:4277",
) -> list[tuple[float, float]]:
    """Densify a polyline along the loxodrome so no segment exceeds ``step_m``.

    Input vertices are EPSG:27700. They are inverse-projected to ``from_crs``
    (OSGB36 geographic), densified on the Airy 1830 Mercator loxodrome, then
    projected back to EPSG:27700.
    """
    step = _require_number(step_m, what="densify step")
    if not (0 < step <= 1000):
        raise ExtentError("EXTENT: densify step out of range")
    if len(coords) < 2:
        return list(coords)

    to_ll = Transformer.from_crs("EPSG:27700", from_crs, always_xy=True)
    to_xy = Transformer.from_crs(from_crs, "EPSG:27700", always_xy=True)
    # Mercator on Airy 1830 — straight lines are loxodromes.
    airy_merc = CRS.from_proj4(
        "+proj=merc +lat_ts=0 +lon_0=0 +x_0=0 +y_0=0 +ellps=airy +units=m +no_defs"
    )
    ll_crs = CRS.from_user_input(from_crs)
    to_merc = Transformer.from_crs(ll_crs, airy_merc, always_xy=True)
    from_merc = Transformer.from_crs(airy_merc, ll_crs, always_xy=True)

    out: list[tuple[float, float]] = [tuple(coords[0])]
    for i in range(len(coords) - 1):
        x0, y0 = coords[i]
        x1, y1 = coords[i + 1]
        lon0, lat0 = to_ll.transform(x0, y0)
        lon1, lat1 = to_ll.transform(x1, y1)
        mx0, my0 = to_merc.transform(lon0, lat0)
        mx1, my1 = to_merc.transform(lon1, lat1)
        dist = math.hypot(mx1 - mx0, my1 - my0)
        if dist <= step or dist == 0:
            out.append((x1, y1))
            continue
        n = int(math.ceil(dist / step))
        for k in range(1, n):
            t = k / n
            mx = mx0 + t * (mx1 - mx0)
            my = my0 + t * (my1 - my0)
            lon, lat = from_merc.transform(mx, my)
            x, y = to_xy.transform(lon, lat)
            out.append((x, y))
        out.append((x1, y1))
    return out


def _inside_ostn15(lon: float, lat: float) -> bool:
    return (
        OSTN15_WEST <= lon <= OSTN15_EAST and OSTN15_SOUTH <= lat <= OSTN15_NORTH
    )


def load_ostn15_grid(path: Path | str, *, expected_sha256: str) -> Path:
    grid_path = Path(path)
    if not grid_path.is_file():
        raise ExtentError(f"EXTENT: OSTN15 grid missing: {grid_path}")
    actual = hashlib.sha256(grid_path.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise ExtentError("EXTENT: OSTN15 grid sha256 mismatch")
    return grid_path


def ostn15_pipeline_string(grid_path: Path | str) -> str:
    """Explicit OSTN15 PROJ pipeline (unitconvert → inv hgridshift → tmerc BNG)."""
    return (
        "+proj=pipeline "
        "+step +proj=unitconvert +xy_in=deg +xy_out=rad "
        f"+step +proj=hgridshift +inv +grids={Path(grid_path).as_posix()} "
        "+step +proj=tmerc +lat_0=49 +lon_0=-2 +k=0.9996012717 "
        "+x_0=400000 +y_0=-100000 +ellps=airy"
    )


def make_ukho_transformers(grid_path: Path) -> tuple[Transformer, Transformer]:
    """Return (OSTN15 pipeline, Helmert EPSG:1314 via 4326→27700)."""
    ostn = Transformer.from_pipeline(ostn15_pipeline_string(grid_path))
    helmert = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    return ostn, helmert


def transform_ukho(
    lon: float,
    lat: float,
    *,
    ostn: Transformer,
    helmert: Transformer,
    stats: TransformStats | None = None,
) -> tuple[float, float]:
    """Transform one WGS 84 vertex; OSTN15 inside grid, Helmert outside.

    Points inside the published grid bbox that still yield non-finite OSTN15
    results (grid edge holes) use Helmert and count as fallbacks.
    """
    if _inside_ostn15(lon, lat):
        x, y = ostn.transform(lon, lat)
        if math.isfinite(x) and math.isfinite(y):
            return float(x), float(y)
        # Grid hole / edge: fall through to Helmert.
    if stats is not None:
        stats.helmert_fallback += 1
    x, y = helmert.transform(lon, lat)
    return float(x), float(y)


def transform_linestring_ukho(
    coords: Sequence[tuple[float, float]],
    *,
    ostn: Transformer,
    helmert: Transformer,
    stats: TransformStats,
) -> LineString:
    out = [
        transform_ukho(lon, lat, ostn=ostn, helmert=helmert, stats=stats)
        for lon, lat in coords
    ]
    return LineString(out)


def _as_multilinestring(geom) -> MultiLineString:
    if geom is None or geom.is_empty:
        return MultiLineString([])
    if geom.geom_type == "LineString":
        return MultiLineString([geom])
    if geom.geom_type == "MultiLineString":
        return geom
    if geom.geom_type in ("GeometryCollection", "MultiPolygon", "Polygon"):
        lines = []
        for g in getattr(geom, "geoms", [geom]):
            if g.geom_type == "LineString":
                lines.append(g)
            elif g.geom_type == "MultiLineString":
                lines.extend(list(g.geoms))
            elif g.geom_type in ("Polygon", "MultiPolygon"):
                lines.append(LineString(g.exterior.coords))
                for poly in g.geoms if g.geom_type == "MultiPolygon" else [g]:
                    for ring in poly.interiors:
                        lines.append(LineString(ring.coords))
        return MultiLineString(lines)
    raise ExtentError(f"EXTENT: unexpected geometry type {geom.geom_type}")


def snap_endpoints(
    lines: Sequence[LineString],
    *,
    snap_m: float,
    part_labels: Sequence[str] | None = None,
    require_labels: Sequence[str] | None = None,
) -> tuple[list[LineString], int, float]:
    """Add connectors from endpoints to the nearest *other* line within ``snap_m``.

    Closed rings (start≈end) are skipped. An endpoint already lying on another
    line within 1e-3 m needs no connector. Only endpoints whose label is in
    ``require_labels`` (default: all) raise when farther than ``snap_m``.
    """
    snap_tol = float(snap_m)
    all_lines = list(lines)
    connectors: list[LineString] = []
    max_gap = 0.0
    labels = list(part_labels) if part_labels else [f"line{i}" for i in range(len(lines))]
    must = set(require_labels) if require_labels is not None else None

    for idx, line in enumerate(lines):
        coords = list(line.coords)
        if len(coords) < 2:
            continue
        start = Point(coords[0])
        end = Point(coords[-1])
        # Closed ring — no free endpoint.
        if start.distance(end) <= 1e-3:
            continue
        label = labels[idx] if idx < len(labels) else f"line{idx}"
        for end_pt in (start, end):
            best_d = float("inf")
            best_pt = None
            for j, other in enumerate(all_lines):
                if j == idx:
                    continue
                d = other.distance(end_pt)
                if d < best_d:
                    best_d = d
                    best_pt = other.interpolate(other.project(end_pt))
            if best_pt is None:
                if must is None or label in must:
                    raise ExtentError(
                        f"EXTENT: unsnapped endpoint {label} at "
                        f"{end_pt.x:.1f},{end_pt.y:.1f} ({snap_tol:.1f} m)"
                    )
                continue
            if best_d <= 1e-3:
                continue
            if best_d > snap_tol + 1e-6:
                if must is None or label in must:
                    raise ExtentError(
                        f"EXTENT: unsnapped endpoint {label} at "
                        f"{end_pt.x:.1f},{end_pt.y:.1f} ({best_d:.1f} m)"
                    )
                continue
            max_gap = max(max_gap, best_d)
            connectors.append(
                LineString([(end_pt.x, end_pt.y), (best_pt.x, best_pt.y)])
            )
    return all_lines + connectors, len(connectors), max_gap


def _edge_key(a: tuple[float, float], b: tuple[float, float]) -> tuple:
    a2 = (round(a[0], 3), round(a[1], 3))
    b2 = (round(b[0], 3), round(b[1], 3))
    return (a2, b2) if a2 <= b2 else (b2, a2)


def _lines_to_edge_set(lines: Iterable[LineString], tol: float = 1.0) -> set[tuple]:
    edges: set[tuple] = set()
    for line in lines:
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            edges.add(_edge_key(coords[i], coords[i + 1]))
    return edges


def _face_boundary_edges(poly: Polygon) -> set[tuple]:
    edges: set[tuple] = set()
    coords = list(poly.exterior.coords)
    for i in range(len(coords) - 1):
        edges.add(_edge_key(coords[i], coords[i + 1]))
    return edges


def _as_multipolygon(geom) -> MultiPolygon:
    geom = make_valid(geom)
    if geom.is_empty:
        return MultiPolygon([])
    if geom.geom_type == "Polygon":
        return MultiPolygon([geom])
    if geom.geom_type == "MultiPolygon":
        return geom
    polys = [
        g
        for g in getattr(geom, "geoms", [])
        if g.geom_type == "Polygon" and not g.is_empty
    ]
    return MultiPolygon(polys)


def flood_faces(
    faces: Sequence[Polygon],
    *,
    barrier_lines: Sequence[LineString],
    land: MultiPolygon,
    seed_xy: tuple[float, float],
) -> tuple[Polygon, list[Polygon]]:
    """Flood from the seed face across non-barrier edges.

    Returns (seed_face, other_flooded_faces). Land faces may be traversed but
    are excluded from the returned flooded set.
    """
    from shapely import STRtree

    seed_pt = Point(seed_xy)
    seed_idx = None
    for i, face in enumerate(faces):
        if face.contains(seed_pt) or face.covers(seed_pt):
            seed_idx = i
            break
    if seed_idx is None:
        raise ExtentError("EXTENT: seed face not found")

    n = len(faces)
    bounds = [f.boundary for f in faces]
    tree = STRtree(bounds)
    bar_u = unary_union(list(barrier_lines)) if barrier_lines else None
    bar_buf = bar_u.buffer(1.0) if bar_u is not None and not bar_u.is_empty else None

    adj: list[list[int]] = [[] for _ in range(n)]
    for i, boundary in enumerate(bounds):
        for j in tree.query(boundary):
            j = int(j)
            if j <= i:
                continue
            shared = boundary.intersection(bounds[j])
            if shared.is_empty or shared.length < 1.0:
                continue
            if bar_buf is not None:
                on_bar = shared.intersection(bar_buf).length
                if on_bar >= shared.length * 0.5:
                    continue
            adj[i].append(j)
            adj[j].append(i)

    visited = {seed_idx}
    queue = [seed_idx]
    flooded: list[int] = []
    while queue:
        cur = queue.pop(0)
        flooded.append(cur)
        for nb in adj[cur]:
            if nb in visited:
                continue
            visited.add(nb)
            queue.append(nb)

    seed_face = faces[seed_idx]
    others: list[Polygon] = []
    for i in flooded:
        if i == seed_idx:
            continue
        face = faces[i]
        rep = face.representative_point()
        if land.contains(rep) or face.intersection(land).area > face.area * 0.5:
            continue
        others.append(face)
    return seed_face, others


def polygonize_lines(lines: Sequence[LineString]) -> list[Polygon]:
    """Node the linework, snap dangling endpoints within ``snap_m``, polygonize.

    Callers that need a custom snap tolerance should use
    ``polygonize_lines_snapped``.
    """
    faces, _, _ = polygonize_lines_snapped(lines, snap_m=150.0)
    return faces


def polygonize_lines_snapped(
    lines: Sequence[LineString],
    *,
    snap_m: float,
) -> tuple[list[Polygon], int, float]:
    """Node → connect dangling endpoints within ``snap_m`` → polygonize.

    Returns (faces, connector_count, max_connector_m).
    """
    from collections import defaultdict

    from shapely import STRtree
    from shapely import node as shapely_node
    from shapely import set_precision

    snap_tol = float(snap_m)
    merged = unary_union(list(lines))
    noded = shapely_node(set_precision(merged, 0.1))
    parts: list[LineString] = []
    if noded.geom_type == "LineString":
        parts = [noded]
    elif noded.geom_type == "MultiLineString":
        parts = list(noded.geoms)
    elif noded.geom_type == "GeometryCollection":
        for geom in noded.geoms:
            if geom.geom_type == "LineString":
                parts.append(geom)
            elif geom.geom_type == "MultiLineString":
                parts.extend(list(geom.geoms))

    degree: dict[tuple[float, float], int] = defaultdict(int)
    for part in parts:
        coords = list(part.coords)
        if len(coords) < 2:
            continue
        a = (round(coords[0][0], 1), round(coords[0][1], 1))
        b = (round(coords[-1][0], 1), round(coords[-1][1], 1))
        degree[a] += 1
        degree[b] += 1
    dangles = [Point(xy) for xy, deg in degree.items() if deg == 1]

    connectors: list[LineString] = []
    max_gap = 0.0
    tree = STRtree(parts)
    for pt in dangles:
        idxs = tree.query(pt.buffer(snap_tol))
        best_d = float("inf")
        best_pt = None
        for i in idxs:
            other = parts[int(i)]
            if other.distance(pt) < 1e-3:
                continue
            d = other.distance(pt)
            if d < best_d:
                best_d = d
                best_pt = other.interpolate(other.project(pt))
        if best_pt is not None and 1e-3 < best_d <= snap_tol + 1e-6:
            connectors.append(LineString([(pt.x, pt.y), (best_pt.x, best_pt.y)]))
            max_gap = max(max_gap, best_d)

    # SI closure endpoints must land within snap_m of the noded graph.
    # (Checked by callers via dedicated SI vertex distance checks.)

    merged2 = unary_union(parts + connectors)
    faces = [
        f
        for f in polygonize(shapely_node(set_precision(merged2, 0.1)))
        if f.area > 1.0
    ]
    return faces, len(connectors), max_gap


def solway_include_scottish_pockets(
    *,
    land: MultiPolygon,
    inshore: MultiPolygon,
    offshore: MultiPolygon,
    si_s1: LineString,
    s1_vertices: Sequence[tuple[float, float]] | None = None,
) -> MultiPolygon:
    """§3.7 Upper Solway: include Scottish-side faces along densified SI s1.

    Boundary-Line MLW crosses SI Sch1 Pt II s1 east of ~3.35°W, so the main
    flood misses water pockets between Scottish land and the SI line. Locally
    polygonize land boundary + densified s1 (with shortest connectors from
    undensified s1#1/#2 to the land boundary so the graph closes), keep water
    faces that touch land inside the upper-s1 corridor, and merge into inshore
    with ``difference(land)`` — OS land is never cut. Vertices 3 and 4 stay
    inside land (C1b).
    """
    del offshore
    verts = list(s1_vertices) if s1_vertices is not None else list(si_s1.coords)
    if len(verts) < 5:
        return inshore

    # Upper Solway corridor (EPSG:27700) around Sch1 Pt II s1 east of ~3.35°W.
    aoi = box(305_000.0, 555_000.0, 340_000.0, 572_000.0)
    upper = LineString(verts[0:5])
    corridor = upper.buffer(700.0)
    land_boundary = land.boundary

    connectors: list[LineString] = []
    for i in (1, 2):
        vertex = Point(verts[i])
        land_pt, _ = nearest_points(land_boundary, vertex)
        if vertex.distance(land_pt) > 1.0:
            connectors.append(LineString([vertex, land_pt]))

    lines: list[LineString] = []
    for geom in (
        land_boundary.intersection(aoi.buffer(3_000.0)),
        si_s1.intersection(aoi.buffer(3_000.0)),
    ):
        if geom.is_empty:
            continue
        if geom.geom_type == "LineString":
            lines.append(geom)
        elif geom.geom_type == "MultiLineString":
            lines.extend(list(geom.geoms))
    lines.extend(connectors)
    if not lines:
        return inshore

    noded = shapely_node(set_precision(unary_union(lines), 0.1))
    add: list = []
    land_touch = land.buffer(1.0)
    for face in polygonize(noded):
        if face.area <= 1.0:
            continue
        land_frac = face.intersection(land).area / face.area
        if land_frac > 0.05:
            continue
        if not face.intersects(land_touch):
            continue
        if not face.intersects(corridor):
            continue
        add.append(face)
    if not add:
        return inshore

    pocket = make_valid(unary_union(add).difference(land))
    return _as_multipolygon(
        make_valid(unary_union([inshore, pocket]).difference(land))
    )


def make_disjoint_zones(
    land: MultiPolygon,
    inshore: MultiPolygon,
    offshore: MultiPolygon,
    *,
    simplify_m: float = 25.0,
) -> tuple[MultiPolygon, MultiPolygon, MultiPolygon]:
    land = _as_multipolygon(
        make_valid(land.simplify(simplify_m, preserve_topology=True))
    )
    inshore = _as_multipolygon(
        make_valid(
            inshore.difference(land).simplify(simplify_m, preserve_topology=True)
        )
    )
    offshore = _as_multipolygon(
        make_valid(
            offshore.difference(unary_union([land, inshore])).simplify(
                simplify_m, preserve_topology=True
            )
        )
    )
    return land, inshore, offshore


def area_km2(geom) -> float:
    return float(geom.area) / 1e6


def check_si_vertices_near_extent(
    si_parts: dict[str, list[tuple[float, float]]],
    *,
    land: MultiPolygon,
    inshore: MultiPolygon,
    offshore: MultiPolygon,
    in_land_si: dict[tuple[str, int], float] | None = None,
    max_sea_m: float = 150.0,
    max_land_m: float = 350.0,
) -> dict[tuple[str, int], float]:
    """C1 (sea ≤150 m) + C1b (in-land set == IN_LAND_SI, each ≤350 m).

    Returns measured land-boundary distances for each in-land SI vertex.
    """
    pins = dict(IN_LAND_SI if in_land_si is None else in_land_si)
    union = unary_union([land, inshore, offshore])
    boundary = union.boundary
    land_boundary = land.boundary
    measured: dict[tuple[str, int], float] = {}
    for part, verts in si_parts.items():
        for i, (x, y) in enumerate(verts):
            pt = Point(x, y)
            key = (part, i)
            # Polygon.contains is False on the boundary → strict interior.
            if land.contains(pt):
                d_land = float(land_boundary.distance(pt))
                measured[key] = d_land
                if key not in pins:
                    raise ExtentError(
                        f"EXTENT-CHECK: SI vertex {part}#{i} inside land "
                        f"but not in IN_LAND_SI"
                    )
                if d_land > max_land_m + 1e-6:
                    raise ExtentError(
                        f"EXTENT-CHECK: pinned SI vertex {part}#{i} "
                        f"{d_land:.1f} m from land boundary "
                        f"(max {int(max_land_m) if max_land_m == int(max_land_m) else max_land_m})"
                    )
                continue
            if key in pins:
                raise ExtentError(
                    f"EXTENT-CHECK: pinned SI vertex {part}#{i} not inside land"
                )
            d = float(boundary.distance(pt))
            if d > max_sea_m + 1e-6:
                raise ExtentError(
                    f"EXTENT-CHECK: SI vertex {part}#{i} {d:.1f} m from edge "
                    f"(max {int(max_sea_m) if max_sea_m == int(max_sea_m) else max_sea_m})"
                )
    for key in pins:
        if key not in measured:
            part, i = key
            raise ExtentError(
                f"EXTENT-CHECK: pinned SI vertex {part}#{i} not inside land"
            )
    return measured


def check_tsl_median(
    tsl_line: LineString,
    inshore: MultiPolygon,
    *,
    sample_m: float = 1000.0,
    max_median_m: float = 50.0,
) -> float:
    outer = inshore.boundary
    length = tsl_line.length
    if length <= 0:
        raise ExtentError("EXTENT-CHECK: TSL median 0.0 m (max 50)")
    dists = []
    n = max(1, int(math.ceil(length / sample_m)))
    for i in range(n + 1):
        pt = tsl_line.interpolate(i / n, normalized=True)
        dists.append(outer.distance(pt))
    dists.sort()
    mid = dists[len(dists) // 2]
    if mid > max_median_m + 1e-6:
        raise ExtentError(
            f"EXTENT-CHECK: TSL median {mid:.1f} m (max {int(max_median_m)})"
        )
    return mid


def check_zone_areas(
    zones: dict[str, MultiPolygon],
    expected_km2: dict[str, float],
    *,
    tol: float = 0.01,
) -> None:
    for name, expected in expected_km2.items():
        if name == "union":
            got = area_km2(unary_union(list(zones.values())))
        else:
            got = area_km2(zones[name])
        lo, hi = expected * (1 - tol), expected * (1 + tol)
        if not (lo <= got <= hi):
            raise ExtentError(
                f"EXTENT-CHECK: {name} area {got:.1f} km2 outside ±1% of "
                f"{int(expected) if expected == int(expected) else expected}"
            )


def check_labels_and_sources(features: list[dict]) -> None:
    for feature in features:
        props = feature.get("properties") or {}
        zone = props.get("zone")
        label = props.get("label") or ""
        if "illustrative" not in str(label).lower():
            raise ExtentError(
                f"EXTENT-CHECK: zone {zone} label missing illustrative"
            )
        if not props.get("sources"):
            raise ExtentError(f"EXTENT-CHECK: zone {zone} label missing illustrative")
        if not props.get("source_dates"):
            raise ExtentError(f"EXTENT-CHECK: zone {zone} label missing illustrative")


def is_art4_tsl_segment(geom, props: dict) -> bool:
    """UK TSL segment that is SI Art 4(b)(ii) (NI TSL to 55°24'54\"N 6°44'36\"W)."""
    if props.get("Feature") != "Territorial Sea Limit":
        return False
    if props.get("State") != "United Kingdom":
        return False
    g = geom if hasattr(geom, "distance") else shape(geom)
    return g.distance(ART4_POINT) < 0.01 and 0.05 < g.length < 0.5
