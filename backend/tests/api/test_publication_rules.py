"""Publication geometry rule: modelled/proxy values and rents are zone-level only.

No public endpoint, tile or layer attaches a modelled or proxy value or rent to sub-zone
geometry (site, parcel, plot, UPRN, building). Plain parcel shapes are fine. Site-level
figures only from sources public at site level (SVDLS, HLS, published business rateable
values). Plot-level spreading lives on /internal behind ENABLE_INTERNAL_ENDPOINTS.
All rows here are SYNTHETIC.
"""

import re
from pathlib import Path

import pytest

from georgist import publication_rules as pr
from georgist.aggregator import build_payload

BACKEND = Path(__file__).resolve().parents[2]
SURFACE = {"code": "S01008677", "vintage": 2011, "price_year": 2023, "measured_rent": 100_000.0,
           "commons_class": "surface_residential", "value_tier": "proxy", "quality": "derived",
           "crosswalk_method": "none", "source_id": "ros_dz2011", "licence": "OGL-3.0",
           "publish_level": "public_zone"}
SITE = {"name": "SYNTHETIC DERELICT SITE", "annual_rent_gbp": 1_000.0, "price_year": 2023,
        "commons_class": "surface_vacant", "value_tier": "market", "quality": "live",
        "publish_level": "public_site", "source_id": "svdls"}


def _app(monkeypatch, internal=False):
    from api.main import create_app

    if internal:
        monkeypatch.setenv("ENABLE_INTERNAL_ENDPOINTS", "1")
        monkeypatch.setenv("INTERNAL_API_TOKEN", "test-internal-token")
    else:
        monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
        monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    return create_app()


def test_every_mounted_public_route_is_declared(monkeypatch):
    from api.main import registered_routes

    paths = {p for _, p in registered_routes(_app(monkeypatch))}
    assert pr.undeclared(paths) == []
    for p in paths:
        if pr.is_public_path(p):
            rule = pr.rule_for(p)
            assert rule.geometry_level in pr.GEOMETRY_LEVELS and rule.source_granularity in pr.SOURCE_GRANULARITIES


def test_no_public_declaration_puts_values_on_private_grain():
    for path, rule in pr.PUBLIC_ROUTE_RULES.items():
        if rule.geometry_level in pr.PRIVATE_GRAIN:
            assert not rule.carries_values, path  # plain shapes only
        if rule.geometry_level != "zone" and rule.carries_values:
            assert rule.value_basis == "measured" and rule.sources <= pr.SITE_PUBLIC_SOURCES, path
    assert pr.rule_for("/layers/georgist/surface-rent").geometry_level == "zone"


@pytest.mark.parametrize("rule", [
    pr.LayerRule("parcel", "zone", "modelled"),
    pr.LayerRule("plot", "zone", "modelled"),
    pr.LayerRule("uprn", "site", "measured", sources=frozenset({"svdls"})),
    pr.LayerRule("building", "zone", "measured"),
    pr.LayerRule("site", "zone", "measured", sources=frozenset({"svdls"})),  # zone value spread to sites
    pr.LayerRule("site", "site", "modelled", sources=frozenset({"svdls"})),
    pr.LayerRule("site", "site", "measured", sources=frozenset({"some_private_feed"})),
    pr.LayerRule("site", "site", "measured"),
    pr.LayerRule("hexagon", "zone", "none"),
])
def test_illegal_declarations_fail_loudly(rule):
    with pytest.raises(pr.PublicationRuleError):
        pr.validate_rule("/layers/x", rule)


@pytest.mark.parametrize("rule", [
    pr.LayerRule("zone", "zone", "modelled"),
    pr.LayerRule("parcel", "zone", "none"),  # plain parcel shapes
    pr.LayerRule("site", "site", "measured", sources=frozenset({"svdls", "hls", "business_rates"})),
])
def test_legal_declarations_pass(rule):
    assert pr.validate_rule("/layers/x", rule) is rule


def test_undeclared_public_route_stops_core_app_and_optional_router(monkeypatch):
    import sys
    import types

    from fastapi import APIRouter

    from api import main

    rogue = APIRouter()

    @rogue.get("/layers/plots/rent")
    def _plots():  # pragma: no cover - never served
        return {}

    with pytest.raises(pr.PublicationRuleError, match="/layers/plots/rent"):
        pr.check_router("rogue", [p for _, p in main.registered_routes(rogue)])
    mod = types.ModuleType("rogue_routes")
    mod.router = rogue
    monkeypatch.setitem(sys.modules, "rogue_routes", mod)
    monkeypatch.setattr(main, "OPTIONAL_ROUTERS", main.OPTIONAL_ROUTERS + (("rogue_routes", "router"),))
    app = main.create_app()
    assert "/layers/plots/rent" not in {p for _, p in main.registered_routes(app)}
    assert main.ROUTER_STATUS["rogue_routes"]["loaded"] is False
    assert "PublicationRuleError" in main.ROUTER_STATUS["rogue_routes"]["error"]


