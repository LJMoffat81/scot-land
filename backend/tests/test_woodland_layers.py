"""NFI and Native Woodland Survey: catalog, 503 when unloaded, bbox when loaded."""

from __future__ import annotations

from layers.platform import platform_catalog
from layers.woodland import LayerUnavailable, NATIVE_WOODLAND, NFI


GLASGOW_BBOX = {
    "south": 55.84,
    "west": -4.30,
    "north": 55.88,
    "east": -4.22,
}


def _fc(layer_id: str, count: int = 1) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[-4.28, 55.85], [-4.27, 55.85], [-4.27, 55.86], [-4.28, 55.86], [-4.28, 55.85]]]
                    ],
                },
                "properties": {
                    "feature_id": f"{layer_id}-1",
                    "layer": layer_id,
                    "licence": "Open Government Licence v3.0",
                },
            }
        ]
        * count,
        "meta": {
            "ok": True,
            "layer": layer_id,
            "count": count,
            "licence": "Open Government Licence v3.0",
            "source_url": "https://www.data.gov.uk/",
        },
    }


def test_catalog_lists_nfi_and_native_woodland_live_with_source_and_licence():
    layers = {row["id"]: row for row in platform_catalog()["layers"]}
    for layer_id, endpoint in (
        ("nfi", "/layers/open/nfi"),
        ("native_woodland", "/layers/open/native-woodland"),
    ):
        row = layers[layer_id]
        assert row["status"] == "live"
        assert row["endpoint"] == endpoint
        assert "Open Government Licence" in (row.get("licence") or "")
        assert row.get("licence_url", "").endswith("/open-government-licence/version/3/")
        assert row.get("source_url", "").startswith("https://www.data.gov.uk/")
        assert row.get("ledger_role") == "ledger-row"
        assert row.get("ledger_row") == "1"
        assert row.get("ui_surface") == "ledger"


def test_nfi_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable("nfi_woodland is missing or empty.")

    monkeypatch.setattr("api.platform_routes.query_nfi_bbox", _boom)
    r = client.get("/layers/open/nfi", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "missing" in detail
    assert "features" not in r.json()


def test_native_woodland_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable("native_woodland is missing or empty.")

    monkeypatch.setattr("api.platform_routes.query_native_woodland_bbox", _boom)
    r = client.get("/layers/open/native-woodland", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    assert "features" not in r.json()


def test_nfi_ok_empty_viewport_is_not_503(client, monkeypatch):
    monkeypatch.setattr(
        "api.platform_routes.query_nfi_bbox",
        lambda *_a, **_k: {
            "type": "FeatureCollection",
            "features": [],
            "meta": {"ok": True, "layer": "nfi", "count": 0},
        },
    )
    r = client.get("/layers/open/nfi", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []
    assert body["meta"]["ok"] is True


def test_native_woodland_bbox_returns_features(client, monkeypatch):
    monkeypatch.setattr(
        "api.platform_routes.query_native_woodland_bbox",
        lambda *_a, **_k: _fc("native_woodland"),
    )
    r = client.get("/layers/open/native-woodland", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["features"]) == 1
    assert body["features"][0]["properties"]["layer"] == "native_woodland"
    assert "Open Government Licence" in body["meta"]["licence"]


def test_nfi_bbox_returns_features(client, monkeypatch):
    monkeypatch.setattr(
        "api.platform_routes.query_nfi_bbox",
        lambda *_a, **_k: _fc("nfi"),
    )
    r = client.get("/layers/open/nfi", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    assert r.json()["features"][0]["properties"]["layer"] == "nfi"


def test_woodland_layer_specs():
    assert NFI.table == "nfi_woodland"
    assert NATIVE_WOODLAND.table == "native_woodland"
    assert NFI.layer_id == "nfi"
    assert NATIVE_WOODLAND.layer_id == "native_woodland"
