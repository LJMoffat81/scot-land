"""LAYERS-ADD-1 public surfaces (L5, L6, L9–L11) + tile/agg 404s."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from api.platform_routes import router
from layers.layer_flags import FLAG_HLS, FLAG_LDP
from layers.layers_add_catalog import (
    GATED_LAYER_IDS,
    TILE_PROPERTY_ALLOWLIST,
    is_layer_extract_present,
    tile_manifest,
)
from layers.platform import platform_catalog

ZONE_RE = re.compile(r"^S01\d{6}$")


def test_l5_flagged_tile_urls_404(monkeypatch):
    monkeypatch.delenv(FLAG_LDP, raising=False)
    monkeypatch.delenv(FLAG_HLS, raising=False)
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    for layer_id in sorted(GATED_LAYER_IDS):
        res = client.get(f"/tiles/{layer_id}/10/1/1")
        assert res.status_code == 404, layer_id


def test_l6_agg_ldp_hls_404_when_flags_off(monkeypatch):
    monkeypatch.delenv(FLAG_LDP, raising=False)
    monkeypatch.delenv(FLAG_HLS, raising=False)
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/layers/add/agg/agg_ldp").status_code == 404
    assert client.get("/layers/add/agg/agg_hls").status_code == 404


def test_l6_open_ldp_hla_flood_404_when_flags_off(monkeypatch):
    monkeypatch.delenv(FLAG_LDP, raising=False)
    monkeypatch.delenv(FLAG_HLS, raising=False)
    monkeypatch.delenv("LAYER_SEPA_FLOOD_EXTENT_ENABLED", raising=False)
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    q = "south=55.8&west=-4.3&north=55.9&east=-4.2"
    assert client.get(f"/layers/open/ldp?{q}").status_code == 404
    assert client.get(f"/layers/open/hla?{q}").status_code == 404
    assert client.get(f"/layers/open/flood?{q}").status_code == 404


def test_l9_tile_allowlists_exclude_address_and_currency():
    banned = re.compile(r"(address|uprn|postcode|owner|£|gbp|rent|value|des_title)", re.I)
    for layer_id, allow in TILE_PROPERTY_ALLOWLIST.items():
        for prop in allow:
            assert not banned.search(prop), f"{layer_id}:{prop}"


def test_l10_zone_id_pattern_helper():
    assert ZONE_RE.match("S01008677")
    assert not ZONE_RE.match("unknown")
    assert not ZONE_RE.match("")


def test_is_layers_skip_when_extract_absent():
    # CI has no Spatial Hub extracts under data/external/.
    assert is_layer_extract_present("green_belt") is False
    assert is_layer_extract_present("school_catchments") is False
    assert is_layer_extract_present("contaminated_land") is False
    manifest = tile_manifest()
    ids = {s["layer_id"] for s in manifest["sources"]}
    assert "green_belt" not in ids
    assert "school_catchments" not in ids
    assert "contaminated_land" not in ids


def test_layers_add_catalog_endpoint(monkeypatch):
    monkeypatch.delenv(FLAG_LDP, raising=False)
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    res = client.get("/layers/add/catalog")
    assert res.status_code == 200
    body = res.json()
    ids = {row["layer_id"] for row in body["layers"]}
    assert "simd2020_domains" in ids
    assert "sepa_frm_maps" not in ids
    assert "ldp_allocations" not in ids
    waiting_ids = {row["layer_id"] for row in body["waiting"]}
    assert waiting_ids == {"ldp_allocations", "housing_land_supply"}


def test_platform_catalog_layers_add_slice():
    catalog = platform_catalog()
    assert "layers_add" in catalog
    assert "layers_add_waiting" in catalog
    for row in catalog["layers_add"]:
        assert row["public"] is True
        assert row["licence_status"] != "prohibited"
