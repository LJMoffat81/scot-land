"""PLANNING-PUBLISH-1 PR-A: publish allow-list refusals, filter, and vintage fill.

Synthetic fixtures only. Each refusal is one change to a tmp copy of the committed YAML.
DB cases (PP-D*) need ARCH1_TEST_DSN and skip when it is unset.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg2
import pytest
import yaml
from fastapi.testclient import TestClient

from api.main import app
from api import tiles_routes as tiles_routes
from etl.adapters.arcgis import fetch_layer_last_edit
from etl.build_scotland_extent import load_only
from etl.refresh_registry import run_weekly_refresh
from etl.run_layer import (
    EXPECTED_FEATURE_COUNTS,
    IngestError,
    _fetch_entry,
    _fetched_vintage,
    run_layer,
)
from layers.registry.admission import AdmissionError, check_admission
from layers.registry.loader import RegistryError, load_registry
from layers.registry.publish import apply_publish_filter, fill_vintage, publish_manifest_fields
from tiles.build import _receipt_vintage

REGISTRY = Path(__file__).resolve().parents[1] / "layers" / "registry"
FEEDS = Path(__file__).resolve().parent / "fixtures" / "planning_publish_1"
EXTENT_TINY = Path(__file__).resolve().parent / "fixtures" / "arch1" / "extent_tiny.27700.geojson"
HUB = "https://data.spatialhub.scot/dataset/housing_land_supply-is"
PREMIUM = "https://data.spatialhub.scot/dataset/housing_land_supply_premium-is"
WFS_PREMIUM = "https://geo.spatialhub.scot/geoserver/sh_hls_premium/wfs"
SG_COPY = "https://www.arcgis.com/home/item.html?id=ba05ffddfe854d95b6386a7ded516e90"

HLS_VINTAGE = (
    "Spatial Hub open extract as of 6 Oct 2026, covering housing land audit years 2020/21 to 2024/25."
)
HLS_CREDIT = (
    "Housing Land Supply - Scotland (open data), Improvement Service Spatial Hub, "
    "as of 6 Oct 2026. Contains OS data © Crown copyright and database right 2026 "
    "and Scottish local authority data from the Spatial Hub. Contains public sector "
    "information licensed under the Open Government Licence v3.0."
)
LDP_TEMPLATE = "Highland Council live data, last updated {date}"
LDP_FALLBACK = "Highland Council live data, last update date not given"
LDP_CREDIT = (
    "Local Development Plan allocations, The Highland Council. Copyright Highland "
    "Council. Contains Ordnance Survey data © Crown copyright and database right "
    "2026. Contains public sector information licensed under the Open Government "
    "Licence v3.0."
)
LDP_LEGEND = [
    {"label": "Local Development Plan allocation (Highland only)", "color": "#7B3F99"}
]
LDP_QUERY = (
    "https://services1.arcgis.com/MfbPb778y5QTu2Wv/arcgis/rest/services/"
    "LocalDevelopmentPlanAllocations/FeatureServer/0/query"
)
E16 = (
    "REGISTRY: {id}: $.vintage: only one {{date}} slot, on an arcgis layer with a fixed fallback"
)


def _copy(tmp_path: Path) -> Path:
    for src in REGISTRY.glob("*.yaml"):
        shutil.copy(src, tmp_path / src.name)
    return tmp_path


def _load(d: Path, layer_id: str) -> dict:
    return yaml.safe_load((d / f"{layer_id}.yaml").read_text(encoding="utf-8"))


def _save(d: Path, layer_id: str, data: dict) -> None:
    (d / f"{layer_id}.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )


def _fails(d: Path, message: str) -> None:
    with pytest.raises(RegistryError) as exc:
        load_registry(d)
    assert str(exc.value) == message


def _feat(auth):
    props = {} if auth is None else {"local_auth": auth}
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [0, 0]},
    }


def _ms(y: int, m: int, d: int, hh: int = 12) -> int:
    return int(datetime(y, m, d, hh, tzinfo=timezone.utc).timestamp() * 1000)


def _meta_client(payload, seen=None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, content=json.dumps(payload).encode())

    return httpx.Client(transport=httpx.MockTransport(handler))


def _dsn() -> str:
    dsn = os.environ.get("ARCH1_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("ARCH1_TEST_DSN not set")
    return dsn


def _table_exists(conn, schema: str, name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema=%s AND table_name=%s
            )
            """,
            (schema, name),
        )
        return bool(cur.fetchone()[0])


