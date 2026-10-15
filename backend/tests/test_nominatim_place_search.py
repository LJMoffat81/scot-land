"""SHARE-FIX Nominatim: cache, 1/s throttle, 429 backoff → 503 (not 502)."""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from spatial import address as address_mod
from spatial.address import (
    NominatimUnavailable,
    USER_AGENT,
    clear_nominatim_cache,
    nominatim_places,
    search_place,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_nominatim_cache()
    # Reset rate limiter so tests do not wait on prior calls.
    address_mod._last_call_monotonic = 0.0
    yield
    clear_nominatim_cache()
    address_mod._last_call_monotonic = 0.0


def test_user_agent_identifies_scot_land_with_contact():
    assert "scot-land" in USER_AGENT.lower()
    assert "scot-land.scot" in USER_AGENT
    assert "contact:" in USER_AGENT.lower() or "@" in USER_AGENT


def test_common_scottish_place_bypasses_nominatim(monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError("Nominatim must not be called for common places")

    monkeypatch.setattr(address_mod, "nominatim_places", _boom)
    out = search_place("Glasgow")
    assert out["kind"] == "point"
    assert out["lat"] == pytest.approx(55.8642)
    assert out["lng"] == pytest.approx(-4.2518)
    assert "Glasgow" in out["label"]


def _patch_client(monkeypatch, transport: httpx.MockTransport) -> None:
    real_client = httpx.Client

    def factory(**kwargs):
        return real_client(transport=transport, timeout=5.0)

    monkeypatch.setattr(address_mod.httpx, "Client", factory)


def test_nominatim_places_caches_second_call(monkeypatch):
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(
            200,
            json=[
                {
                    "lat": "55.95",
                    "lon": "-3.19",
                    "display_name": "Leith, Edinburgh, Scotland, UK",
                    "address": {
                        "state": "Scotland",
                        "ISO3166-2-lvl4": "GB-SCT",
                    },
                }
            ],
        )

    _patch_client(monkeypatch, httpx.MockTransport(handler))
    # Skip real 1s throttle in this unit test.
    monkeypatch.setattr(address_mod, "_wait_for_rate_slot", lambda: None)

    first = nominatim_places("Leith")
    second = nominatim_places("Leith")
    assert first == second
    assert len(calls) == 1


def test_429_retries_honour_retry_after_then_succeeds(monkeypatch):
    attempts: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(429, headers={"Retry-After": "0.01"}, text="slow down")
        return httpx.Response(
            200,
            json=[
                {
                    "lat": "56.12",
                    "lon": "-3.94",
                    "display_name": "Stirling, Scotland, UK",
                    "address": {
                        "state": "Scotland",
                        "ISO3166-2-lvl4": "GB-SCT",
                    },
                }
            ],
        )

    _patch_client(monkeypatch, httpx.MockTransport(handler))
    monkeypatch.setattr(address_mod, "_wait_for_rate_slot", lambda: None)
    monkeypatch.setattr(address_mod.time, "sleep", lambda s: sleeps.append(s))

    rows = nominatim_places("Stirling High Street")
    assert len(rows) == 1
    assert len(attempts) == 3
    assert any(s >= 0.01 for s in sleeps)


def test_429_exhausted_raises_nominatim_unavailable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0"}, text="nope")

    _patch_client(monkeypatch, httpx.MockTransport(handler))
    monkeypatch.setattr(address_mod, "_wait_for_rate_slot", lambda: None)
    monkeypatch.setattr(address_mod.time, "sleep", lambda _s: None)

    with pytest.raises(NominatimUnavailable):
        nominatim_places("Somewhere obscure")

def test_place_route_maps_nominatim_unavailable_to_503(client, monkeypatch):
    def _boom(_q: str, **_k: Any):
        raise NominatimUnavailable("Place search is busy. Try again in a moment.")

    monkeypatch.setattr("api.agr_routes.search_place", _boom)
    r = client.get("/place", params={"q": "Some street in Fife"})
    assert r.status_code == 503, r.text
    assert r.status_code != 502
    detail = r.json().get("detail", "")
    assert "Try again" in detail or "busy" in detail.lower()


def test_rate_slot_enforces_one_second_gap(monkeypatch):
    stamps: list[float] = []
    real_monotonic = time.monotonic
    # Deterministic clock starting at 100.
    clock = {"t": 100.0}

    def fake_monotonic() -> float:
        return clock["t"]

    def fake_sleep(seconds: float) -> None:
        clock["t"] += seconds
        stamps.append(seconds)

    monkeypatch.setattr(address_mod.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(address_mod.time, "sleep", fake_sleep)
    address_mod._last_call_monotonic = 0.0

    address_mod._wait_for_rate_slot()
    first_at = clock["t"]
    address_mod._wait_for_rate_slot()
    # Second call must wait ~1s from the first.
    assert clock["t"] - first_at >= 0.99
    assert stamps and stamps[-1] >= 0.99
    # Silence unused.
    assert real_monotonic
