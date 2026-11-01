"""BATCHA-TILES-FIX-2B: honour serve.simplify_m + per-layer tile tuning.

Synthetic fixtures only. Real-data sizes that justify the YAML values are in the
frozen BATCHA-TILES-FIX-2B.md §4/§6.
"""

from __future__ import annotations

import shutil
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from layers.registry.loader import REGISTRY_DIR, load_registry
from tiles.build import TilesError, _export_geojsonseq, export_simplify_m

_HELPERS_PATH = Path(__file__).resolve().parent / "fixtures" / "arch2" / "helpers.py"
_spec = importlib.util.spec_from_file_location("arch2_helpers_btf2b", _HELPERS_PATH)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
sys.modules["arch2_helpers_btf2b"] = _helpers
_spec.loader.exec_module(_helpers)

connect = _helpers.connect
require_dsn = _helpers.require_dsn


def _jagged_1km_wkt() -> str:
    """Closed 1 km square with a 401-point ring (jagged southern edge)."""
    pts: list[str] = []
    # Southern edge: 397 points from x=0..~1000 with 1 m zigzag (under 10 m tolerance),
    # then NE/NW corners and close → 401 ring vertices including the closing point.
    for i in range(397):
        x = i * (1000.0 / 396.0)
        y = float(i % 2)
        pts.append(f"{x:.10g} {y:.10g}")
    pts.extend(
        [
            "1000 0",
            "1000 1000",
            "0 1000",
            "0 0",
        ]
    )
    assert len(pts) == 401
    ring = ", ".join(pts)
    return f"MULTIPOLYGON((({ring})))"


@pytest.fixture
def pg():
    require_dsn()
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS layers")
        cur.execute('DROP TABLE IF EXISTS layers."btf2b-jag"')
        cur.execute(
            'CREATE TABLE layers."btf2b-jag" ('
            "feature_id text, props jsonb, "
            "geom geometry(MultiPolygon, 27700))"
        )
        cur.execute(
            'INSERT INTO layers."btf2b-jag" VALUES (%s, %s, ST_GeomFromText(%s, 27700))',
            ("f1", json.dumps({"k": "v"}), _jagged_1km_wkt()),
        )
        cur.execute(
            'SELECT ST_NPoints(geom) FROM layers."btf2b-jag" WHERE feature_id = %s',
            ("f1",),
        )
        assert cur.fetchone()[0] == 401
    yield conn
    with conn.cursor() as cur:
        cur.execute('DROP TABLE IF EXISTS layers."btf2b-jag"')
    conn.close()


def test_b1_export_honours_simplify_m(pg, tmp_path: Path) -> None:
    out_raw = tmp_path / "raw.geojsonl"
    out_s = tmp_path / "simp.geojsonl"
    n0 = _export_geojsonseq(
        pg, "btf2b-jag", keep_fields=["k"], precision_dp=6, dest=out_raw, simplify_m=0.0
    )
    n1 = _export_geojsonseq(
        pg, "btf2b-jag", keep_fields=["k"], precision_dp=6, dest=out_s, simplify_m=10.0
    )
    assert n0 == n1 == 1
    raw = json.loads(out_raw.read_text(encoding="utf-8").splitlines()[0])
    simp = json.loads(out_s.read_text(encoding="utf-8").splitlines()[0])
    assert raw["properties"] == simp["properties"] == {"feature_id": "f1", "k": "v"}

    def npts(feat: dict[str, Any]) -> int:
        geom = feat["geometry"]
        ring = (
            geom["coordinates"][0][0]
            if geom["type"] == "MultiPolygon"
            else geom["coordinates"][0]
        )
        return len(ring)

    assert npts(raw) == 401
    assert npts(simp) == 5


def test_b2_negative_tolerance_refused(pg, tmp_path: Path) -> None:
    out = tmp_path / "neg.geojsonl"
    with pytest.raises(TilesError) as exc:
        _export_geojsonseq(
            pg,
            "btf2b-jag",
            keep_fields=[],
            precision_dp=6,
            dest=out,
            simplify_m=-1.0,
        )
    assert str(exc.value) == "TILES: btf2b-jag: serve.simplify_m must be >= 0"


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ({"geometry": "point", "serve": {"simplify_m": 10}}, 0.0),
        ({"geometry": "polygon", "serve": {"simplify_m": 10}}, 10.0),
        ({"geometry": "line", "serve": {"simplify_m": 5}}, 5.0),
        ({"geometry": "polygon", "serve": {"simplify_m": 0}}, 0.0),
        ({"geometry": "polygon"}, 0.0),
    ],
)
def test_b3_export_simplify_m_truth_table(raw: dict[str, Any], want: float) -> None:
    assert export_simplify_m(raw) == want


