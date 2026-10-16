"""GBP-LIVE-V1 — public £ behind one flag (default OFF) + under-review zones."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from georgist import gbp_live as gl


@pytest.fixture(autouse=True)
def _clear_gbp_cache():
    gl.clear_gbp_live_cache()
    yield
    gl.clear_gbp_live_cache()


def _write_cfg(tmp_path: Path, *, enabled: bool, under_review=None) -> Path:
    path = tmp_path / "gbp_live.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "gbp_live": {
                    "enabled": enabled,
                    "under_review_zones": list(under_review or []),
                }
            }
        ),
        encoding="utf-8",
    )
    gl.clear_gbp_live_cache()
    return path


def _publishable_row(**overrides):
    base = {
        "code": "S01014713",
        "vintage": 2022,
        "measured_rent": 12000.0,
        "uncertainty_low": 6000.0,
        "uncertainty_high": 18000.0,
        # 10 ha → £1.20 / £0.60 / £1.80 per m² (GBP-LIVE-V1b display unit).
        "residential_land_ha": 10.0,
        "quality": "modelled",
        "publish_level": "public_zone",
        "publication_status": "ok",
        "fill_method": "observed_pooled",
        "proxy_tags": ["estimate_label=measured"],
        "value_tier": "proxy",
    }
    base.update(overrides)
    return base


def _stub_place_seams(monkeypatch):
    monkeypatch.setattr(
        "layers.platform.lookup_parcel_geojson",
        lambda lat, lng: {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": {
                "label": "TEST-PARCEL",
                "inspire_id": "inspire-test-1",
                "area_sqm": 120.0,
            },
        },
    )
    monkeypatch.setattr(
        "layers.platform._land_register_outline",
        lambda lat, lng: {"status": "inside_outline"},
    )
    monkeypatch.setattr(
        "layers.platform.vdl_at_point",
        lambda lat, lng: {
            "ok": True,
            "intersects": True,
            "sites": [
                {
                    "name": "Demo vacant site",
                    "site_type": "Vacant Land",
                    "size_ha": 0.4,
                }
            ],
        },
    )
    monkeypatch.setattr(
        "layers.platform._data_zone_at",
        lambda lat, lng: {
            "status": "ok",
            "code": "S01014713",
            "name": "Demo Zone 2022",
            "vintage": 2022,
            "zones": [
                {
                    "code": "S01008677",
                    "vintage": 2011,
                    "name": "Demo Zone 2011",
                    "on_boundary": False,
                },
                {
                    "code": "S01014713",
                    "vintage": 2022,
                    "name": "Demo Zone 2022",
                    "on_boundary": False,
                },
            ],
            "source": "test",
            "vintages_loaded": [2011, 2022],
        },
    )
    monkeypatch.setattr(
        "layers.platform._intermediate_zone_for",
        lambda data_zone: {
            "status": "ok",
            "code": "S02002727",
            "name": "Old Town, Princes Street and Leith Street",
            "note": None,
            "licence": "OGL v3.0 — NRS/Scottish Government Intermediate Zones",
        },
    )
    monkeypatch.setattr(
        "layers.platform._place_label_from_nrs",
        lambda lat, lng, *, council_name=None, postcode=None: (
            "Edinburgh, Old Town" if council_name else (postcode or "This place")
        ),
    )
    monkeypatch.setattr(
        "layers.platform._resolve_council",
        lambda lat, lng, *, council_code=None, council_name=None: (
            council_code or "S12000049",
            council_name or "Glasgow City",
        ),
    )


def test_config_default_off():
    cfg = gl.load_gbp_live_config()
    assert cfg["enabled"] is False
    assert cfg["under_review_zones"] == ()
    assert gl.gbp_live_enabled() is False


def test_public_settings_flag_off():
    settings = gl.public_settings()
    assert settings["enabled"] is False
    assert settings["banner"] is None
    assert settings["rent_rate_wording"] is None


def test_public_settings_flag_on(tmp_path):
    path = _write_cfg(tmp_path, enabled=True)
    settings = gl.public_settings(path)
    assert settings["enabled"] is True
    assert settings["banner"] == gl.EARLY_ESTIMATES_BANNER
    assert settings["rent_rate_wording"] == gl.rent_rate_wording_how_it_works()
    assert "yield" not in settings["rent_rate_wording"].lower()
    assert settings["unit"] == gl.UNIT
    assert settings["unit_wording"] == gl.UNIT_WORDING
    assert "£" not in str(settings)


def test_rent_rate_wording_signed_off():
    assert gl.rent_rate_wording_card() == (
        "Yearly rent: up to 4.5% of the land's value"
    )
    assert gl.rent_rate_wording_how_it_works() == (
        "We turn land value into a yearly rent of up to 4.5% of that value."
    )
    assert "yield" not in gl.rent_rate_wording_card().lower()
    assert "yield" not in gl.rent_rate_wording_how_it_works().lower()


def test_platform_gbp_live_route_default_off(monkeypatch):
    monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
    from api.main import create_app

    client = TestClient(create_app())
    response = client.get("/platform/gbp-live")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert "yield_wording" not in body
    assert "£" not in str(body)


def test_place_card_flag_off_no_pound(monkeypatch):
    _stub_place_seams(monkeypatch)
    from api.main import create_app

    client = TestClient(create_app())
    response = client.get("/platform/place", params={"lat": 55.86, "lng": -4.25})
    assert response.status_code == 200
    body = response.json()
    assert body["gbp_live"]["enabled"] is False
    assert "surface_rent_display" not in body
    assert "£" not in str(body)
    assert "yield" not in str(body).lower() or "yield" in str(
        # allow internal-only keys never present on public card
        []
    )


def test_place_card_flag_on_shows_range_and_label(monkeypatch, tmp_path):
    _stub_place_seams(monkeypatch)
    path = _write_cfg(tmp_path, enabled=True)
    row = _publishable_row()
    monkeypatch.setattr(gl, "CONFIG_PATH", path)
    monkeypatch.setattr(
        gl, "fetch_surface_rent_row", lambda code, vintage: row
    )
    gl.clear_gbp_live_cache()

    from layers.platform import place_context

    card = place_context(55.86, -4.25)
    assert card["gbp_live"]["enabled"] is True
    assert card["gbp_live"]["unit"] == gl.UNIT
    assert card["gbp_live"]["unit_wording"] == gl.UNIT_WORDING
    display = card["surface_rent_display"]
    assert display["state"] == "ok"
    # Zone £12k / 10 ha / 10_000 = £0.12 per m² (etc.).
    assert display["low"] == 0.06
    assert display["central"] == 0.12
    assert display["high"] == 0.18
    assert display["unit"] == "per m²"
    assert display["unit_wording"] == "per square metre of land, per year"
    assert "£" not in display["unit_wording"]
    assert display["central_label"] == "most likely"
    assert display["numerator"] == "measured_rent"
    assert display["denominator"] == "residential_land_ha"
    assert display["estimate_label"] == "Measured"
    assert display["rent_rate_wording"] == gl.rent_rate_wording_card()
    assert "yield_wording" not in display
    assert "yield" not in display["rent_rate_wording"].lower()
    assert display["grain"] == "data_zone"
    assert "total" not in display
    assert "scotland_total" not in str(card).lower()
    assert "£" not in str(display)


def test_numerator_is_residential_surface_rent_fields():
    """GBP-LIVE-V1c: numerator fields are residential surface rent only."""
    assert gl.NUMERATOR_CENTRAL_FIELD == "measured_rent"
    assert gl.NUMERATOR_LOW_FIELD == "uncertainty_low"
    assert gl.NUMERATOR_HIGH_FIELD == "uncertainty_high"
    assert gl.NUMERATOR_FIELDS == (
        "uncertainty_low",
        "measured_rent",
        "uncertainty_high",
    )
    assert gl.AREA_FIELD == "residential_land_ha"
    assert "farmland" not in "".join(gl.NUMERATOR_FIELDS)
    assert "other_land" not in "".join(gl.NUMERATOR_FIELDS)
    for banned in gl.EXCLUDED_AREA_FIELDS:
        assert banned != gl.AREA_FIELD
        assert banned not in gl.NUMERATOR_FIELDS


def test_per_m2_uses_residential_land_ha_not_other_land(tmp_path):
    path = _write_cfg(tmp_path, enabled=True)
    row = _publishable_row(
        measured_rent=20_000.0,
        uncertainty_low=10_000.0,
        uncertainty_high=30_000.0,
        residential_land_ha=2.0,
        # Farmland / other-land area must not affect the per-m² rate.
        other_land_ha=999.0,
        farmland_ha=500.0,
        zone_ha=1000.0,
    )
    display = gl.surface_rent_display_for_row(row, code=row["code"], path=path)
    assert display["state"] == "ok"
    assert display["central"] == 1.0  # 20000 / (2 * 10000)
    assert display["low"] == 0.5
    assert display["high"] == 1.5
    assert display["numerator"] == "measured_rent"
    assert display["denominator"] == "residential_land_ha"
    assert display["numerator_fields"] == list(gl.NUMERATOR_FIELDS)


def test_missing_area_estimate_unavailable_no_pound(tmp_path):
    path = _write_cfg(tmp_path, enabled=True)
    row = _publishable_row()
    del row["residential_land_ha"]
    display = gl.surface_rent_display_for_row(row, code=row["code"], path=path)
    assert display["state"] == "under_review"
    assert display["label"] == gl.ESTIMATE_UNAVAILABLE_LABEL
    assert display["label"] == "estimate unavailable"
    assert display["central"] is None
    assert "£" not in str(display)


def test_zero_area_estimate_unavailable(tmp_path):
    path = _write_cfg(tmp_path, enabled=True)
    row = _publishable_row(residential_land_ha=0.0)
    display = gl.surface_rent_display_for_row(row, code=row["code"], path=path)
    assert display["state"] == "under_review"
    assert display["label"] == "estimate unavailable"
    assert display["central"] is None


def test_negative_area_estimate_unavailable(tmp_path):
    path = _write_cfg(tmp_path, enabled=True)
    row = _publishable_row(residential_land_ha=-1.0)
    display = gl.surface_rent_display_for_row(row, code=row["code"], path=path)
    assert display["state"] == "under_review"
    assert display["label"] == "estimate unavailable"
    assert display["central"] is None


def test_clamped_negative_residual_estimate_unavailable(tmp_path):
    path = _write_cfg(tmp_path, enabled=True)
    row = _publishable_row(
        measured_rent=0.0,
        uncertainty_low=0.0,
        uncertainty_high=0.0,
        negative_residual=True,
    )
    display = gl.surface_rent_display_for_row(row, code=row["code"], path=path)
    assert display["state"] == "under_review"
    assert display["label"] == "estimate unavailable"
    assert display["central"] is None
    assert "£" not in str(display)


def test_zero_measured_rent_estimate_unavailable(tmp_path):
    path = _write_cfg(tmp_path, enabled=True)
    row = _publishable_row(
        measured_rent=0.0,
        uncertainty_low=0.0,
        uncertainty_high=100.0,
        negative_residual=False,
    )
    display = gl.surface_rent_display_for_row(row, code=row["code"], path=path)
    assert display["state"] == "under_review"
    assert display["label"] == "estimate unavailable"
    assert display["central"] is None


def test_zero_low_estimate_unavailable(tmp_path):
    """GBP-LIVE-V1d: low <= 0 clamps even when central/high are positive."""
    path = _write_cfg(tmp_path, enabled=True)
    row = _publishable_row(
        measured_rent=100.0,
        uncertainty_low=0.0,
        uncertainty_high=200.0,
        negative_residual=False,
    )
    display = gl.surface_rent_display_for_row(row, code=row["code"], path=path)
    assert display["state"] == "under_review"
    assert display["label"] == "estimate unavailable"
    assert display["central"] is None
    assert "£" not in str(display)


def test_zero_high_estimate_unavailable(tmp_path):
    """GBP-LIVE-V1d: high <= 0 clamps even when central is positive."""
    path = _write_cfg(tmp_path, enabled=True)
    row = _publishable_row(
        measured_rent=100.0,
        uncertainty_low=50.0,
        uncertainty_high=0.0,
        negative_residual=False,
    )
    display = gl.surface_rent_display_for_row(row, code=row["code"], path=path)
    assert display["state"] == "under_review"
    assert display["label"] == "estimate unavailable"
    assert display["central"] is None
    assert "£" not in str(display)


def test_place_card_flag_on_under_review_no_pound(monkeypatch, tmp_path):
    _stub_place_seams(monkeypatch)
    path = _write_cfg(tmp_path, enabled=True, under_review=["S01014713"])
    row = _publishable_row(code="S01014713")
    monkeypatch.setattr(gl, "CONFIG_PATH", path)
    monkeypatch.setattr(
        gl, "fetch_surface_rent_row", lambda code, vintage: row
    )
    gl.clear_gbp_live_cache()

    from layers.platform import place_context

    card = place_context(55.86, -4.25)
    display = card["surface_rent_display"]
    assert display["state"] == "under_review"
    assert display["label"] == gl.ESTIMATE_UNAVAILABLE_LABEL
    assert display["low"] is None
    assert display["central"] is None
    assert display["high"] is None
    assert "£" not in str(display)
    surface = next(r for r in card["agr_rows"] if r["id"] == "surface")
    assert surface["range"] == gl.ESTIMATE_UNAVAILABLE_LABEL


def test_placeholder_never_shows_money(tmp_path):
    path = _write_cfg(tmp_path, enabled=True)
    row = _publishable_row(quality="placeholder", publication_status="ok")
    display = gl.surface_rent_display_for_row(row, code=row["code"], path=path)
    assert display["state"] == "hidden"
    assert display["central"] is None


def test_blocked_row_hidden(tmp_path):
    path = _write_cfg(tmp_path, enabled=True)
    row = _publishable_row(publication_status="blocked", publish_level="internal")
    display = gl.surface_rent_display_for_row(row, code=row["code"], path=path)
    assert display["state"] == "hidden"


def test_estimate_labels_visitor_words():
    assert gl.visitor_estimate_label("measured") == "Measured"
    assert gl.visitor_estimate_label("partly_estimated") == "Partly estimated"
    assert gl.visitor_estimate_label("fully_estimated") == "Fully estimated"


def test_early_estimates_banner_copy():
    assert gl.EARLY_ESTIMATES_BANNER == (
        "Early estimates; ranges are wide and will change."
    )
    assert gl.ESTIMATE_UNAVAILABLE_LABEL == "estimate unavailable"
    assert gl.UNIT_WORDING == "per square metre of land, per year"
