"""Postcode search for the map: UK postcode -> centroid point, via postcodes.io (no key).

postcodes.io serves the ONS Postcode Directory (Office for National Statistics, OGL v3;
contains OS data (c) Crown copyright and database right; contains Royal Mail data (c) Royal
Mail copyright and database right). The site footer already carries those attributions.

Postcodes only: free-text place search needs a keyed geocoder (OS Names) and is not offered.
The route returns a point and nothing else: no value, no rent, no address. The map then runs
the same data-zone lookup as a click. Postcodes are not logged or stored.
Errors are honest: 422 not a postcode / outside Scotland, 404 unknown postcode, 503 geocoder
unreachable or slow (short timeout; never a guessed location).
"""

from __future__ import annotations

import re

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.common import _load_postcode_api_url

router = APIRouter()

TIMEOUT_S = 4.0
# Full UK postcode (outward + inward), spaces optional. Partial postcodes are not geocoded.
POSTCODE_RE = re.compile(r"^([A-Z]{1,2}[0-9][A-Z0-9]?)\s*([0-9][A-Z]{2})$")
SOURCE = "postcodes.io (ONS Postcode Directory)"
LICENCE = ("Source: Office for National Statistics licensed under the Open Government Licence v3.0; "
           "contains OS data (c) Crown copyright and database right; contains Royal Mail data "
           "(c) Royal Mail copyright and database right")
POSTCODES_ONLY = "Search finds full UK postcodes only (e.g. G2 1DU). Or click the map."


def normalise_postcode(q: str) -> str | None:
    m = POSTCODE_RE.match(re.sub(r"\s+", " ", (q or "").strip().upper()))
    return f"{m.group(1)} {m.group(2)}" if m else None


def _api_url() -> str:
    try:
        return _load_postcode_api_url()
    except Exception:  # config missing: the documented public endpoint
        return "https://api.postcodes.io/postcodes"


def _client() -> httpx.Client:  # seam for tests
    return httpx.Client(timeout=TIMEOUT_S, headers={"Accept": "application/json"})


def _error(status: int, error: str, message: str) -> HTTPException:
    # `detail` is a plain string so the frontend shows it as-is.
    return HTTPException(status_code=status, detail=message, headers={"X-Geocode-Error": error})


@router.get("/geocode/postcode")
def geocode_postcode(q: str = Query(..., max_length=16, description="Full UK postcode, e.g. G2 1DU")) -> JSONResponse:
    postcode = normalise_postcode(q)
    if postcode is None:
        raise _error(422, "not_a_postcode", POSTCODES_ONLY)
    url = f"{_api_url().rstrip('/')}/{postcode.replace(' ', '')}"
    try:
        with _client() as client:
            resp = client.get(url)
    except httpx.HTTPError:
        raise _error(503, "geocoder_unavailable", "Postcode search is unavailable right now. Click the map instead.") from None
    if resp.status_code == 404:
        raise _error(404, "postcode_not_found", f"Postcode {postcode} wasn't found. Check it, or click the map.")
    if resp.status_code != 200:
        raise _error(503, "geocoder_unavailable", "Postcode search is unavailable right now. Click the map instead.")
    try:
        result = resp.json()["result"]
        lat, lng = float(result["latitude"]), float(result["longitude"])
    except (ValueError, KeyError, TypeError):
        # Terminated or non-geographic postcodes come back without coordinates: no guess.
        raise _error(404, "postcode_not_found", f"Postcode {postcode} has no map location. Click the map instead.") from None
    if result.get("country") != "Scotland":
        raise _error(422, "outside_scotland", f"{postcode} is outside Scotland. Search a Scottish postcode or click the map.")
    return JSONResponse({"postcode": result.get("postcode") or postcode, "lat": lat, "lng": lng,
                         "kind": "postcode_centroid", "source": SOURCE, "licence": LICENCE},
                        headers={"Cache-Control": "public, max-age=86400"})