def test_b4_build_tileset_passes_registry_tolerance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tiles import build as b

    (tmp_path / "tiles").mkdir()
    monkeypatch.setenv("TILES_DIR", str(tmp_path / "tiles"))
    storage = _helpers.write_storage_yaml(tmp_path / "storage.yaml")
    entries = load_registry(REGISTRY_DIR)
    monkeypatch.setattr(b, "registry", lambda: entries)
    seen: list[float] = []

    class _Stop(Exception):
        pass

    def _boom(*_a: Any, simplify_m: float = 0.0, **_k: Any) -> int:
        seen.append(simplify_m)
        raise _Stop()

    monkeypatch.setattr(b, "_export_geojsonseq", _boom)

    class _Cur:
        q = ""

        def __enter__(self):
            return self

        def __exit__(self, *a: Any) -> None:
            return None

        def execute(self, q: str, *_a: Any) -> None:
            self.q = q

        def fetchone(self):
            if "information_schema" in self.q:
                return (True,)
            if "count(*)" in self.q.lower():
                return (1,)
            return (True,)

        def fetchall(self):
            return [("x@2026-11-01-0123abcd", "2026-11-01")]

    class _Conn:
        autocommit = True

        def cursor(self):
            return _Cur()

    for lid, want in (("sepa-flood", 10.0), ("sepa-car", 0.0), ("councils", 0.0), ("pipelines", 5.0)):
        with pytest.raises(_Stop):
            b.build_tileset(lid, conn=_Conn(), storage_path=storage)
        assert seen[-1] == want


def test_b5_tuned_layer_config_is_pinned() -> None:
    e = {k: v.raw for k, v in load_registry(REGISTRY_DIR).items()}
    assert e["sepa-car"]["zoom"]["max"] == 12
    assert e["sepa-car"]["keep_fields"] == [
        "car_layer",
        "authorisation_level",
        "authorisation_status",
        "regulatory_area",
        "authorisation_activity",
        "category",
    ]
    assert e["sepa-flood"]["keep_fields"] == ["source"]
    assert e["sepa-flood"]["zoom"]["low_zoom"] == "coalesce"
    assert e["native-woodland"]["keep_fields"] == ["woodland_type"]
    assert e["nfi"]["keep_fields"] == ["category"]
    for lid in ("sepa-car", "naturescot-designations"):
        assert e[lid]["tiles"]["budget"] == {"total_mb": 15, "tile_kb": 500, "z0_7_mb": 2}
    assert e["sepa-flood"]["tiles"]["budget"] == {"total_mb": 23.5, "tile_kb": 459, "z0_7_mb": 3.0}
    assert e["native-woodland"]["tiles"]["budget"] == {"total_mb": 22, "tile_kb": 500, "z0_7_mb": 2.7}
    assert e["nfi"]["tiles"]["budget"] == {"total_mb": 43, "tile_kb": 500, "z0_7_mb": 3.7}
    for lid in ("naturescot-designations", "sepa-flood", "native-woodland", "nfi"):
        assert e[lid]["zoom"]["max"] == 11
        assert e[lid]["serve"]["simplify_m"] == 10


def test_b6_car_free_text_never_tiled() -> None:
    # SEPA CAR authorisation_description is free text with holder site addresses.
    for lid, entry in load_registry(REGISTRY_DIR).items():
        assert "authorisation_description" not in (entry.raw.get("keep_fields") or []), lid


# --- GIS conditions (1 Nov) ------------------------------------------------

from tiles.build import SIMPLIFY_NOTE, display_simplification  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def test_b7_councils_and_extent_never_simplified() -> None:
    e = {k: v.raw for k, v in load_registry(REGISTRY_DIR).items()}
    for lid in ("councils", "scotland-extent"):
        assert e[lid]["serve"]["simplify_m"] == 0
        assert export_simplify_m(e[lid]) == 0.0
        assert display_simplification(e[lid]) is None


