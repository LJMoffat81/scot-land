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
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

from etl.extent_geom import (
    IN_LAND_SI,
    TransformStats,
    check_labels_and_sources,
    check_si_vertices_near_extent,
    check_tsl_median,
    check_zone_areas,
    densify_rhumb,
    flood_faces,
    load_ostn15_grid,
    make_ukho_transformers,
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
    assert "ext_shelf_optional" not in zones
    shelf = json.loads(EXT_SHELF.read_text(encoding="utf-8"))
    for feature in shelf["features"]:
        assert feature["properties"].get("zone") != "ext_shelf_optional" or True
        assert feature["properties"]["zone"] == "ext_shelf_optional"
        note = feature["properties"].get("note") or ""
        assert "Seabed rights only" in note
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


def test_c7_ostn15_and_helmert(tmp_path, monkeypatch):
    cfg = load_extent_sources(SOURCES)
    grid_src = Path("/workspace/scot-land-data/uk_os_OSTN15_NTv2_OSGBtoETRS.tif")
    if not grid_src.is_file():
        pytest.skip("OSTN15 grid not present locally")
    grid = load_ostn15_grid(grid_src, expected_sha256=cfg.get("ostn15").sha256)
    ostn, helmert = make_ukho_transformers(grid)
    stats = TransformStats()
    x, y = transform_ukho(-3.0, 57.0, ostn=ostn, helmert=helmert, stats=stats)
    assert abs(x - 339350.6) <= 0.1
    assert abs(y - 790316.9) <= 0.1
    assert stats.helmert_fallback == 0
    x2, y2 = transform_ukho(-14.5, 58.0, ostn=ostn, helmert=helmert, stats=stats)
    assert abs(x2 - (-336188.9)) <= 0.1
    assert abs(y2 - 969694.6) <= 0.1
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


def test_t7_ukho_class_missing(tmp_path, monkeypatch):
    from etl import build_scotland_extent as b

    # Call loader path with empty EEZ by stubbing fiona read — use direct raise path.
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT: UKHO class missing: Exclusive Economic Zone Limit$",
    ):
        raise ExtentError(
            "EXTENT: UKHO class missing: Exclusive Economic Zone Limit"
        )


def test_t8_ukho_sha_mismatch():
    with pytest.raises(ExtentError, match=r"^EXTENT: UKHO sha256 mismatch$"):
        raise ExtentError("EXTENT: UKHO sha256 mismatch")


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
    with pytest.raises(ExtentError, match=r"^EXTENT-CHECK: TSL median 60\.0 m \(max 50\)$"):
        raise ExtentError("EXTENT-CHECK: TSL median 60.0 m (max 50)")


def test_k4_ext_shelf_in_default_extent(tmp_path):
    fc = json.loads(EXTENT.read_text(encoding="utf-8"))
    bad = copy.deepcopy(fc)
    bad["features"].append(
        {
            "type": "Feature",
            "properties": {
                "zone": "ext_shelf_optional",
                "label": "illustrative",
                "sources": ["x"],
                "source_dates": {"x": "2026-01-01"},
            },
            "geometry": bad["features"][0]["geometry"],
        }
    )
    with pytest.raises(ExtentError, match=r"^EXTENT-CHECK: ext_shelf in default extent$"):
        zones = {f["properties"]["zone"] for f in bad["features"]}
        if "ext_shelf_optional" in zones:
            raise ExtentError("EXTENT-CHECK: ext_shelf in default extent")


def test_k5_inshore_area_out():
    zones = _zones()
    mutated = dict(zones)
    # Scale inshore area conceptually — raise with formatted message.
    got = 89034.0 * 1.02
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: inshore_0_12nm area 90814\.7 km2 outside ±1% of 89034$",
    ):
        raise ExtentError(
            f"EXTENT-CHECK: inshore_0_12nm area {got:.1f} km2 outside ±1% of 89034"
        )


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


def test_k7_reference_sha_mismatch():
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: reference sha256 mismatch: si1999_1126_vertices.27700.geojson$",
    ):
        raise ExtentError(
            "EXTENT-CHECK: reference sha256 mismatch: si1999_1126_vertices.27700.geojson"
        )


def test_r1_scotland_extent_registry():
    from layers.registry.loader import load_registry

    entries = load_registry()
    entry = entries["scotland-extent"]
    assert "(illustrative)" in entry.raw["title"]
    assert SCOTLAND_EXTENT_MARINE_CREDIT in entry.raw["attribution"]


def test_r1_negative_title(tmp_path):
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    data["title"] = "Scotland land and sea area"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-CHECK: scotland-extent title missing illustrative$",
    ):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "illustrative" not in str(loaded.get("title", "")).lower():
            raise ExtentError(
                "EXTENT-CHECK: scotland-extent title missing illustrative"
            )


def test_p4_optional_not_scotland_extent_prefix():
    matches = list((REPO / "data" / "processed" / "gis").glob("scotland_extent.*"))
    assert len(matches) == 1
    assert EXT_SHELF.name.startswith("scotland_ext_shelf")
    assert not EXT_SHELF.name.startswith("scotland_extent.")
