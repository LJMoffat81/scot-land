"""MAPREF-FIX — place-card map reference is OSGB36 BNG (EPSG:27700), ±50 m."""

from __future__ import annotations

from pyproj import Transformer

from layers.platform import _square_reference

_TO_OSGB36 = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)

# Three known onshore points; expect easting,northing within ±50 m of pyproj.
KNOWN_POINTS = (
    ("Edinburgh EH1", 55.9533, -3.1883),
    ("Inverness", 57.4778, -4.2247),
    ("Glasgow centre", 55.8609, -4.2514),
)


def test_square_reference_osgb36_three_known_points():
    for name, lat, lng in KNOWN_POINTS:
        ref = _square_reference(lat, lng)
        assert "," in ref, name
        easting_s, northing_s = ref.split(",", 1)
        easting, northing = int(easting_s), int(northing_s)
        exp_e, exp_n = _TO_OSGB36.transform(lng, lat)
        assert abs(easting - exp_e) <= 50, f"{name} easting {easting} vs {exp_e}"
        assert abs(northing - exp_n) <= 50, f"{name} northing {northing} vs {exp_n}"
        # British National Grid band (not lat/lng index millions / negatives).
        assert 50_000 < easting < 700_000, name
        assert 0 < northing < 1_300_000, name
        assert "what3words" not in ref.lower()
        assert "Scot-LAND" not in ref


def test_edinburgh_and_inverness_near_spec_examples():
    """Spec examples are approximate; stay within a few hundred metres of them."""
    edin = _square_reference(55.9533, -3.1883)
    e_e, e_n = (int(x) for x in edin.split(","))
    assert abs(e_e - 325_900) < 200
    assert abs(e_n - 673_600) < 500

    inv = _square_reference(57.4778, -4.2247)
    i_e, i_n = (int(x) for x in inv.split(","))
    assert abs(i_e - 266_000) < 800
    assert abs(i_n - 845_000) < 400
