"""Common Good linked registers — honest gaps, no invented spatial hits."""

from __future__ import annotations

from layers.common_good import (
    catalog_layer,
    common_good_payload,
    load_common_good,
    place_common_good,
)
from layers.platform import place_context, platform_catalog


def test_config_lists_verified_registers_and_linked_spatial():
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

    # No source may claim OGL or request ingest — loader would skip all.
    for source in spatial:
        licence = str(source.get("licence") or "")
        assert not licence.upper().startswith("OGL"), source.get("id")
        assert source.get("ingest") is False
        assert source.get("status") == "linked"
        assert source.get("feature_server")

    highland = [s for s in spatial if s.get("council_code") == "S12000017"]
    assert len(highland) == 2
    for source in highland:
        assert source.get("licence") == "unconfirmed"
        assert source.get("catalog_url") or source.get("open_data_url")

    fife = [s for s in spatial if s.get("council_code") == "S12000047"]
    assert len(fife) == 1
    assert "INSPIRE" in (fife[0].get("licence") or "")
    assert fife[0].get("catalog_url") or fife[0].get("metadata_url")


def test_payload_states_national_spatial_gap():
    payload = common_good_payload()
    assert payload["ok"] is True
    assert payload["status"] == "linked"
    assert "national" in payload["national_gap"].lower()
    assert "spatial" in payload["national_gap"].lower()
    assert payload["map_overlay"]["status"] == "gap"
    assert payload["register_count"] == len(payload["registers"])
    assert payload["council_count"] == 32
    assert "unconfirmed" in (payload["note"] or "").lower()

    highland = [
        s
        for s in payload["spatial_sources"]
        if s.get("council_code") == "S12000017"
    ]
    assert len(highland) == 2
    assert all(s.get("licence") == "unconfirmed" for s in highland)
    assert all(s.get("ingest") is False for s in highland)

    fife = [
        s
        for s in payload["spatial_sources"]
        if s.get("council_code") == "S12000047"
    ]
    assert len(fife) == 1
    assert "INSPIRE" in (fife[0].get("licence") or "")
    assert fife[0].get("metadata_url") or fife[0].get("catalog_url")


def test_place_card_never_claims_on_point_hit():
    edinburgh = place_common_good("S12000036")
    assert edinburgh["status"] == "linked"
    assert edinburgh["on_this_point"] is None
    assert edinburgh["register"]["url"]

    highland = place_common_good("S12000017")
    assert highland["status"] == "linked"
    assert highland["on_this_point"] is None
    assert highland["spatial"]["licence"] == "unconfirmed"
    assert highland["spatial"]["ingest"] is False
    assert highland["register"]["url"]

    unknown = place_common_good("S12000005")
    assert unknown["status"] == "gap"
    assert unknown["on_this_point"] is None
    assert unknown["register"] is None


def test_fife_links_spatial_metadata_without_proxy():
    fife = place_common_good("S12000047")
    assert fife["status"] == "linked"
    assert fife["spatial"]["metadata_url"] or fife["spatial"]["catalog_url"]
    assert fife["on_this_point"] is None
    assert fife["spatial"]["ingest"] is False
    assert "expired" in (fife["spatial"].get("host_note") or "").lower()


def test_catalog_and_place_context_wire_common_good():
    layer = catalog_layer()
    assert layer["id"] == "common_good"
    assert layer["status"] == "linked"
    assert layer["endpoint"] == "/api/common-good.json"
    assert "unconfirmed" in (layer.get("licence") or "").lower()
    assert "OGL" not in (layer.get("licence") or "")
    assert layer.get("source_url")
    assert layer.get("ledger_role") == "ownership-context"
    assert layer.get("ui_surface") == "ledger"

    catalog = platform_catalog()
    ids = [row["id"] for row in catalog["layers"]]
    assert "common_good" in ids
    assert "fife_land_map" not in ids
    cg = next(row for row in catalog["layers"] if row["id"] == "common_good")
    assert cg["status"] == "linked"
    assert cg["endpoint"] == "/api/common-good.json"
    assert cg.get("ledger_role") == "ownership-context"
    assert cg.get("ui_surface") == "ledger"
    assert "unconfirmed" in (cg.get("licence") or "").lower()

    card = place_context(55.95, -3.19, council_code="S12000036")
    assert card["common_good"]["status"] == "linked"
    assert card["common_good"]["on_this_point"] is None


def test_api_common_good_json(client):
    response = client.get("/api/common-good.json")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["map_overlay"]["status"] == "gap"
    assert body["register_count"] >= 5
    assert any(
        row.get("council_code") == "S12000036" for row in body["registers"]
    )
    assert any(
        s.get("licence") == "unconfirmed" for s in body["spatial_sources"]
    )
    assert not any(
        str(s.get("licence") or "").upper().startswith("OGL")
        for s in body["spatial_sources"]
    )


def test_downloads_lists_common_good(client):
    response = client.get("/downloads")
    assert response.status_code == 200
    items = response.json().get("items") or []
    cg = next(item for item in items if item.get("id") == "common_good")
    assert "/api/common-good.json" in (cg.get("endpoint") or "")
    assert "OGL" not in (cg.get("licence") or "")
