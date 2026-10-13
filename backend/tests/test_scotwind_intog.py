"""ScotWind / INTOG natural-capital overlay: OGL catalog, 503, polygons only."""

from __future__ import annotations

from pathlib import Path

import yaml

from layers.platform import platform_catalog
from layers.scotwind import (
    CATALOG_CREDIT,
    EVIDENCE_TAG,
    LICENCE,
    OGL_LICENCE_URL,
    PUBLICATION_STATUS_OK,
    LayerUnavailable,
    _public_props,
    source_meta,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
NORTH_SEA_BBOX = {
    "south": 56.0,
    "west": -3.0,
    "north": 59.5,
    "east": 1.0,
}


def setup_function():
    source_meta.cache_clear()


def test_scotwind_catalog_ogl_credit_and_evidence_tag():
    layer = next(
        row for row in platform_catalog()["layers"] if row["id"] == "scotwind_intog"
    )
    assert layer["status"] == "live"
    assert layer["endpoint"] == "/layers/open/scotwind-intog"
    assert layer["licence"] == LICENCE == "OGL-3.0"
    assert layer["licence_url"] == OGL_LICENCE_URL
    assert layer["attribution"] == CATALOG_CREDIT
    assert "the Crown Estate Scotland" in layer["attribution"]
    assert layer["evidence_tag"] == EVIDENCE_TAG == "market"
    assert layer["publication_status"] == PUBLICATION_STATUS_OK == "ok"
    assert layer["ledger_role"] == "ledger-row"
    assert layer["ledger_row"] == "4"
    assert layer["ui_surface"] == "ledger"
    assert "surface rent" in layer["description"].lower()
    assert "HOLD" in layer["description"] or "hold" in layer["description"].lower()


def test_source_meta_matches_registry():
    meta = source_meta()
    assert meta["licence"] == "OGL-3.0"
    assert meta["evidence_tag"] == "market"
    assert meta["publication_status"] == "ok"
    assert meta["attribution"] == CATALOG_CREDIT
    assert meta["licence_url"] == OGL_LICENCE_URL
    assert meta["fees_config"].endswith("scotwind_option_fees.yaml")


def test_fees_hold_config_exists_and_forbids_layer_attachment():
    path = REPO_ROOT / "data" / "config" / "scotwind_option_fees.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["status"] == "hold"
    assert doc["layer_attachment"] == "forbidden"
    assert doc["evidence"] == "press_release_only"
    assert doc["polygons_layer"]["fees_on_features"] is False
    assert doc["sources"]


def test_public_props_are_polygons_only_no_fee_fields():
    meta = source_meta()
    props = _public_props(
        {
            "id": "scotwind:1",
            "leasing_round": "scotwind",
            "award_id": 1,
            "lead_applicant": "Example",
            "technology": "Fixed",
            "category": None,
            "innovation_category": None,
            "capacity_mw": 1000,
            "area_km2": 200,
            "evidence_tag": "market",
            "publication_status": "ok",
        },
        meta,
    )
    assert "option_fee_gbp" not in props
    assert "option_fee_per_km2_gbp" not in props
    assert "fee_status" not in props
    assert "annual_rent" not in props
    assert "surface_rent" not in props
    assert props["adds_to_surface_rent"] is False
    assert props["evidence_tag"] == "market"
    assert props["publication_status"] == "ok"
    assert props["attribution"] == CATALOG_CREDIT


def test_scotwind_bbox_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable(
            "ScotWind/INTOG option polygons are not available: "
            "ces_scotwind_intog is missing or empty."
        )

    monkeypatch.setattr("api.platform_routes.scotwind_bbox", _boom)
    r = client.get("/layers/open/scotwind-intog", params=NORTH_SEA_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "missing" in detail
    assert "features" not in r.json()
    assert "MOCK" not in r.text


def test_scotwind_bbox_503_when_is_loaded_false(client, monkeypatch):
    monkeypatch.setattr("layers.scotwind.is_loaded", lambda: False)
    r = client.get("/layers/open/scotwind-intog", params=NORTH_SEA_BBOX)
    assert r.status_code == 503, r.text
    assert "ces_scotwind_intog" in r.json().get("detail", "").lower()


def test_scotwind_bbox_ok_when_loaded(client, monkeypatch):
    def _payload(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[-2.0, 57.0], [-1.9, 57.0], [-1.9, 57.1], [-2.0, 57.1], [-2.0, 57.0]]
                        ],
                    },
                    "properties": {
                        "id": "scotwind:1",
                        "leasing_round": "scotwind",
                        "award_id": 1,
                        "evidence_tag": "market",
                        "publication_status": "ok",
                        "adds_to_surface_rent": False,
                        "licence": "OGL-3.0",
                        "licence_url": OGL_LICENCE_URL,
                        "attribution": CATALOG_CREDIT,
                    },
                }
            ],
            "meta": {
                "ok": True,
                "layer": "scotwind_intog",
                "count": 1,
                "evidence_tag": "market",
                "publication_status": "ok",
                "fees_on_features": False,
                "adds_to_surface_rent": False,
                "licence": "OGL-3.0",
                "licence_url": OGL_LICENCE_URL,
                "attribution": CATALOG_CREDIT,
            },
        }

    monkeypatch.setattr("api.platform_routes.scotwind_bbox", _payload)
    r = client.get("/layers/open/scotwind-intog", params=NORTH_SEA_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["evidence_tag"] == "market"
    assert body["meta"]["publication_status"] == "ok"
    assert body["meta"]["fees_on_features"] is False
    assert body["meta"]["adds_to_surface_rent"] is False
    props = body["features"][0]["properties"]
    assert "option_fee" not in props
    assert "fee_status" not in props


def test_downloads_lists_scotwind_ogl(client):
    r = client.get("/downloads")
    assert r.status_code == 200, r.text
    items = {row["id"]: row for row in r.json()["items"]}
    row = items["scotwind_intog"]
    assert row["endpoint"] == "/layers/open/scotwind-intog"
    assert row["licence"] == "OGL-3.0"
    assert row["licence_url"] == OGL_LICENCE_URL
    assert row["attribution"] == CATALOG_CREDIT


def test_ingest_row_builder_has_no_fee_fields():
    from etl.ingest_scotwind_intog import _row_from_feature

    feature = {
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-2.0, 57.0], [-1.9, 57.0], [-1.9, 57.1], [-2.0, 57.1], [-2.0, 57.0]]],
        },
        "properties": {
            "Id": 7,
            "Lead_App": "Example Wind",
            "Technology": "Floating",
            "Total_Cap": 500,
            "Area_km2": 100,
        },
    }
    row = _row_from_feature(
        feature,
        leasing_round="scotwind",
        award_field="Id",
        capacity_field="Total_Cap",
    )
    assert row is not None
    assert row["id"] == "scotwind:7"
    assert "option_fee_gbp" not in row
    assert "fee_status" not in row
    assert row["evidence_tag"] == "market"
    assert row["publication_status"] == "ok"
    assert row["licence"] == "OGL-3.0"
