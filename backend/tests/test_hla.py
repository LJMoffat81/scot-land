"""Housing Land Audit / Housing Land Supply: OGL catalog, ingest helpers, 503 path."""

from __future__ import annotations

from pathlib import Path

import yaml

from etl.ingest_hla_sites import (
    capacity_for,
    hectares_for,
    site_id_for,
    vintage_for,
)
from layers.hla import ATTRIBUTION, LICENCE, SPATIAL_HUB_URL, hla_source_meta
from layers.platform import platform_catalog

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
FIXTURE = REPO_ROOT / "data" / "fixtures" / "hla" / "sample_sites.geojson"

GLASGOW_BBOX = {
    "south": 55.84,
    "west": -4.30,
    "north": 55.88,
    "east": -4.22,
}


def test_sources_yaml_records_ogl_hla():
    sources = yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8"))
    hla = sources["hla"]
    assert hla["licence"] == "OGL-3.0"
    assert "housing_land_supply-is" in hla["spatial_hub_url"]
    assert hla["bbox_endpoint"] == "/layers/open/hla"
    assert hla["postgis_source"] == "hla"
    assert "PSGA" in " ".join(hla["gaps"]) or "Digimap" in " ".join(hla["gaps"])


def test_catalog_lists_live_hla_layer():
    layers = {row["id"]: row for row in platform_catalog()["layers"]}
    hla = layers["hla"]
    assert hla["status"] == "live"
    assert hla["licence"] == "OGL-3.0"
    assert hla["endpoint"] == "/layers/open/hla"
    assert SPATIAL_HUB_URL in (hla.get("source_url") or "")
    assert "OGL" in LICENCE
    assert "Improvement Service" in ATTRIBUTION


def test_hla_source_meta_from_registry():
    meta = hla_source_meta()
    assert meta["licence"] == "OGL-3.0"
    assert "housing_land_supply-is" in meta["spatial_hub_url"]
    assert meta["gaps"]


def test_ingest_helpers_map_spatial_hub_fields():
    props = {
        "hls_uid": "HLS00012",
        "site_refer": "ABC1",
        "la_s_code": "S12000049",
        "hla_year": "2024/25",
        "ha_geometry": "2.5",
        "remaining": "18",
    }
    assert site_id_for(props, 0) == "HLS00012"
    assert hectares_for(props, None) == 2.5
    assert capacity_for(props) == 18
    assert vintage_for(props) == "2024/25"
    assert site_id_for({"la_s_code": "S12000036", "site_refer": "X"}, 3) == (
        "S12000036|X|3"
    )


def test_synthetic_fixture_exists_and_is_marked():
    assert FIXTURE.is_file()
    text = FIXTURE.read_text(encoding="utf-8")
    assert "synthetic-test-only" in text
    assert "FeatureCollection" in text


def test_hla_503_when_not_loaded(client, monkeypatch):
    def _down(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": "planning_sites has no HLA rows",
                "layer": "hla",
            },
        }

    monkeypatch.setattr("api.platform_routes.hla_bbox", _down)
    r = client.get("/layers/open/hla", params=GLASGOW_BBOX)
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "").lower()
    assert "not available" in detail or "hla" in detail
    assert "features" not in r.json()


def test_hla_ok_empty_viewport_is_not_503(client, monkeypatch):
    def _empty(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": True,
                "layer": "hla",
                "count": 0,
                "licence": "OGL-3.0",
                "gaps": ["patchy capacity"],
            },
        }

    monkeypatch.setattr("api.platform_routes.hla_bbox", _empty)
    r = client.get("/layers/open/hla", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []
    assert body["meta"]["ok"] is True


def test_hla_ok_returns_site_level_properties(client, monkeypatch):
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
                                [-4.26, 55.86],
                                [-4.25, 55.86],
                                [-4.25, 55.87],
                                [-4.26, 55.87],
                                [-4.26, 55.86],
                            ]
                        ],
                    },
                    "properties": {
                        "site_id": "SYN-HLA-002",
                        "local_authority": "Glasgow City",
                        "size_ha": 0.4,
                        "capacity_homes": 12,
                        "hla_year": "2024/25",
                        "layer": "hla",
                        "licence": "OGL-3.0",
                    },
                }
            ],
            "meta": {
                "ok": True,
                "layer": "hla",
                "count": 1,
                "licence": "OGL-3.0",
                "spatial_hub_url": SPATIAL_HUB_URL,
            },
        }

    monkeypatch.setattr("api.platform_routes.hla_bbox", _sites)
    r = client.get("/layers/open/hla", params=GLASGOW_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["licence"] == "OGL-3.0"
    props = body["features"][0]["properties"]
    assert props["site_id"] == "SYN-HLA-002"
    assert props["capacity_homes"] == 12
    assert props["layer"] == "hla"


def test_hla_catalog_is_ledger_row_1a():
    from layers.platform import platform_catalog

    layer = next(r for r in platform_catalog()["layers"] if r["id"] == "hla")
    assert layer["status"] == "live"
    assert layer["ledger_role"] == "ledger-row"
    assert layer["ledger_row"] == "1a"
    assert layer["ui_surface"] == "ledger"
