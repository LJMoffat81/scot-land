"""GET /layers/context/data-zones/at: real (code, vintage) or an honest error. Never 'unknown'.

Boundaries here are SYNTHETIC squares in EPSG:27700 near Edinburgh; codes are
real-format but the shapes are not the real zones.
"""

import json

import pytest

from georgist import dz_lookup

# Edinburgh city centre, roughly (325_700, 673_900) in BNG.
LAT, LON = 55.9533, -3.1883


def _square(x0, y0, size):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + size, y0], [x0 + size, y0 + size],
                                                [x0, y0 + size], [x0, y0]]]}


def _write(tmp_path, name, features):
    fc = {"type": "FeatureCollection",
          "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::27700"}},
          "features": [{"type": "Feature", "properties": p, "geometry": g} for p, g in features]}
    (tmp_path / name).write_text(json.dumps(fc))


@pytest.fixture
def boundary_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dz_lookup, "PROCESSED_DIR", tmp_path)
    dz_lookup._file_cache.clear()
    dz_lookup._bng_to_wgs84 = None
    yield tmp_path
    dz_lookup._file_cache.clear()
    dz_lookup._bng_to_wgs84 = None


def test_503_when_no_db_and_no_file(client, boundary_dir):
    r = client.get("/layers/context/data-zones/at", params={"lat": LAT, "lon": LON})
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error"] == "dz_boundaries_unavailable"
    assert "db: not_configured" in detail["reasons"]
    assert "unknown" not in r.text


def test_file_fallback_returns_both_vintages(client, boundary_dir):
    _write(boundary_dir, "dz2011_boundaries.geojson",
           [({"DataZone": "S01008677", "Name": "Synthetic Old Town"}, _square(325_000, 673_000, 2_000))])
    _write(boundary_dir, "dz2022_boundaries.geojson",
           [({"dzcode": "S01016000", "dzname": "Synthetic 2022"}, _square(325_000, 673_000, 2_000))])
    r = client.get("/layers/context/data-zones/at", params={"lat": LAT, "lon": LON})
    assert r.status_code == 200, r.text
    body = r.json()
    # Default public grain is DZ2022 when both vintages hit.
    assert body["code"] == "S01016000" and body["vintage"] == 2022
    assert body["dz2011"]["name"] == "Synthetic Old Town"
    assert body["dz2022"]["code"] == "S01016000"
    assert body["vintages_loaded"] == [2011, 2022]
    assert body["source"].startswith("file:")


def test_lng_alias_and_dz2022_only(client, boundary_dir):
    _write(boundary_dir, "dz2022_boundaries.geojson",
           [({"code": "S01016000"}, _square(325_000, 673_000, 2_000))])
    r = client.get("/layers/context/data-zones/at", params={"lat": LAT, "lng": LON})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "S01016000" and body["vintage"] == 2022 and body["dz2011"] is None


def test_404_when_point_misses_every_zone(client, boundary_dir):
    _write(boundary_dir, "dz2011_boundaries.geojson",
           [({"code": "S01008677"}, _square(200_000, 600_000, 1_000))])
    r = client.get("/layers/context/data-zones/at", params={"lat": LAT, "lon": LON})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "no_data_zone_at_point"


def test_bad_or_wrong_vintage_codes_are_refused(client, boundary_dir):
    # 'unknown', a DZ2022 code in the DZ2011 file, and a non-Scottish code: all refused.
    sq = _square(325_000, 673_000, 2_000)
    _write(boundary_dir, "dz2011_boundaries.geojson",
           [({"code": "unknown"}, sq), ({"code": "S01016000"}, sq), ({"code": "E01000001"}, sq)])
    r = client.get("/layers/context/data-zones/at", params={"lat": LAT, "lon": LON})
    assert r.status_code == 404
    assert "unknown" not in json.dumps(r.json()["detail"]["vintages_checked"])


