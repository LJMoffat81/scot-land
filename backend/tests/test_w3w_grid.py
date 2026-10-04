"""Rate and size limits for the what3words grid endpoint."""

from fastapi.testclient import TestClient

import api.main as main

_SMALL = {"south": 55.950, "west": -3.195, "north": 55.952, "east": -3.193}


def _client() -> TestClient:
    main.reset_w3w_rate_limit()
    return TestClient(main.app)


def test_a_normal_grid_and_the_maps_cell_count_succeed():
    client = _client()
    response = client.get("/layers/w3w-grid", params={**_SMALL, "max_cells": 200})
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["meta"]["max_cells"] == 200
    assert 1 <= body["meta"]["cell_count"] <= 200


def test_a_burst_well_over_sixty_a_minute_is_refused(monkeypatch):
    monkeypatch.setattr(main, "_w3w_now", lambda: 1_000.0)
    client = _client()
    codes = [
        client.get("/layers/w3w-grid", params={**_SMALL, "max_cells": 10}).status_code
        for _ in range(70)
    ]
    assert codes[:20] == [200] * 20
    assert codes[20:] == [429] * 50


def test_an_oversized_area_is_refused():
    client = _client()
    response = client.get(
        "/layers/w3w-grid",
        params={"south": 54.5, "west": -8.0, "north": 60.5, "east": -1.0, "max_cells": 200},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Ask for a smaller area."


def test_too_many_cells_is_refused():
    client = _client()
    response = client.get("/layers/w3w-grid", params={**_SMALL, "max_cells": 1200})
    assert response.status_code == 400
    assert response.json()["detail"] == "Ask for fewer cells."
