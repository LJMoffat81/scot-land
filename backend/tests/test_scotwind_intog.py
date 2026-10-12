"""ScotWind / INTOG natural-capital overlay: catalog, 503, no invented fees/rent."""

from __future__ import annotations

from layers.platform import platform_catalog
from layers.scotwind import (
    EVIDENCE_TAG,
    FEE_STATUS_ABSENT,
    OGL_LICENCE_URL,
    PUBLICATION_STATUS_PARTIAL,
    LayerUnavailable,
    _public_props,
    source_meta,
)


NORTH_SEA_BBOX = {
    "south": 56.0,
    "west": -3.0,
    "north": 59.5,
    "east": 1.0,
}


def test_scotwind_catalog_records_licence_url_and_evidence_tag():
    layer = next(
        row for row in platform_catalog()["layers"] if row["id"] == "scotwind_intog"
    )
    assert layer["status"] == "live"
    assert layer["endpoint"] == "/layers/open/scotwind-intog"
    assert layer["licence_url"] == OGL_LICENCE_URL
    assert "GIS confirming" in layer["licence"]
    assert layer["evidence_tag"] == EVIDENCE_TAG == "market"
    assert layer["publication_status"] == PUBLICATION_STATUS_PARTIAL
    assert "surface rent" in layer["description"].lower()
    assert layer["source_url"]


def test_source_meta_matches_registry():
    meta = source_meta()
    assert meta["evidence_tag"] == "market"
    assert meta["fee_status"] == FEE_STATUS_ABSENT
    assert meta["publication_status"] == "partial"
    assert meta["licence_url"] == OGL_LICENCE_URL


def test_public_props_never_expose_fee_or_rent_amounts():
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
            "fee_status": FEE_STATUS_ABSENT,
            "publication_status": "partial",
            # DB may hold fee columns; public props must not echo invented £.
            "option_fee_gbp": 99_999_999,
            "option_fee_per_km2_gbp": 100_000,
        },
        meta,
    )
    assert "option_fee_gbp" not in props
    assert "option_fee_per_km2_gbp" not in props
    assert "annual_rent" not in props
    assert "surface_rent" not in props
    assert props["adds_to_surface_rent"] is False
    assert props["fee_status"] == FEE_STATUS_ABSENT
    assert props["evidence_tag"] == "market"


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
                        "coordinates": [[[-2.0, 57.0], [-1.9, 57.0], [-1.9, 57.1], [-2.0, 57.1], [-2.0, 57.0]]],
                    },
                    "properties": {
                        "id": "scotwind:1",
                        "leasing_round": "scotwind",
                        "award_id": 1,
                        "evidence_tag": "market",
                        "fee_status": FEE_STATUS_ABSENT,
                        "publication_status": "partial",
                        "adds_to_surface_rent": False,
                        "licence": "OGL-3.0 (CES Spatial Hub; GIS confirming dataset-level terms)",
                        "licence_url": OGL_LICENCE_URL,
                    },
                }
            ],
            "meta": {
                "ok": True,
                "layer": "scotwind_intog",
                "count": 1,
                "evidence_tag": "market",
                "publication_status": "partial",
                "fee_status": FEE_STATUS_ABSENT,
                "adds_to_surface_rent": False,
                "licence": "OGL-3.0 (CES Spatial Hub; GIS confirming dataset-level terms)",
                "licence_url": OGL_LICENCE_URL,
            },
        }

    monkeypatch.setattr("api.platform_routes.scotwind_bbox", _payload)
    r = client.get("/layers/open/scotwind-intog", params=NORTH_SEA_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["evidence_tag"] == "market"
    assert body["meta"]["adds_to_surface_rent"] is False
    props = body["features"][0]["properties"]
    assert "option_fee" not in props
    assert props["fee_status"] == FEE_STATUS_ABSENT


def test_downloads_lists_scotwind(client):
    r = client.get("/downloads")
    assert r.status_code == 200, r.text
    items = {row["id"]: row for row in r.json()["items"]}
    row = items["scotwind_intog"]
    assert row["endpoint"] == "/layers/open/scotwind-intog"
    assert row["licence_url"] == OGL_LICENCE_URL
    assert "GIS confirming" in row["licence"]


def test_ingest_row_builder_leaves_fees_null():
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
    assert row["option_fee_gbp"] is None
    assert row["option_fee_per_km2_gbp"] is None
    assert row["fee_status"] == "not_in_open_attributes"
    assert row["evidence_tag"] == "market"
    assert row["publication_status"] == "partial"
