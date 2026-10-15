"""PostGIS-backed /layers/parcels: serves when loaded; honest empty viewport for fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

URL = os.getenv("WEALTH_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
pytestmark = pytest.mark.skipif(not URL, reason="WEALTH_TEST_DATABASE_URL not set")


@pytest.fixture(autouse=True)
def _parcels_public_on(monkeypatch):
    """PostGIS parcel suite needs the public flag (default is off)."""
    monkeypatch.setenv("PARCELS_PUBLIC", "true")

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "cadastral_index_polygons.geojson"
)

# Viewport covering the synthetic Glasgow fixture polygons
FIXTURE_BBOX = {
    "south": 55.8595,
    "west": -4.2610,
    "north": 55.8615,
    "east": -4.2570,
}

# Balfron (Stirling) — synthetic STG parcel in the CI fixture
BALFRON_BBOX = {
    "south": 56.0705,
    "west": -4.3400,
    "north": 56.0725,
    "east": -4.3375,
}

# Highlands — outside fixture scope
EMPTY_BBOX = {
    "south": 57.45,
    "west": -4.30,
    "north": 57.50,
    "east": -4.20,
}

CONFIRMED_ATTRIBUTION = (
    "© Crown copyright. Reproduced with the permission of Registers of Scotland. "
    "Contains OS data © Crown copyright and database right 2026."
)
OGL_V3_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)


@pytest.fixture
def parcels_loaded(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    from etl import ingest_inspire_parcels as ingest
    from layers import cadastral

    cadastral.parcel_source_meta.cache_clear()
    conn = ingest.connect()
    try:
        ingest.ensure_table(conn)
        count = ingest.load_geojson(FIXTURE, conn, replace=True)
        from etl.ingest_inspire_parcels import REPO_ROOT

        county_counts = ingest._county_counts_from_table(conn)
        ingest.write_load_meta(
            conn,
            count=count,
            vintage="2026-10-12",
            load_scope="fixture",
            licence="synthetic-test-only",
            source_url=str(FIXTURE.relative_to(REPO_ROOT)),
            input_path=FIXTURE,
            county_counts=county_counts,
        )
    finally:
        conn.close()
    assert cadastral.is_loaded()
    yield
    # leave rows for other tests in the same process; replace=True keeps them small


def test_parcels_bbox_200_when_fixture_loaded(client, parcels_loaded):
    r = client.get("/layers/parcels", params=FIXTURE_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) >= 1
    assert body["meta"]["ok"] is True
    assert body["meta"]["fixture_scoped"] is True
    assert body["meta"]["load_scope"] == "fixture"
    assert body["meta"]["licence"] == "synthetic-test-only"
    assert body["meta"]["attribution"] == CONFIRMED_ATTRIBUTION
    assert body["meta"]["harvest_year"] == 2026
    assert body["meta"]["county_counts"]["GLA"] == 2
    assert body["meta"]["county_counts"]["STG"] == 1
    assert any("fixture-scoped" in g.lower() for g in body["meta"]["gaps"])
    for feature in body["features"]:
        props = feature["properties"]
        assert props["inspire_id"].startswith("SYN-")
        assert props["fixture"] is True
        assert "owner" not in props
        assert "price" not in props
        assert "title" not in props
        assert "MOCK" not in r.text


def test_parcels_balfron_bbox_returns_features(client, parcels_loaded):
    r = client.get("/layers/parcels", params=BALFRON_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) >= 1
    assert any(
        "BALFRON" in str(f["properties"].get("inspire_id", "")).upper()
        or f["properties"].get("county") == "STG"
        for f in body["features"]
    )
    assert body["meta"]["attribution"] == CONFIRMED_ATTRIBUTION


def test_parcels_empty_viewport_is_200_not_503_when_fixture_loaded(
    client, parcels_loaded
):
    r = client.get("/layers/parcels", params=EMPTY_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []
    assert body["meta"]["ok"] is True
    assert body["meta"]["count"] == 0
    assert body["meta"]["fixture_scoped"] is True
    assert any("fixture-scoped" in g.lower() for g in body["meta"]["gaps"])


def test_catalog_boundaries_lists_ogl30_and_endpoint(client):
    r = client.get("/layers/catalog")
    assert r.status_code == 200, r.text
    layers = {layer["id"]: layer for layer in r.json()["layers"]}
    boundaries = layers["boundaries"]
    # PARCELS_PUBLIC=true in this module's fixture → catalog live.
    assert boundaries["status"] == "live"
    assert boundaries["endpoint"] == "/layers/parcels"
    assert boundaries["licence"] == (
        "Licensed under the Open Government Licence v3.0"
    )
    assert boundaries["licence_url"] == OGL_V3_URL
    assert boundaries["attribution"] == CONFIRMED_ATTRIBUTION
    assert "ros.gov.uk" in boundaries["source_url"]
    assert "inspire" not in (boundaries.get("licence_url") or "").lower() or (
        "nationalarchives.gov.uk" in boundaries["licence_url"]
    )
    # Never point at the 2017 OS INSPIRE end-user licence.
    assert "2017" not in (boundaries.get("licence_url") or "")
    assert "end-user" not in (boundaries.get("licence_url") or "").lower()