def test_b8_shared_edges_survive_export_at_zero(pg, tmp_path: Path) -> None:
    with pg.cursor() as cur:
        cur.execute('DROP TABLE IF EXISTS layers."btf2b-pair"')
        cur.execute(
            'CREATE TABLE layers."btf2b-pair" (feature_id text, props jsonb, '
            "geom geometry(MultiPolygon, 27700))"
        )
        edge = ", ".join(f"3000 {2000 + i * 10}.{i % 2}" for i in range(101))
        west = f"MULTIPOLYGON(((2000 2000, {edge}, 2000 3010, 2000 2000)))"
        back = ", ".join(f"3000 {2000 + i * 10}.{i % 2}" for i in reversed(range(101)))
        east = f"MULTIPOLYGON(((3000 2000, 4000 2000, 4000 3010, {back})))"
        for fid, wkt in (("w", west), ("e", east)):
            cur.execute(
                'INSERT INTO layers."btf2b-pair" VALUES (%s, %s, ST_GeomFromText(%s, 27700))',
                (fid, "{}", wkt),
            )
    out = tmp_path / "pair.geojsonl"
    try:
        n = _export_geojsonseq(pg, "btf2b-pair", keep_fields=[], precision_dp=6, dest=out, simplify_m=0.0)
    finally:
        with pg.cursor() as cur:
            cur.execute('DROP TABLE IF EXISTS layers."btf2b-pair"')
    assert n == 2
    rows = {json.loads(l)["properties"]["feature_id"]: json.loads(l)["geometry"] for l in out.read_text().splitlines()}

    def pts(g: dict[str, Any]) -> set[tuple[float, float]]:
        ring = g["coordinates"][0][0] if g["type"] == "MultiPolygon" else g["coordinates"][0]
        return {tuple(p) for p in ring}

    shared = pts(rows["w"]) & pts(rows["e"])
    assert len(shared) == 101


def test_b9_export_keeps_every_feature_when_simplified(pg, tmp_path: Path) -> None:
    with pg.cursor() as cur:
        cur.execute(
            'INSERT INTO layers."btf2b-jag" VALUES (%s, %s, ST_GeomFromText(%s, 27700))',
            ("tiny", "{}", "MULTIPOLYGON(((5000 5000, 5003 5000, 5003 5003, 5000 5003, 5000 5000)))"),
        )
        cur.execute('SELECT count(*) FROM layers."btf2b-jag"')
        before = cur.fetchone()[0]
    out = tmp_path / "all.geojsonl"
    n = _export_geojsonseq(pg, "btf2b-jag", keep_fields=[], precision_dp=6, dest=out, simplify_m=10.0)
    assert before == n == len(out.read_text().splitlines()) == 2


def test_b10_build_refuses_feature_loss_message() -> None:
    src = (REPO / "backend" / "tiles" / "build.py").read_text(encoding="utf-8")
    assert 'f"TILES: {layer_id}: export kept {exported} of {n_features} features "' in src
    assert "if exported != n_features:" in src
    assert "tippecanoe low-zoom culling" in src
    assert 'entry_payload["display_simplification"] = disclosure' in src


