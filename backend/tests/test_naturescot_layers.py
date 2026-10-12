"""NatureScot SSSI / designations: catalog, 503 when unloaded, no placeholders."""

from __future__ import annotations

from layers.naturescot import LayerUnavailable
from layers.platform import platform_catalog


GLASGOW_BBOX = {
    "south": 55.84,
    "west": -4.30,
    "north": 55.88,
    "east": -4.22,
}


OGL_V3_URL = (
    "https://www.nationalarchives.gov.uk/doc/"
    "open-government-licence/version/3/"
)


def test_catalog_includes_sssi_and_naturescot_with_ogl():
    layers = {row["id"]: row for row in platform_catalog()["layers"]}
    sssi = layers["sssi"]
    assert sssi["status"] == "live"
    assert sssi["licence"] == "OGL-3.0"
    assert sssi["licence_url"] == OGL_V3_URL
    assert sssi["endpoint"] == "/layers/open/sssi"
    assert "nature.scot" in (sssi.get("source_url") or "")

    des = layers["naturescot_designations"]
    assert des["status"] == "live"
    assert des["licence"] == "OGL-3.0"
    assert des["licence_url"] == OGL_V3_URL
    assert des["endpoint"] == "/layers/open/naturescot-designations"
    assert "nature.scot" in (des.get("source_url") or "")


def test_sssi_bbox_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable(
            "SSSI designations are not available: naturescot_sssi is missing or empty."
        )

    monkeypatch.setattr("api.platform_routes.sssi_bbox", _boom)
    r = client.get("/layers/open/sssi", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "missing" in detail
    assert "features" not in r.json()
    assert "MOCK" not in r.text


def test_designations_bbox_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable(
            "NatureScot designations are not available: naturescot_designations "
            "is missing or empty."
        )

    monkeypatch.setattr("api.platform_routes.naturescot_designations_bbox", _boom)
    r = client.get("/layers/open/naturescot-designations", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    assert "features" not in r.json()


def test_sssi_ok_empty_viewport_is_not_503(client, monkeypatch):
    def _empty(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": True,
                "layer": "sssi",
                "count": 0,
                "licence": "OGL-3.0",
                "gaps": ["Indicative NatureScot boundaries — not a title plan"],
            },
        }

    monkeypatch.setattr("api.platform_routes.sssi_bbox", _empty)
    r = client.get("/layers/open/sssi", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []
    assert body["meta"]["ok"] is True
    assert body["meta"]["licence"] == "OGL-3.0"


def test_designations_ok_with_feature(client, monkeypatch):
    def _one(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-4.29, 55.85],
                                [-4.28, 55.85],
                                [-4.28, 55.86],
                                [-4.29, 55.86],
                                [-4.29, 55.85],
                            ]
                        ],
                    },
                    "properties": {
                        "name": "Fixture SPA",
                        "designation_type": "spa",
                        "pa_code": "9001",
                        "layer": "naturescot_designations",
                        "licence": "OGL-3.0",
                    },
                }
            ],
            "meta": {
                "ok": True,
                "layer": "naturescot_designations",
                "count": 1,
                "licence": "OGL-3.0",
            },
        }

    monkeypatch.setattr("api.platform_routes.naturescot_designations_bbox", _one)
    r = client.get("/layers/open/naturescot-designations", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["features"]) == 1
    assert body["features"][0]["properties"]["designation_type"] == "spa"
    assert body["meta"]["licence"] == "OGL-3.0"


def test_downloads_index_lists_naturescot(client):
    r = client.get("/downloads")
    assert r.status_code == 200, r.text
    items = {row["id"]: row for row in r.json().get("items") or []}
    assert items["sssi_overlay"]["licence"] == "OGL-3.0"
    assert items["sssi_overlay"]["endpoint"] == "/layers/open/sssi"
    assert items["naturescot_designations_overlay"]["licence"] == "OGL-3.0"
    assert (
        items["naturescot_designations_overlay"]["endpoint"]
        == "/layers/open/naturescot-designations"
    )


def test_naturescot_catalog_is_constraint():
    from layers.platform import platform_catalog

    layers = {r["id"]: r for r in platform_catalog()["layers"]}
    for lid in ("sssi", "naturescot_designations"):
        assert layers[lid]["status"] == "live"
        assert layers[lid]["ledger_role"] == "constraint"
        assert layers[lid]["ledger_row"] is None
        assert layers[lid]["ui_surface"] == "ledger"