def _router_paths(module_file: Path) -> list[str]:
    return re.findall(r'@router\.get\("([^"]+)"', module_file.read_text())


def test_cadastral_parcel_routes_declared_as_plain_shapes():
    """Cadastral router serves RoS INSPIRE parcel shapes: declared parcel geometry, no value."""
    paths = _router_paths(BACKEND / "api" / "cadastral_routes.py")
    parcel_paths = [p for p in paths if p.startswith("/layers/parcels")]
    assert parcel_paths and all(not pr.rule_for(p).carries_values for p in parcel_paths)
    assert all(pr.rule_for(p).geometry_level == "parcel" for p in parcel_paths)


def test_legacy_routers_with_undeclared_routes_would_not_mount():
    """AGR still has undeclared routes (skipped at boot). Platform is fully declared and mounts."""
    agr_missing = pr.undeclared(_router_paths(BACKEND / "api" / "agr_routes.py"))
    assert agr_missing
    with pytest.raises(pr.PublicationRuleError):
        pr.check_router("agr_routes.py", _router_paths(BACKEND / "api" / "agr_routes.py"))
    assert pr.undeclared(_router_paths(BACKEND / "api" / "platform_routes.py")) == []
    assert pr.undeclared(_router_paths(BACKEND / "api" / "cadastral_routes.py")) == []


def test_plot_level_spreading_is_internal_only(monkeypatch):
    from api.main import registered_routes

    public = {p for _, p in registered_routes(_app(monkeypatch))}
    assert not any(p.startswith(pr.INTERNAL_PREFIX) for p in public)
    assert not any(re.search(r"(plot|uprn|building)", p) for p in public)
    internal = {p for _, p in registered_routes(_app(monkeypatch, internal=True))}
    assert any(p.startswith(pr.INTERNAL_PREFIX) for p in internal)
    assert pr.undeclared(internal) == pr.undeclared(public) == []  # /internal is exempt, never public


@pytest.mark.parametrize("bad", [
    {"value_tier": "proxy"}, {"value_tier": "shadow"}, {"quality": "modelled"},
    {"source_id": None}, {"source_id": "ros_dz2011"}, {"source_id": "home_valuation_model"},
])
def test_site_rows_must_be_measured_and_site_public(bad):
    with pytest.raises(pr.PublicationRuleError):
        pr.check_site_row("/layers/georgist/resource-rent", {**SITE, **bad})


@pytest.mark.parametrize("src", ["svdls", "hls", "business_rates", "SVDLS"])
def test_site_public_sources_pass(src):
    pr.check_site_row("/layers/georgist/resource-rent", {**SITE, "source_id": src})


def test_public_wealth_payload_refuses_modelled_site_rows_internal_lists_them():
    peat = {**SITE, "name": "SYNTHETIC PEAT", "value_tier": "shadow", "quality": "modelled", "source_id": None}
    with pytest.raises(pr.PublicationRuleError, match="zone-level only"):
        build_payload(SURFACE, [], [peat])
    assert any(c["name"] == "SYNTHETIC PEAT" for c in build_payload(SURFACE, [], [peat], internal=True)["components"])
    # Withheld rows show no figure, so they do not trip the rule.
    build_payload(SURFACE, [], [{**peat, "publish_level": "internal"}])
    build_payload(SURFACE, [SITE], [])


def test_zone_layer_rows_must_be_data_zones():
    pr.check_zone_row("/layers/georgist/surface-rent", {"code": "S01008677"})
    for code in ("UPRN906700000001", "S01", None, "parcel-7"):
        with pytest.raises(pr.PublicationRuleError):
            pr.check_zone_row("/layers/georgist/surface-rent", {"code": code})


def test_public_route_error_is_a_loud_500(monkeypatch):
    from fastapi.testclient import TestClient

    from api import wealth_routes

    class Boom:
        def get_total_wealth(self, *a, **k):
            raise pr.PublicationRuleError("/georgist/wealth", "site row 'X' carries a proxy/modelled figure")

    monkeypatch.setattr(wealth_routes, "aggregator", Boom())
    r = TestClient(_app(monkeypatch)).get("/georgist/wealth", params={"lat": 55.95, "lng": -3.19,
                                                                      "zone_id": "S01008677"})
    assert r.status_code == 500
    assert r.json()["detail"]["error"] == "publication_rule_violation"
