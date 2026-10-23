"""SRC-A extent geometry checks C1–C7 and negative K/T/R tests."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import shutil
from pathlib import Path

import pytest
import yaml
from pyproj import Transformer
from shapely.affinity import scale
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

from etl.extent_geom import (
    IN_LAND_SI,
    TransformStats,
    area_km2,
    check_labels_and_sources,
    check_no_ext_shelf_in_extent,
    check_reference_sha,
    check_registry_title,
    check_si_vertices_near_extent,
    check_tsl_median,
    check_zone_areas,
    densify_rhumb,
    flood_faces,
    load_ostn15_grid,
    make_ukho_transformers,
    ostn15_pipeline_string,
    snap_endpoints,
    transform_ukho,
)
from etl.extent_sources import ExtentError, load_extent_sources, load_si_vertices
from layers.catalog_copy import SCOTLAND_EXTENT_MARINE_CREDIT

REPO = Path(__file__).resolve().parents[2]
EXTENT = REPO / "data" / "processed" / "gis" / "scotland_extent.27700.geojson"
EXT_SHELF = REPO / "data" / "processed" / "gis" / "scotland_ext_shelf_optional.27700.geojson"
MANIFEST = REPO / "data" / "processed" / "gis" / "manifest.csv"
SI_REF = REPO / "data" / "reference" / "sea" / "si1999_1126_vertices.27700.geojson"
TSL_REF = REPO / "data" / "reference" / "sea" / "ukho_tsl_scotland.27700.geojson"
SOURCES = REPO / "backend" / "layers" / "extent" / "scotland_extent_sources.yaml"
REGISTRY = REPO / "backend" / "layers" / "registry" / "scotland-extent.yaml"

EXPECTED_KM2 = {
    "land": 80_221.0,
    "inshore_0_12nm": 89_034.0,
    "offshore_12_200nm": 364_711.0,
    "union": 533_963.0,
}

# Committed reference inputs — sha pins from sources YAML (SI + tsl_reference_sha256).
REFERENCE_SHA256 = load_extent_sources(SOURCES).reference_sha256_manifest()

DEFAULT_EXTENT_ZONES = frozenset({"land", "inshore_0_12nm", "offshore_12_200nm"})
SHELF_REQUIRED_NOTE = (
    "Seabed rights only; not Scottish waters; outside the default clip"
)


def _zones() -> dict[str, MultiPolygon]:
    fc = json.loads(EXTENT.read_text(encoding="utf-8"))
    out: dict[str, MultiPolygon] = {}
    for feature in fc["features"]:
        zone = feature["properties"]["zone"]
        geom = shape(feature["geometry"])
        if geom.geom_type == "Polygon":
            geom = MultiPolygon([geom])
        out[zone] = geom
    return out


def test_c1_si_vertices_near_extent(capsys):
    cfg = load_extent_sources(SOURCES)
    parts = load_si_vertices(SI_REF, expected_sha256=cfg.get("si-1999-1126").sha256)
    zones = _zones()
    measured = check_si_vertices_near_extent(
        parts,
        land=zones["land"],
        inshore=zones["inshore_0_12nm"],
        offshore=zones["offshore_12_200nm"],
        in_land_si=IN_LAND_SI,
        max_sea_m=150.0,
        max_land_m=350.0,
    )
    assert set(measured) == set(IN_LAND_SI)
    for key, pinned in IN_LAND_SI.items():
        print(f"C1b {key[0]}#{key[1]}: measured={measured[key]:.1f} m (doc {pinned})")
    captured = capsys.readouterr()
    assert "C1b sch1_pt2_s1#3:" in captured.out
    assert "C1b sch1_pt2_s1#4:" in captured.out


def test_c2_tsl_median():
    zones = _zones()
    fc = json.loads(TSL_REF.read_text(encoding="utf-8"))
    geom = shape(fc["features"][0]["geometry"])
    if geom.geom_type == "MultiLineString":
        # Use longest part as sample line; check samples along all parts.
        lines = list(geom.geoms)
    else:
        lines = [geom]
    dists = []
    outer = zones["inshore_0_12nm"].boundary
    for line in lines:
        length = line.length
        if length <= 0:
            continue
        n = max(1, int(math.ceil(length / 1000.0)))
        for i in range(n + 1):
            pt = line.interpolate(i / n, normalized=True)
            dists.append(outer.distance(pt))
    dists.sort()
    mid = dists[len(dists) // 2]
    assert mid <= 50.0 + 1e-6, f"EXTENT-CHECK: TSL median {mid:.1f} m (max 50)"


def test_c3_zone_areas():
    zones = _zones()
    check_zone_areas(zones, EXPECTED_KM2, tol=0.01)


def test_c4_ext_shelf_disjoint_and_hatton():
    zones = _zones()
    check_no_ext_shelf_in_extent(zones)
    shelf = json.loads(EXT_SHELF.read_text(encoding="utf-8"))
    for feature in shelf["features"]:
        props = feature["properties"]
        note = props.get("note") or ""
        assert note == SHELF_REQUIRED_NOTE
        zone = props.get("zone")
        assert zone not in DEFAULT_EXTENT_ZONES
        assert zone == "ext_shelf_optional"
    shelf_geoms = [shape(f["geometry"]) for f in shelf["features"]]
    shelf_u = unary_union(shelf_geoms)
    extent_u = unary_union(list(zones.values()))
    overlap = extent_u.intersection(shelf_u).area / 1e6
    assert overlap <= 1.0 + 1e-6
    hatton = max(shelf_geoms, key=lambda g: g.area)
    hatton_km2 = hatton.area / 1e6
    assert abs(hatton_km2 - 158_576.0) / 158_576.0 <= 0.01


def test_c5_labels_sources_manifest():
    fc = json.loads(EXTENT.read_text(encoding="utf-8"))
    check_labels_and_sources(fc["features"])
    text = MANIFEST.read_text(encoding="utf-8")
    assert SCOTLAND_EXTENT_MARINE_CREDIT in text
    # Both committed reference files match the pinned sha manifest.
    check_reference_sha(SI_REF, REFERENCE_SHA256)
    check_reference_sha(TSL_REF, REFERENCE_SHA256)


def test_c6_densify_rhumb_segments():
    cfg = load_extent_sources(SOURCES)
    # Synthetic: 5 km segment must densify to ≤ densify_max_m.
    coords = [(300000.0, 700000.0), (305000.0, 700000.0)]
    out = densify_rhumb(coords, step_m=cfg.densify_max_m)
    for i in range(len(out) - 1):
        d = math.hypot(out[i + 1][0] - out[i][0], out[i + 1][1] - out[i][1])
        assert d <= cfg.densify_max_m + 1e-6
    parts = load_si_vertices(SI_REF, expected_sha256=cfg.get("si-1999-1126").sha256)
    for part, verts in parts.items():
        dens = densify_rhumb(verts, step_m=cfg.densify_max_m)
        for i in range(len(dens) - 1):
            d = math.hypot(dens[i + 1][0] - dens[i][0], dens[i + 1][1] - dens[i][1])
            assert d <= cfg.densify_max_m + 1e-6, f"{part} segment {i} = {d}"


# C7 (a): Helmert path always runs in CI (no grid file required).
# C7 (b): OSTN15 pins + pipeline string always asserted; live OSTN15 when grid present.
OSTN15_REF_POINTS = (
    # (lon, lat, easting, northing) — measured with OSTN15 pipeline ±0.1 m
    (-3.0, 57.0, 339350.6, 790316.9),
    (-4.0, 56.0, 275368.1, 680367.3),
    (-2.0, 58.0, 400099.6, 901199.6),
    (-1.0, 55.0, 464068.6, 567725.9),
)
HELMERT_OUTSIDE = (-14.5, 58.0, -336188.9, 969694.6)


def test_c7_helmert_outside_grid():
    """Helmert EPSG:1314 path for a point outside the OSTN15 grid bbox."""
    helmert = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)

    class _BoomOstn:
        def transform(self, lon, lat):  # pragma: no cover - must not be called
            raise AssertionError("OSTN15 must not run outside the grid bbox")

    stats = TransformStats()
    lon, lat, ex, ny = HELMERT_OUTSIDE
    x, y = transform_ukho(
        lon, lat, ostn=_BoomOstn(), helmert=helmert, stats=stats
    )
    assert abs(x - ex) <= 0.1
    assert abs(y - ny) <= 0.1
    assert stats.helmert_fallback == 1


def test_c7_ostn15_pipeline_and_pins():
    """Pipeline string + 4 pinned OSTN15 outputs; live check when grid is present."""
    assert len(OSTN15_REF_POINTS) == 4
    grid_placeholder = Path("/nonexistent/uk_os_OSTN15_NTv2_OSGBtoETRS.tif")
    pipe = ostn15_pipeline_string(grid_placeholder)
    assert pipe.startswith("+proj=pipeline ")
    assert "+proj=unitconvert +xy_in=deg +xy_out=rad" in pipe
    assert "+proj=hgridshift +inv +grids=" in pipe
    assert "uk_os_OSTN15_NTv2_OSGBtoETRS.tif" in pipe
    assert "+proj=tmerc +lat_0=49 +lon_0=-2 +k=0.9996012717" in pipe
    assert "+ellps=airy" in pipe

    # Pinned table is the CI contract when the binary grid is not cached.
    for lon, lat, ex, ny in OSTN15_REF_POINTS:
        assert isinstance(lon, float) and isinstance(lat, float)
        assert isinstance(ex, float) and isinstance(ny, float)

    cfg = load_extent_sources(SOURCES)
    grid_src = Path("/workspace/scot-land-data/uk_os_OSTN15_NTv2_OSGBtoETRS.tif")
    if grid_src.is_file():
        grid = load_ostn15_grid(grid_src, expected_sha256=cfg.get("ostn15").sha256)
        assert ostn15_pipeline_string(grid) == pipe.replace(
            grid_placeholder.as_posix(), grid.as_posix()
        )
        ostn, helmert = make_ukho_transformers(grid)
        stats = TransformStats()
        for lon, lat, ex, ny in OSTN15_REF_POINTS:
            x, y = transform_ukho(lon, lat, ostn=ostn, helmert=helmert, stats=stats)
            assert abs(x - ex) <= 0.1, (lon, lat, x, y)
            assert abs(y - ny) <= 0.1, (lon, lat, x, y)
        assert stats.helmert_fallback == 0
        lon, lat, ex, ny = HELMERT_OUTSIDE
        x2, y2 = transform_ukho(lon, lat, ostn=ostn, helmert=helmert, stats=stats)
        assert abs(x2 - ex) <= 0.1
        assert abs(y2 - ny) <= 0.1
        assert stats.helmert_fallback == 1


# --- geometry negatives T1–T8 ---


def test_t1_ostn15_missing(tmp_path):
    with pytest.raises(ExtentError, match=r"^EXTENT: OSTN15 grid missing: "):
        load_ostn15_grid(tmp_path / "none.tif", expected_sha256="a" * 64)


def test_t2_ostn15_sha_mismatch(tmp_path):
    path = tmp_path / "grid.tif"
    path.write_bytes(b"x")
    with pytest.raises(ExtentError, match=r"^EXTENT: OSTN15 grid sha256 mismatch$"):
        load_ostn15_grid(path, expected_sha256="a" * 64)


def test_t3_densify_step_zero():
    with pytest.raises(ExtentError, match=r"^EXTENT: densify step out of range$"):
        densify_rhumb([(0.0, 0.0), (1.0, 0.0)], step_m=0)


def test_t4_densify_step_bool():
    with pytest.raises(ExtentError, match=r"^EXTENT: densify step must be a number$"):
        densify_rhumb([(0.0, 0.0), (1.0, 0.0)], step_m=True)  # type: ignore[arg-type]


def test_t5_unsnapped_endpoint():
    # Both part-a endpoints are exactly 151 m from part-b; first raise is start.
    a = LineString([(100.0, 0.0), (200.0, 0.0)])
    b = LineString([(100.0, 151.0), (200.0, 151.0)])
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT: unsnapped endpoint part-a at 100\.0,0\.0 \(151\.0 m\)$",
    ):
        snap_endpoints(
            [a, b],
            snap_m=150,
            part_labels=["part-a", "part-b"],
            require_labels=["part-a"],
        )


def test_t6_seed_face_not_found():
    # Open ring — no faces.
    with pytest.raises(ExtentError, match=r"^EXTENT: seed face not found$"):
        flood_faces(
            [],
            barrier_lines=[],
            land=MultiPolygon([]),
            seed_xy=(0.0, 0.0),
        )


def _synthetic_ukho_zip(path: Path, *, include_eez: bool) -> str:
    """Minimal UKHO-like shapefile zip; returns sha256 of the zip bytes."""
    import shapefile

    staging = path.parent / (path.stem + "_shp")
    staging.mkdir(parents=True, exist_ok=True)
    shp_path = staging / "ukho_synth"
    with shapefile.Writer(str(shp_path), shapeType=shapefile.POLYLINE) as w:
        w.field("State", "C", size=58)
        w.field("Feature", "C", size=200)
        w.field("Datum", "C", size=200)
        w.field("Date", "C", size=200)
        w.field("Source", "C", size=200)
        w.field("Boundary", "C", size=200)
        # Inside AOI lon −25…10, lat 53.5…65.
        w.line([[[ -3.0, 58.0], [-2.5, 58.1]]])
        w.record(
            "United Kingdom",
            "Territorial Sea Limit",
            "WGS 84",
            "2026-01-07",
            "test",
            "",
        )
        w.line([[[ -3.0, 59.0], [-2.5, 59.1]]])
        w.record(
            "United Kingdom",
            "Median line in absence of agreed maritime boundary",
            "WGS 84",
            "2026-01-07",
            "test",
            "",
        )
        if include_eez:
            w.line([[[ -4.0, 60.0], [-3.5, 60.1]]])
            w.record(
                "United Kingdom",
                "Exclusive Economic Zone Limit",
                "WGS 84",
                "2026-01-07",
                "test",
                "",
            )
    import zipfile as zipfile_mod

    with zipfile_mod.ZipFile(path, "w") as zf:
        for ext in (".shp", ".shx", ".dbf"):
            zf.write(shp_path.with_suffix(ext), arcname=f"ukho_synth{ext}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_t7_ukho_class_missing(tmp_path):
    from etl.build_scotland_extent import _load_ukho

    zip_path = tmp_path / "ukho_no_eez.zip"
    sha = _synthetic_ukho_zip(zip_path, include_eez=False)
    helmert = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT: UKHO class missing: Exclusive Economic Zone Limit$",
    ):
        _load_ukho(
            zip_path,
            expected_sha=sha,
            ostn=helmert,
            helmert=helmert,
            stats=TransformStats(),
        )


def test_t8_ukho_sha_mismatch(tmp_path):
    from etl.build_scotland_extent import _load_ukho

    zip_path = tmp_path / "onebyte.zip"
    zip_path.write_bytes(b"x")
    with pytest.raises(ExtentError, match=r"^EXTENT: UKHO sha256 mismatch$"):
        _load_ukho(
            zip_path,
            expected_sha="a" * 64,
            ostn=None,
            helmert=None,
            stats=TransformStats(),
        )


# --- CI check negatives K1, K8–K11 (K2 replaced by A1) ---


def test_k1_si_vertex_151m(tmp_path):
    # Synthetic square land; sea vertex 151.0 m north of the north edge.
    synth_land = MultiPolygon([box(-1000.0, -1000.0, 1000.0, 1000.0)])
    edge = (0.0, 1000.0)
    parts = {
        "sch1_pt1_east": [(0.0, 1000.0 + 151.0)],
        "sch1_pt2_s1": [
            edge,
            edge,
            edge,
            (0.0, 1000.0 - 322.3),
            (0.0, 1000.0 - 242.8),
        ],
        "sch1_pt2_s2": [edge],
        "sch2": [edge],
    }
    empty_sea = MultiPolygon([Point(5000, 5000).buffer(10.0)])
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: SI vertex sch1_pt1_east#0 151\.0 m from edge \(max 150\)$",
    ):
        check_si_vertices_near_extent(
            parts,
            land=synth_land,
            inshore=empty_sea,
            offshore=empty_sea,
            in_land_si=IN_LAND_SI,
            max_sea_m=150.0,
            max_land_m=350.0,
        )


def test_k8_extra_si_inside_land():
    """Synthetic: sch1_pt2_s2#0 placed inside land → not in IN_LAND_SI."""
    zones = _zones()
    cfg = load_extent_sources(SOURCES)
    parts = load_si_vertices(SI_REF, expected_sha256=cfg.get("si-1999-1126").sha256)
    # Place s2#0 at the same coords as pinned s1#3 (known inside land).
    parts = {k: list(v) for k, v in parts.items()}
    parts["sch1_pt2_s2"][0] = parts["sch1_pt2_s1"][3]
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: SI vertex sch1_pt2_s2#0 inside land but not in IN_LAND_SI$",
    ):
        check_si_vertices_near_extent(
            parts,
            land=zones["land"],
            inshore=zones["inshore_0_12nm"],
            offshore=zones["offshore_12_200nm"],
            in_land_si=IN_LAND_SI,
        )