def test_on_boundary_flag(client, boundary_dir):
    # Two adjacent squares sharing the edge the point lies on.
    from pyproj import Transformer

    x, y = Transformer.from_crs(4326, 27700, always_xy=True).transform(LON, LAT)
    _write(boundary_dir, "dz2011_boundaries.geojson", [
        ({"code": "S01008677"}, _square(x - 1_000, y - 500, 1_000)),
        ({"code": "S01008678"}, _square(x, y - 500, 1_000)),
    ])
    body = client.get("/layers/context/data-zones/at", params={"lat": LAT, "lon": LON}).json()
    assert body["dz2011"]["on_boundary"] is True
    assert body["code"] in {"S01008677", "S01008678"}


@pytest.mark.parametrize("params,status", [
    ({"lat": 51.5, "lon": -0.12}, 400),          # London
    ({"lat": LAT}, 422),                        # no lon
    ({"lat": "abc", "lon": LON}, 422),
])
def test_input_validation(client, boundary_dir, params, status):
    assert client.get("/layers/context/data-zones/at", params=params).status_code == status


def test_by_code_point_is_inside_that_zone(client, boundary_dir):
    _write(boundary_dir, "dz2011_boundaries.geojson",
           [({"DataZone": "S01008677", "Name": "Synthetic Old Town"}, _square(325_000, 673_000, 2_000))])
    r = client.get("/layers/context/data-zones/by-code", params={"code": "s01008677"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "S01008677"
    assert body["name"] == "Synthetic Old Town"
    assert body["vintage"] == 2011
    bounds = body["bounds"]
    assert bounds["west"] < body["lng"] < bounds["east"]
    assert bounds["south"] < body["lat"] < bounds["north"]
    at = client.get("/layers/context/data-zones/at", params={"lat": body["lat"], "lng": body["lng"]})
    assert at.status_code == 200, at.text
    at_body = at.json()
    assert at_body["code"] == "S01008677"
    at_bounds = at_body["bounds"]
    assert at_bounds["west"] < body["lng"] < at_bounds["east"]
    assert at_bounds["south"] < body["lat"] < at_bounds["north"]
    assert "unknown" not in r.text


def test_point_file_reuses_bng_transformer(boundary_dir, monkeypatch):
    _write(boundary_dir, "dz2011_boundaries.geojson",
           [({"DataZone": "S01008677", "Name": "Synthetic Old Town"}, _square(325_000, 673_000, 2_000))])
    created: list[tuple[object, object]] = []
    real_from_crs = dz_lookup.Transformer.from_crs

    def spy(crs_from, crs_to, always_xy=False):
        created.append((crs_from, crs_to))
        return real_from_crs(crs_from, crs_to, always_xy=always_xy)

    monkeypatch.setattr(dz_lookup.Transformer, "from_crs", spy)
    dz_lookup._bng_to_wgs84 = None
    first = dz_lookup._point_file("S01008677", 2011)
    second = dz_lookup._point_file("S01008677", 2011)
    assert first == second
    assert first["code"] == "S01008677"
    assert created == [(27700, 4326)]


def test_by_code_404_when_boundaries_have_a_different_zone(client, boundary_dir):
    _write(boundary_dir, "dz2011_boundaries.geojson",
           [({"code": "S01008678", "name": "Other"}, _square(325_000, 673_000, 2_000))])
    r = client.get("/layers/context/data-zones/by-code", params={"code": "S01008677"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "data_zone_not_found"
    assert "unknown" not in r.text


def test_by_code_422_and_503(client, boundary_dir):
    bad = client.get("/layers/context/data-zones/by-code", params={"code": "EH1 1YZ"})
    assert bad.status_code == 422
    missing = client.get("/layers/context/data-zones/by-code", params={"code": "S01008677"})
    assert missing.status_code == 503
    assert missing.json()["detail"]["error"] == "dz_boundaries_unavailable"


def test_single_route_owner():
    from api.main import app, registered_routes

    owners = [r for r in registered_routes(app) if r[1] == "/layers/context/data-zones/at"]
    assert len(owners) == 1
    from pathlib import Path

    legacy = (Path(__file__).resolve().parents[2] / "api" / "agr_routes.py").read_text()
    assert '@router.get("/layers/context/data-zones/at")' not in legacy
