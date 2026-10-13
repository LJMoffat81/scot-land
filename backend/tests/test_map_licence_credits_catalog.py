"""Catalog licence fields that drive the public map credits control."""

from layers.platform import platform_catalog


def test_boundaries_catalog_carries_ros_attribution_and_licence_url():
    layer = next(L for L in platform_catalog()["layers"] if L["id"] == "boundaries")
    assert "Open Government Licence" in layer["licence"]
    assert "open-government-licence" in layer["licence_url"]
    assert "Registers of Scotland" in layer["attribution"]
    assert "OS data" in layer["attribution"]
    # Confirmed #62 wording — attribution line itself is not the licence phrase.
    assert "OGL-3.0" not in layer["attribution"]


def test_data_zones_catalog_carries_attribution():
    layer = next(L for L in platform_catalog()["layers"] if L["id"] == "data_zones")
    assert "Open Government Licence" in layer["licence"]
    assert layer.get("attribution")
    assert "not a rent" in layer["attribution"].lower()


def test_non_commercial_catalog_entries_tagged():
    layers = {L["id"]: L for L in platform_catalog()["layers"]}
    for layer_id in ("carbon_peatland", "nsta_oil_gas"):
        layer = layers[layer_id]
        assert layer["licence"] == "non-commercial"
        assert "non-commercial" in layer["attribution"].lower()
        assert layer["licence_url"]
        assert layer["ui_surface"] == "ledger"


def test_dz_context_layers_include_attribution():
    layers = [L for L in platform_catalog()["layers"] if L["id"].startswith("dz_")]
    assert layers
    for layer in layers:
        assert layer.get("attribution")
        assert "Open Government Licence" in layer["attribution"] or "OGL" in layer["licence"]
