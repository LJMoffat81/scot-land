from unittest.mock import patch

import httpx

from layers.platform import _probe_outline, place_context, platform_catalog, scotlis_links
from spatial.parcels import CadastralParcel

NO_OUTLINE_LABEL = "Not yet on the Land Register"
NO_OUTLINE_NOTE = (
    "We found no Land Register boundary at this point. Its title may still be in the "
    "older Sasine register, or the land may not be registered at all. We estimate it "
    "by area and land type, and show no boundaries, titles or owners."
)
SASINE_GAP_NOTE = "Private names and Sasine extents stay on ScotLIS / paid products."
EDINBURGH = (55.9533, -3.1883)


def test_platform_catalog_has_brief_layers():
    cat = platform_catalog()
    ids = {layer["id"] for layer in cat["layers"]}
    assert cat["version"] == 2
    assert cat["brief"] == "docs/PLATFORM.md"
    assert "agr_value" in ids
    assert "vdl" in ids
    assert "la_holdings" in ids
    assert "common_good" in ids
    assert cat["data_policy"]["portal_scraping"] is False
    assert cat["data_policy"]["gaps_visible"] is True
    statuses = {layer["id"]: layer["status"] for layer in cat["layers"]}
    assert statuses["vdl"] == "live"
    assert statuses["public_crown"] == "live"
    assert statuses["la_holdings"] == "gap"
    assert statuses["planning"] == "linked"
    assert statuses["common_good"] == "linked"
    public = next(layer for layer in cat["layers"] if layer["id"] == "public_crown")
    assert public["endpoint"] == "/layers/open/public-land"


def test_scotlis_links_point_to_official_service():
    links = scotlis_links(55.9533, -3.1883, postcode="EH1 1YZ")
    assert "scotlis.ros.gov.uk" in links["public_home"]
    assert "ros.gov.uk" in links["about"]
    assert links["search_hint"] == "EH1 1YZ"
    assert "title" in links["note"].lower()


@patch("layers.platform.vdl_at_point")
@patch("layers.platform.public_land_at_point")
def test_place_context_exposes_gaps(mock_public, mock_vdl):
    mock_vdl.return_value = {"ok": True, "intersects": False, "sites": []}
    mock_public.return_value = {"ok": True, "intersects": False, "holdings": []}
    card = place_context(55.9533, -3.1883, postcode="EH1 1YZ")
    assert "vacant_or_derelict" in card
    assert card["public_or_crown"]["status"] == "live"
    assert card["public_or_crown"]["on_this_point"] is False
    assert card["local_authority_holding"]["status"] == "gap"
    assert card["common_good"]["status"] == "gap"
    assert card["private_or_sasine"]["status"] == "gap"
    assert card["private_or_sasine"]["note"] == SASINE_GAP_NOTE
    assert "scotlis.ros.gov.uk" in card["scotlis"]["public_home"]
    assert card["filters"]["public_private"] == "unknown"


@patch("layers.platform.vdl_at_point")
@patch("layers.platform.public_land_at_point")
def test_place_context_flags_public_holding(mock_public, mock_vdl):
    mock_vdl.return_value = {"ok": True, "intersects": False, "sites": []}
    mock_public.return_value = {
        "ok": True,
        "intersects": True,
        "holdings": [
            {
                "organisation": "Scottish Crown Estate",
                "site_name": "Glenlivet",
                "area_ha": 23094.7,
            }
        ],
        "note": "Five national bodies only.",
        "source": "SG 2024",
    }
    card = place_context(57.25, -3.35)
    assert card["public_or_crown"]["on_this_point"] is True
    assert card["public_or_crown"]["holdings"][0]["site_name"] == "Glenlivet"
    assert "public_or_crown" in card["flags"]
    assert card["filters"]["public_private"] == "public"


def _quiet(mock_public, mock_vdl) -> None:
    mock_vdl.return_value = {"ok": True, "intersects": False, "sites": []}
    mock_public.return_value = {"ok": True, "intersects": False, "holdings": []}


def _parcel() -> CadastralParcel:
    return CadastralParcel(
        inspire_id="inspire-secret",
        label="SCT0007431917",
        national_reference="SCT0007431917",
        area_sqm=760.0,
        county="GLC",
        geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
    )


def _assert_status_only(field: dict) -> None:
    assert set(field) <= {"status", "note"}
    blob = str(field)
    assert "inspire-secret" not in blob
    assert "SCT0007431917" not in blob
    assert "geometry" not in field
    assert "Polygon" not in blob
    assert "owner" not in field
    assert "price" not in field


@patch("layers.platform._probe_outline")
@patch("layers.platform.lookup_parcel")
@patch("layers.platform.lookup_parcel_geojson", return_value=None)
@patch("layers.platform.vdl_at_point")
@patch("layers.platform.public_land_at_point")
def test_outline_inside_when_the_lookup_returns_a_parcel(
    mock_public, mock_vdl, _geojson, mock_lookup, mock_probe
):
    _quiet(mock_public, mock_vdl)
    mock_lookup.return_value = _parcel()
    card = place_context(*EDINBURGH)
    field = card["land_register_outline"]
    assert field == {"status": "inside_outline"}
    _assert_status_only(field)
    assert NO_OUTLINE_LABEL not in str(field)
    assert NO_OUTLINE_NOTE not in str(field)
    assert card["private_or_sasine"]["note"] == SASINE_GAP_NOTE
    mock_probe.assert_not_called()


