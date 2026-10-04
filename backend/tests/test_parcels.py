from spatial.parcels import (
    TRANSPARENT_PNG,
    _point_for_label,
    fetch_parcel_tile_png,
    tile_bounds_3857,
    tile_intersects_scotland,
)


def test_tile_bounds_z0():
    minx, miny, maxx, maxy = tile_bounds_3857(0, 0, 0)
    assert minx < 0 < maxx
    assert miny < 0 < maxy
    # roughly full world mercator
    assert abs(minx + 20037508.34) < 1
    assert abs(maxx - 20037508.34) < 1


def test_edinburgh_tile_in_scotland():
    # z=10 tile roughly covering central belt
    assert tile_intersects_scotland(10, 490, 320) or tile_intersects_scotland(8, 120, 75)
    # Far ocean should not
    assert not tile_intersects_scotland(5, 0, 0)


def test_a_title_point_is_kept_only_when_the_label_matches():
    payload = {
        "features": [
            {
                "properties": {
                    "nationalcadastralreference": "SCT0007431917",
                    "point_geom": {"type": "Point", "coordinates": [-4.243037, 55.858366]},
                }
            }
        ]
    }
    point = _point_for_label(payload, "SCT0007431917")
    assert point == {"lat": 55.858366, "lng": -4.243037, "label": "SCT0007431917"}
    assert _point_for_label(payload, "SCT0000000001") is None
    assert _point_for_label({"features": []}, "SCT0007431917") is None


def test_low_zoom_returns_transparent():
    png = fetch_parcel_tile_png(5, 0, 0)
    assert png == TRANSPARENT_PNG


def test_fetch_parcel_tile_edinburgh_has_png_header():
    # Zoom 15 around Edinburgh (approx XYZ for -3.19, 55.95)
    # Web mercator tile calc: use a known-good z/x/y if network available
    import math

    lat, lon, z = 55.9533, -3.1883, 15
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    png = fetch_parcel_tile_png(z, x, y)
    assert png.startswith(b"\x89PNG")
    # Live WMS should return a real tile (larger than 1×1 transparent)
    assert len(png) > 100
