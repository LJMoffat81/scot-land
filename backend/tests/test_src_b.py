"""SRC-B: ladder fields, nesting report, councils pin, built-up credit, clip."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml
from shapely.geometry import box

from etl.build_boundaries import CouncilsError, assert_council_count
from etl.run_layer import CheckError, run_layer
from layers.builtup_mask import BUILTUP_CREDIT, BUILTUP_METHOD_NOTE
from layers.ladder import (
    LadderError,
    REPORT_PATH,
    assert_nests,
    assert_registry_matches_report,
    check_nesting,
    load_report,
)
from layers.registry.loader import REGISTRY_DIR, RegistryError, load_registry

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"

_HELPERS_PATH = Path(__file__).resolve().parent / "fixtures" / "arch2" / "helpers.py"
_spec = importlib.util.spec_from_file_location("arch2_helpers_src_b", _HELPERS_PATH)
assert _spec and _spec.loader
_helpers = importlib.util.module_from_spec(_spec)
sys.modules["arch2_helpers_src_b"] = _helpers
_spec.loader.exec_module(_helpers)

connect = _helpers.connect
drop_layer_tables = _helpers.drop_layer_tables
load_tiny_extent = _helpers.load_tiny_extent
require_dsn = _helpers.require_dsn

# §2a B3 sites (exact paths). 025 SQL is the sole old-string exemption.
_B3_CREDIT_SITES = [
    BACKEND / "layers" / "builtup_mask.py",
    BACKEND / "etl" / "ingest_builtup_mask.py",
    REPO / "data" / "config" / "sources.yaml",
    BACKEND / "layers" / "platform.py",
    REPO / "frontend" / "lib" / "layerCatalog.ts",
    REPO / "frontend" / "components" / "ScotlandMap.tsx",
    BACKEND / "tests" / "test_builtup_mask.py",
    REPO / "docs" / "mintlify" / "map-layer-guide.mdx",
    REPO / "scripts" / "data" / "README-builtup-mask.md",
]
# Split so this test file does not itself contain the banned contiguous string.
_OLD_BUILTUP = "NRS Settlements 2022 (OGL v3), " + "contains OS data"
_SQL_EXEMPT = BACKEND / "db" / "schema" / "025_map_builtup_mask.sql"
_N8_SELF = Path(__file__).resolve()


def _base(**over) -> dict:
    entry = {
        "id": "x",
        "title": "X",
        "geography": "scotland",
        "clip": "land+sea",
        "unit": "dz2022",
        "ladder_level": "dz2022",
        "nests": True,
        "licence": "OGL-3.0",
        "attribution": "Test attribution",
        "source": {
            "type": "postgis_table",
            "table": "dz_boundaries",
            "id_field": "code",
            "where": "vintage = 2022",
        },
        "geometry": "polygon",
        "clip_keep_all": True,
        "refresh": {"cron": "0 5 1 * *", "max_mb": 300, "max_s": 600},
        "serve": {
            "mode": "pmtiles",
            "simplify_m": 0,
            "precision_dp": 6,
            "max_mb": 15,
        },
        "zoom": {"min": 0, "max": 14, "low_zoom": "keep_all"},
        "style": {},
        "legend": [],
        "lineage": {
            "derived_from": [],
            "method": "source",
            "roll_up_to": ["council", "scotland"],
        },
        "keep_fields": ["name"],
        "tiles": {"budget": {"total_mb": 60, "tile_kb": 500, "z0_7_mb": 4}},
    }
    entry.update(over)
    return entry


def _write(tmp_path: Path, data: dict, name: str = "x") -> Path:
    (tmp_path / f"{name}.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    return tmp_path


# --- B4 / N1–N2c ---


def test_n1_ladder_level_required(tmp_path):
    data = _base()
    del data["ladder_level"]
    _write(tmp_path, data)
    with pytest.raises(
        RegistryError,
        match=r"^REGISTRY: x: \$\.ladder_level: required for polygon unit 'dz2022'$",
    ):
        load_registry(tmp_path)


def test_n2_nests_required(tmp_path):
    data = _base()
    del data["nests"]
    _write(tmp_path, data)
    with pytest.raises(
        RegistryError,
        match=r"^REGISTRY: x: \$\.nests: required for polygon unit 'dz2022'$",
    ):
        load_registry(tmp_path)


def test_n2b_ladder_level_enum(tmp_path):
    data = _base(ladder_level="town")
    _write(tmp_path, data)
    with pytest.raises(
        RegistryError,
        match=r"^REGISTRY: x: \$\.ladder_level: 'town' is not one of .*$",
    ):
        load_registry(tmp_path)


def test_n2c_unit_none_exempt_without_ladder_fields(tmp_path):
    data = _base(
        unit="none",
        clip="sea",
        clip_keep_all=False,
        source={
            "type": "arcgis",
            "url": "https://example.com/FeatureServer/0/query",
            "where": "1=1",
        },
    )
    del data["ladder_level"]
    del data["nests"]
    del data["tiles"]
    data["serve"] = {
        "mode": "geojson",
        "simplify_m": 0,
        "precision_dp": 6,
        "max_mb": 15,
    }
    _write(tmp_path, data)
    entries = load_registry(tmp_path)
    assert "x" in entries
    assert "ladder_level" not in entries["x"].raw


def test_n2c_mutation_exemption_removed_fails(tmp_path, monkeypatch):
    """Mutation: with the unit-none exemption removed, N2c must fail."""
    import layers.registry.loader as loader

    def _no_exempt(entry_id: str, data: dict) -> None:
        if data.get("geometry") != "polygon":
            return
        unit = data.get("unit")
        for key in ("ladder_level", "nests"):
            if key not in data:
                raise RegistryError(
                    f"REGISTRY: {entry_id}: $.{key}: required for polygon unit '{unit}'"
                )

    monkeypatch.setattr(loader, "_check_ladder_fields", _no_exempt)
    data = _base(
        unit="none",
        clip="sea",
        clip_keep_all=False,
        source={
            "type": "arcgis",
            "url": "https://example.com/FeatureServer/0/query",
            "where": "1=1",
        },
    )
    del data["ladder_level"]
    del data["nests"]
    del data["tiles"]
    data["serve"] = {
        "mode": "geojson",
        "simplify_m": 0,
        "precision_dp": 6,
        "max_mb": 15,
    }
    _write(tmp_path, data)
    with pytest.raises(
        RegistryError,
        match=r"^REGISTRY: x: \$\.ladder_level: required for polygon unit 'none'$",
    ):
        load_registry(tmp_path)


# --- G4 / N4 ---


def test_n4_councils_count_31():
    with pytest.raises(
        CouncilsError,
        match=r"^councils: expected 32 Scottish councils, got 31$",
    ):
        assert_council_count(31)


# --- B5 / N6 / N7 + synthetic fixtures ---


def test_b5_nested_squares_zero_crossings():
    dz = [
        box(0, 0, 10, 10),
        box(10, 0, 20, 10),
        box(0, 10, 10, 20),
        box(10, 10, 20, 20),
    ]
    features = [box(0, 0, 20, 20)]
    assert check_nesting(features, dz, tol_m=1.0) == []


def test_b5_l_shape_two_crossings():
    dz = [
        box(0, 0, 10, 10),
        box(10, 0, 20, 10),
        box(0, 10, 10, 20),
        box(10, 10, 20, 20),
    ]
    # L along the bottom and left: fully covers bottom-left, partially
    # covers bottom-right and top-left (2 crossings), misses top-right.
    l_shape = box(0, 0, 20, 5).union(box(0, 0, 5, 20))
    crossed = check_nesting([l_shape], dz, tol_m=1.0)
    assert len(crossed) == 2


def test_n6_nests_true_but_crosses():
    dz = [
        box(0, 0, 10, 10),
        box(10, 0, 20, 10),
        box(0, 10, 10, 20),
        box(10, 10, 20, 20),
    ]
    l_shape = box(0, 0, 20, 5).union(box(0, 0, 5, 20))
    with pytest.raises(
        LadderError,
        match=r"^ladder: layer 'x' marked nests: true but crosses 2 dz2022 zones$",
    ):
        assert_nests("x", [l_shape], dz, nests=True, tol_m=1.0)


def test_n6_mutation_tol_1e6_fails():
    """Mutation: tol 1.0 → 1e6 must fail the N6 crossing detection."""
    dz = [
        box(0, 0, 10, 10),
        box(10, 0, 20, 10),
        box(0, 10, 10, 20),
        box(10, 10, 20, 20),
    ]
    l_shape = box(0, 0, 20, 5).union(box(0, 0, 5, 20))
    # With huge tol, the crossing band swallows all partial overlaps.
    assert check_nesting([l_shape], dz, tol_m=1e6) == []
    with pytest.raises(LadderError):
        assert_nests("x", [l_shape], dz, nests=True, tol_m=1.0)
    # Mutated tol: nests:true claim would incorrectly pass.
    assert_nests("x", [l_shape], dz, nests=True, tol_m=1e6)


def test_b5_registry_nests_match_report():
    assert_registry_matches_report(registry_dir=REGISTRY_DIR, report_path=REPORT_PATH)
    report = load_report(REPORT_PATH)
    entries = load_registry(REGISTRY_DIR)
    for eid, layer in (report.get("layers") or {}).items():
        assert eid in entries
        assert bool(entries[eid].raw["nests"]) is bool(layer["nests"])


def test_n7_report_mismatch(tmp_path):
    report = load_report(REPORT_PATH)
    altered = json.loads(json.dumps(report))
    # Force a mismatch for a layer that exists.
    target = next(iter(altered["layers"]))
    altered["layers"][target]["nests"] = not altered["layers"][target]["nests"]
    path = tmp_path / "ladder_report.json"
    path.write_text(json.dumps(altered), encoding="utf-8")
    # Registry still has the committed nests; report flipped.
    claimed = bool(load_registry(REGISTRY_DIR)[target].raw["nests"])
    reported = bool(altered["layers"][target]["nests"])
    assert claimed != reported
    with pytest.raises(
        LadderError,
        match=(
            rf"^ladder report mismatch for '{re.escape(target)}': "
            rf"registry nests={str(claimed).lower()}, "
            rf"report={str(reported).lower()}$"
        ),
    ):
        assert_registry_matches_report(
            registry_dir=REGISTRY_DIR, report_path=path
        )


# --- B3 / N8 ---


def assert_builtup_credit(paths: list[Path]) -> None:
    """Raise if any path's text lacks the locked BUILTUP_CREDIT string."""
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        if BUILTUP_CREDIT not in text:
            raise AssertionError(
                f"builtup credit drift: {path} does not contain BUILTUP_CREDIT"
            )