@patch("layers.platform._probe_outline")
@patch("layers.platform.lookup_parcel", return_value=None)
@patch("layers.platform.lookup_parcel_geojson", return_value=None)
@patch("layers.platform.vdl_at_point")
@patch("layers.platform.public_land_at_point")
def test_outline_empty_answer_is_no_outline(
    mock_public, mock_vdl, _geojson, _lookup, mock_probe
):
    _quiet(mock_public, mock_vdl)
    card = place_context(
        *EDINBURGH,
        parcel={
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": []},
            "properties": {"inspire_id": "inspire-secret", "label": "SCT0007431917"},
        },
    )
    field = card["land_register_outline"]
    assert field == {"status": "no_outline", "note": NO_OUTLINE_NOTE}
    _assert_status_only(field)
    assert "inspire-secret" not in str(field)
    mock_probe.assert_not_called()


@patch("layers.platform._probe_outline")
@patch("layers.platform.lookup_parcel")
@patch("layers.platform.lookup_parcel_geojson", return_value=None)
@patch("layers.platform.vdl_at_point")
@patch("layers.platform.public_land_at_point")
def test_outline_http_error_or_timeout_is_unknown_without_the_card_line(
    mock_public, mock_vdl, _geojson, mock_lookup, mock_probe
):
    _quiet(mock_public, mock_vdl)
    for error in (httpx.ConnectError("refused"), httpx.ReadTimeout("timed out")):
        mock_lookup.side_effect = error
        card = place_context(*EDINBURGH)
        field = card["land_register_outline"]
        assert field == {"status": "unknown"}
        assert field["status"] != "no_outline"
        _assert_status_only(field)
        assert NO_OUTLINE_LABEL not in str(field)
        assert NO_OUTLINE_NOTE not in str(field)
    mock_probe.assert_not_called()


@patch("layers.platform._probe_outline", return_value="error")
@patch("spatial.parcels._feature_at", return_value=None)
@patch("layers.platform.lookup_parcel_geojson", return_value=None)
@patch("layers.platform.vdl_at_point")
@patch("layers.platform.public_land_at_point")
def test_outline_swallowed_lookup_failure_is_unknown(
    mock_public, mock_vdl, _geojson, _feature, mock_probe
):
    _quiet(mock_public, mock_vdl)
    card = place_context(*EDINBURGH)
    assert card["land_register_outline"] == {"status": "unknown"}
    assert NO_OUTLINE_LABEL not in str(card["land_register_outline"])
    mock_probe.assert_called_once()


@patch("layers.platform._probe_outline", return_value="empty")
@patch("spatial.parcels._feature_at", return_value=None)
@patch("layers.platform.lookup_parcel_geojson", return_value=None)
@patch("layers.platform.vdl_at_point")
@patch("layers.platform.public_land_at_point")
def test_outline_swallowed_empty_answer_is_no_outline(
    mock_public, mock_vdl, _geojson, _feature, mock_probe
):
    _quiet(mock_public, mock_vdl)
    card = place_context(*EDINBURGH)
    field = card["land_register_outline"]
    assert field["status"] == "no_outline"
    assert field["note"] == NO_OUTLINE_NOTE
    assert set(field) == {"status", "note"}
    mock_probe.assert_called_once()


@patch("layers.platform.lookup_parcel")
@patch("layers.platform.lookup_parcel_geojson", return_value=None)
@patch("layers.platform.vdl_at_point")
@patch("layers.platform.public_land_at_point")
def test_outline_is_absent_over_sea_and_outside_scotland(
    mock_public, mock_vdl, _geojson, mock_lookup
):
    _quiet(mock_public, mock_vdl)
    # North Sea inside the rough bbox, and London, outside Scotland.
    for lat, lng in ((56.1, -1.2), (51.5074, -0.1278)):
        card = place_context(lat, lng)
        assert "land_register_outline" not in card
        assert card["private_or_sasine"]["status"] == "gap"
        assert card["private_or_sasine"]["note"] == SASINE_GAP_NOTE
    mock_lookup.assert_not_called()


def test_probe_tells_an_empty_answer_from_a_failed_call(monkeypatch):
    class _Response:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPError(f"status {self.status_code}")

        def json(self):
            if isinstance(self._payload, Exception):
                raise self._payload
            return self._payload

    class _Client:
        def __init__(self, response=None, error=None):
            self.response = response
            self.error = error

        def get(self, *args, **kwargs):
            if self.error is not None:
                raise self.error
            return self.response

    def install(client):
        monkeypatch.setattr("spatial.parcels._http", lambda: client)

    install(_Client(_Response(200, {"features": []})))
    assert _probe_outline(*EDINBURGH) == "empty"

    install(_Client(_Response(200, {"type": "FeatureCollection"})))
    assert _probe_outline(*EDINBURGH) == "empty"

    install(
        _Client(
            _Response(
                200,
                {"features": [{"geometry": {"type": "Polygon", "coordinates": []}, "properties": {"inspireid": "x"}}]},
            )
        )
    )
    assert _probe_outline(*EDINBURGH) == "inside"

    install(_Client(error=httpx.ReadTimeout("timed out")))
    assert _probe_outline(*EDINBURGH) == "error"

    install(_Client(error=httpx.ConnectError("refused")))
    assert _probe_outline(*EDINBURGH) == "error"

    install(_Client(_Response(503, {"features": []})))
    assert _probe_outline(*EDINBURGH) == "error"

    install(_Client(_Response(200, ValueError("not json"))))
    assert _probe_outline(*EDINBURGH) == "error"
