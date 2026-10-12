"""SVDLS geometry precedence: Spatial Hub survey > RoS title outline > point."""

from __future__ import annotations

from layers.svdls_geometry import (
    GEOMETRY_PRECEDENCE,
    GEOMETRY_SOURCE_POINT,
    GEOMETRY_SOURCE_ROS_TITLE_OUTLINE,
    GEOMETRY_SOURCE_SPATIALHUB_SURVEY,
    GIS_PROVENANCE_TO_SOURCE,
    is_public_geometry_source,
    normalize_geometry_source,
    pick_geometry_source,
    resolve_site_geometry,
)
from layers.vdl import LIVE_GEOMETRY_SOURCE, _site_props


def test_precedence_order_is_spatialhub_then_ros_then_point():
    assert GEOMETRY_PRECEDENCE == (
        GEOMETRY_SOURCE_SPATIALHUB_SURVEY,
        GEOMETRY_SOURCE_ROS_TITLE_OUTLINE,
        GEOMETRY_SOURCE_POINT,
    )


def test_pick_prefers_spatialhub_over_ros_and_point():
    assert (
        pick_geometry_source(
            [
                GEOMETRY_SOURCE_POINT,
                GEOMETRY_SOURCE_ROS_TITLE_OUTLINE,
                GEOMETRY_SOURCE_SPATIALHUB_SURVEY,
            ]
        )
        == GEOMETRY_SOURCE_SPATIALHUB_SURVEY
    )


def test_pick_prefers_ros_over_point_when_no_spatialhub():
    assert (
        pick_geometry_source(
            [GEOMETRY_SOURCE_POINT, GEOMETRY_SOURCE_ROS_TITLE_OUTLINE]
        )
        == GEOMETRY_SOURCE_ROS_TITLE_OUTLINE
    )


def test_pick_falls_back_to_point():
    assert pick_geometry_source([GEOMETRY_SOURCE_POINT]) == GEOMETRY_SOURCE_POINT
    assert pick_geometry_source([]) is None
    assert pick_geometry_source([None, ""]) is None


def test_gis_provenance_aliases_map_to_room_tags():
    assert normalize_geometry_source("spatialhub_polygon") == (
        GEOMETRY_SOURCE_SPATIALHUB_SURVEY
    )
    assert normalize_geometry_source("spatialhub_buffer") == (
        GEOMETRY_SOURCE_SPATIALHUB_SURVEY
    )
    assert normalize_geometry_source("ros_inspire_outline") == (
        GEOMETRY_SOURCE_ROS_TITLE_OUTLINE
    )
    assert normalize_geometry_source("point_sized") == GEOMETRY_SOURCE_POINT
    assert set(GIS_PROVENANCE_TO_SOURCE.values()) == set(GEOMETRY_PRECEDENCE)


def test_resolve_site_geometry_selects_highest_precedence():
    geom, source = resolve_site_geometry(
        {
            "point_sized": {"kind": "point"},
            "ros_inspire_outline": {"kind": "ros"},
            "spatialhub_polygon": {"kind": "hub"},
        }
    )
    assert source == GEOMETRY_SOURCE_SPATIALHUB_SURVEY
    assert geom == {"kind": "hub"}

    geom, source = resolve_site_geometry(
        {
            "point": {"kind": "point"},
            "ros_title_outline": {"kind": "ros"},
        }
    )
    assert source == GEOMETRY_SOURCE_ROS_TITLE_OUTLINE
    assert geom == {"kind": "ros"}

    geom, source = resolve_site_geometry({"point_sized": {"kind": "point"}})
    assert source == GEOMETRY_SOURCE_POINT
    assert geom == {"kind": "point"}

    assert resolve_site_geometry({}) == (None, None)
    assert resolve_site_geometry({"spatialhub_survey": None}) == (None, None)


def test_ros_title_outline_not_public_until_cleared():
    assert is_public_geometry_source(GEOMETRY_SOURCE_SPATIALHUB_SURVEY) is True
    assert is_public_geometry_source(GEOMETRY_SOURCE_POINT) is True
    assert is_public_geometry_source(GEOMETRY_SOURCE_ROS_TITLE_OUTLINE) is False
    assert is_public_geometry_source("ros_inspire_outline") is False


def test_live_vdl_features_tagged_spatialhub_survey():
    assert LIVE_GEOMETRY_SOURCE == GEOMETRY_SOURCE_SPATIALHUB_SURVEY
    props = _site_props(
        {
            "site_name": "TEST",
            "site_type": "Vacant Land",
            "site_size": "1.0",
            "site_code": "X1",
        }
    )
    assert props["geometry_source"] == GEOMETRY_SOURCE_SPATIALHUB_SURVEY
    assert props["geometry_source_label"] == "Spatial Hub survey"