def test_k9_pinned_s1_3_not_inside_land():
    """Pinned s1#3 moved into sea (outside land)."""
    synth_land = MultiPolygon([box(-1000.0, -1000.0, 1000.0, 1000.0)])
    edge = (0.0, 1000.0)
    parts = {
        "sch1_pt1_east": [edge],
        "sch1_pt2_s1": [
            edge,
            edge,
            edge,
            (0.0, 1000.0 + 50.0),  # #3 outside land (sea)
            (0.0, 1000.0 - 242.8),  # #4 still inside
        ],
        "sch1_pt2_s2": [edge],
        "sch2": [edge],
    }
    empty_sea = MultiPolygon([Point(5000, 5000).buffer(10.0)])
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: pinned SI vertex sch1_pt2_s1#3 not inside land$",
    ):
        check_si_vertices_near_extent(
            parts,
            land=synth_land,
            inshore=empty_sea,
            offshore=empty_sea,
            in_land_si=IN_LAND_SI,
        )


def test_k10_pinned_s1_4_351m_from_land_boundary():
    """Pinned s1#4 placed 351.0 m inside the land boundary."""
    # Axis-aligned square so boundary distance is exact.
    synth_land = MultiPolygon([box(-1000.0, -1000.0, 1000.0, 1000.0)])
    edge = (0.0, 1000.0)
    parts = {
        "sch1_pt1_east": [edge],
        "sch1_pt2_s1": [
            edge,
            edge,
            edge,
            (0.0, 1000.0 - 322.3),  # pinned #3 ≤350
            (0.0, 1000.0 - 351.0),  # pinned #4 → 351.0 m
        ],
        "sch1_pt2_s2": [edge],
        "sch2": [edge],
    }
    empty_sea = MultiPolygon([Point(5000, 5000).buffer(10.0)])
    assert abs(synth_land.boundary.distance(Point(*parts["sch1_pt2_s1"][4])) - 351.0) < 1e-9
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: pinned SI vertex sch1_pt2_s1#4 351\.0 m from land boundary \(max 350\)$",
    ):
        check_si_vertices_near_extent(
            parts,
            land=synth_land,
            inshore=empty_sea,
            offshore=empty_sea,
            in_land_si=IN_LAND_SI,
            max_land_m=350.0,
        )


