"""Display denominators (rules v0.5): residential-hectare default, per dwelling, per resident.

Pending denominators are reported, never computed. Never per whole-zone hectare.
"""

from pathlib import Path

from georgist.aggregator import build_payload
from georgist.display_views import DEFAULT_VIEW, PENDING, VIEW_ORDER, surface_views

SURFACE = {"code": "S01008677", "vintage": 2011, "price_year": 2023, "dwellings": 400,
           "count_year": 2023, "measured_rent": 100_000.0, "uncertainty_low": 60_000.0,
           "uncertainty_high": 150_000.0, "value_tier": "proxy", "quality": "derived",
           "publish_level": "public_zone", "publication_status": "ok", "commons_class": "surface_residential"}


DW_2023 = {"vintage": 2011, "count_year": 2023, "total_dwellings": 400}


def test_default_is_residential_hectare_and_pending_without_denominators():
    d = surface_views(SURFACE, None, shown=True, dwelling_count=DW_2023)
    assert d["default"] == DEFAULT_VIEW == "per_residential_hectare"
    assert d["order"] == list(VIEW_ORDER) == ["per_residential_hectare", "per_dwelling", "per_resident"]
    v = d["views"]
    assert v["per_residential_hectare"] == {"status": PENDING, "value": None, "low": None, "high": None,
                                            "denominator": "residential_land_ha"}
    assert v["per_dwelling"]["status"] == "ok" and v["per_dwelling"]["value"] == 250.0
    assert v["per_dwelling"]["low"] == 150.0 and v["per_dwelling"]["high"] == 375.0
    assert v["per_resident"]["status"] == PENDING and v["per_resident"]["value"] is None
    assert v["per_resident"]["second_home_share_status"] == PENDING


def test_residential_land_used_when_loaded():
    v = surface_views(SURFACE, {"residential_land_ha": 20.0, "settlement_area_ha": 50.0}, shown=True)["views"]
    assert v["per_residential_hectare"]["status"] == "ok"
    assert v["per_residential_hectare"]["value"] == 5_000.0
    assert v["per_residential_hectare"]["denominator"] == "residential_land_ha"


def test_interim_settlement_area_is_flagged_rough():
    v = surface_views(SURFACE, {"settlement_area_ha": 50.0}, shown=True)["views"]["per_residential_hectare"]
    assert v["status"] == "interim_rough" and v["value"] == 2_000.0 and "rough" in v["flag"]


def test_per_resident_carries_second_home_share():
    row = {**SURFACE, "second_home_share": 0.25}
    pop = {"vintage": 2011, "count_year": 2023, "population": 800}
    v = surface_views(row, None, shown=True, population_count=pop)["views"]["per_resident"]
    assert v["value"] == 125.0 and v["second_home_share"] == 0.25 and "second-home" in v["flag"]


def test_counts_join_on_price_year_and_vintage_only():
    """count_year must equal price_year and the vintage must match; never filled from elsewhere."""
    from georgist.display_views import DWELLINGS_MISSING, POPULATION_MISSING

    row = {**SURFACE, "dwellings": None, "count_year": None}  # no own count on the row
    ok_dw = {"vintage": 2011, "count_year": 2023, "total_dwellings": 500, "second_home_share": 0.02}
    ok_pop = {"vintage": 2011, "count_year": 2023, "population": 1_000}
    d = surface_views(row, None, shown=True, dwelling_count=ok_dw, population_count=ok_pop)
    assert d["views"]["per_dwelling"]["value"] == 200.0 and d["views"]["per_resident"]["value"] == 100.0
    assert d["flags"] == []
    for bad in ({"count_year": 2022}, {"vintage": 2022}, {"vintage": "DZ2011"}, {"count_year": None}):
        d = surface_views(row, None, shown=True, dwelling_count={**ok_dw, **bad}, population_count={**ok_pop, **bad})
        assert d["views"]["per_dwelling"]["value"] is None and d["views"]["per_dwelling"]["status"] == PENDING
        assert d["views"]["per_resident"]["value"] is None and d["views"]["per_resident"]["status"] == PENDING
        assert d["flags"] == [DWELLINGS_MISSING, POPULATION_MISSING]
    # Valuation's own dwellings are never the denominator (Data Zones' dwellings_by_year is), even same-year.
    for year in (2022, 2023):
        d = surface_views({**SURFACE, "count_year": year}, None, shown=True)
        assert d["views"]["per_dwelling"]["value"] is None and DWELLINGS_MISSING in d["flags"]


def test_dwellings_come_from_datazones_dwellings_total():
    from georgist.display_views import DWELLINGS_DISAGREE, DWELLINGS_SOURCE

    assert DWELLINGS_SOURCE == "datazones.dwellings_by_year.dwellings_total"
    d = surface_views(SURFACE, None, shown=True, dwelling_count={**DW_2023, "total_dwellings": 500})
    v = d["views"]["per_dwelling"]
    assert v["value"] == 200.0 and v["denominator_source"] == DWELLINGS_SOURCE and v["denominator_year"] == 2023
    assert d["flags"] == [DWELLINGS_DISAGREE, "population_count_missing_for_price_year"]  # own 400 != 500


