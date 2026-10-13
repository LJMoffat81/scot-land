"""Cadastral and public-land routes: 503 when data unavailable — never placeholders."""

from __future__ import annotations

from layers.cadastral import LayerUnavailable
from layers.platform import platform_catalog
from layers.public_land import DASHBOARD_URL, LICENCE


GLASGOW_BBOX = {
    "south": 55.84,
    "west": -4.30,
    "north": 55.88,
    "east": -4.22,
}


def test_public_crown_catalog_is_gap_unverified_not_open():
    layer = next(
        row for row in platform_catalog()["layers"] if row["id"] == "public_crown"
    )
    assert layer["status"] == "gap"
    assert layer["licence"] == "unverified/not open"
    assert layer["licence"] != "OGL-3.0"
    assert "OGL" not in layer["licence"]
    assert layer["source_url"] == DASHBOARD_URL
    assert "endpoint" not in layer


def test_parcels_bbox_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable(
            "Cadastral parcels are not available: inspire_parcels is missing or empty."
        )

    monkeypatch.setattr("api.cadastral_routes.parcels_bbox", _boom)
    r = client.get("/layers/parcels", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "missing" in detail
    body = r.json()
    assert "features" not in body
    assert "MOCK" not in r.text


def test_parcels_bbox_503_when_is_loaded_false(client, monkeypatch):
    monkeypatch.setattr("layers.cadastral.is_loaded", lambda: False)
    r = client.get("/layers/parcels", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    assert "inspire_parcels" in r.json().get("detail", "").lower()


def test_public_land_503_when_upstream_fails(client, monkeypatch):
    def _down(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {"ok": False, "error": "upstream timeout", "layer": "public_land"},
        }

    monkeypatch.setattr("api.platform_routes.public_land_bbox", _down)
    r = client.get("/layers/open/public-land", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "upstream" in detail
    assert "features" not in r.json()


def test_public_land_ok_empty_viewport_is_not_503(client, monkeypatch):
    def _empty(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": True,
                "layer": "public_land",
                "count": 0,
                "licence": LICENCE,
                "source_url": DASHBOARD_URL,
                "bodies": [],
                "gaps": ["Local-authority land not included"],
            },
        }

    monkeypatch.setattr("api.platform_routes.public_land_bbox", _empty)
    r = client.get("/layers/open/public-land", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []
    assert body["meta"]["ok"] is True
    assert body["meta"]["licence"] == "unverified/not open"
    assert body["meta"]["source_url"] == DASHBOARD_URL


def test_downloads_omit_unverified_public_land(client):
    r = client.get("/downloads")
    assert r.status_code == 200, r.text
    item_ids = {row["id"] for row in r.json()["items"]}
    assert "public_land_overlay" not in item_ids
    assert "public_crown_map" not in item_ids
    for row in r.json()["items"]:
        assert row.get("licence") != "unverified/not open"
        label = (row.get("label") or "").lower()
        rid = str(row.get("id") or "").lower()
        if ("public" in label and "crown" in label) or rid.startswith(
            "public_land"
        ) or rid.startswith("public_crown"):
            raise AssertionError(f"open downloads still list public/Crown: {row}")
