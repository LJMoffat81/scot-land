"""SEPA-FLOOD-1: Data Zone shares from medium-likelihood Flood Maps v3.0."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.platform_routes import router
from etl.ingest_sepa_frm_v3 import (
    LicenceError,
    RejectedFloodSource,
    aggregate_directory,
)
from georgist.publication_rules import PUBLIC_ROUTE_RULES
from layers.flood_dz import PROPERTY_KEYS

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sepa_frm_v3"
GLASGOW = "-4.30,55.84,-4.22,55.88"
DZ_SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [
            [-4.26, 55.85],
            [-4.24, 55.85],
            [-4.24, 55.87],
            [-4.26, 55.87],
            [-4.26, 55.85],
        ]
    ],
}


def test_half_coverage_fixture_is_50_and_0():
    rows = aggregate_directory(FIXTURES / "half")
    by_zone = {row["data_zone"]: row for row in rows}
    assert set(by_zone) == {"S01013482", "S01013483"}
    covered = by_zone["S01013482"]
    other = by_zone["S01013483"]
    assert covered["pct_area_river"] == 50
    assert other["pct_area_river"] == 0
    assert covered["pct_area_coastal"] == 0
    assert covered["pct_area_surface"] == 0
    assert other["pct_area_coastal"] == 0
    assert other["pct_area_surface"] == 0
    assert covered["source_version"] == "v3.0"
    for row in rows:
        assert set(row) == set(PROPERTY_KEYS)
        for key in ("pct_area_river", "pct_area_coastal", "pct_area_surface"):
            assert 0 <= row[key] <= 100


def test_climate_change_file_is_rejected():
    with pytest.raises(RejectedFloodSource):
        aggregate_directory(FIXTURES / "reject_cc")


def test_high_likelihood_file_is_rejected():
    with pytest.raises(RejectedFloodSource):
        aggregate_directory(FIXTURES / "reject_high")


def test_non_ogl_licence_aborts():
    with pytest.raises(LicenceError):
        aggregate_directory(FIXTURES / "bad_licence")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_flood_dz_whitelist_and_zone_geometry(monkeypatch):
    monkeypatch.setattr("layers.flood_dz.is_loaded", lambda: True)

    def _rows(west, south, east, north):
        return [
            {
                "data_zone": "S01014567",
                "pct_area_river": 50,
                "pct_area_coastal": 0,
                "pct_area_surface": 100,
                "source_version": "v3.0",
                "geometry": DZ_SQUARE,
                "flood_geom": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                },
            }
        ]

    monkeypatch.setattr("layers.flood_dz.fetch_rows", _rows)
    response = _client().get(f"/layers/open/flood-dz?bbox={GLASGOW}&kind=river")
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["loaded"] is True
    assert len(body["features"]) == 1
    feature = body["features"][0]
    assert set(feature["properties"]) == set(PROPERTY_KEYS)
    assert "flood_geom" not in feature["properties"]
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["geometry"] == DZ_SQUARE
    for key in ("pct_area_river", "pct_area_coastal", "pct_area_surface"):
        assert isinstance(feature["properties"][key], int)
        assert 0 <= feature["properties"][key] <= 100
    assert "£" not in response.text


def test_flood_dz_empty_table_is_503(monkeypatch):
    monkeypatch.setattr("layers.flood_dz.is_loaded", lambda: False)
    response = _client().get(f"/layers/open/flood-dz?bbox={GLASGOW}&kind=surface")
    assert response.status_code == 503
    assert response.json()["detail"] == "SEPA flood Data Zone table is not loaded yet."


def test_flood_dz_route_is_zone_level():
    rule = PUBLIC_ROUTE_RULES["/layers/open/flood-dz"]
    assert rule.geometry_level == "zone"
    assert rule.value_basis == "none"
