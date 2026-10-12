"""Contract: publication_status=blocked overrides publish_level=public_zone.

A synthetic surface-rent row may carry publish_level=public_zone and still be
part of a blocked run (publication_status=blocked). Public consumers must see
no figures for it:

- GET /layers/georgist/surface-rent (public layer)
- GET /georgist/wealth (per-zone lookup)

Synthetic fixtures only. Skips when the Wealth publication stack or a throwaway
PostGIS URL is absent (main today; stack lives on lead/wealth-api-boot).
"""

from __future__ import annotations

import os

import pytest

# Wealth publication helpers are not on main yet — do not greenwash a missing gate.
pytest.importorskip(
    "georgist.wealth_schema",
    reason=(
        "Wealth publication stack absent on this revision "
        "(blocked-vs-public_zone lives on lead/wealth-api-boot / PR #1)."
    ),
)

URL = os.getenv("WEALTH_TEST_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not URL, reason="WEALTH_TEST_DATABASE_URL not set")

ZONE = "S01008677"  # real-format 2011 code; the row is SYNTHETIC


@pytest.fixture
def pg(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    from etl.migrate_to_postgis import apply_schema
    from georgist import db

    conn = db.connect()
    with conn.cursor() as cur:
        # Drop alembic_version so apply_schema (alembic upgrade head) rebuilds
        # after CI already stamped head on this throwaway DB.
        cur.execute(
            "DROP TABLE IF EXISTS alembic_version, inspire_parcels, surface_rent_dz, "
            "resource_wealth, eco_wealth, planning_sites, dz_spine, dz_boundaries, "
            "dz_denominators, dz_dwelling_counts, dz_population_counts CASCADE"
        )
        cur.execute("DROP SCHEMA IF EXISTS processed CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS processed_internal CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS datazones CASCADE")
    conn.commit()
    apply_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def surface_row(make_valuation_row):
    from georgist.wealth_schema import to_db_row

    def _make(zone=ZONE, **over):
        row = to_db_row(make_valuation_row(250_000, code=zone, infra_share=200_000.0))
        row.update(over)
        return row

    return _make


def test_blocked_overrides_public_zone_no_figures_on_layer_or_zone_lookup(
    pg, client, surface_row
):
    """Blocked run + publish_level=public_zone → no figures on layer or zone lookup."""
    from etl.migrate_to_postgis import upsert_surface_rent

    # Explicit public_zone licence level inside a blocked run — block must win.
    blocked = surface_row(
        publish_level="public_zone",
        publication_status="blocked",
    )
    assert blocked["publish_level"] == "public_zone"
    assert blocked["publication_status"] == "blocked"
    rent_token = f"{blocked['measured_rent']:.0f}"
    assert upsert_surface_rent(pg, [blocked]) == 1

    layer = client.get("/layers/georgist/surface-rent")
    # Nothing publishable: withhold rather than serve the public_zone figures.
    assert layer.status_code == 503, layer.text
    detail = layer.json().get("detail") or {}
    assert detail.get("error") == "surface_rent_not_built"
    assert detail.get("withheld_by_reason", {}).get("blocked") == 1
    assert ZONE not in (layer.json().get("data") or {})
    assert rent_token not in layer.text

    wealth = client.get(
        "/georgist/wealth",
        params={"lat": 55.95, "lng": -3.19, "zone_id": ZONE},
    )
    assert wealth.status_code == 200, wealth.text
    body = wealth.json()["wealth"]
    component = body["components"][0]
    assert component["publish_level"] == "public_zone"
    assert component["publication_status"] == "blocked"
    assert component["excluded_reason"] == "blocked"
    assert component.get("withheld") is True
    assert component["measured_rent_gbp"] is None
    assert component.get("uncertainty_low") is None
    assert component.get("uncertainty_high") is None
    assert body["totals_by_tier"] == {}
    assert rent_token not in wealth.text