def test_b3_credit_sites_contain_builtup_credit():
    assert_builtup_credit(_B3_CREDIT_SITES)
    # Old string must not appear except the literal-exempt SQL history comment.
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() in {_SQL_EXEMPT.resolve(), _N8_SELF}:
            continue
        if path.suffix.lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".gpkg",
            ".zip",
            ".pbf",
            ".mvt",
            ".pyc",
            ".so",
            ".whl",
        }:
            continue
        if "node_modules" in path.parts or ".git" in path.parts:
            continue
        if ".venv" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if _OLD_BUILTUP in text:
            pytest.fail(f"old builtup credit still present in {path}")


def test_n8_builtup_credit_pin(tmp_path):
    """N8: shared assert_builtup_credit fails on a real site copy with credit removed."""
    src = _B3_CREDIT_SITES[0]
    assert BUILTUP_CREDIT in src.read_text(encoding="utf-8")
    copy = tmp_path / src.name
    copy.write_text(
        src.read_text(encoding="utf-8").replace(BUILTUP_CREDIT, "REMOVED"),
        encoding="utf-8",
    )
    with pytest.raises(
        AssertionError,
        match=r"^builtup credit drift: .+ does not contain BUILTUP_CREDIT$",
    ):
        assert_builtup_credit([copy])


