"""zone_id must be a real data zone code; 'unknown' is refused before any DB work."""

import pytest
from fastapi import HTTPException

from api.wealth_routes import parse_vintage, resolve_zone

EDINBURGH = {"lat": 55.95, "lng": -3.19}


@pytest.mark.parametrize("bad", ["unknown", "", "S0100", "S02001234", "X01008677", "S01008677x", "null"])
def test_bad_zone_id_is_422(client, bad):
    r = client.get("/georgist/wealth", params={**EDINBURGH, "zone_id": bad})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "invalid_zone_id"


def test_missing_zone_id_is_422(client):
    assert client.get("/georgist/wealth", params=EDINBURGH).status_code == 422


@pytest.mark.parametrize("code", ["S01000001", "S01006505", "S01020874", "S01999901"])
def test_out_of_range_code_is_422(client, code):
    r = client.get("/georgist/wealth", params={**EDINBURGH, "zone_id": code})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "zone_id_out_of_range"


def test_vintage_mismatch_is_422(client):
    r = client.get("/georgist/wealth", params={**EDINBURGH, "zone_id": "S01008677", "vintage": "2022"})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "vintage_mismatch"


@pytest.mark.parametrize("bad", ["DZ2011", "dz2022", "2011.0", "11", ""])
def test_text_vintage_is_rejected_loudly_not_mapped(client, bad):
    """Integer vintage standard: 'DZ2011' is a 422 invalid_vintage, never treated as 2011.
    The internal routes use the same parse_vintage."""
    r = client.get("/georgist/wealth", params={**EDINBURGH, "zone_id": "S01008677", "vintage": bad})
    assert r.status_code == 422 and r.json()["detail"]["error"] == "invalid_vintage"
    assert "2011 or 2022" in r.json()["detail"]["message"]
    with pytest.raises(HTTPException) as exc:
        parse_vintage(bad)
    assert exc.value.status_code == 422


def test_layer_rejects_text_vintage(client):
    r = client.get("/layers/georgist/surface-rent", params={"vintage": "DZ2011"})
    assert r.status_code == 422 and r.json()["detail"]["error"] == "invalid_vintage"


def test_integer_vintage_accepted_and_returned_as_integer():
    assert resolve_zone("S01008677", parse_vintage("2011")) == ("S01008677", 2011, "explicit")


def test_validation_runs_before_db():
    """With no DB, a bad zone is still 422 (not 503): nothing is computed for 'unknown'."""
    with pytest.raises(HTTPException) as exc:
        resolve_zone("unknown", None)
    assert exc.value.status_code == 422


@pytest.mark.parametrize(
    "code,vintage",
    [("S01006506", 2011), ("S01013481", 2011), ("S01013482", 2022), ("S01020873", 2022)],
)
def test_vintage_inferred_from_code_range(code, vintage):
    assert resolve_zone(code, None) == (code, vintage, "inferred_from_code")


def test_lower_case_and_whitespace_normalised():
    assert resolve_zone(" s01008677 ", 2011)[0:2] == ("S01008677", 2011)


def test_outside_scotland_is_400(client):
    r = client.get("/georgist/wealth", params={"lat": 51.5, "lng": -0.12, "zone_id": "S01008677"})
    assert r.status_code == 400