def test_b15_build_tileset_refuses_dropped_features(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tiles import build as b

    (tmp_path / "tiles").mkdir()
    monkeypatch.setenv("TILES_DIR", str(tmp_path / "tiles"))
    storage = _helpers.write_storage_yaml(tmp_path / "storage.yaml")
    entries = load_registry(REGISTRY_DIR)
    monkeypatch.setattr(b, "registry", lambda: entries)
    monkeypatch.setattr(b, "_export_geojsonseq", lambda *_a, **_k: 2)

    class _Cur:
        q = ""

        def __enter__(self):
            return self

        def __exit__(self, *a: Any) -> None:
            return None

        def execute(self, q: str, *_a: Any) -> None:
            self.q = q

        def fetchone(self):
            return (True,) if "EXISTS" in self.q else (3,)

        def fetchall(self):
            return [("x@2026-11-01-0123abcd", "2026-11-01")]

    class _Conn:
        autocommit = True

        def cursor(self):
            return _Cur()

    with pytest.raises(b.TilesError) as exc:
        b.build_tileset("sepa-flood", conn=_Conn(), storage_path=storage)
    assert str(exc.value) == "TILES: sepa-flood: export kept 2 of 3 features (simplify_m 10)"


@pytest.mark.parametrize(
    ("lid", "n"),
    [("pipelines", "5"), ("nfi", "10"), ("naturescot-sssi", "10")],
)
def test_b11_manifest_disclosure_text(lid: str, n: str) -> None:
    raw = load_registry(REGISTRY_DIR)[lid].raw
    d = display_simplification(raw)
    assert d is not None
    assert d["note"] == f"Display geometry simplified to {n} m; official boundaries unsimplified for analysis"
    assert d["simplify_m"] == float(n)


def test_b12_every_simplified_layer_gets_disclosure() -> None:
    for lid, entry in load_registry(REGISTRY_DIR).items():
        sm = float((entry.raw.get("serve") or {}).get("simplify_m") or 0)
        assert (display_simplification(entry.raw) is not None) == (sm > 0), lid
    assert SIMPLIFY_NOTE.startswith("Display geometry simplified to ")


def test_b13_clip_and_check_read_unsimplified_extent_only() -> None:
    sql_dir = REPO / "backend" / "etl" / "sql"
    for name in ("clip.sql", "check_outside.sql"):
        text = (sql_dir / name).read_text(encoding="utf-8")
        assert "ref.extent" in text, name
        assert "scotland-extent" not in text and "pmtiles" not in text and "Simplify" not in text, name
    run_layer_src = (REPO / "backend" / "etl" / "run_layer.py").read_text(encoding="utf-8")
    assert "tiles" not in run_layer_src.replace("budget exceeded", "")
    assert "simplify_m" not in run_layer_src


def test_b14_woodland_count_check_and_runbook() -> None:
    from etl import ingest_woodland_layers as w

    assert w.LAYERS["native_woodland"]["expected_rows"] == 95_814
    assert w.LAYERS["nfi"]["expected_rows"] == 207_640
    w.check_count("native_woodland", 95_814)
    with pytest.raises(SystemExit) as exc:
        w.check_count("native_woodland", 5)
    assert str(exc.value).startswith("native_woodland: got 5, expected 95,814")
    src = (REPO / "backend" / "etl" / "ingest_woodland_layers.py").read_text(encoding="utf-8")
    assert "    if args.check_counts:\n        check_count(" in src
    doc = (REPO / "docs" / "HOME_DEPLOY.md").read_text(encoding="utf-8")
    assert "python -m etl.ingest_woodland_layers --layer nfi --from-wfs --replace --check-counts" in doc
    assert "`--layer native_woodland`" in doc
    assert "never `--fixture` on the PC" in doc


# --- GIS GO (b): sepa-flood keeps tiny polygons at maxzoom -------------------


def test_b16_registry_option_only_on_declaring_layers() -> None:
    """Honest scope: the keep_all and simplify profiles already pass
    --no-tiny-polygon-reduction (tiles/profiles.py); the registry option
    tiles.no_tiny_polygon_reduction only adds it for other profiles, and only
    sepa-flood (coalesce) declares it."""
    from tiles.profiles import tippecanoe_flags

    for prof in ("keep_all", "simplify"):
        assert "--no-tiny-polygon-reduction" in tippecanoe_flags(prof, zoom_max=11, keep_fields=[])
    for prof in ("coalesce", "cluster"):
        assert "--no-tiny-polygon-reduction" not in tippecanoe_flags(prof, zoom_max=11, keep_fields=["a"])
    declared = {
        lid
        for lid, e in load_registry(REGISTRY_DIR).items()
        if (e.raw.get("tiles") or {}).get("no_tiny_polygon_reduction")
    }
    assert declared == {"sepa-flood"}
    src = (REPO / "backend" / "tiles" / "build.py").read_text(encoding="utf-8")
    assert src.count('"--no-tiny-polygon-reduction"') == 1
    assert '(raw.get("tiles") or {}).get("no_tiny_polygon_reduction", False)' in src


@pytest.mark.parametrize("flag", [True, False])
def test_b17_run_tippecanoe_adds_flag_only_on_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, flag: bool
) -> None:
    from tiles import build as b

    seen: list[list[str]] = []

    class _R:
        returncode = 0

    monkeypatch.setattr(b.shutil, "which", lambda _n: "/bin/tippecanoe")
    monkeypatch.setattr(b.subprocess, "run", lambda cmd, **_k: seen.append(cmd) or _R())
    b._run_tippecanoe(
        layer_id="x", geojsonseq=tmp_path / "a", out_pmtiles=tmp_path / "b",
        zoom_max=11, low_zoom="coalesce", keep_fields=["source"],
        no_tiny_polygon_reduction=flag,
    )
    assert ("--no-tiny-polygon-reduction" in seen[0]) is flag


