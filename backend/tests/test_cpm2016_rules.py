"""M6b frozen CPM 2016 rules: class set, headline, 0/−1/−2, planar-only, no conversion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from georgist.cpm2016_rules import (
    ALLOWED_IMPORTANCE,
    AREA_DISCLOSURE,
    AREA_METHOD,
    ATTRIBUTION,
    BUDGET_TILE_KB,
    BUDGET_TOTAL_MB_PROVISIONAL,
    BUDGET_Z0_7_MB_PROVISIONAL,
    CLIP,
    CLIP_TOLERANCE_M,
    CRS,
    DISSOLVE_BY,
    FIELD,
    FORBIDDEN_USER_TOKENS,
    GPKG_FEATURE_COUNT,
    GPKG_LAYER,
    GPKG_SHA256,
    HA_LESS_THAN_ONE,
    KEEP_FIELDS,
    LICENCE,
    LOW_ZOOM,
    PUBLISHED,
    S71,
    SERVE_MAX_MB_PROVISIONAL,
    SIMPLIFY_M,
    SOURCE_URL,
    SSDI,
    ZOOM_MAX,
    ZOOM_MIN,
    Cpm2016RuleError,
    class_5_hectares,
    format_hectares,
    headline_hectares,
    normalize_importance,
    peat_role,
    refuse_geodesic,
    unknown_hectares,
)
from layers.registry.admission import check_admission
from layers.registry.loader import load_registry

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "backend" / "layers" / "registry"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cpm2016_importance_stub.geojson"
YAML_PATH = REGISTRY / "carbon-peatland.yaml"


def test_source_pin_is_gpkg_not_wms():
    assert SOURCE_URL.endswith("CPM2016_SCOTLAND_GPKG_27700.zip")
    assert "ogc.nature.scot" not in SOURCE_URL
    assert SSDI == "51b36efb-3521-4243-9bb0-93f8a7a60a71"
    assert PUBLISHED == "2016-06-29"
    assert FIELD == "IMPORTANCE"
    assert CRS == "EPSG:27700"
    assert CLIP == "land"
    assert CLIP_TOLERANCE_M == 50
    assert LICENCE == "NCGL"
    assert ATTRIBUTION == (
        "© SNH and JHI. Available under a Non-Commercial Government Licence."
    )
    assert AREA_DISCLOSURE == "planar British National Grid (EPSG:27700)"
    assert S71.endswith("(NatureScot).")
    assert GPKG_SHA256 is None  # pending first download on Laurie's PC
    assert GPKG_LAYER is None
    assert GPKG_FEATURE_COUNT is None


def test_allowed_class_set():
    assert ALLOWED_IMPORTANCE == frozenset({-2, -1, 0, 1, 2, 3, 4, 5})
    for code in ALLOWED_IMPORTANCE:
        normalize_importance(code)
    with pytest.raises(Cpm2016RuleError, match="outside the official class set"):
        normalize_importance(6)
    with pytest.raises(Cpm2016RuleError, match="outside the official class set"):
        normalize_importance(-3)
    with pytest.raises(Cpm2016RuleError, match="not an integer"):
        normalize_importance("peat")
    with pytest.raises(Cpm2016RuleError, match="not an integer"):
        normalize_importance(1.5)


@pytest.mark.parametrize(
    "code, role",
    [
        (1, "headline"),
        (2, "headline"),
        (3, "not_headline"),
        (4, "not_headline"),
        (5, "class_5_separate"),
        (0, "zero"),
        (-2, "zero"),
        (-1, "unknown"),
        ("1", "headline"),
        (2.0, "headline"),
    ],
)
def test_peat_role(code, role):
    assert peat_role(code) == role


def test_headline_is_class_1_and_2_only():
    areas = {
        1: 100.0,
        2: 25.5,
        3: 999.0,
        4: 999.0,
        5: 999.0,
        0: 999.0,
        -1: 999.0,
        -2: 999.0,
    }
    assert headline_hectares(areas) == pytest.approx(125.5)
    assert unknown_hectares(areas) == pytest.approx(999.0)
    assert class_5_hectares(areas) == pytest.approx(999.0)
    assert headline_hectares({1: 10, 2: 5}) == pytest.approx(15)
    assert headline_hectares({5: 400}) == 0
    assert headline_hectares({-1: 50}) == 0
    assert headline_hectares({0: 80, -2: 20}) == 0
    assert headline_hectares({}) == 0


def test_class_minus_1_is_never_imputed_into_headline():
    # Option a: unknown stays in its own column and is excluded from 1+2.
    areas = {1: 10.0, 2: 5.0, -1: 1000.0}
    assert headline_hectares(areas) == pytest.approx(15.0)
    assert unknown_hectares(areas) == pytest.approx(1000.0)
    assert peat_role(-1) == "unknown"
    assert peat_role(-1) != "zero"


def test_refuse_geodesic():
    refuse_geodesic("planar")
    with pytest.raises(Cpm2016RuleError, match="no geodesic"):
        refuse_geodesic("geodesic")
    with pytest.raises(Cpm2016RuleError, match="no geodesic"):
        refuse_geodesic("ellipsoid")
    assert AREA_METHOD == "planar"


def test_format_hectares_matches_m5():
    assert format_hectares(0) == "0"
    assert format_hectares(0.4) == HA_LESS_THAN_ONE
    assert format_hectares(1.4) == "1"
    assert format_hectares(213803) == "213,803"
    with pytest.raises(Cpm2016RuleError, match="must not be negative"):
        format_hectares(-1)


def test_forbidden_conversion_tokens():
    assert "\u00a3" in FORBIDDEN_USER_TOKENS
    assert "tC" in FORBIDDEN_USER_TOKENS
    assert "carbon price" in FORBIDDEN_USER_TOKENS
    # The rules module lists the ban; user-facing yaml and the stub must not
    # introduce a price, a stock unit, or a pound sign.
    for path in (YAML_PATH, FIXTURE):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        assert "carbon price" not in lowered
        assert "\u00a3" not in text
        assert "emission factor" not in lowered
        assert "tco₂e" not in lowered
        assert "tco2e" not in lowered
        assert "gbp_display" not in lowered


def test_stub_fixture_covers_every_class():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["crs"]["properties"]["name"].endswith("EPSG::27700")
    codes = [feat["properties"]["IMPORTANCE"] for feat in data["features"]]
    assert sorted(codes) == sorted(ALLOWED_IMPORTANCE)
    assert len(codes) == len(set(codes)) == 8


def test_registry_yaml_matches_gis_and_rules():
    raw = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    assert raw["id"] == "carbon-peatland"
    assert raw["clip"] == CLIP
    assert raw["clip_keep_all"] is False
    assert raw["licence"] == LICENCE
    assert raw["non_commercial"] is True
    assert raw["attribution"] == ATTRIBUTION
    assert raw["value_layer"] is False
    assert raw["shows"] == "natural_capital"
    assert raw["policy_question"] == ["Q6"]
    assert raw["keep_fields"] == list(KEEP_FIELDS)
    assert raw["serve"]["simplify_m"] == SIMPLIFY_M
    assert raw["serve"]["max_mb"] == SERVE_MAX_MB_PROVISIONAL
    assert raw["serve"]["mode"] == "pmtiles"
    assert raw["zoom"]["min"] == ZOOM_MIN
    assert raw["zoom"]["max"] == ZOOM_MAX
    assert raw["zoom"]["low_zoom"] == LOW_ZOOM
    assert raw["tiles"]["no_tiny_polygon_reduction"] is True
    assert raw["tiles"]["dissolve_by"] == DISSOLVE_BY
    assert raw["tiles"]["budget"]["total_mb"] == BUDGET_TOTAL_MB_PROVISIONAL
    assert raw["tiles"]["budget"]["tile_kb"] == BUDGET_TILE_KB
    assert raw["tiles"]["budget"]["z0_7_mb"] == BUDGET_Z0_7_MB_PROVISIONAL
    assert raw["style"]["fill"]["fill-opacity"] > 0
    assert raw["source"]["type"] == "postgis_table"
    # Dissolve-before-tile is wired via tiles.dissolve_by; keep_fields is importance only.
    text = YAML_PATH.read_text(encoding="utf-8")
    assert "Dissolve by importance" in text
    assert DISSOLVE_BY == "importance"


def test_registry_admits_carbon_peatland():
    entries = load_registry(REGISTRY)
    check_admission(entries)
    assert entries["carbon-peatland"].raw["licence"] == "NCGL"
    assert entries["carbon-peatland"].raw["non_commercial"] is True