@pytest.fixture
def conn():
    connection = psycopg2.connect(_dsn())
    connection.autocommit = True
    with connection.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    yield connection
    connection.close()


@pytest.fixture
def tiny_extent(conn, monkeypatch, tmp_path):
    """Same land box as test_arch1_clip.tiny_extent (0–10000 m)."""
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    monkeypatch.setenv("LAYER_RECEIPT_DIR", str(tmp_path))
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS ref")
        cur.execute("CREATE SCHEMA IF NOT EXISTS stage")
        cur.execute("CREATE SCHEMA IF NOT EXISTS layers")
        for table in ("extent_buf50_sub", "extent_sub", "extent"):
            cur.execute(f"DROP TABLE IF EXISTS ref.{table} CASCADE")
        for table in ("hls-open", "hls-open_prev", "hls-open__new"):
            cur.execute(f'DROP TABLE IF EXISTS layers."{table}" CASCADE')
            cur.execute(f'DROP TABLE IF EXISTS stage."{table}" CASCADE')
    gis = tmp_path / "gis"
    gis.mkdir()
    dest = gis / "scotland_extent.27700.geojson"
    dest.write_bytes(EXTENT_TINY.read_bytes())
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    (gis / "manifest.csv").write_text(
        "file,sha256\n" f"scotland_extent.27700.geojson,{sha}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("etl.build_scotland_extent.MANIFEST_PATH", gis / "manifest.csv")
    load_only(dest)
    yield conn


def test_pp_w0_committed_registry_loads():
    reg = load_registry(REGISTRY)
    check_admission(reg)
    hls = reg["hls-open"].raw["publish"]
    assert len(hls["allow"]) == 32
    assert all(r["licence_url"] == HUB for r in hls["allow"])
    assert {r["authority"] for r in hls["exclude"]} == {"North Lanarkshire"}
    assert reg["ldp-highland"].raw["publish"]["source_authority"] == "Highland"
    context = [eid for eid, e in reg.items() if e.raw.get("shows") == "context"]
    assert len(context) == 6


def test_pp_r1_nl_in_allow_and_exclude(tmp_path):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["publish"]["allow"].append({"authority": "North Lanarkshire", "licence_url": HUB})
    _save(d, "hls-open", data)
    _fails(
        d,
        "REGISTRY: hls-open: $.publish.exclude[0].authority: North Lanarkshire is both allowed and excluded",
    )


def test_pp_r2_hard_exclude_missing(tmp_path):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["publish"]["exclude"] = []
    _save(d, "hls-open", data)
    _fails(
        d,
        "REGISTRY: hls-open: $.publish.exclude: must list North Lanarkshire (PL 13 Nov 2026)",
    )


def test_pp_r3_hard_exclude_in_allow(tmp_path):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["publish"]["exclude"] = []
    data["publish"]["allow"].append({"authority": "North Lanarkshire", "licence_url": HUB})
    _save(d, "hls-open", data)
    _fails(
        d,
        "REGISTRY: hls-open: $.publish.allow: North Lanarkshire is excluded (PL 13 Nov 2026)",
    )


@pytest.mark.parametrize(
    "row",
    [
        {"authority": "Fife"},
        {"authority": "Fife", "licence_url": ""},
        {"authority": "Fife", "licence_url": None},
    ],
)
def test_pp_r4_licence_url_required(tmp_path, row):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["publish"]["allow"][0] = row
    _save(d, "hls-open", data)
    _fails(d, "REGISTRY: hls-open: $.publish.allow[0].licence_url: required for Fife")


@pytest.mark.parametrize("url", ["http://data.spatialhub.scot/x", "https://"])
def test_pp_r4_licence_url_must_be_https(tmp_path, url):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["publish"]["allow"][0] = {"authority": "Fife", "licence_url": url}
    _save(d, "hls-open", data)
    _fails(d, "REGISTRY: hls-open: $.publish.allow[0].licence_url: must be https:// for Fife")


@pytest.mark.parametrize("authority", ["  ", 123])
def test_pp_r5_authority_required(tmp_path, authority):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["publish"]["allow"][0] = {"authority": authority, "licence_url": HUB}
    _save(d, "hls-open", data)
    _fails(d, "REGISTRY: hls-open: $.publish.allow[0].authority: required")


def test_pp_r6_duplicate_authority(tmp_path):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["publish"]["allow"].insert(1, dict(data["publish"]["allow"][0]))
    _save(d, "hls-open", data)
    _fails(d, "REGISTRY: hls-open: $.publish.allow[1].authority: duplicate Aberdeen City")


def test_pp_r7_exclude_reason_required(tmp_path):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["publish"]["exclude"][0]["reason"] = " "
    _save(d, "hls-open", data)
    _fails(
        d,
        "REGISTRY: hls-open: $.publish.exclude[0].reason: required for North Lanarkshire",
    )


@pytest.mark.parametrize("url", [PREMIUM, WFS_PREMIUM, SG_COPY])
def test_pp_r8_deny_source_url(tmp_path, url):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["source"]["url"] = url
    _save(d, "hls-open", data)
    _fails(
        d,
        "REGISTRY: hls-open: $.source.url: Premium or SG ArcGIS HLS copy is never allowed",
    )


def test_pp_r8b_deny_licence_url(tmp_path):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["publish"]["allow"][0]["licence_url"] = PREMIUM
    _save(d, "hls-open", data)
    _fails(
        d,
        "REGISTRY: hls-open: $.publish.allow[0].licence_url: Premium or SG ArcGIS HLS copy is never allowed",
    )


def test_pp_r9_publish_required(tmp_path):
    d = _copy(tmp_path)
    data = _load(d, "ldp-highland")
    del data["publish"]
    _save(d, "ldp-highland", data)
    _fails(d, "REGISTRY: ldp-highland: $.publish: required")


@pytest.mark.parametrize("both", [True, False])
def test_pp_r10_exactly_one_authority_source(tmp_path, both):
    d = _copy(tmp_path)
    data = _load(d, "ldp-highland")
    if both:
        data["publish"]["authority_field"] = "local_auth"
    else:
        del data["publish"]["source_authority"]
    _save(d, "ldp-highland", data)
    _fails(
        d,
        "REGISTRY: ldp-highland: $.publish: exactly one of authority_field or source_authority",
    )


@pytest.mark.parametrize("allow", [[], "x"])
def test_pp_r11_allow_must_be_non_empty_list(tmp_path, allow):
    d = _copy(tmp_path)
    data = _load(d, "ldp-highland")
    data["publish"]["allow"] = allow
    _save(d, "ldp-highland", data)
    _fails(d, "REGISTRY: ldp-highland: $.publish.allow: must be a non-empty list")


def test_pp_r12_vintage_required_by_admission(tmp_path):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    del data["vintage"]
    _save(d, "hls-open", data)
    with pytest.raises(AdmissionError) as exc:
        check_admission(load_registry(d))
    assert str(exc.value) == "ADMISSION: hls-open: $.vintage: required (charter v2 §4.5)"


def test_pp_r13_attribution_min_length(tmp_path):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["attribution"] = ""
    _save(d, "hls-open", data)
    _fails(d, "REGISTRY: hls-open: $.attribution: '' should be non-empty")


def test_pp_r14_publish_not_object(tmp_path):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["publish"] = "x"
    _save(d, "hls-open", data)
    _fails(d, "REGISTRY: hls-open: $.publish: expected object")


def test_pp_r14_allow_row_not_object(tmp_path):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["publish"]["allow"][0] = "x"
    _save(d, "hls-open", data)
    _fails(d, "REGISTRY: hls-open: $.publish.allow[0]: expected object")


def test_pp_r14_exclude_authority_blank(tmp_path):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    data["publish"]["exclude"][0]["authority"] = ""
    _save(d, "hls-open", data)
    _fails(d, "REGISTRY: hls-open: $.publish.exclude[0].authority: required")


def test_pp_f1_filter_keeps_allow_only():
    publish = {
        "authority_field": "local_auth",
        "allow": [{"authority": "Fife", "licence_url": HUB}],
        "exclude": [{"authority": "North Lanarkshire", "reason": "x"}],
    }
    feats = [
        _feat("Fife"),
        _feat("North Lanarkshire"),
        _feat("Atlantis"),
        _feat(None),
        _feat(""),
        _feat(" Fife "),
        _feat(123),
    ]
    kept, counts = apply_publish_filter("hls-open", publish, feats)
    assert [f["properties"].get("local_auth") for f in kept] == ["Fife", " Fife "]
    assert counts == {"kept_by_authority": {"Fife": 2}, "excluded": 1, "refused": 4}


def test_pp_f2_source_authority_keeps_all():
    publish = {
        "source_authority": "Highland",
        "allow": [{"authority": "Highland", "licence_url": "https://map-highland.opendata.arcgis.com/x"}],
    }
    feats = [_feat(None), _feat("Fife")]
    kept, counts = apply_publish_filter("ldp-highland", publish, feats)
    assert len(kept) == 2
    assert counts == {"kept_by_authority": {"Highland": 2}, "excluded": 0, "refused": 0}


def test_pp_f3_no_publish_block_unchanged():
    feats = [_feat("Atlantis")]
    kept, counts = apply_publish_filter("x", None, feats)
    assert kept is feats and counts == {}


def test_pp_w1_refresh_skips_manual_geojson_file():
    def entry(lid, src_type):
        return {
            "id": lid,
            "refresh": {"cron": "0 4 * * 1", "max_mb": 50, "max_s": 120},
            "source": {"type": src_type},
        }

    entries = {
        "hls-open": entry("hls-open", "geojson_file"),
        "ldp-highland": entry("ldp-highland", "arcgis"),
    }
    calls: list[str] = []

    def runner(lid):
        calls.append(lid)
        return {
            "id": lid,
            "before": 1,
            "after": 1,
            "outside": 0,
            "repaired": 0,
            "url": "https://example.invalid/q",
            "as_of": "2026-11-13",
            "dataset_version": f"{lid}@2026-11-13-abcdef12",
            "extent_sha256": "a" * 64,
        }

    summary = run_weekly_refresh(entries=entries, runner=runner, tile_builder=lambda lid: {})
    assert calls == ["ldp-highland"]
    assert summary == {
        "refreshed": ["ldp-highland"],
        "tiles_built": [],
        "skipped_manual": ["hls-open"],
    }


@pytest.mark.parametrize("gated", [False, True])
def test_pp_w2_gated_by_takedown(tmp_path, monkeypatch, gated):
    d = _copy(tmp_path)
    data = _load(d, "hls-open")
    if gated:
        data["gated_by"] = "takedown"
    _save(d, "hls-open", data)
    reg = load_registry(d)
    monkeypatch.setattr(tiles_routes, "registry", lambda: reg)
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    version = "2026-11-13.abcdef12"
    (tiles / "manifest.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "tilesets": {
                    "hls-open": {
                        "version": version,
                        "file": "x.pmtiles",
                        "attribution": "a",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TILES_DIR", str(tiles))
    client = TestClient(app)
    body = client.get("/v1/tiles/manifest.json").json()
    assert ("hls-open" in body["tilesets"]) is (not gated)
    if gated:
        response = client.get(f"/v1/tiles/hls-open/{version}/0/0/0.mvt")
        assert response.status_code == 404
        assert response.json() == {"detail": "unknown tileset"}


def test_pp_w3_hls_open_never_fetches_remote():
    entry = load_registry(REGISTRY)["hls-open"]
    with pytest.raises(IngestError) as exc:
        _fetch_entry(entry, from_file=None)
    assert str(exc.value) == (
        "INGEST: hls-open geojson_file reads local files only; source.url is remote "
        "(use --from-file or a fetching source type)"
    )


def test_pp_w4_manifest_fields_credits_and_coverage():
    reg = load_registry(REGISTRY)
    hls = publish_manifest_fields(reg["hls-open"].raw)
    assert hls["vintage"] == HLS_VINTAGE
    assert len(hls["coverage"]["included"]) == 32
    assert hls["coverage"]["excluded"][0]["authority"] == "North Lanarkshire"
    assert "North Lanarkshire" not in {r["authority"] for r in hls["coverage"]["included"]}
    assert reg["hls-open"].raw["attribution"] == HLS_CREDIT
    assert reg["ldp-highland"].raw["attribution"] == LDP_CREDIT
    assert publish_manifest_fields(reg["councils"].raw) == {}


def test_pp_w5_filter_precedes_count_and_stage():
    src = (Path(__file__).resolve().parents[1] / "etl" / "run_layer.py").read_text(encoding="utf-8")
    body = src[src.index("def run_layer(") :]
    i_filter = body.index("apply_publish_filter(")
    assert i_filter < body.index("EXPECTED_FEATURE_COUNTS.get(layer_id)")
    assert i_filter < body.index("_load_stage(")
    assert EXPECTED_FEATURE_COUNTS["hls-open"] == 5946


def test_pp_v0_committed_ldp_strings_exact():
    raw = load_registry(REGISTRY)["ldp-highland"].raw
    assert raw["vintage"] == LDP_TEMPLATE
    assert raw["legend"] == LDP_LEGEND


def test_pp_v1_filled_form_6_oct_2026():
    seen: list[httpx.Request] = []
    client = _meta_client({"editingInfo": {"dataLastEditDate": _ms(2026, 10, 6)}}, seen)
    got = fill_vintage(
        "ldp-highland",
        LDP_TEMPLATE,
        fetch_layer_last_edit(LDP_QUERY, client=client),
    )
    assert got == "Highland Council live data, last updated 6 Oct 2026"
    assert str(seen[0].url) == LDP_QUERY[: -len("/query")] + "?f=json"


def test_pp_v2_single_digit_day():
    assert fill_vintage("ldp-highland", LDP_TEMPLATE, _ms(2026, 3, 1)) == (
        "Highland Council live data, last updated 1 Mar 2026"
    )


def test_pp_v2b_two_digit_day_kept():
    assert fill_vintage("ldp-highland", LDP_TEMPLATE, _ms(2026, 11, 13)) == (
        "Highland Council live data, last updated 13 Nov 2026"
    )


def test_pp_v3a_fallback_key_missing():
    client = _meta_client({"editingInfo": {"lastEditDate": _ms(2026, 10, 6)}})
    assert (
        fill_vintage(
            "ldp-highland", LDP_TEMPLATE, fetch_layer_last_edit(LDP_QUERY, client=client)
        )
        == LDP_FALLBACK
    )


def test_pp_v3b_fallback_null():
    client = _meta_client({"editingInfo": {"dataLastEditDate": None}})
    assert (
        fill_vintage(
            "ldp-highland", LDP_TEMPLATE, fetch_layer_last_edit(LDP_QUERY, client=client)
        )
        == LDP_FALLBACK
    )


def test_pp_v3c_fallback_non_numeric_string():
    client = _meta_client({"editingInfo": {"dataLastEditDate": "yesterday"}})
    assert (
        fill_vintage(
            "ldp-highland", LDP_TEMPLATE, fetch_layer_last_edit(LDP_QUERY, client=client)
        )
        == LDP_FALLBACK
    )


def test_pp_v3d_fallback_zero():
    client = _meta_client({"editingInfo": {"dataLastEditDate": 0}})
    assert (
        fill_vintage(
            "ldp-highland", LDP_TEMPLATE, fetch_layer_last_edit(LDP_QUERY, client=client)
        )
        == LDP_FALLBACK
    )


def test_pp_v3e_fallback_unreadable_metadata():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"<html>"))
    )
    assert (
        fill_vintage(
            "ldp-highland", LDP_TEMPLATE, fetch_layer_last_edit(LDP_QUERY, client=client)
        )
        == LDP_FALLBACK
    )


