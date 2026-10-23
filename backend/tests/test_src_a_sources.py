"""SRC-A sources YAML and SI vertex loader — positive and negative tests."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from etl.extent_sources import (
    UKHO_ATTRIBUTION,
    ExtentError,
    load_extent_sources,
    load_si_vertices,
)

REPO = Path(__file__).resolve().parents[2]
SOURCES = REPO / "backend" / "layers" / "extent" / "scotland_extent_sources.yaml"
SCHEMA = REPO / "backend" / "layers" / "extent" / "schema.json"
SI_REF = REPO / "data" / "reference" / "sea" / "si1999_1126_vertices.27700.geojson"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "src_a"


def _valid_sources_dict() -> dict:
    return yaml.safe_load(SOURCES.read_text(encoding="utf-8"))


def _write_yaml(path: Path, data) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_s25_committed_sources_validate_and_load():
    import jsonschema

    data = _valid_sources_dict()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(data)
    cfg = load_extent_sources(SOURCES)
    assert cfg.snap_m == 150
    assert cfg.densify_max_m == 1000
    assert cfg.solway.aoi == (305000.0, 555000.0, 340000.0, 572000.0)
    assert cfg.solway.corridor_m == 700.0
    assert cfg.get("ukho-mlb").attribution == UKHO_ATTRIBUTION


def test_s1_missing_file(tmp_path):
    missing = tmp_path / "nope.yaml"
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: sources file missing: "):
        load_extent_sources(missing)


def test_s2_empty_file(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_bytes(b"")
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: sources file empty: "):
        load_extent_sources(path)


def test_s3_whitespace_only(tmp_path):
    path = tmp_path / "ws.yaml"
    path.write_text("   \n\t\n", encoding="utf-8")
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: sources file empty: "):
        load_extent_sources(path)


def test_s4_invalid_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("a: [\n", encoding="utf-8")
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: sources file not YAML: "):
        load_extent_sources(path)


def test_s5_top_level_list(tmp_path):
    path = _write_yaml(tmp_path / "list.yaml", [{"id": "ukho-mlb"}])
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: sources root must be a mapping$"):
        load_extent_sources(path)


def test_s6_missing_sources(tmp_path):
    data = _valid_sources_dict()
    del data["sources"]
    path = _write_yaml(tmp_path / "nosrc.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: missing key sources$"):
        load_extent_sources(path)


def test_s7_unknown_top_key(tmp_path):
    data = _valid_sources_dict()
    data["extra"] = 1
    path = _write_yaml(tmp_path / "extra.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: unknown key extra$"):
        load_extent_sources(path)


def test_s8_missing_sha256(tmp_path):
    data = _valid_sources_dict()
    for entry in data["sources"]:
        if entry["id"] == "ukho-mlb":
            del entry["sha256"]
    path = _write_yaml(tmp_path / "nosha.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: ukho-mlb missing key sha256$"):
        load_extent_sources(path)


def test_s9_sha256_63_hex(tmp_path):
    data = _valid_sources_dict()
    for entry in data["sources"]:
        if entry["id"] == "ukho-mlb":
            entry["sha256"] = "a" * 63
    path = _write_yaml(tmp_path / "short.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: ukho-mlb sha256 invalid$"):
        load_extent_sources(path)


def test_s10_sha256_int(tmp_path):
    data = _valid_sources_dict()
    for entry in data["sources"]:
        if entry["id"] == "ukho-mlb":
            entry["sha256"] = 123
    path = _write_yaml(tmp_path / "intsha.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: ukho-mlb sha256 must be a string$"):
        load_extent_sources(path)


def test_s11_url_http(tmp_path):
    data = _valid_sources_dict()
    for entry in data["sources"]:
        if entry["id"] == "ukho-mlb":
            entry["url"] = "http://example.com/x"
    path = _write_yaml(tmp_path / "http.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: ukho-mlb url must be https$"):
        load_extent_sources(path)


def test_s12_licence_ccby(tmp_path):
    data = _valid_sources_dict()
    for entry in data["sources"]:
        if entry["id"] == "ukho-mlb":
            entry["licence"] = "CC-BY-4.0"
    path = _write_yaml(tmp_path / "lic.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: ukho-mlb licence must be OGL-3.0$"):
        load_extent_sources(path)


def test_s13_attribution_mismatch(tmp_path):
    data = _valid_sources_dict()
    for entry in data["sources"]:
        if entry["id"] == "ukho-mlb":
            entry["attribution"] = UKHO_ATTRIBUTION[:-1] + "X"
    path = _write_yaml(tmp_path / "attr.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: ukho-mlb attribution mismatch$"):
        load_extent_sources(path)


def test_s14_published_invalid_date(tmp_path):
    data = _valid_sources_dict()
    for entry in data["sources"]:
        if entry["id"] == "ukho-mlb":
            entry["published"] = "2026-13-01"
    path = _write_yaml(tmp_path / "baddate.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: ukho-mlb published invalid date$"):
        load_extent_sources(path)


def test_s15_published_bool(tmp_path):
    data = _valid_sources_dict()
    for entry in data["sources"]:
        if entry["id"] == "ukho-mlb":
            entry["published"] = True
    path = _write_yaml(tmp_path / "booldate.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: ukho-mlb published must be a date$"):
        load_extent_sources(path)


def test_s15_published_date_object_ok(tmp_path):
    data = _valid_sources_dict()
    for entry in data["sources"]:
        if entry["id"] == "ukho-mlb":
            entry["published"] = date(2026, 1, 7)
    path = _write_yaml(tmp_path / "dateobj.yaml", data)
    cfg = load_extent_sources(path)
    assert cfg.get("ukho-mlb").published == "2026-01-07"


def test_s16_crs_bool(tmp_path):
    data = _valid_sources_dict()
    for entry in data["sources"]:
        if entry["id"] == "ukho-mlb":
            entry["crs"] = True
    path = _write_yaml(tmp_path / "crsbool.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: ukho-mlb crs must be an integer$"):
        load_extent_sources(path)


def test_s17_crs_float(tmp_path):
    data = _valid_sources_dict()
    for entry in data["sources"]:
        if entry["id"] == "ukho-mlb":
            entry["crs"] = 4326.0
    path = _write_yaml(tmp_path / "crsfloat.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: ukho-mlb crs must be an integer$"):
        load_extent_sources(path)


def test_s18_snap_m_bool(tmp_path):
    data = _valid_sources_dict()
    data["snap_m"] = True
    path = _write_yaml(tmp_path / "snapbool.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: snap_m must be a number$"):
        load_extent_sources(path)


def test_s19_snap_m_150_01(tmp_path):
    data = _valid_sources_dict()
    data["snap_m"] = 150.01
    path = _write_yaml(tmp_path / "snaphi.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: snap_m out of range$"):
        load_extent_sources(path)


def test_s20_snap_m_zero(tmp_path):
    data = _valid_sources_dict()
    data["snap_m"] = 0
    path = _write_yaml(tmp_path / "snap0.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: snap_m out of range$"):
        load_extent_sources(path)


def test_s21_densify_1000_5(tmp_path):
    data = _valid_sources_dict()
    data["densify_max_m"] = 1000.5
    path = _write_yaml(tmp_path / "denhi.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: densify_max_m out of range$"):
        load_extent_sources(path)


def test_s22_densify_string(tmp_path):
    data = _valid_sources_dict()
    data["densify_max_m"] = "500"
    path = _write_yaml(tmp_path / "denstr.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: densify_max_m must be a number$"):
        load_extent_sources(path)


def test_s23_missing_ostn15(tmp_path):
    data = _valid_sources_dict()
    data["sources"] = [e for e in data["sources"] if e["id"] != "ostn15"]
    path = _write_yaml(tmp_path / "noostn.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: missing source ostn15$"):
        load_extent_sources(path)


def test_s24_duplicate_source(tmp_path):
    data = _valid_sources_dict()
    data["sources"].append(dict(data["sources"][0]))
    path = _write_yaml(tmp_path / "dup.yaml", data)
    with pytest.raises(ExtentError, match=r"^EXTENT-SRC: duplicate source ukho-mlb$"):
        load_extent_sources(path)


# --- SI vertices ---


def test_v_positive_si_ref():
    cfg = load_extent_sources(SOURCES)
    parts = load_si_vertices(SI_REF, expected_sha256=cfg.get("si-1999-1126").sha256)
    assert list(parts) == [
        "sch1_pt1_east",
        "sch1_pt2_s1",
        "sch1_pt2_s2",
        "sch2",
    ]
    assert [len(parts[p]) for p in parts] == [7, 33, 118, 21]


def test_v1_missing(tmp_path):
    with pytest.raises(ExtentError, match=r"^EXTENT-SI: file missing: "):
        load_si_vertices(tmp_path / "none.geojson")


def test_v2_empty(tmp_path):
    path = tmp_path / "empty.geojson"
    path.write_bytes(b"")
    with pytest.raises(ExtentError, match=r"^EXTENT-SI: file empty: "):
        load_si_vertices(path)


def test_v3_invalid_json(tmp_path):
    path = tmp_path / "bad.geojson"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ExtentError, match=r"^EXTENT-SI: file not GeoJSON: "):
        load_si_vertices(path)


def test_v4_root_list(tmp_path):
    path = tmp_path / "list.geojson"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ExtentError, match=r"^EXTENT-SI: root must be a FeatureCollection$"):
        load_si_vertices(path)


def _si_fc() -> dict:
    return json.loads(SI_REF.read_text(encoding="utf-8"))


def test_v5_missing_part(tmp_path):
    fc = _si_fc()
    fc["features"] = [f for f in fc["features"] if f["properties"]["part"] != "sch2"]
    path = tmp_path / "nopart.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-SI: parts must be sch1_pt1_east,sch1_pt2_s1,sch1_pt2_s2,sch2$",
    ):
        load_si_vertices(path)


def test_v6_wrong_vertex_count(tmp_path):
    fc = _si_fc()
    for f in fc["features"]:
        if f["properties"]["part"] == "sch1_pt2_s1":
            f["geometry"]["coordinates"] = f["geometry"]["coordinates"][:-1]
    path = tmp_path / "short.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-SI: sch1_pt2_s1 has 32 vertices, expected 33$",
    ):
        load_si_vertices(path)


def test_v7_coord_bool(tmp_path):
    fc = _si_fc()
    for f in fc["features"]:
        if f["properties"]["part"] == "sch2":
            f["geometry"]["coordinates"][0] = [True, 700000]
    path = tmp_path / "bool.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")
    with pytest.raises(ExtentError, match=r"^EXTENT-SI: sch2 vertex 0 not numeric$"):
        load_si_vertices(path)


def test_v8_coord_string(tmp_path):
    fc = _si_fc()
    for f in fc["features"]:
        if f["properties"]["part"] == "sch2":
            f["geometry"]["coordinates"][0] = ["x", 700000]
    path = tmp_path / "str.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")
    with pytest.raises(ExtentError, match=r"^EXTENT-SI: sch2 vertex 0 not numeric$"):
        load_si_vertices(path)


def test_v9_outside_bng(tmp_path):
    fc = _si_fc()
    for f in fc["features"]:
        if f["properties"]["part"] == "sch2":
            f["geometry"]["coordinates"][0] = [-2_000_000, 700000]
    path = tmp_path / "oob.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")
    with pytest.raises(
        ExtentError,
        match=r"^EXTENT-SI: sch2 vertex 0 outside EPSG:27700 bounds$",
    ):
        load_si_vertices(path)


def test_v10_sha_mismatch(tmp_path):
    path = tmp_path / "si.geojson"
    shutil.copy(SI_REF, path)
    with pytest.raises(ExtentError, match=r"^EXTENT-SI: sha256 mismatch$"):
        load_si_vertices(path, expected_sha256="0" * 64)


def test_v11_point_geom(tmp_path):
    fc = _si_fc()
    for f in fc["features"]:
        if f["properties"]["part"] == "sch2":
            f["geometry"] = {
                "type": "Point",
                "coordinates": f["geometry"]["coordinates"][0],
            }
    path = tmp_path / "pt.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")
    with pytest.raises(ExtentError, match=r"^EXTENT-SI: sch2 must be a LineString$"):
        load_si_vertices(path)