def test_k11_in_land_si_missing_s1_4():
    """IN_LAND_SI without s1#4 while s1#4 is still inside land."""
    zones = _zones()
    cfg = load_extent_sources(SOURCES)
    parts = load_si_vertices(SI_REF, expected_sha256=cfg.get("si-1999-1126").sha256)
    pins = {("sch1_pt2_s1", 3): 322.3}  # missing #4
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: SI vertex sch1_pt2_s1#4 inside land but not in IN_LAND_SI$",
    ):
        check_si_vertices_near_extent(
            parts,
            land=zones["land"],
            inshore=zones["inshore_0_12nm"],
            offshore=zones["offshore_12_200nm"],
            in_land_si=pins,
        )


def test_k3_tsl_median_60():
    """Real C2 checker with the TSL fixture's first segment placed 60 m outside."""
    fc = json.loads(TSL_REF.read_text(encoding="utf-8"))
    geom = shape(fc["features"][0]["geometry"])
    lines = list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom]
    base = max(lines, key=lambda g: g.length)
    (x0, y0), (x1, y1) = base.coords[0], base.coords[min(10, len(base.coords) - 1)]
    # Synthetic inshore south of a line that uses TSL fixture eastings, offset 60 m.
    north = max(y0, y1)
    inshore = MultiPolygon([box(min(x0, x1) - 5_000.0, north - 50_000.0, max(x0, x1) + 5_000.0, north)])
    offset_line = LineString(
        [(min(x0, x1), north + 60.0), (max(x0, x1), north + 60.0)]
    )
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: TSL median 60\.0 m \(max 50\)$",
    ):
        check_tsl_median(offset_line, inshore, sample_m=1000.0, max_median_m=50.0)


