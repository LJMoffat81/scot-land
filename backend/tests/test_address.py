import pytest

from spatial.address import lookup_params, search_door


def _row(number: str, street: str, postcode: str, lat: str, lon: str) -> dict:
    return {
        "lat": lat,
        "lon": lon,
        "address": {
            "house_number": number,
            "road": street,
            "postcode": postcode,
            "country_code": "gb",
        },
    }


def test_one_door_returns_a_point_and_no_rent():
    result = search_door(
        "G1 1BL",
        "12",
        rows=[_row("12", "Buchanan Street", "G1 1BL", "55.860100", "-4.250200")],
    )

    assert result["status"] == "one"
    assert result["postcode"] == "G1 1BL"
    assert result["matches"][0]["lat"] == 55.8601
    assert result["matches"][0]["lng"] == -4.2502
    assert result["matches"][0]["label"] == "12 Buchanan Street"
    assert "rent" not in result
    assert "annual_charge_gbp" not in result


def test_tenement_token_matches_the_building_number():
    result = search_door(
        "g11bl",
        "2/1",
        rows=[_row("2", "High Street", "G1 1BL", "55.861", "-4.251")],
    )

    assert result["status"] == "one"
    assert result["door"] == "2/1"
    assert result["matches"][0]["label"] == "2/1 High Street"


def test_plain_number_does_not_match_a_lettered_door():
    result = search_door(
        "G1 1BL",
        "12",
        rows=[_row("12A", "High Street", "G1 1BL", "55.861", "-4.251")],
    )

    assert result["status"] == "none"
    assert "not in the open address set" in result["note"]


def test_same_number_on_two_streets_stays_a_choice():
    result = search_door(
        "G1 1BL",
        "12",
        rows=[
            _row("12", "King Street", "G1 1BL", "55.870", "-4.260"),
            _row("12", "High Street", "G1 1BL", "55.860", "-4.250"),
        ],
    )

    assert result["status"] == "many"
    assert [item["street"] for item in result["matches"]] == [
        "High Street",
        "King Street",
    ]


def test_a_different_postcode_is_not_a_match():
    result = search_door(
        "G1 1BL",
        "12",
        rows=[_row("12", "High Street", "G1 1DU", "55.860", "-4.250")],
    )

    assert result["status"] == "none"
    assert result["matches"] == []


def test_a_node_and_a_way_for_the_same_door_are_one_match():
    result = search_door(
        "EH1 1SR",
        "1",
        rows=[
            _row("1", "High Street", "EH1 1SR", "55.950708", "-3.184422"),
            _row("1", "High Street", "EH1 1SR", "55.950688", "-3.184365"),
        ],
    )

    assert result["status"] == "one"
    assert len(result["matches"]) == 1


def test_the_search_uses_the_street_and_not_a_structured_postcode():
    params = lookup_params("EH1 1SR", "1", "High Street")

    assert params["q"] == "1 High Street, EH1 1SR"
    assert "postalcode" not in params


def test_a_word_is_not_a_door_number():
    with pytest.raises(ValueError):
        search_door("G1 1BL", "Glasgow", rows=[])
