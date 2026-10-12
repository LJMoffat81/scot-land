"""NRS settlements/localities: 503 when unloaded; catalog + publication wiring."""

from __future__ import annotations

from layers.nrs_places import LayerUnavailable

GLASGOW_BBOX = {
    "south": 55.84,
    "west": -4.30,
    "north": 55.88,
    "east": -4.22,
}


def test_settlements_bbox_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable(
            "NRS settlements are not available: nrs_settlements is missing or empty."
        )

    monkeypatch.setattr("api.nrs_routes.query_bbox", _boom)
    r = client.get("/layers/open/settlements", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "missing" in detail
    assert "features" not in r.json()


def test_localities_bbox_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable(
            "NRS localities are not available: nrs_localities is missing or empty."
        )

    monkeypatch.setattr("api.nrs_routes.query_bbox", _boom)
    r = client.get("/layers/open/localities", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    assert "features" not in r.json()


def test_settlements_bbox_503_when_is_loaded_false(client, monkeypatch):
    monkeypatch.setattr("layers.nrs_places.is_loaded", lambda _kind: False)
    r = client.get("/layers/open/settlements", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    assert "nrs_settlements" in r.json().get("detail", "").lower()


def test_catalog_lists_nrs_layers_live():
    from layers.platform import platform_catalog

    layers = {row["id"]: row for row in platform_catalog()["layers"]}
    assert layers["settlements"]["status"] == "live"
    assert layers["settlements"]["endpoint"] == "/layers/open/settlements"
    assert layers["settlements"]["licence"] == "OGL-3.0"
    assert layers["localities"]["status"] == "live"
    assert layers["localities"]["endpoint"] == "/layers/open/localities"
    assert "Census2022" in (layers["settlements"].get("source_url") or "")


def test_nrs_routes_have_publication_declarations():
    from georgist.publication_rules import PUBLIC_ROUTE_RULES

    for path in (
        "/layers/open/settlements",
        "/layers/open/localities",
        "/layers/open/settlements/at",
        "/layers/open/localities/at",
    ):
        rule = PUBLIC_ROUTE_RULES[path]
        assert rule.value_basis == "none"
        assert rule.geometry_level == "site"
