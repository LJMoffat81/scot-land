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
    yield tmp_path
    dz_lookup._file_cache.clear()


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


def test_miss_returns_empty_zone(client, boundary_dir):
    _write(boundary_dir, "dz2011_boundaries.geojson",
           [({"code": "S01008677"}, _square(200_000, 600_000, 1_000))])
    r = client.get("/layers/context/data-zones/at", params={"lat": LAT, "lon": LON})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] is None and body["name"] is None and body["vintage"] is None
    assert body["zones"] == [] and body["dz2011"] is None and body["dz2022"] is None
    assert body["vintages_loaded"] == [2011]
    assert "unknown" not in r.text


# Atlantic, inside the Scotland bounding box, outside every land zone.
SEA_LAT, SEA_LON = 58.42, -6.05


def test_sea_point_returns_200_empty_zone(client, boundary_dir):
    _write(boundary_dir, "dz2022_boundaries.geojson",
           [({"code": "S01016000", "name": "Synthetic inland"}, _square(325_000, 673_000, 2_000))])
    r = client.get("/layers/context/data-zones/at", params={"lat": SEA_LAT, "lon": SEA_LON})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lat"] == SEA_LAT and body["lon"] == SEA_LON
    assert body["code"] is None and body["name"] is None and body["vintage"] is None
    assert body["zones"] == [] and body["dz2011"] is None and body["dz2022"] is None
    assert body["vintages_loaded"] == [2022]
    assert "unknown" not in r.text


def test_inland_point_returns_its_zone(client, boundary_dir):
    _write(boundary_dir, "dz2011_boundaries.geojson",
           [({"DataZone": "S01008677", "Name": "Synthetic Old Town"}, _square(325_000, 673_000, 2_000))])
    r = client.get("/layers/context/data-zones/at", params={"lat": LAT, "lon": LON})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "S01008677" and body["vintage"] == 2011
    assert body["name"] == "Synthetic Old Town"
    assert body["dz2011"]["code"] == "S01008677"


def test_bad_or_wrong_vintage_codes_are_refused(client, boundary_dir):
    # 'unknown', a DZ2022 code in the DZ2011 file, and a non-Scottish code: all refused.
    sq = _square(325_000, 673_000, 2_000)
    _write(boundary_dir, "dz2011_boundaries.geojson",
           [({"code": "unknown"}, sq), ({"code": "S01016000"}, sq), ({"code": "E01000001"}, sq)])
    r = client.get("/layers/context/data-zones/at", params={"lat": LAT, "lon": LON})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["zones"] == [] and body["code"] is None
    assert body["vintages_loaded"] == [2011]
    assert "unknown" not in json.dumps(body)


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
    ({"lat": 91, "lon": LON}, 422),             # invalid latitude
    ({"lat": -91, "lon": LON}, 422),
])
def test_input_validation(client, boundary_dir, params, status):
    assert client.get("/layers/context/data-zones/at", params=params).status_code == status


def test_single_route_owner():
    from api.main import app, registered_routes

    owners = [r for r in registered_routes(app) if r[1] == "/layers/context/data-zones/at"]
    assert len(owners) == 1
    from pathlib import Path

    legacy = (Path(__file__).resolve().parents[2] / "api" / "agr_routes.py").read_text()
    assert '@router.get("/layers/context/data-zones/at")' not in legacy
