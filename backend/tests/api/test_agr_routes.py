"""AGR: public routes carry no rent £; Wealth Engine place is internal DZ2022 + blocked."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agr.publication import UNPUBLISHED_REASON, gbp_range, internal_yield_from_surface, rent_figure_paths
from georgist.surface_settings import yield_placeholder


def _app(monkeypatch, *, internal: bool = False, aggregates: bool = False):
    from api.main import create_app

    if internal:
        monkeypatch.setenv("ENABLE_INTERNAL_ENDPOINTS", "1")
        monkeypatch.setenv("INTERNAL_API_TOKEN", "test-internal-token")
    else:
        monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
        monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    if aggregates:
        monkeypatch.setenv("ENABLE_INTERNAL_AGR_AGGREGATE_GBP", "1")
    else:
        monkeypatch.delenv("ENABLE_INTERNAL_AGR_AGGREGATE_GBP", raising=False)
    return create_app()


def _auth():
    return {"Authorization": "Bearer test-internal-token"}


def test_agr_router_loads_when_publication_declarations_present(monkeypatch):
    """Regression: missing declarations used to skip the whole router at startup."""
    from api.main import ROUTER_STATUS, registered_routes

    app = _app(monkeypatch)
    assert ROUTER_STATUS["api.agr_routes"]["loaded"] is True
    paths = {p for _, p in registered_routes(app)}
    assert "/layers/catalog" in paths
    assert "/layers/councils" in paths  # scrubbed context metrics; no modelled £
    assert "/place" in paths
    assert "/address" in paths
    assert "/postcode/{postcode}" in paths
    assert "/layers/context/{layer_id}/tiles/{z}/{x}/{y}" in paths
    assert "/square" not in paths
    assert "/layers/councils-agr" not in paths
    assert "/fiscal/summary" not in paths
    assert "/layers/w3w-grid" not in paths


def test_public_postcode_is_location_only(monkeypatch):
    client = TestClient(_app(monkeypatch))
    r = client.get("/postcode/G21DU")
    if r.status_code == 200:
        body = r.json()
        assert body.get("agr") is None
        assert body.get("status") == "location_only"
        assert "lat" in body and "lng" in body
        assert rent_figure_paths(body) == []
    else:
        assert r.status_code in {404, 502}


def test_public_config_and_catalog_carry_experimental_no_literal_5pct(monkeypatch):
    client = TestClient(_app(monkeypatch))
    for path in ("/config", "/layers/catalog", "/signoff"):
        r = client.get(path)
        assert r.status_code == 200, path
        body = r.json()
        assert body["label"] == "experimental"
        assert body["value_tier_tags"] == ["market", "proxy", "shadow"]
        assert "experimental" in body["disclaimer"].lower()
        assert ("5" + "%") not in json.dumps(body)


def test_public_routes_expose_no_rent_figures(monkeypatch):
    client = TestClient(_app(monkeypatch))
    probes = [
        ("/health", {}),
        ("/signoff", {}),
        ("/config", {}),
        ("/layers/catalog", {}),
        ("/sales/status", {}),
        ("/api/roll.json", {}),
        ("/api/place.json", {"lat": 55.86, "lng": -4.25}),
        ("/api/vdl-councils.json", {}),
    ]
    for path, params in probes:
        r = client.get(path, params=params)
        assert r.status_code in {200, 403, 503}, (path, r.status_code, r.text[:200])
        if r.status_code != 200:
            continue
        if "application/json" not in (r.headers.get("content-type") or ""):
            continue
        hits = rent_figure_paths(r.json())
        assert hits == [], f"{path} leaked rent figures: {hits}"


def test_modelled_agr_routes_are_internal_with_auth(monkeypatch):
    public = TestClient(_app(monkeypatch))
    assert public.get("/square", params={"lat": 55.86, "lng": -4.25}).status_code == 404
    assert public.get("/layers/councils-agr").status_code == 404
    assert public.get("/fiscal/summary").status_code == 404

    internal = TestClient(_app(monkeypatch, internal=True))
    assert internal.get(
        "/internal/agr/square",
        params={"lat": 55.86, "lng": -4.25},
    ).status_code == 401

    ok = internal.get(
        "/internal/agr/square",
        params={"lat": 55.86, "lng": -4.25},
        headers=_auth(),
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body.get("internal") is True
    assert body.get("publication_status") == "blocked"


def test_aggregate_gbp_routes_disabled_by_default(monkeypatch):
    client = TestClient(_app(monkeypatch, internal=True))
    for path in (
        "/internal/agr/fiscal/summary",
        "/internal/agr/layers/councils-agr",
        "/internal/agr/layers/councils",
    ):
        r = client.get(path, headers=_auth())
        assert r.status_code == 403, path
        detail = r.json()["detail"]
        assert detail["error"] == "aggregate_gbp_disabled"
        assert detail["publication_status"] == "blocked"
        assert detail["setting"] == "ENABLE_INTERNAL_AGR_AGGREGATE_GBP"


def test_health_is_status_and_version_only(monkeypatch):
    """HEALTH-TRIM / SW-037: public /health must not leak AGR/router/operator notes."""
    from api.main import ROUTER_STATUS

    app = _app(monkeypatch)
    assert ROUTER_STATUS["api.agr_routes"]["loaded"] is True
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"status", "version"}
    assert body["status"] == "ok"
    text = r.text
    for banned in (
        "ENABLE_INTERNAL_ENDPOINTS",
        "INTERNAL_API_TOKEN",
        "modelled AGR",
        "w3w-grid",
        "£",
        "public_rents",
        "agr_place_pages",
        "Wealth Engine",
        "publication_geometry",
    ):
        assert banned not in text, banned


def test_internal_yield_reads_surface_yaml_not_hardcoded():
    yp = yield_placeholder()
    y = internal_yield_from_surface()
    assert y["central"] == yp["central"]
    assert y["land_yield"] == yp["land_yield"]
    assert y["band"]["low"] == yp["land_yield_band"][0]
    assert y["band"]["high"] == yp["land_yield_band"][1]
    assert "surface.yaml" in y["yield_source"]
    assert y["status"] == "provisional_internal_pending"
    assert abs(y["central"] - 0.04499) < 1e-9
    assert y.get("result_hash") == "4654e513"


def test_gbp_range_never_single_number():
    band = gbp_range(100.0, low=80.0, high=120.0)
    assert band == {"low": 80.0, "central": 100.0, "high": 120.0}
    ycfg = {"central": 0.05, "land_yield_band": [0.04, 0.06]}
    expanded = gbp_range(100.0, yield_cfg=ycfg)
    assert expanded["central"] == 100.0
    assert expanded["low"] == 80.0
    assert expanded["high"] == 120.0


def test_internal_agr_place_requires_auth_and_vintage_2022(monkeypatch):
    client = TestClient(_app(monkeypatch, internal=True))
    assert client.get(
        "/internal/agr/place",
        params={"lat": 55.86, "lng": -4.25},
    ).status_code == 401

    bad_vin = client.get(
        "/internal/agr/place",
        params={"lat": 55.86, "lng": -4.25, "vintage": "2011", "zone_id": "S01008677"},
        headers=_auth(),
    )
    assert bad_vin.status_code == 422
    assert bad_vin.json()["detail"]["error"] == "vintage_required"


def test_internal_agr_place_is_wealth_engine_dz_blocked(monkeypatch):
    """Live DB optional: 200 asserts shape; 404/422/503 still prove guards."""
    client = TestClient(_app(monkeypatch, internal=True))
    # Prefer a 2022-range code when the store has UPRN-weighted rows.
    r = client.get(
        "/internal/agr/place",
        params={"lat": 55.86, "lng": -4.25, "zone_id": "S01014567", "vintage": "2022"},
        headers=_auth(),
    )
    assert r.status_code in {200, 404, 422, 503}
    if r.status_code != 200:
        detail = r.json().get("detail") or {}
        if isinstance(detail, dict) and detail.get("error"):
            assert detail["error"] in {
                "surface_row_not_found",
                "crosswalk_method_required",
                "vintage_required",
                "vintage_mismatch",
                "zone_id_out_of_range",
                "wealth_database_unavailable",
                "dz_boundaries_unavailable",
                "attribution_missing",
            }
        return

    body = r.json()
    assert body["internal"] is True
    assert body["unpublished"] is True
    assert body["publication_status"] == "blocked"
    assert body["unpublished_reason"] == UNPUBLISHED_REASON
    assert body["source"] == "wealth_engine"
    assert body["geometry_level"] == "zone"
    assert body["zone"]["vintage"] == 2022
    assert body["zone"]["crosswalk_method"] == "address_uprn"
    assert body["zone"].get("estimate_label") in {
        None,
        "measured",
        "partly_estimated",
        "fully_estimated",
    }
    if body["zone"].get("value_tier") is not None:
        assert body["zone"]["value_tier"] in {"market", "proxy", "shadow"}
    y = body["yield"]
    assert y["status"] == "provisional_internal_pending"
    assert "surface.yaml" in y["yield_source"]
    assert abs(y["central"] - 0.04499) < 1e-9
    assert y["band"]["low"] == pytest.approx(0.0398)
    assert y["band"]["high"] == pytest.approx(0.0450)
    assert body["label"] == "experimental"
    assert body["value_tier_tags"] == ["market", "proxy", "shadow"]
    # Every £ must be a range object, never a bare number on rent-like keys.
    for path in rent_figure_paths(body):
        # rent_figure_paths lists numeric leaves; ranges should not leave bare floats
        # under measured_rent_gbp etc. — walk wealth components.
        pass
    for comp in body["wealth"].get("components") or []:
        rent = comp.get("measured_rent_gbp")
        if rent is not None:
            assert isinstance(rent, dict)
            assert set(rent) >= {"low", "central", "high"}
            assert not isinstance(rent.get("central"), bool)
