"""Public catalogue and routes must not advertise or serve modelled AGR £."""

from __future__ import annotations

import re
from typing import Any

from fastapi.testclient import TestClient

from georgist.publication_rules import (
    FORBIDDEN_PUBLIC_AGR_PROPERTIES,
    EXEMPT_PATHS,
    is_public_path,
)
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


CHARTER_PRINCIPLE = (
    "Annual Ground Rent for every place in Scotland; every figure labelled "
    "Market, Modelled, or Estimate; figures not published yet"
)


def test_public_catalog_principle_and_no_agr_pound_metrics():
    catalog = platform_catalog()
    assert catalog["principle"] == CHARTER_PRINCIPLE
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
                    "siteRentalPerSqmGbp": 12.5,
                    "vacantFullAgrGbp": 999,
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


def _collect_forbidden_keys(obj: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str) and key in FORBIDDEN_PUBLIC_AGR_PROPERTIES:
                found.add(key)
            found |= _collect_forbidden_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            found |= _collect_forbidden_keys(item)
    return found


def _fill_path_template(path: str) -> str:
    """Substitute path params so every public GET can be called once."""
    filled = path
    filled = filled.replace("{postcode}", "G21DU")
    filled = filled.replace("{layer_id}", "flood")
    filled = filled.replace("{z}", "6")
    filled = filled.replace("{x}", "30")
    filled = filled.replace("{y}", "18")
    # Any remaining {param} → a neutral token (route should 4xx, still scanned).
    return re.sub(r"\{[^}/]+\}", "x", filled)


# Query bag large enough for bbox / place / geocode routes; unused keys are ignored.
_PUBLIC_PROBE_PARAMS = {
    "south": 55.8,
    "west": -4.35,
    "north": 55.9,
    "east": -4.2,
    "lat": 55.86,
    "lng": -4.25,
    "lon": -4.25,
    "pc": "G2 1DU",
    "postcode": "G2 1DU",
    "max_features": 5,
    "vintage": 2011,
    "zone": "S01008680",
    "zone_id": "S01008680",
}


def test_every_public_route_output_has_no_forbidden_agr_keys(monkeypatch):
    """Walk every mounted public GET; JSON bodies must not carry forbidden AGR £ keys."""
    from api.main import registered_routes

    app = _app(monkeypatch)
    client = TestClient(app)
    public_gets = sorted({
        path for method, path in registered_routes(app)
        if method == "GET" and is_public_path(path) and path not in EXEMPT_PATHS
    })
    assert public_gets, "expected mounted public GET routes"

    violations: list[str] = []
    for template in public_gets:
        url = _fill_path_template(template)
        response = client.get(url, params=_PUBLIC_PROBE_PARAMS)
        content_type = (response.headers.get("content-type") or "").lower()
        if "json" not in content_type:
            continue
        try:
            body = response.json()
        except ValueError:
            continue
        bad = _collect_forbidden_keys(body)
        if bad:
            violations.append(f"{template} -> {url} keys={sorted(bad)}")

    assert not violations, "forbidden AGR £ keys on public routes:\n" + "\n".join(violations)
