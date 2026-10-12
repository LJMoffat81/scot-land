"""Common Good — OGL PostGIS overlay + linked registers; honest gaps."""

from __future__ import annotations

from layers.common_good import (
    catalog_layer,
    common_good_payload,
    load_common_good,
    place_common_good,
)
from layers.common_good_spatial import LayerUnavailable
from layers.platform import place_context, platform_catalog

HIGHLAND_BBOX = {
    "south": 57.4,
    "west": -4.3,
    "north": 57.9,
    "east": -4.1,
}


def test_config_lists_ogl_spatial_and_verified_registers():
    data = load_common_good()
    registers = data.get("registers") or {}
    assert len(registers) >= 5
    assert len(registers) < 32
    for code, row in registers.items():
        assert code.startswith("S12")
        assert row.get("url", "").startswith("https://")
        assert row.get("name")
        assert row.get("kind") in {"register", "spatial_metadata"}

    spatial = data.get("spatial_sources") or []
    assert len(spatial) >= 3
    ogl = [
        s
        for s in spatial
        if str(s.get("licence") or "").upper().startswith("OGL")
    ]
    assert len(ogl) >= 2
    for source in ogl:
        assert source.get("feature_server")
        assert source.get("catalog_url") or source.get("open_data_url")
        assert source.get("ingest", True) is not False

    fife = [s for s in spatial if s.get("council_code") == "S12000047"]
    assert len(fife) == 1
    assert fife[0].get("ingest") is False
    assert "INSPIRE" in (fife[0].get("licence") or "")
    assert fife[0].get("catalog_url") or fife[0].get("metadata_url")


def test_payload_exposes_ogl_overlay_and_fife_linked():
    payload = common_good_payload()
    assert payload["ok"] is True
    assert "national" in payload["national_gap"].lower()
    assert payload["register_count"] == len(payload["registers"])
    assert payload["council_count"] == 32
    assert payload["ogl_spatial_source_count"] >= 2
    assert payload["map_overlay"]["endpoint"] == "/layers/open/common-good"
    assert payload["map_overlay"]["postgis_table"] == "common_good_sites"
    # Unloaded CI / local without ingest stays linked + reason, never invents rows.
    assert payload["map_overlay"]["status"] in {"live", "linked"}
    if payload["map_overlay"]["status"] == "linked":
        assert payload["map_overlay"]["reason"]
        assert payload["map_overlay"]["postgis_rows"] == 0

    fife = [
        s
        for s in payload["spatial_sources"]
        if s.get("council_code") == "S12000047"
    ]
    assert len(fife) == 1
    assert "INSPIRE" in (fife[0].get("licence") or "")
    assert fife[0].get("metadata_url") or fife[0].get("catalog_url")


def test_place_card_without_coords_never_claims_on_point():
    edinburgh = place_common_good("S12000036")
    assert edinburgh["status"] in {"linked", "live"}
    assert edinburgh["on_this_point"] is None
    assert edinburgh["register"]["url"]

    unknown = place_common_good("S12000005")
    # Unloaded PostGIS + no register → gap; loaded → live with no on-point claim.
    assert unknown["status"] in {"gap", "live"}
    assert unknown["on_this_point"] is None
    assert unknown["register"] is None


def test_fife_links_spatial_metadata_without_proxy():
    fife = place_common_good("S12000047")
    assert fife["status"] in {"linked", "live"}
    assert fife["spatial"]["metadata_url"] or fife["spatial"]["catalog_url"]
    assert fife["on_this_point"] is None
    assert "expired" in (fife["spatial"].get("host_note") or "").lower()


def test_catalog_is_live_and_wires_common_good():
    layer = catalog_layer()
    assert layer["id"] == "common_good"
    assert layer["status"] == "live"
    assert layer["endpoint"] == "/layers/open/common-good"
    assert layer["stats_endpoint"] == "/api/common-good.json"
    assert "OGL" in (layer.get("licence") or "")
    assert layer.get("source_url")
    assert layer.get("ledger_role") == "ownership-context"
    assert layer.get("ui_surface") == "ledger"

    catalog = platform_catalog()
    ids = [row["id"] for row in catalog["layers"]]
    assert "common_good" in ids
    assert "fife_land_map" not in ids
    cg = next(row for row in catalog["layers"] if row["id"] == "common_good")
    assert cg["status"] == "live"
    assert cg["endpoint"] == "/layers/open/common-good"
    assert cg.get("ledger_role") == "ownership-context"
    assert cg.get("ui_surface") == "ledger"
    assert cg.get("licence_url")

    card = place_context(55.95, -3.19, council_code="S12000036")
    assert card["common_good"]["status"] in {"linked", "live"}
    # Edinburgh is outside Highland OGL coverage — no invented hit.
    assert card["common_good"]["on_this_point"] in {None, False}


def test_api_common_good_json(client):
    response = client.get("/api/common-good.json")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["map_overlay"]["endpoint"] == "/layers/open/common-good"
    assert body["register_count"] >= 5
    assert any(
        row.get("council_code") == "S12000036" for row in body["registers"]
    )
    assert any(
        str(s.get("licence") or "").upper().startswith("OGL")
        for s in body["spatial_sources"]
    )


def test_downloads_lists_common_good(client):
    response = client.get("/downloads")
    assert response.status_code == 200
    items = response.json().get("items") or []
    assert any(item.get("id") == "common_good" for item in items)


def test_common_good_503_when_unloaded(client, monkeypatch):
    def _down(*_a, **_k):
        raise LayerUnavailable("common_good_sites empty")

    monkeypatch.setattr("api.platform_routes.common_good_bbox", _down)
    r = client.get("/layers/open/common-good", params=HIGHLAND_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "common good" in detail
    assert "features" not in r.json()


def test_common_good_ok_empty_viewport(client, monkeypatch):
    def _empty(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": True,
                "layer": "common_good",
                "count": 0,
                "licence": "OGL-3.0",
            },
        }

    monkeypatch.setattr("api.platform_routes.common_good_bbox", _empty)
    r = client.get("/layers/open/common-good", params=HIGHLAND_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []
    assert body["meta"]["ok"] is True
    assert body["meta"]["licence"] == "OGL-3.0"


def test_common_good_ok_returns_site_properties(client, monkeypatch):
    def _sites(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-4.16, 57.81],
                                [-4.15, 57.81],
                                [-4.15, 57.82],
                                [-4.16, 57.82],
                                [-4.16, 57.81],
                            ]
                        ],
                    },
                    "properties": {
                        "site_id": "test-tain",
                        "name": "TEST COMMON GOOD",
                        "site_kind": "site",
                        "council_code": "S12000017",
                        "council_name": "Highland",
                        "area_ha": 0.5,
                        "layer": "common_good",
                        "licence": "OGL-3.0",
                        "source_id": "highland_common_good_sites",
                    },
                }
            ],
            "meta": {
                "ok": True,
                "layer": "common_good",
                "count": 1,
                "licence": "OGL-3.0",
            },
        }

    monkeypatch.setattr("api.platform_routes.common_good_bbox", _sites)
    r = client.get("/layers/open/common-good", params=HIGHLAND_BBOX)
    assert r.status_code == 200, r.text
    props = r.json()["features"][0]["properties"]
    assert props["name"] == "TEST COMMON GOOD"
    assert props["licence"] == "OGL-3.0"
    assert props["layer"] == "common_good"
    assert props["council_name"] == "Highland"