@pytest.mark.parametrize(
    "filled",
    [
        None,
        "",
        LDP_TEMPLATE,
        "dataLastEditDate 1791000000000",
        "last updated {date}",
        "Highland Council live data, last updated 6 Oct 2026",
    ],
)
def test_pp_v4_manifest_vintage_never_template_or_field_name(filled):
    raw = load_registry(REGISTRY)["ldp-highland"].raw
    out = publish_manifest_fields(raw, filled_vintage=filled)["vintage"]
    assert "{" not in out and "}" not in out and "dataLastEditDate" not in out
    expect = (
        filled
        if filled == "Highland Council live data, last updated 6 Oct 2026"
        else LDP_FALLBACK
    )
    assert out == expect


def test_pp_v5_receipt_vintage_needs_same_dataset_version(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYER_RECEIPT_DIR", str(tmp_path))
    assert _receipt_vintage("ldp-highland", "2026-11-13.abcd1234") is None
    (tmp_path / "ldp-highland.receipt.json").write_text(
        json.dumps(
            {
                "dataset_version": "2026-11-13.abcd1234",
                "vintage": "Highland Council live data, last updated 6 Oct 2026",
            }
        ),
        encoding="utf-8",
    )
    assert _receipt_vintage("ldp-highland", "2026-11-13.abcd1234") == (
        "Highland Council live data, last updated 6 Oct 2026"
    )
    assert _receipt_vintage("ldp-highland", "2026-11-14.ffff0000") is None


def test_pp_v6_fetched_vintage_at_fetch_and_from_file_fallback():
    entries = load_registry(REGISTRY)
    client = _meta_client({"editingInfo": {"dataLastEditDate": _ms(2026, 10, 6)}})
    assert _fetched_vintage(entries["ldp-highland"], from_file=None, client=client) == (
        "Highland Council live data, last updated 6 Oct 2026"
    )
    assert _fetched_vintage(entries["ldp-highland"], from_file=Path("x.geojson")) == LDP_FALLBACK
    assert _fetched_vintage(entries["hls-open"], from_file=None) is None


@pytest.mark.parametrize(
    ("layer_id", "vintage"),
    [
        ("ldp-highland", "Highland Council live data, last updated {when}"),
        ("ldp-highland", "{date} {date}"),
        ("hls-open", "as of {date}"),
    ],
)
def test_pp_v7_vintage_slot_rules(tmp_path, layer_id, vintage):
    d = _copy(tmp_path)
    data = _load(d, layer_id)
    data["vintage"] = vintage
    _save(d, layer_id, data)
    _fails(d, E16.format(id=layer_id))


def test_pp_d1_clip_keeps_two_fife_rows(tiny_extent, monkeypatch):
    monkeypatch.delitem(EXPECTED_FEATURE_COUNTS, "hls-open")
    receipt = run_layer("hls-open", from_file=FEEDS / "pp_d1_feed.geojson", conn=tiny_extent)
    assert receipt["before"] == 3
    assert receipt["after"] == 2
    assert receipt["outside"] == 0
    assert receipt["publish"] == {
        "kept_by_authority": {"Fife": 3},
        "excluded": 1,
        "refused": 2,
    }
    with tiny_extent.cursor() as cur:
        cur.execute('SELECT count(*) FROM layers."hls-open"')
        assert cur.fetchone()[0] == 2
        cur.execute(
            """
            SELECT ST_XMax(geom) FROM layers."hls-open"
            WHERE props->>'kind' = 'straddle'
            """
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] <= 10000


def test_pp_d2_zero_after_allow_list_refused(tiny_extent, monkeypatch):
    monkeypatch.delitem(EXPECTED_FEATURE_COUNTS, "hls-open")
    with pytest.raises(IngestError) as exc:
        run_layer("hls-open", from_file=FEEDS / "pp_d2_feed.geojson", conn=tiny_extent)
    assert str(exc.value) == "INGEST: hls-open: 0 features after publish allow-list"
    assert not _table_exists(tiny_extent, "stage", "hls-open")
    assert not _table_exists(tiny_extent, "layers", "hls-open")


def test_pp_d3_expected_count_after_filter(tiny_extent):
    with pytest.raises(IngestError) as exc:
        run_layer("hls-open", from_file=FEEDS / "pp_d3_feed.geojson", conn=tiny_extent)
    assert str(exc.value) == "hls-open: expected 5946 features, got 2"
