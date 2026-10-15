"""Public place-card contract: council, data zone, layers, links — no AGR £."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient


def _app(monkeypatch):
    from api.main import create_app

    monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    return create_app()


def _stub_place_seams(monkeypatch):
    """Keep place-card tests offline and deterministic."""
    monkeypatch.setattr(
        "layers.platform.lookup_parcel_geojson",
        lambda lat, lng: {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": {
                "label": "TEST-PARCEL",
                "inspire_id": "inspire-test-1",
                "area_sqm": 120.0,
            },
        },
    )
    monkeypatch.setattr(
        "layers.platform._land_register_outline",
        lambda lat, lng: {"status": "inside_outline"},
    )
    monkeypatch.setattr(
        "layers.platform.vdl_at_point",
        lambda lat, lng: {
            "ok": True,
            "intersects": True,
            "sites": [
                {
                    "name": "Demo vacant site",
                    "site_type": "Vacant Land",
                    "size_ha": 0.4,
                }
            ],
        },
    )
    monkeypatch.setattr(
        "layers.platform._data_zone_at",
        lambda lat, lng: {
            "status": "ok",
            "code": "S01014713",
            "name": "Demo Zone 2022",
            "vintage": 2022,
            "zones": [
                {
                    "code": "S01008677",
                    "vintage": 2011,
                    "name": "Demo Zone 2011",
                    "on_boundary": False,
                },
                {
                    "code": "S01014713",
                    "vintage": 2022,
                    "name": "Demo Zone 2022",
                    "on_boundary": False,
                },
            ],
            "source": "test",
            "vintages_loaded": [2011, 2022],
        },
    )
    monkeypatch.setattr(
        "layers.platform._intermediate_zone_for",
        lambda data_zone: {
            "status": "ok",
            "code": "S02002727",
            "name": "Old Town, Princes Street and Leith Street",
            "note": None,
            "licence": "OGL v3.0 — NRS/Scottish Government Intermediate Zones",
        },
    )
    monkeypatch.setattr(
        "layers.platform._place_label_from_nrs",
        lambda lat, lng, *, council_name=None, postcode=None: (
            "Edinburgh, Old Town" if council_name else (postcode or "This place")
        ),
    )
    monkeypatch.setattr(
        "layers.platform._resolve_council",
        lambda lat, lng, *, council_code=None, council_name=None: (
            council_code or "S12000049",
            council_name or "Glasgow City",
        ),
    )


def test_platform_place_contract_shape(monkeypatch):
    _stub_place_seams(monkeypatch)
    client = TestClient(_app(monkeypatch))
    response = client.get("/platform/place", params={"lat": 55.86, "lng": -4.25})
    assert response.status_code == 200
    body = response.json()

    assert body["contract"] == "place_card_v1"
    assert body["council_code"] == "S12000049"
    assert body["council_name"] == "Glasgow City"
    assert body["data_zone"]["code"] == "S01014713"
    assert body["data_zone"]["vintage"] == 2022
    assert body["data_zone"]["status"] == "ok"
    assert body["intermediate_zone"]["name"] == (
        "Old Town, Princes Street and Leith Street"
    )
    assert body["intermediate_zone"]["status"] == "ok"
    assert "No data" not in (body["intermediate_zone"].get("name") or "")
    assert "inspire_id" not in (body.get("land_outline") or {})
    assert body.get("land_outline", {}).get("label") == "Land outline"

    layer_ids = [row["id"] for row in body["layers"]]
    assert layer_ids == [
        "boundaries",
        "vdl",
        "public_crown",
        "common_good",
        "la_holdings",
        "sasine_private",
    ]
    by_id = {row["id"]: row for row in body["layers"]}
    assert by_id["boundaries"]["intersects"] is True
    assert by_id["vdl"]["intersects"] is True
    assert by_id["public_crown"]["status"] == "gap"
    assert by_id["public_crown"]["intersects"] is None
    assert by_id["common_good"]["intersects"] is None
    assert by_id["la_holdings"]["status"] == "gap"
    assert by_id["sasine_private"]["status"] == "gap"

    # Charter: every place-card layer carries a licence credit.
    for row in body["layers"]:
        assert row.get("licence"), f"layer {row['id']} missing licence credit"
    assert "Open Government Licence" in by_id["boundaries"]["licence"]
    assert by_id["boundaries"]["licence_url"]
    assert by_id["vdl"]["licence"] == "OGL-3.0"
    assert by_id["vdl"]["licence_url"]
    assert "unverified" in by_id["public_crown"]["licence"].lower()

    # Designer v3.1 fields — map reference is grid indices only (no label prefix).
    assert re.fullmatch(r"-?\d+,-?\d+", body["square_reference"])
    assert "Scot-LAND" not in body["square_reference"]
    assert "what3words" not in body["square_reference"].lower()
    assert "agr_rows" in body
    assert [r["id"] for r in body["agr_rows"]] == ["surface", "resource", "nature"]
    for row in body["agr_rows"]:
        assert row["amount_label"] == "figures pending sign-off"
        assert row["tag"] in {"market", "proxy", "shadow"}
    surface = body["agr_rows"][0]
    assert {n["id"] for n in surface["of_which"]} == {
        "planning_uplift",
        "infrastructure_share",
    }
    assert body["holder"]["label"]
    assert body["constraints"]
    assert body["intermediate_zone"].get("name")

    link_ids = {row["id"] for row in body["links"]}
    assert "scotlis" in link_ids
    assert "methodology" in link_ids
    assert "vdl_register" in link_ids

    # No modelled residual AGR £ on the public place card.
    assert "agr" not in body
    blob = str(body).lower()
    assert "plot_gbp" not in blob
    assert "annual_ground_rent" not in blob
    assert "£" not in str(body)
    assert "what3words" not in blob


def test_api_place_json_has_no_agr(monkeypatch):
    _stub_place_seams(monkeypatch)
    client = TestClient(_app(monkeypatch))
    response = client.get(
        "/api/place.json",
        params={"lat": 55.86, "lng": -4.25},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["contract"] == "place_card_v1"
    assert "agr" not in body
    assert body["council_code"] == "S12000049"
    assert any(row["id"] == "boundaries" for row in body["layers"])


def test_place_context_unit_no_agr_keys(monkeypatch):
    from layers.platform import place_context

    _stub_place_seams(monkeypatch)
    card = place_context(55.95, -3.19)
    assert card["contract"] == "place_card_v1"
    assert "agr" not in card
    assert isinstance(card["layers"], list)
    assert isinstance(card["links"], list)
    assert card["data_zone"]["status"] == "ok"
