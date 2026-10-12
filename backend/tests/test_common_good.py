"""Common Good linked registers — honest gaps, no invented spatial hits."""

from __future__ import annotations

from layers.common_good import (
    catalog_layer,
    common_good_payload,
    load_common_good,
    place_common_good,
)
from layers.platform import place_context, platform_catalog


def test_config_lists_verified_registers_only():
    data = load_common_good()
    registers = data.get("registers") or {}
    assert len(registers) >= 5
    assert len(registers) < 32
    for code, row in registers.items():
        assert code.startswith("S12")
        assert row.get("url", "").startswith("https://")
        assert row.get("name")
        assert row.get("kind") in {"register", "spatial_metadata"}


def test_payload_states_national_spatial_gap():
    payload = common_good_payload()
    assert payload["ok"] is True
    assert payload["status"] == "linked"
    assert "national" in payload["national_gap"].lower()
    assert "spatial" in payload["national_gap"].lower()
    assert payload["map_overlay"]["status"] == "gap"
    assert payload["register_count"] == len(payload["registers"])
    assert payload["council_count"] == 32
    fife = [
        s
        for s in payload["spatial_sources"]
        if s.get("council_code") == "S12000047"
    ]
    assert len(fife) == 1
    assert "INSPIRE" in (fife[0].get("licence") or "")
    assert fife[0].get("metadata_url")


def test_place_card_never_claims_on_point_hit():
    edinburgh = place_common_good("S12000036")
    assert edinburgh["status"] == "linked"
    assert edinburgh["on_this_point"] is None
    assert edinburgh["register"]["url"]

    unknown = place_common_good("S12000005")
    assert unknown["status"] == "gap"
    assert unknown["on_this_point"] is None
    assert unknown["register"] is None


def test_fife_links_spatial_metadata_without_proxy():
    fife = place_common_good("S12000047")
    assert fife["status"] == "linked"
    assert fife["spatial"]["metadata_url"]
    assert fife["on_this_point"] is None
    assert "expired" in (fife["spatial"].get("host_note") or "").lower()


def test_catalog_and_place_context_wire_common_good():
    layer = catalog_layer()
    assert layer["id"] == "common_good"
    assert layer["status"] == "linked"
    assert layer["endpoint"] == "/api/common-good.json"

    catalog = platform_catalog()
    ids = [row["id"] for row in catalog["layers"]]
    assert "common_good" in ids
    cg = next(row for row in catalog["layers"] if row["id"] == "common_good")
    assert cg["status"] == "linked"

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


def test_downloads_lists_common_good(client):
    response = client.get("/downloads")
    assert response.status_code == 200
    items = response.json().get("items") or []
    assert any(item.get("id") == "common_good" for item in items)
