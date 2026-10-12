"""LDP allocations: catalog, PostGIS bbox path, honest national gaps."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from etl.ingest_ldp_allocations import features_from_geojson
from layers.ldp import (
    SPATIAL_HUB_URL,
    SPATIALDATA_METADATA_URL,
    catalog_layer,
    coverage_summary,
    query_bbox,
    source_meta,
)
from layers.platform import platform_catalog

REPO_ROOT = Path(__file__).resolve().parents[2]

GLASGOW_BBOX = {
    "south": 55.8,
    "west": -4.4,
    "north": 55.95,
    "east": -4.1,
}


def test_sources_yaml_catalogues_ogl_and_spatial_hub():
    cfg = yaml.safe_load((REPO_ROOT / "data" / "config" / "sources.yaml").read_text(encoding="utf-8"))
    ldp = cfg["ldp_allocations"]
    assert ldp["licence"] == "OGL-3.0"
    assert ldp["spatial_hub_url"] == SPATIAL_HUB_URL
    assert "Edinburgh" in " ".join(ldp["gaps"])
    assert "fragmented" in " ".join(ldp["gaps"]).lower()
    seeds = ldp["ingest_seeds"]
    assert seeds and all("OGL" in s["licence"].upper() for s in seeds)
    assert any(s["id"] == "highland_ldp_allocations" for s in seeds)


def test_catalog_layer_live_with_gaps_and_endpoint():
    layer = catalog_layer()
    assert layer["id"] == "ldp_allocations"
    assert layer["status"] == "live"
    assert layer["endpoint"] == "/layers/open/ldp"
    assert layer["licence"] == "OGL-3.0"
    assert layer["source_url"] == SPATIAL_HUB_URL
    assert layer["spatial_hub_url"] == SPATIAL_HUB_URL
    assert layer["ledger_role"] == "ledger-row"
    assert layer["ledger_row"] == "1a"
    assert layer["ui_surface"] == "ledger"
    assert any("Edinburgh" in g for g in layer["gaps"])
    catalog = platform_catalog()
    ids = [row["id"] for row in catalog["layers"]]
    assert "ldp_allocations" in ids
    assert ids.index("ldp_allocations") > ids.index("vdl")


def test_source_meta_points_at_spatialdata_record():
    meta = source_meta()
    assert meta["metadata_url"] == SPATIALDATA_METADATA_URL
    assert meta["licence"] == "OGL-3.0"


def test_geojson_ingest_helper_builds_rows():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "code": "H1",
                    "allocation": "Housing",
                    "source": "Highland LDP",
                    "hectares": 2.5,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-4.25, 57.48],
                            [-4.24, 57.48],
                            [-4.24, 57.49],
                            [-4.25, 57.49],
                            [-4.25, 57.48],
                        ]
                    ],
                },
            }
        ],
    }
    rows = features_from_geojson(
        fc,
        authority="Highland",
        licence="OGL-3.0",
        source_url="https://example.test/highland",
    )
    assert len(rows) == 1
    assert rows[0]["site_id"] == "Highland:H1"
    assert rows[0]["allocation"] == "Housing"
    assert rows[0]["hectares"] == pytest.approx(2.5)


def test_ldp_503_when_not_loaded(client, monkeypatch):
    def _down(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": False,
                "error": "ldp_allocations is missing or empty",
                "layer": "ldp_allocations",
            },
        }

    monkeypatch.setattr("api.platform_routes.ldp_bbox", _down)
    r = client.get("/layers/open/ldp", params=GLASGOW_BBOX)
    assert r.status_code == 503
    assert "not available" in r.json()["detail"].lower()


def test_ldp_ok_empty_viewport_is_not_503(client, monkeypatch):
    def _empty(*_a, **_k):
        return {
            "type": "FeatureCollection",
            "features": [],
            "meta": {
                "ok": True,
                "layer": "ldp_allocations",
                "count": 0,
                "gaps": ["City of Edinburgh LDP spatial data is unavailable"],
                "licence": "OGL-3.0",
                "source_url": SPATIAL_HUB_URL,
            },
        }

    monkeypatch.setattr("api.platform_routes.ldp_bbox", _empty)
    r = client.get("/layers/open/ldp", params=GLASGOW_BBOX)
    assert r.status_code == 200
    body = r.json()
    assert body["features"] == []
    assert body["meta"]["ok"] is True


def test_ldp_ok_returns_allocation_properties(client, monkeypatch):
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
                                [-4.25, 57.48],
                                [-4.24, 57.48],
                                [-4.24, 57.49],
                                [-4.25, 57.49],
                                [-4.25, 57.48],
                            ]
                        ],
                    },
                    "properties": {
                        "site_id": "Highland:H1",
                        "authority": "Highland",
                        "allocation": "Housing",
                        "code": "H1",
                        "layer": "ldp_allocations",
                        "licence": "OGL-3.0",
                    },
                }
            ],
            "meta": {
                "ok": True,
                "layer": "ldp_allocations",
                "count": 1,
                "licence": "OGL-3.0",
                "source_url": SPATIAL_HUB_URL,
                "gaps": ["City of Edinburgh LDP spatial data is unavailable"],
            },
        }

    monkeypatch.setattr("api.platform_routes.ldp_bbox", _sites)
    r = client.get("/layers/open/ldp", params=GLASGOW_BBOX)
    assert r.status_code == 200
    feat = r.json()["features"][0]
    assert feat["properties"]["allocation"] == "Housing"
    assert feat["properties"]["licence"] == "OGL-3.0"


def test_api_ldp_coverage_meta(client, monkeypatch):
    monkeypatch.setattr(
        "api.platform_routes.ldp_coverage",
        lambda: {
            "ok": False,
            "loaded": False,
            "authorities": [],
            "n_features": 0,
            "gaps": ["City of Edinburgh LDP spatial data is unavailable"],
            "licence": "OGL-3.0",
            "source_url": SPATIAL_HUB_URL,
        },
    )
    r = client.get("/api/ldp.json")
    assert r.status_code == 200
    body = r.json()
    assert body["loaded"] is False
    assert any("Edinburgh" in g for g in body["gaps"])


def test_query_bbox_unloaded_returns_meta_ok_false(monkeypatch):
    monkeypatch.setattr("layers.ldp.is_loaded", lambda: False)
    out = query_bbox(55.8, -4.4, 55.95, -4.1)
    assert out["meta"]["ok"] is False
    assert out["features"] == []


def test_coverage_summary_unloaded_lists_gaps(monkeypatch):
    monkeypatch.setattr("layers.ldp.is_loaded", lambda: False)
    summary = coverage_summary()
    assert summary["loaded"] is False
    assert any("fragmented" in g.lower() or "Edinburgh" in g for g in summary["gaps"])
