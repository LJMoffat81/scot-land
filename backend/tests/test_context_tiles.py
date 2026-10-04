import ssl

from urllib.parse import parse_qs, urlparse

from spatial.context_tiles import (
    FEATURES,
    RASTER,
    _ssl_context,
    fetch_context_geojson,
    fetch_context_tile,
    raster_request_url,
    tile_intersects_context,
    urban_rural_query_url,
)
from spatial.parcels import TRANSPARENT_PNG


def test_marine_client_keeps_certificate_checks():
    ctx = _ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_unknown_raster_is_transparent_and_builds_no_url():
    assert fetch_context_tile("not-a-layer", 6, 31, 20) == TRANSPARENT_PNG
    assert raster_request_url("https://example.com", 6, 31, 20) is None
    assert raster_request_url("../secrets", 6, 31, 20) is None


def test_unknown_feature_layer_is_empty():
    geo = fetch_context_geojson("not-a-layer")
    assert geo["features"] == []
    assert geo["meta"]["ok"] is False


def test_allowlist_hosts_are_the_government_ones():
    for spec in RASTER.values():
        assert raster_request_url(spec.layer_id, 0, 0, 0) is None or spec.url.startswith(
            "https://"
        )
        host = spec.url.split("/")[2]
        assert host in {
            "msmap1.atkinsgeospatial.com",
            "map.sepa.org.uk",
            "maps.gov.scot",
            "ogc.nature.scot",
        }
    for spec in FEATURES.values():
        host = spec.url.split("/")[2]
        assert host in {
            "services-eu1.arcgis.com",
            "services3.arcgis.com",
            "assets.publishing.service.gov.uk",
        }


def test_sea_tile_url_stays_on_the_marine_plan():
    assert tile_intersects_context(7, 63, 39)
    url = raster_request_url("sea-12nm", 7, 63, 39)
    assert url is not None
    assert url.startswith("https://msmap1.atkinsgeospatial.com/geoserver/nmp/wms?")
    assert "nmp%3ANew_12_Nautical_Mile_Limit" in url or "nmp:New_12_Nautical_Mile_Limit" in url
    assert "example.com" not in url


def test_far_tile_is_not_requested():
    assert raster_request_url("scottish-zone", 5, 0, 0) is None


def test_urban_rural_tile_asks_only_for_layer_one():
    url = raster_request_url("urban-rural", 8, 124, 79)
    assert url is not None
    parsed = urlparse(url)
    assert parsed.netloc == "maps.gov.scot"
    assert parsed.path.endswith("/PeopleSociety/MapServer/export")
    assert parse_qs(parsed.query)["layers"] == ["show:1"]
    assert "SIMD" not in url
    assert "FloodDisadvantage" not in url


def test_urban_rural_class_asks_only_for_the_eight_class_name():
    url = urban_rural_query_url(58.445374, -3.094138)
    assert url is not None
    parsed = urlparse(url)
    assert parsed.netloc == "maps.gov.scot"
    assert parsed.path.endswith("/MapServer/1/query")
    fields = parse_qs(parsed.query)
    assert fields["outFields"] == ["ur8name"]
    assert "ur2name" not in url
    assert "ur6name" not in url
    assert urban_rural_query_url(0, 0) is None


def test_repd_keeps_scottish_operating_solar_only():
    from spatial.context_tiles import _repd_features

    text = (
        "Technology Type,Development Status (short),Country,Site Name,"
        "Installed Capacity (MWelec),X-coordinate,Y-coordinate\n"
        "Solar Photovoltaics,Operational,Scotland,Town Solar,5,258000,665000\n"
        "Wind Offshore,Operational,Scotland,Sea Wind,100,400000,700000\n"
        "Wind Onshore,Under Construction,Scotland,Hill Wind,20,300000,800000\n"
        "Solar Photovoltaics,Application Submitted,Scotland,Not Built,1,258000,665000\n"
        "Hydro,Operational,England,English Hydro,10,400000,300000\n"
        "Biomass (dedicated),Operational,Scotland,Plant,30,258000,665000\n"
    )
    features = _repd_features(text)
    sites = sorted(item["properties"]["site"] for item in features)
    assert sites == ["Hill Wind", "Town Solar"]
    assert "operator" not in features[0]["properties"]
