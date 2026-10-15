"""LCA (James Hutton) routes: 503 when unloaded; catalogue licence honesty."""

from __future__ import annotations

from etl.ingest_lca import CLASS_LABELS, class_label
from layers.lca import LayerUnavailable
from layers.platform import platform_catalog


GLASGOW_BBOX = {
    "south": 55.84,
    "west": -4.30,
    "north": 55.88,
    "east": -4.22,
}


def test_catalog_lists_lca_live_with_hutton_licence():
    layer = next(row for row in platform_catalog()["layers"] if row["id"] == "lca")
    # LAYER-CATALOG-STATUS — not ingested on public hosts yet.
    assert layer["status"] == "gap"
    assert layer["endpoint"] == "/layers/open/lca"
    assert "hutton" in (layer.get("source_url") or "").lower()
    licence = (layer.get("licence") or "").lower()
    assert licence == "james hutton institute open data licence"
    # Must not claim the product itself is OGL-3.0.
    assert licence != "ogl-3.0"
    assert not licence.startswith("ogl")
    note = (layer.get("licence_note") or "").lower()
    assert "not ogl-3.0" in note
    attribution = layer.get("attribution") or ""
    assert "James Hutton Institute" in attribution
    assert "All rights reserved" in attribution
    assert "Open Government Licence v.2.0" in attribution
    share = (layer.get("share_alike") or "").lower()
    assert "equivalent" in share
    assert "attribution" in share
    assert layer.get("licence_url")
    assert layer.get("ledger_role") == "constraint"
    assert layer.get("ledger_row") is None
    assert layer.get("ui_surface") == "ledger"


def test_lca_bbox_503_when_not_loaded(client, monkeypatch):
    def _boom(*_a, **_k):
        raise LayerUnavailable(
            "Land Capability for Agriculture is not available: "
            "lca_agriculture is missing or empty."
        )

    monkeypatch.setattr("api.platform_routes.lca_bbox", _boom)
    r = client.get("/layers/open/lca", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "missing" in detail
    assert "features" not in r.json()
    assert "MOCK" not in r.text


def test_lca_bbox_503_when_is_loaded_false(client, monkeypatch):
    monkeypatch.setattr("layers.lca.is_loaded", lambda: False)
    r = client.get("/layers/open/lca", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    assert "lca_agriculture" in r.json().get("detail", "").lower()


def test_lca_bbox_ok_empty_viewport(client, monkeypatch):
    def _empty(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": True,
                "layer": "lca",
                "count": 0,
                "licence": (
                    "James Hutton Institute Open Data Licence "
                    "(public-sector information under OGL v2.0 — not pure OGL)"
                ),
            },
        }

    monkeypatch.setattr("api.platform_routes.lca_bbox", _empty)
    r = client.get("/layers/open/lca", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []
    assert body["meta"]["ok"] is True


def test_downloads_lists_lca(client):
    r = client.get("/downloads")
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    assert any(item.get("id") == "lca_overlay" for item in items)


def test_ingest_class_labels_cover_hutton_codes():
    assert "Class 1" in class_label(1.0)
    assert "Built-up" in class_label(888.0)
    assert "Inland water" in class_label(999.0)
    assert 9500.0 in CLASS_LABELS
