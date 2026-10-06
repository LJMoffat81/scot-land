"""/geocode/postcode against a mocked postcodes.io (no network). Responses are SYNTHETIC."""

import httpx
import pytest
from fastapi.testclient import TestClient


def _client_with(monkeypatch, handler):
    from api import geocode_routes
    from api.main import create_app

    seen = []

    def wrapped(request):
        seen.append(str(request.url))
        return handler(request)

    monkeypatch.setattr(geocode_routes, "_client",
                        lambda: httpx.Client(transport=httpx.MockTransport(wrapped), timeout=geocode_routes.TIMEOUT_S))
    return TestClient(create_app()), seen


def _ok(country="Scotland", lat=55.861, lng=-4.25, postcode="G2 1DU"):
    return lambda request: httpx.Response(200, json={"status": 200, "result": {
        "postcode": postcode, "latitude": lat, "longitude": lng, "country": country}})


@pytest.mark.parametrize("q,expected", [("g21du", "G2 1DU"), (" G2  1DU ", "G2 1DU"), ("EH1 1YZ", "EH1 1YZ"),
                                        ("AB10 1AB", "AB10 1AB"), ("George Square", None), ("G2", None), ("", None)])
def test_normalise_postcode(q, expected):
    from api.geocode_routes import normalise_postcode

    assert normalise_postcode(q) == expected


def test_scottish_postcode_returns_point_only(monkeypatch):
    c, seen = _client_with(monkeypatch, _ok())
    r = c.get("/geocode/postcode", params={"q": "g2 1du"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["postcode"], body["lat"], body["lng"]) == ("G2 1DU", 55.861, -4.25)
    assert "Open Government Licence" in body["licence"] and "Royal Mail" in body["licence"]
    assert set(body) == {"postcode", "lat", "lng", "kind", "source", "licence"}  # no values, no address
    assert seen and seen[0].endswith("/G21DU")


def test_free_text_is_refused_without_calling_out(monkeypatch):
    c, seen = _client_with(monkeypatch, _ok())
    r = c.get("/geocode/postcode", params={"q": "George Square"})
    assert r.status_code == 422 and "postcodes only" in r.json()["detail"]
    assert seen == []


def test_unknown_postcode_is_404(monkeypatch):
    c, _ = _client_with(monkeypatch, lambda req: httpx.Response(404, json={"status": 404, "error": "Postcode not found"}))
    r = c.get("/geocode/postcode", params={"q": "G2 9ZZ"})
    assert r.status_code == 404 and "wasn't found" in r.json()["detail"]


def test_outside_scotland_is_422(monkeypatch):
    c, _ = _client_with(monkeypatch, _ok(country="England", lat=51.5, lng=-0.12, postcode="SW1A 1AA"))
    r = c.get("/geocode/postcode", params={"q": "SW1A 1AA"})
    assert r.status_code == 422 and "outside Scotland" in r.json()["detail"]


def test_no_coordinates_is_404_not_a_guess(monkeypatch):
    c, _ = _client_with(monkeypatch, _ok(lat=None, lng=None))
    r = c.get("/geocode/postcode", params={"q": "G2 1DU"})
    assert r.status_code == 404 and "no map location" in r.json()["detail"]


@pytest.mark.parametrize("handler", [
    lambda req: (_ for _ in ()).throw(httpx.ConnectTimeout("slow", request=req)),
    lambda req: httpx.Response(502, text="bad gateway"),
])
def test_geocoder_down_is_503(monkeypatch, handler):
    c, _ = _client_with(monkeypatch, handler)
    r = c.get("/geocode/postcode", params={"q": "G2 1DU"})
    assert r.status_code == 503 and "unavailable" in r.json()["detail"]
