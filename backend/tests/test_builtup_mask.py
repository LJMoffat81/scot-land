"""UX10-2 built-up mask: 503 when unloaded; catalog + publication wiring; QA helpers."""

from __future__ import annotations

import json
from pathlib import Path

from etl.ingest_builtup_mask import VISITOR_ATTRIBUTION
from layers.builtup_mask import (
    BUILTUP_CREDIT,
    EXPECTED_DZ2022_MASKED,
    LayerUnavailable,
)
from layers.platform import platform_catalog

# Pin: exact BUILTUP_CREDIT text must appear in this file (SRC-B N8 / §2a).
_BUILTUP_CREDIT_PIN = "Built-up areas: NRS Settlements 2022. Copyright National Records of Scotland, contains Ordnance Survey data © Crown copyright and database right 2026 (OGL v3)"

GLASGOW_BBOX = {
    "south": 55.84,
    "west": -4.30,
    "north": 55.88,
    "east": -4.22,
}

FIXTURE_QA = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "builtup_mask"
    / "qa_builtup_mask.json"
)
NATIONAL_QA = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "data"
    / "builtup-mask"
    / "qa_builtup_mask.json"
)


def test_builtup_mask_bbox_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable(
            "Built-up mask builtup_mask is not available: map_builtup_mask is missing or empty."
        )

    monkeypatch.setattr("api.platform_routes.builtup_mask_bbox", _boom)
    r = client.get("/layers/open/builtup-mask", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "missing" in detail
    assert "features" not in r.json()


def test_dz2022_masked_bbox_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable(
            "Built-up mask dz2022_masked is not available: dz2022_masked is missing or empty."
        )

    monkeypatch.setattr("api.platform_routes.builtup_mask_bbox", _boom)
    r = client.get("/layers/open/dz2022-masked", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    assert "features" not in r.json()


def test_builtup_mask_tiles_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable("Built-up mask builtup_mask is not available")

    monkeypatch.setattr("api.platform_routes.builtup_mask_mvt", _boom)
    r = client.get("/layers/open/builtup-mask/tiles/10/500/300")
    assert r.status_code == 503, r.text


def test_dz2022_masked_tiles_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable("Built-up mask dz2022_masked is not available")

    monkeypatch.setattr("api.platform_routes.builtup_mask_mvt", _boom)
    r = client.get("/layers/open/dz2022-masked/tiles/10/500/300")
    assert r.status_code == 503, r.text


def test_catalog_lists_builtup_mask_live_with_nrs_os_attribution():
    layers = {row["id"]: row for row in platform_catalog()["layers"]}
    row = layers["builtup_mask"]
    assert row["status"] == "live"
    assert row["endpoint"] == "/layers/open/dz2022-masked"
    assert row["tile_endpoint"] == "/layers/open/dz2022-masked/tiles/{z}/{x}/{y}"
    assert row["licence"] == "OGL-3.0"
    assert _BUILTUP_CREDIT_PIN == BUILTUP_CREDIT
    assert VISITOR_ATTRIBUTION == BUILTUP_CREDIT
    assert row["attribution"] == BUILTUP_CREDIT
    assert "NRS Settlements 2022" in row["attribution"]
    assert "Ordnance Survey data" in row["attribution"]
    assert "£" not in json.dumps(row)


def test_builtup_mask_routes_have_publication_declarations():
    from georgist.publication_rules import PUBLIC_ROUTE_RULES

    for path in (
        "/layers/open/builtup-mask",
        "/layers/open/dz2022-masked",
        "/layers/open/builtup-mask/tiles/{z}/{x}/{y}",
        "/layers/open/dz2022-masked/tiles/{z}/{x}/{y}",
    ):
        rule = PUBLIC_ROUTE_RULES[path]
        assert rule.value_basis == "none"
        assert rule.geometry_level == "zone"


def test_national_qa_json_matches_acceptance():
    qa = json.loads(NATIONAL_QA.read_text(encoding="utf-8"))
    assert qa["dz2022_masked_rows"] == EXPECTED_DZ2022_MASKED
    assert qa["dz2022_with_uprn"] == EXPECTED_DZ2022_MASKED
    assert qa["masked_codes_unique"] is True
    assert qa["masked_codes_subset_of_dz2022"] is True
    assert qa["uprn_inside_mask_pct"] == 100.0
    assert qa["uprn_outside_mask"] == 0
    assert qa["dz_with_uprn_missing_masked_geom"] == []


def test_fixture_geojson_codes_are_valid_dz2022():
    root = Path(__file__).resolve().parent / "fixtures" / "builtup_mask"
    dz = json.loads((root / "dz2022_masked.4326.geojson").read_text(encoding="utf-8"))
    codes = [f["properties"]["code"] for f in dz["features"]]
    assert len(codes) == len(set(codes))
    for code in codes:
        assert code.startswith("S01") and len(code) == 9
    fixture_qa = json.loads(FIXTURE_QA.read_text(encoding="utf-8"))
    assert fixture_qa["uprn_inside_mask_pct"] == 100.0
