"""Community ownership layer: catalog, 503 when unloaded, honest gaps."""

from __future__ import annotations

from layers.community_ownership import LayerUnavailable, catalog_layer
from layers.platform import platform_catalog


GLASGOW_BBOX = {
    "south": 55.84,
    "west": -4.30,
    "north": 55.88,
    "east": -4.22,
}


def test_catalog_layer_is_live_ogl():
    row = catalog_layer()
    assert row["id"] == "community_ownership"
    assert row["status"] == "live"
    assert row["group"] == "ownership"
    assert row["endpoint"] == "/layers/open/community-ownership"
    assert "Open Government Licence" in row["licence"]
    assert row.get("licence_url")
    assert "gov.scot" in (row.get("source_url") or "")
    assert row.get("gaps")
    assert row.get("ledger_role") == "ownership-context"
    assert row.get("ui_surface") == "ledger"
    assert row.get("ledger_row") is None


def test_platform_catalog_includes_community_ownership():
    live = {
        layer["id"]: layer
        for layer in platform_catalog()["layers"]
        if layer.get("status") == "live"
    }
    assert "community_ownership" in live
    assert live["community_ownership"]["endpoint"] == "/layers/open/community-ownership"


def test_community_ownership_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable(
            "Community ownership overlay is not available: "
            "community_ownership_assets is missing or empty."
        )

    monkeypatch.setattr(
        "api.platform_routes.community_ownership_bbox", _boom
    )
    r = client.get("/layers/open/community-ownership", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "missing" in detail
    assert "features" not in r.json()


def test_community_ownership_503_when_is_loaded_false(client, monkeypatch):
    monkeypatch.setattr("layers.community_ownership.is_loaded", lambda: False)
    r = client.get("/layers/open/community-ownership", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    assert "community_ownership" in r.json().get("detail", "").lower()


def test_community_ownership_ok_empty_viewport_is_not_503(client, monkeypatch):
    def _empty(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": True,
                "layer": "community_ownership",
                "count": 0,
                "licence": "Open Government Licence v3.0",
                "gaps": ["Points are postcode centroids — not title extents"],
            },
        }

    monkeypatch.setattr(
        "api.platform_routes.community_ownership_bbox", _empty
    )
    r = client.get("/layers/open/community-ownership", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []
    assert body["meta"]["ok"] is True


def test_place_card_exposes_community_ownership_block(monkeypatch):
    from layers.platform import place_context

    monkeypatch.setattr(
        "layers.platform.community_ownership_at_point",
        lambda *_a, **_k: {
            "ok": True,
            "intersects": True,
            "assets": [
                {
                    "asset_id": "cos2024-0001",
                    "group_name": "Example Trust",
                    "asset_name": "Village Hall",
                    "asset_type": "Building only",
                }
            ],
            "licence": "Open Government Licence v3.0",
            "source": "SG",
            "note": "postcode centroids",
        },
    )
    monkeypatch.setattr(
        "layers.platform.vdl_at_point",
        lambda *_a, **_k: {"ok": True, "intersects": False, "sites": []},
    )
    monkeypatch.setattr(
        "layers.platform.hla_at_point",
        lambda *_a, **_k: {"ok": True, "intersects": False, "sites": []},
    )
    monkeypatch.setattr(
        "layers.platform.lookup_parcel_geojson",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "layers.platform._land_register_outline",
        lambda *_a, **_k: None,
    )
    card = place_context(55.86, -4.25, council_code="S12000049")
    assert card["community_ownership"]["on_this_point"] is True
    assert card["community_ownership"]["assets"][0]["group_name"] == "Example Trust"
    assert "community_ownership" in card["flags"]