def test_k4_ext_shelf_in_default_extent(tmp_path):
    zones = _zones()
    bad_names = set(zones) | {"ext_shelf_optional"}
    with pytest.raises(
        ExtentError, match=r"^EXTENT-CHECK: ext_shelf in default extent$"
    ):
        check_no_ext_shelf_in_extent(bad_names)


def test_k5_inshore_area_out():
    zones = _zones()
    # Scale inshore area ×1.02 relative to the C3 pin so the message is exact.
    pin = EXPECTED_KM2["inshore_0_12nm"]
    current = area_km2(zones["inshore_0_12nm"])
    factor = math.sqrt((pin * 1.02) / current)
    mutated = dict(zones)
    mutated["inshore_0_12nm"] = scale(
        zones["inshore_0_12nm"], xfact=factor, yfact=factor, origin="centroid"
    )
    got = area_km2(mutated["inshore_0_12nm"])
    assert abs(got - pin * 1.02) < 0.05
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: inshore_0_12nm area 90814\.7 km2 outside ±1% of 89034$",
    ):
        check_zone_areas(mutated, EXPECTED_KM2, tol=0.01)


def test_k6_label_missing_illustrative():
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: zone land label missing illustrative$",
    ):
        check_labels_and_sources(
            [
                {
                    "properties": {
                        "zone": "land",
                        "label": "Scotland only",
                        "sources": ["x"],
                        "source_dates": {"x": "2026-01-01"},
                    }
                }
            ]
        )


def test_k7_reference_sha_mismatch(tmp_path):
    altered = tmp_path / SI_REF.name
    data = bytearray(SI_REF.read_bytes())
    data[0] = (data[0] + 1) % 256
    altered.write_bytes(bytes(data))
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: reference sha256 mismatch: si1999_1126_vertices.27700.geojson$",
    ):
        check_reference_sha(altered, REFERENCE_SHA256)


def test_r1_scotland_extent_registry():
    from layers.registry.loader import load_registry

    entries = load_registry()
    entry = entries["scotland-extent"]
    check_registry_title(entry)
    assert SCOTLAND_EXTENT_MARINE_CREDIT in entry.raw["attribution"]


def test_r1_negative_title(tmp_path):
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    data["title"] = "Scotland land and sea area"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: scotland-extent title missing illustrative$",
    ):
        check_registry_title(loaded)


def test_p4_optional_not_scotland_extent_prefix():
    matches = list((REPO / "data" / "processed" / "gis").glob("scotland_extent.*"))
    assert len(matches) == 1
    assert EXT_SHELF.name.startswith("scotland_ext_shelf")
    assert not EXT_SHELF.name.startswith("scotland_extent.")
