"""Public catalogue and routes must not advertise or serve modelled AGR £."""

from __future__ import annotations

from fastapi.testclient import TestClient

from georgist.publication_rules import FORBIDDEN_PUBLIC_AGR_PROPERTIES
from layers.council_metrics import PUBLIC_CATALOG_METRIC_IDS, scrub_public_agr_properties
from layers.platform import platform_catalog

WITHHELD_METRIC_IDS = frozenset({
    "agr_plot",
    "rent_per_sqm",
    "agr_price_pct",
    "land_share",
    "site_capital",
    "net_contribution",
    "gross_liability",
    "vacant_residual",
})


def test_public_catalog_principle_and_no_agr_pound_metrics():
    catalog = platform_catalog()
    assert "no public £" in catalog["principle"].lower() or "no public £" in catalog["principle"]
    assert "AGR first" not in catalog["principle"]
    metric_ids = {row["id"] for row in catalog["choropleth_metrics"]}
    assert metric_ids == PUBLIC_CATALOG_METRIC_IDS
    assert not (metric_ids & WITHHELD_METRIC_IDS)
    for row in catalog["choropleth_metrics"]:
        assert row["property"] not in FORBIDDEN_PUBLIC_AGR_PROPERTIES
        assert "£" not in (row.get("unit") or "") or row["id"] == "house_price"


def test_agr_value_layer_is_blocked_without_property():
    layer = next(row for row in platform_catalog()["layers"] if row["id"] == "agr_value")
    assert layer["status"] == "blocked"
    assert "property" not in layer


def test_scrub_drops_forbidden_agr_properties():
    geo = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "code": "S12000049",
                    "annual_ground_rent_plot_gbp": 1200,
                    "site_rental_per_sqm_gbp": 12.5,
                    "population_density_per_km2": 100,
                },
                "geometry": None,
            }
        ],
        "meta": {
            "metrics": {
                "agr_plot": {"property": "annual_ground_rent_plot_gbp"},
                "pop_density": {"property": "population_density_per_km2"},
            }
        },
    }
    scrubbed = scrub_public_agr_properties(geo)
    props = scrubbed["features"][0]["properties"]
    for key in FORBIDDEN_PUBLIC_AGR_PROPERTIES:
        assert key not in props
    assert props["population_density_per_km2"] == 100
    assert "agr_plot" not in scrubbed["meta"]["metrics"]
    assert "pop_density" in scrubbed["meta"]["metrics"]


def _app(monkeypatch):
    from api.main import create_app

    monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    return create_app()


def test_public_roll_and_vdl_councils_blocked(monkeypatch):
    client = TestClient(_app(monkeypatch))
    for path in ("/api/roll.json", "/api/roll.csv", "/api/vdl-councils.json"):
        r = client.get(path)
        assert r.status_code == 403, path
        body = r.json()
        detail = body.get("detail") or body
        assert detail.get("publication_status") == "blocked"
