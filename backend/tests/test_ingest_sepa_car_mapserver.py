"""Unit tests for SEPA CAR MapServer → PostGIS ingest (no network required)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from etl.ingest_sepa_car import (
    BACKOFF_SECONDS,
    feature_to_row,
    get_with_retry,
    rows_from_features,
)


def test_feature_to_row_parses_point_and_tags_market():
    feat = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-4.25, 55.85]},
        "properties": {
            "authorisation_no": "CAR/S/1043284",
            "authorisation_holder": "MIDLOCK FARM",
            "authorisation_description": "Midlock Farm",
            "authorisation_status": "Granted",
            "authorisation_level": "CAR Simple Licence",
            "category": "Permit",
            "regulatory_area": "Water",
            "authorisation_activity": "Sheep Dip onto Land",
            "representative_ngr": "NS 95844 21321",
            "easting": 295844,
            "northing": 621321,
        },
    }
    row = feature_to_row(feat, "simple")
    assert row is not None
    assert row["authorisation_no"] == "CAR/S/1043284"
    assert row["car_layer"] == "simple"
    assert row["value_tier"] == "market"
    assert row["publication_status"] == "ok"
    assert row["lng"] == pytest.approx(-4.25)
    assert row["lat"] == pytest.approx(55.85)


def test_feature_to_row_skips_missing_auth_no():
    assert feature_to_row({"properties": {}, "geometry": None}, "simple") is None


def test_rows_from_features_keeps_layer_tag():
    features = [
        {
            "geometry": {"type": "Point", "coordinates": [-3.2, 56.1]},
            "properties": {
                "authorisation_no": "CAR/R/1",
                "authorisation_status": "Granted",
            },
        }
    ]
    rows = rows_from_features(features, "registration")
    assert len(rows) == 1
    assert rows[0]["car_layer"] == "registration"


def test_get_with_retry_succeeds_after_503(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("etl.ingest_sepa_car.time.sleep", sleeps.append)

    calls = {"n": 0}

    def fake_get(url, params=None):
        calls["n"] += 1
        request = httpx.Request("GET", url)
        if calls["n"] < 3:
            response = httpx.Response(503, request=request)
            return response
        return httpx.Response(200, request=request, json={"features": []})

    client = MagicMock()
    client.get.side_effect = fake_get
    response = get_with_retry(
        client,
        "https://map.sepa.org.uk/example/query",
        params={"f": "geojson"},
        max_retries=5,
        backoff=BACKOFF_SECONDS,
    )
    assert response.status_code == 200
    assert calls["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_get_with_retry_raises_after_exhaustion(monkeypatch):
    monkeypatch.setattr("etl.ingest_sepa_car.time.sleep", lambda *_a, **_k: None)

    def always_503(url, params=None):
        request = httpx.Request("GET", url)
        return httpx.Response(503, request=request)

    client = MagicMock()
    client.get.side_effect = always_503
    with pytest.raises(httpx.HTTPStatusError):
        get_with_retry(
            client,
            "https://map.sepa.org.uk/example/query",
            params={},
            max_retries=3,
            backoff=(0.01, 0.01, 0.01),
        )