def test_b3_method_note_locked():
    from layers.platform import platform_catalog

    assert "50 m" in BUILTUP_METHOD_NOTE
    assert BUILTUP_METHOD_NOTE in (
        BACKEND / "layers" / "platform.py"
    ).read_text(encoding="utf-8")
    row = next(r for r in platform_catalog()["layers"] if r["id"] == "builtup_mask")
    assert row["description"] == BUILTUP_METHOD_NOTE
    assert row["attribution"] == BUILTUP_CREDIT


# --- B6 clip ---


@pytest.fixture
def tiny_extent(monkeypatch, tmp_path):
    require_dsn()
    conn = connect()
    drop_layer_tables(conn, "src-b-land")
    load_tiny_extent(conn, monkeypatch, tmp_path)
    monkeypatch.setenv("ARCH1_TEST_DSN", require_dsn())
    monkeypatch.setattr("etl.run_layer.RECEIPT_DIR", tmp_path / "receipts")
    yield conn
    drop_layer_tables(conn, "src-b-land")
    conn.close()


def _land_entry() -> dict:
    return {
        "id": "src-b-land",
        "title": "SRC-B land clip probe",
        "geography": "scotland",
        "clip": "land",
        "unit": "none",
        "licence": "OGL-3.0",
        "attribution": "Test",
        "source": {
            "type": "geojson_file",
            "url": "https://example.com/src-b-land.geojson",
        },
        "geometry": "polygon",
        "clip_keep_all": False,
        "refresh": {"cron": "0 5 1 * *", "max_mb": 10, "max_s": 60},
        "serve": {
            "mode": "geojson",
            "simplify_m": 0,
            "precision_dp": 6,
            "max_mb": 15,
        },
        "zoom": {"min": 0, "max": 12, "low_zoom": "simplify"},
        "style": {},
        "legend": [],
        "lineage": {
            "derived_from": [],
            "method": "source",
            "roll_up_to": [],
        },
    }


