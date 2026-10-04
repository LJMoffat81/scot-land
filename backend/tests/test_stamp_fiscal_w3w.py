"""Stamp on the fiscal summary and the what3words grid. Figures stay put."""

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

import api.main as main
from agr.fiscal import fiscal_summary
from agr.scenarios import resolve_active_scenario
from layers.grid_layer import build_w3w_agr_grid

_spec = importlib.util.spec_from_file_location(
    "test_engine_layers",
    Path(__file__).with_name("test_engine_layers.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_assert_stamp = _mod._assert_stamp

_SMALL = {"south": 55.950, "west": -3.195, "north": 55.952, "east": -3.193}


def test_fiscal_summary_carries_the_health_stamp():
    client = TestClient(main.app)
    health = client.get("/health")
    assert health.status_code == 200
    response = client.get("/fiscal/summary")
    assert response.status_code == 200
    body = response.json()
    stamp = body.pop("stamp")
    assert stamp == health.json()["stamp"]
    _assert_stamp(stamp)
    expected = fiscal_summary(
        resolve_active_scenario("replace_full_basket"),
        dividend_enabled=True,
        remote_credit_enabled=True,
    )
    assert body == expected


def test_a_bad_fiscal_scenario_is_not_stamped():
    client = TestClient(main.app)
    response = client.get("/fiscal/summary", params={"scenario": "not_a_scenario"})
    assert response.status_code == 400
    assert "stamp" not in response.json()


def test_w3w_grid_carries_the_health_stamp():
    main.reset_w3w_rate_limit()
    client = TestClient(main.app)
    health = client.get("/health")
    assert health.status_code == 200
    params = {**_SMALL, "max_cells": 200}
    response = client.get("/layers/w3w-grid", params=params)
    assert response.status_code == 200
    body = response.json()
    stamp = body.pop("stamp")
    assert stamp == health.json()["stamp"]
    _assert_stamp(stamp)
    assert body["type"] == "FeatureCollection"
    expected = build_w3w_agr_grid(
        _SMALL["south"],
        _SMALL["west"],
        _SMALL["north"],
        _SMALL["east"],
        max_cells=200,
    )
    assert body == expected


def test_a_bad_w3w_bbox_is_not_stamped():
    main.reset_w3w_rate_limit()
    client = TestClient(main.app)
    inverted = client.get(
        "/layers/w3w-grid",
        params={"south": 55.952, "west": -3.195, "north": 55.950, "east": -3.193, "max_cells": 200},
    )
    assert inverted.status_code == 400
    assert "stamp" not in inverted.json()
    oversized = client.get(
        "/layers/w3w-grid",
        params={"south": 54.5, "west": -8.0, "north": 60.5, "east": -1.0, "max_cells": 200},
    )
    assert oversized.status_code == 400
    assert "stamp" not in oversized.json()


def test_a_w3w_burst_that_is_refused_has_no_stamp(monkeypatch):
    monkeypatch.setattr(main, "_w3w_now", lambda: 1_000.0)
    main.reset_w3w_rate_limit()
    client = TestClient(main.app)
    responses = [
        client.get("/layers/w3w-grid", params={**_SMALL, "max_cells": 10})
        for _ in range(21)
    ]
    refused = responses[20]
    assert refused.status_code == 429
    assert "stamp" not in refused.json()