def test_missing_counts_flag_the_payload():
    p = build_payload({**SURFACE, "count_year": 2021}, [], [])
    assert {"dwellings_count_missing_for_price_year", "population_count_missing_for_price_year"} <= set(p["flags"])


def test_withheld_or_missing_surface_has_no_view_values():
    for surface, shown, status in ((SURFACE, False, "withheld"), (None, False, "not_available")):
        views = surface_views(surface, {"residential_land_ha": 10.0}, shown=shown,
                              population_count={"vintage": 2011, "count_year": 2023, "population": 5})["views"]
        assert all(v["value"] is None and v["status"] == status for v in views.values())


def test_payload_has_display_block():
    p = build_payload(SURFACE, [], [], denominators={"residential_land_ha": 25.0})
    assert p["display"]["views"]["per_residential_hectare"]["value"] == 4_000.0
    blocked = build_payload({**SURFACE, "publication_status": "blocked"}, [], [],
                            denominators={"residential_land_ha": 25.0})
    assert blocked["display"]["views"]["per_residential_hectare"]["value"] is None


def test_never_whole_zone_hectare():
    sql = (Path(__file__).resolve().parents[2] / "db" / "schema" / "003_dz_denominators.sql").read_text()
    code_lines = [ln.split("--")[0] for ln in sql.splitlines()]
    assert not any("zone_area" in ln or "area_ha " in ln.replace("settlement_area_ha", "") for ln in code_lines)
    v = surface_views(SURFACE, {"zone_area_ha": 1_000.0}, shown=True)["views"]
    assert v["per_residential_hectare"]["status"] == PENDING  # whole-zone area is ignored, not used


def test_valuation_row_values_win_over_denominator_table():
    row = {**SURFACE, "residential_land_ha": 10.0, "res_land_rough": False, "second_home_share": 0.4,
           "vacant_share": 0.05}
    v = surface_views(row, {"residential_land_ha": 999.0}, shown=True,
                      dwelling_count={"vintage": 2011, "count_year": 2023, "total_dwellings": 400,
                                      "second_home_share": None},
                      population_count={"vintage": 2011, "count_year": 2023, "population": 1000})["views"]
    assert v["per_dwelling"]["denominator_source"] == "datazones.dwellings_by_year.dwellings_total"
    assert v["per_residential_hectare"]["value"] == 10_000.0
    assert v["per_residential_hectare"]["denominator_source"] == "surface_rent_dz"
    assert v["per_resident"]["second_home_share"] == 0.4 and "second-home" in v["per_resident"]["flag"]
    rough = surface_views({**row, "res_land_rough": True}, None, shown=True)["views"]["per_residential_hectare"]
    assert rough["status"] == "interim_rough" and rough["denominator"] == "settlement_area_ha"


def test_zero_dwellings_from_spine_is_not_applicable_never_zero():
    """Rules v0.7: zone_spine.zero_dwellings is the single source and overrides the surface row."""
    from georgist.display_views import NOT_APPLICABLE, ZERO_DWELLINGS

    spine = {"zero_dwellings": True, "pop_dwellings_mismatch": False}
    d = surface_views(SURFACE, {"residential_land_ha": 10.0}, shown=True, dwelling_count=DW_2023, spine=spine)
    assert d["flags"] == [ZERO_DWELLINGS]
    assert all(v["status"] == NOT_APPLICABLE and v["value"] is None for v in d["views"].values())
    p = build_payload(SURFACE, [], [], denominators={"residential_land_ha": 10.0}, dwelling_count=DW_2023,
                      spine=spine)
    comp = p["components"][0]
    assert comp["measured_rent_gbp"] is None and comp["status"] == NOT_APPLICABLE
    assert comp["in_totals"] is False and comp["excluded_reason"] == ZERO_DWELLINGS
    assert p["totals_by_tier"] == {} or all(t["total_gbp"] is None or t["components"] == 0
                                            for t in p["totals_by_tier"].values())
    assert ZERO_DWELLINGS in p["flags"] and p["policy"]["policy_rent"] is None
    assert p["attribution"]["infra_share"] is None and p["attributions"] == []
    # Valuation's own row (dwellings 400, a rent) does not override the spine; nor does a NULL flag create one.
    assert surface_views(SURFACE, None, shown=True, spine={"zero_dwellings": None})["flags"] != [ZERO_DWELLINGS]
    assert surface_views({**SURFACE, "dwellings": 0}, None, shown=True)["flags"] != [ZERO_DWELLINGS]


def test_pop_dwellings_mismatch_withholds_per_resident_even_when_years_align():
    from georgist.display_views import POP_DWELLINGS_MISMATCH

    pop = {"vintage": 2011, "count_year": 2023, "population": 800}
    d = surface_views(SURFACE, None, shown=True, dwelling_count=DW_2023, population_count=pop,
                      spine={"zero_dwellings": False, "pop_dwellings_mismatch": True})
    v = d["views"]["per_resident"]
    assert v["value"] is None and v["reason"] == POP_DWELLINGS_MISMATCH and POP_DWELLINGS_MISMATCH in d["flags"]
    assert d["views"]["per_dwelling"]["value"] == 250.0  # other views unaffected