@pytest.mark.skipif(shutil.which("tippecanoe") is None, reason="tippecanoe not on PATH")
def test_b18_synthetic_near_pixel_polygons_survive_with_flag(tmp_path: Path) -> None:
    from tiles import build as b
    from tiles.measure import distinct_ids_at_zoom

    raw = load_registry(REGISTRY_DIR)["sepa-flood"].raw
    seq = tmp_path / "tiny.geojsonl"
    lines = []
    for i in range(400):  # synthetic ~3 x 5.5 m rectangles, near a z11 pixel
        x, y = -4.0 + (i % 20) * 0.01, 56.0 + (i // 20) * 0.01
        d = 0.00005
        ring = [[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]
        lines.append(json.dumps({"type": "Feature", "properties": {"feature_id": f"f{i}", "source": "River"},
                                 "geometry": {"type": "Polygon", "coordinates": [ring]}}))
    seq.write_text("\n".join(lines) + "\n")

    def culled(flag: bool) -> int:
        out = tmp_path / f"t{flag}.pmtiles"
        b._run_tippecanoe(
            layer_id="sepa-flood", geojsonseq=seq, out_pmtiles=out,
            zoom_max=raw["zoom"]["max"], low_zoom=raw["zoom"]["low_zoom"],
            keep_fields=raw["keep_fields"], no_tiny_polygon_reduction=flag,
        )
        return 400 - len(distinct_ids_at_zoom(out, layer_id="sepa-flood", zoom=raw["zoom"]["max"]))

    assert culled(bool(raw["tiles"]["no_tiny_polygon_reduction"])) == 0
    assert culled(False) > 0  # proves the fixture would catch a regression


def test_b19_flood_culled_pin_and_refusal(pg) -> None:
    from tiles import build as b

    assert load_registry(REGISTRY_DIR)["sepa-flood"].raw["tiles"]["max_culled"] == 16
    with pytest.raises(b.TilesError) as exc:
        b.report_culled(pg, "btf2b-jag", present_ids=set(), n_features=1, zoom=11, max_culled=0)
    assert str(exc.value) == "TILES: btf2b-jag: 1 features culled at z11 > tiles.max_culled 0"
    # duplicate ids are not culls: every distinct id present -> 0 even if rows > ids
    assert b.report_culled(pg, "btf2b-jag", present_ids={"f1"}, n_features=99, zoom=11, max_culled=0) == 0


def test_b20_culled_log_lists_id_and_area(pg, caplog: pytest.LogCaptureFixture) -> None:
    from tiles import build as b

    with pg.cursor() as cur:
        cur.execute(
            'INSERT INTO layers."btf2b-jag" VALUES (%s, %s, ST_GeomFromText(%s, 27700))',
            ("tiny", "{}", "MULTIPOLYGON(((5000 5000, 5003 5000, 5003 5003, 5000 5003, 5000 5000)))"),
        )
        cur.execute('SELECT feature_id FROM layers."btf2b-jag" WHERE feature_id <> %s', ("tiny",))
        keep = {r[0] for r in cur.fetchall()}
    caplog.set_level("WARNING", logger="tiles.build")
    n = b.report_culled(pg, "btf2b-jag", present_ids=keep, n_features=len(keep) + 1, zoom=11, max_culled=16)
    assert n == 1
    msgs = [r.getMessage() for r in caplog.records]
    assert msgs == [
        f"TILES: btf2b-jag: 1 of {len(keep) + 1} features absent at z11 (tippecanoe low-zoom culling)",
        "TILES: btf2b-jag: culled z11 id=tiny area_m2=9.0",
    ]
    caplog.clear()
    assert b.report_culled(pg, "btf2b-jag", present_ids=keep | {"tiny"}, n_features=len(keep) + 1, zoom=11, max_culled=0) == 0
    assert caplog.records == []


def test_b21_flood_disclosure_exact_text() -> None:
    d = display_simplification(load_registry(REGISTRY_DIR)["sepa-flood"].raw)
    assert d == {
        "simplify_m": 10.0,
        "note": "Display geometry simplified to 10 m; official boundaries unsimplified for analysis. "
        "Features smaller than one tile pixel may not render; analysis uses the full SEPA data in PostGIS.",
    }
    assert display_simplification(load_registry(REGISTRY_DIR)["nfi"].raw)["note"] == (
        "Display geometry simplified to 10 m; official boundaries unsimplified for analysis"
    )