def test_b6_land_clip_10m_poke(tiny_extent, monkeypatch, tmp_path):
    reg = tmp_path / "reg"
    reg.mkdir()
    _write(reg, _land_entry(), name="src-b-land")
    mapping = load_registry(reg)
    monkeypatch.setattr("etl.run_layer.registry", lambda: mapping)

    # Land is 0–10000. Square mostly inside, poking 10 m north of the edge.
    poke = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::27700"},
        },
        "features": [
            {
                "type": "Feature",
                "id": "poke10",
                "properties": {"name": "poke10"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [4000, 9900],
                            [5000, 9900],
                            [5000, 10010],
                            [4000, 10010],
                            [4000, 9900],
                        ]
                    ],
                },
            }
        ],
    }
    path = tmp_path / "poke10.geojson"
    path.write_text(json.dumps(poke), encoding="utf-8")
    receipt = run_layer("src-b-land", from_file=path, conn=tiny_extent)
    assert receipt["outside"] == 0
    assert receipt["after"] == 1


def test_b6_mutation_clip_disabled_fails(tiny_extent, monkeypatch, tmp_path):
    """Mutation: with the clip disabled, check_outside must fail."""
    reg = tmp_path / "reg"
    reg.mkdir()
    _write(reg, _land_entry(), name="src-b-land")
    mapping = load_registry(reg)
    monkeypatch.setattr("etl.run_layer.registry", lambda: mapping)

    # Extend 60 m past land so the unclipped geom is outside land+50 m.
    poke = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::27700"},
        },
        "features": [
            {
                "type": "Feature",
                "id": "poke60",
                "properties": {"name": "poke60"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [4000, 9900],
                            [5000, 9900],
                            [5000, 10060],
                            [4000, 10060],
                            [4000, 9900],
                        ]
                    ],
                },
            }
        ],
    }
    path = tmp_path / "poke60.geojson"
    path.write_text(json.dumps(poke), encoding="utf-8")

    def _no_clip(conn, layer_id, entry, *, new_name):
        # Copy stage → layers without intersecting land.
        src = f'stage."{layer_id}"'
        dst = f'layers."{new_name}"'
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {dst}")
            cur.execute(f"CREATE TABLE {dst} AS TABLE {src}")
            cur.execute(f"SELECT count(*) FROM {dst}")
            return int(cur.fetchone()[0])

    monkeypatch.setattr("etl.run_layer._clip", _no_clip)
    with pytest.raises(CheckError, match=r"features outside scotland\+50m"):
        run_layer("src-b-land", from_file=path, conn=tiny_extent)
