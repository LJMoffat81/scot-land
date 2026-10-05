import hashlib

import pytest

from agr.settlement import PATH, SHA256, FOLD_NAMES, route_for_fold, zone_class_for


def test_zone_class_table_is_the_pinned_official_lookup():
    raw = PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SHA256
    assert b"\r" not in raw
    lines = raw.decode("utf-8").splitlines()
    assert lines[0] == "dz2011,ur8"
    assert len(lines) == 6977
    assert len({line.split(",")[0] for line in lines[1:]}) == 6976


def test_city_centres_are_large_urban_and_a_remote_town_is_countryside():
    aberdeen = zone_class_for("S01006646")
    assert aberdeen == {
        "fold": 1,
        "name": "Large Urban Areas",
        "year": 2020,
        "route": "town",
    }
    dundee = zone_class_for("S01007705")
    assert dundee["fold"] == 1
    assert dundee["route"] == "town"
    remote_town = zone_class_for("S01007289")
    assert remote_town["fold"] == 5
    assert remote_town["name"] == "Very Remote Small Towns"
    assert remote_town["route"] == "countryside"
    very_remote = zone_class_for("S01006789")
    assert very_remote["name"] == "Very Remote Rural Areas"
    assert very_remote["route"] == "countryside"
    assert zone_class_for("nope") is None
    assert zone_class_for("S01000000") is None


def test_route_follows_the_point_split():
    for fold in range(1, 5):
        assert route_for_fold(fold) == "town"
        assert FOLD_NAMES[fold]
    for fold in range(5, 9):
        assert route_for_fold(fold) == "countryside"
    with pytest.raises(ValueError):
        route_for_fold(0)
    with pytest.raises(ValueError):
        route_for_fold(9)


def test_a_stand_in_table_is_not_checked_against_the_pin(tmp_path):
    path = tmp_path / "ur.csv"
    path.write_text("dz2011,ur8\nS01006646,6\nS01006647,0\nnope,1\n", encoding="utf-8")
    rural = zone_class_for("S01006646", path)
    assert rural["fold"] == 6
    assert rural["name"] == "Accessible Rural Areas"
    assert rural["route"] == "countryside"
    assert rural["year"] == 2020
    assert "gbp" not in rural
    assert zone_class_for("S01006647", path) is None
    assert zone_class_for("nope", path) is None
