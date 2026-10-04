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


def test_a_postcode_stays_a_postcode_and_a_title_is_padded():
    from spatial.address import normalise_title, search_place

    assert search_place("g1 1bl") == {"kind": "postcode", "postcode": "G1 1BL"}
    assert search_place("KW1 4AA")["postcode"] == "KW1 4AA"
    assert normalise_title("sct 7431917") == "SCT0007431917"
    assert normalise_title("SCT0007431917") == "SCT0007431917"
    assert normalise_title("G1 1BL") is None


def test_a_title_miss_has_no_point_when_the_service_cannot_filter(monkeypatch):
    from spatial.address import TITLE_MISS, search_place
    import spatial.parcels as parcels

    monkeypatch.setattr(parcels, "lookup_parcel_by_title", lambda label: None)
    result = search_place("SCT7431917")

    assert result["kind"] == "title_miss"
    assert result["label"] == "SCT0007431917"
    assert result["note"] == TITLE_MISS
    assert "lat" not in result
    assert "rent" not in result


def test_one_scottish_place_is_a_point_and_england_is_dropped():
    from spatial.address import search_place

    rows = [
        {
            "lat": "55.9533456",
            "lon": "-3.1883749",
            "display_name": "City of Edinburgh, Alba / Scotland, United Kingdom",
            "address": {"state": "Alba / Scotland", "ISO3166-2-lvl4": "GB-SCT"},
        },
        {
            "lat": "51.5074",
            "lon": "-0.1278",
            "display_name": "London, England, United Kingdom",
            "address": {"state": "England", "ISO3166-2-lvl4": "GB-ENG"},
        },
    ]
    result = search_place("Edinburgh", rows=rows)

    assert result["kind"] == "point"
    assert result["label"] == "City of Edinburgh, Alba / Scotland"
    assert result["lat"] == 55.953346
    assert "rent" not in result

    plain = search_place(
        "Edinburgh",
        rows=[
            {
                "lat": "55.9533",
                "lon": "-3.1883",
                "display_name": "Edinburgh, Scotland, United Kingdom",
                "address": {"state": "Scotland"},
            }
        ],
    )
    assert plain["kind"] == "point"
    assert plain["label"] == "Edinburgh, Scotland"


def test_several_places_stay_a_list():
    from spatial.address import search_place

    rows = [
        {
            "lat": "55.8601",
            "lon": "-4.2502",
            "display_name": "Buchanan Street, Glasgow, Scotland, United Kingdom",
            "address": {"state": "Scotland"},
        },
        {
            "lat": "55.8612",
            "lon": "-4.2431",
            "display_name": "George Street, Glasgow, Scotland, United Kingdom",
            "address": {"state": "Scotland"},
        },
    ]
    result = search_place("Glasgow street", rows=rows)

    assert result["kind"] == "places"
    assert len(result["matches"]) == 2
    assert result["matches"][0]["label"].startswith("Buchanan Street")
