from agr.areas import lookup_council


def test_edinburgh_coords_map_to_edinburgh():
    council = lookup_council(55.9533, -3.1883)
    assert council.code == "S12000036"
    assert council.name == "City of Edinburgh"
    assert council.average_price_gbp > 200_000
    assert council.lookup_method == "boundary"


def test_inverness_point_is_urban():
    council = lookup_council(57.4778, -4.2247)
    assert council.code == "S12000017"
    assert council.name == "Highland"
    assert council.rural is False


def test_cairngorms_point_is_countryside():
    council = lookup_council(57.08, -3.65)
    assert council.code == "S12000034"
    assert council.rural is True