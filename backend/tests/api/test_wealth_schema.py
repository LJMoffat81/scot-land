"""surface_rent_dz contract: SQL, Python adapter and enums agree; reconciliation rules."""

import re
from pathlib import Path
from typing import get_args

import pytest

from georgist import surface_rent as sr
from georgist import wealth_schema as ws

SQL = (Path(__file__).resolve().parents[2] / "db" / "schema" / "001_wealth_core.sql").read_text()


def _table_block(name: str) -> str:
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {name} \((.*?)\n\);", SQL, re.S)
    assert m, name
    return m.group(1)


def _columns(name: str) -> list[str]:
    cols = []
    for line in _table_block(name).splitlines():
        line = line.split("--")[0].strip()
        m = re.match(r"^([a-z_][a-z0-9_]*)\s+(TEXT|SMALLINT|INTEGER|NUMERIC|BOOLEAN|DATE|JSONB|TIMESTAMPTZ|BIGSERIAL|geometry)", line)
        if m:
            cols.append(m.group(1))
    return cols


def _check_values(block: str, column: str) -> set[str]:
    m = re.search(rf"{column}\s+TEXT[^\n]*?CHECK \({column} IN \(([^)]*)\)\)", block, re.S)
    if not m:
        m = re.search(rf"CHECK \({column} IN \(([^)]*)\)\)", block, re.S)
    assert m, column
    return set(re.findall(r"'([^']+)'", m.group(1)))


def test_sql_surface_columns_match_adapter():
    """Same names, same order: Valuation's OUTPUT_COLUMNS (agreed year names), then DB extras."""
    cols = [c for c in _columns("surface_rent_dz") if c != "updated_at"]
    assert cols == list(ws.SURFACE_DB_COLUMNS)


def test_no_forbidden_columns():
    for table in ("surface_rent_dz", "planning_sites", "resource_wealth", "eco_wealth"):
        for col in _columns(table):
            assert not any(tok in col for tok in ws.FORBIDDEN_COLUMN_TOKENS), (table, col)


def test_sql_enums_match_python_literals():
    s = _table_block("surface_rent_dz")
    assert _check_values(s, "value_tier") == set(get_args(ws.ValueTier))
    assert _check_values(s, "quality") == set(get_args(ws.Quality))
    assert _check_values(s, "use_basis") == set(get_args(ws.UseBasis))
    assert _check_values(s, "publish_level") == set(get_args(ws.PublishLevel))
    assert _check_values(s, "crosswalk_method") == set(ws.SURFACE_CROSSWALK_METHODS)
    assert _check_values(s, "fill_method") == set(get_args(ws.FillMethod))
    assert _check_values(s, "publication_status") == set(ws.PUBLICATION_STATUSES) == {"ok", "blocked"}
    for table in ("resource_wealth", "eco_wealth"):
        b = _table_block(table)
        assert _check_values(b, "publish_level") == set(ws.PUBLISH_LEVELS)
        assert _check_values(b, "publication_status") == {"ok", "blocked"}
    assert set(ws.SURFACE_CROSSWALK_METHODS) < set(get_args(ws.CrosswalkMethod))
    r = _table_block("resource_wealth")
    assert _check_values(r, "crosswalk_method") == set(get_args(ws.CrosswalkMethod))
    p = _table_block("planning_sites")
    assert _check_values(p, "source") == set(get_args(ws.PlanningSource))
    assert _check_values(p, "geom_source") == set(get_args(ws.GeomSource))


def test_planning_sites_has_agreed_columns():
    want = {"site_id", "source", "permitted_use", "planning_status", "status_date", "dz2011_code",
            "dz2022_code", "plan_authority", "deciding_authority", "geom_source", "geom",
            "hectares", "capacity_homes", "publish_level"}
    assert want <= set(_columns("planning_sites"))
    assert "27700" in _table_block("planning_sites")


def test_breakdown_and_policy_columns_present_and_separate():
    cols = _columns("surface_rent_dz")
    for c in ("planning_uplift", "infra_share", "policy_rent", "policy_despec_factor", "measured_rent", "raw_residual",
              "negative_residual", "absent_from_ros_price_file", "price_year", "source_id", "licence"):
        assert c in cols
    assert set(ws.ATTRIBUTION_COLUMNS) == {"planning_uplift", "infra_share"}


# ---------------------------------------------------------------- adapter

def test_db_columns_are_valuation_columns_plus_extras():
    n = len(sr.OUTPUT_COLUMNS)
    assert ws.SURFACE_DB_COLUMNS[n:] == ws.DB_EXTRA_COLUMNS
    assert "publication_status" in ws.SURFACE_DB_COLUMNS
    assert ws.SURFACE_DB_COLUMNS[:n] == tuple(sr.OUTPUT_COLUMNS)  # Valuation fd03c4b: agreed names, no mapping


def test_year_columns_use_agreed_names():
    """Rules section 2: price_year = money year, evidence_year = raw sales/evidence year."""
    assert {"price_year", "evidence_year"} <= set(ws.SURFACE_DB_COLUMNS)
    assert not set(ws.PRE_RENAME_NAMES) & set(ws.SURFACE_DB_COLUMNS)
    assert {"code", "vintage", "price_year", "evidence_year", "count_year"} <= set(ws.PUBLIC_SURFACE_COLUMNS)
    code_sql = "\n".join(ln.split("--")[0] for ln in SQL.splitlines())
    for old in (*ws.PRE_RENAME_NAMES, "sales_price_year"):
        assert not re.search(rf"\b{old}\b", code_sql), old
    for table in ("resource_wealth", "eco_wealth"):
        assert {"price_year", "evidence_year"} <= set(_columns(table))


@pytest.mark.parametrize("new,old", [("price_year", "price_base_year"), ("code", "zone_code"),
                                     ("vintage", "zone_vintage"), ("count_year", "dwelling_year")])
def test_old_names_refused(make_valuation_row, new, old):
    row = make_valuation_row(250_000)
    assert row["price_year"] == 2025 and row["evidence_year"] == 2023 and row["count_year"] == 2025
    renamed = {(old if k == new else k): v for k, v in row.items()}
    with pytest.raises(ValueError, match="pre-rename"):
        ws.to_db_row(renamed)
    with pytest.raises(ValueError, match="price_year"):
        ws.to_db_row({**row, "price_year": None})


def test_publish_level_is_three_values_and_blocked_is_a_status():
    """Rules v0.4 section 2."""
    assert ws.PUBLISH_LEVELS == ("public_site", "public_zone", "internal")
    assert set(ws.PUBLISH_LEVELS) == set(sr.PUBLISH_LEVELS)
    assert "blocked" not in _check_values(_table_block("surface_rent_dz"), "publish_level")
    with pytest.raises(ValueError):
        ws.map_publish_level("blocked")


@pytest.mark.parametrize("row,status", [
    ({"publish_level": "public_zone", "proxy_tags": []}, "ok"),
    ({"publish_level": "public_zone", "proxy_tags": ["reconciliation_breach"]}, "blocked"),
    ({"publish_level": "public_zone", "publication_status": "blocked"}, "blocked"),
    ({"publish_level": "blocked"}, "blocked"),  # pre-v0.4 rows
])
def test_publication_status_derivation(row, status):
    assert ws.derive_publication_status(row) == status


def test_bad_publication_status_refused():
    with pytest.raises(ValueError):
        ws.derive_publication_status({"publication_status": "hidden"})


def test_block_keeps_level_and_hides_publicly():
    row = {"publish_level": "public_zone", "publication_status": "blocked", "quality": "derived"}
    assert row["publish_level"] == "public_zone" and not ws.publicly_served(row)
    assert ws.publicly_served({**row, "publication_status": "ok"})  # clearing the block restores it
    assert not ws.publicly_served({**row, "publication_status": "ok", "quality": "placeholder"})
    assert not ws.publicly_served({**row, "publication_status": "ok", "publish_level": "internal"})


def test_reconciliation_breach_row_is_blocked(make_valuation_row):
    rec = sr.reconciliation_check(module_rents={"surface": (1e9, 1e9, 1e9)},
                                  observed_total_value_gbp=1_000.0, gross_yield_value=0.05)
    assert not rec.ok
    row = ws.to_db_row(make_valuation_row(250_000, reconciliation=rec))
    assert row["publication_status"] == "blocked"
    assert not ws.publicly_served(row)


RULES_DIAGNOSTICS = ("raw_residual", "drc_low_gbp", "drc_high_gbp", "typical_sale_gbp", "price_skew_flag",
                     "mean_median_ratio", "rebuild_mix_basis")


def test_diagnostics_are_internal_only():
    """Rules v0.4 section 2: diagnostics may sit on the row but are never served publicly."""
    for col in RULES_DIAGNOSTICS:
        assert col in ws.SURFACE_DB_COLUMNS, col  # still stored
        assert col in ws.INTERNAL_ONLY_COLUMNS, col
        assert col not in ws.PUBLIC_SURFACE_COLUMNS, col
    assert not set(ws.PUBLIC_SURFACE_COLUMNS) & set(ws.INTERNAL_ONLY_COLUMNS)
    assert set(ws.PUBLIC_SURFACE_COLUMNS) <= set(ws.SURFACE_DB_COLUMNS)


def test_public_view_drops_diagnostics(make_valuation_row):
    view = ws.public_surface_view(ws.to_db_row(make_valuation_row(250_000)))
    assert not set(view) & set(ws.INTERNAL_ONLY_COLUMNS)
    assert view["measured_rent"] is not None


def test_python_enums_match_valuation_module():
    assert set(get_args(ws.Quality)) == set(sr.QUALITY)
    assert set(get_args(ws.FillMethod)) == set(sr.FILL_METHODS)
    assert set(get_args(ws.CrosswalkMethod)) == set(sr.CROSSWALK_METHODS)
    assert set(ws.ATTRIBUTION_COLUMNS) == {"planning_uplift", "infra_share"}


def test_adapter_keeps_valuation_row_and_maps_publish(make_valuation_row):
    vrow = make_valuation_row(250_000)
    row = ws.to_db_row(vrow)
    assert tuple(row) == ws.SURFACE_DB_COLUMNS
    for k in ws.SURFACE_COLUMNS:
        assert row[k] == vrow[k], k
    assert row["publish_level"] == "public_zone" and row["publication_status"] == "ok"
    assert row["planning_uplift"] is None
    assert row["planning_uplift_flag"] == "pending_existing_use_proxy"


def test_model_filled_is_public_zone(make_valuation_row):
    vrow = make_valuation_row(250_000, fill_obs=False)
    assert ws.to_db_row(vrow)["publish_level"] == "public_zone"


@pytest.mark.parametrize("legacy,level", [("public", "public_zone"), ("zone_total_only", "public_zone")])
def test_legacy_publish_vocabulary_mapped(legacy, level):
    assert ws.map_publish_level(legacy) == level


def test_negative_residual_kept_raw_and_flagged(make_valuation_row):
    row = ws.to_db_row(make_valuation_row(20_000))
    assert row["raw_residual"] < 0
    assert row["negative_residual"] is True
    assert row["land_value"] == 0


def test_absent_from_ros_flag_carried(make_valuation_row):
    assert ws.to_db_row(make_valuation_row(), absent_from_ros_price_file=True)["absent_from_ros_price_file"] is True


def test_adapter_refuses_foreign_rows():
    with pytest.raises(ValueError):
        ws.to_db_row({"code": "S01008677"})


def test_unknown_publish_level_refused():
    with pytest.raises(ValueError):
        ws.map_publish_level("everyone")


@pytest.mark.parametrize("method", ["pop_hhres_2022", "footprint_area", "native", "area_weighted"])
def test_surface_crosswalk_refuses_population_area_and_unknown(method):
    with pytest.raises(ValueError):
        ws.check_crosswalk(method, surface=True)


def test_crosswalk_enum_for_other_layers():
    assert ws.check_crosswalk("footprint_area", surface=False) == "footprint_area"


def test_per_person_same_vintage_only():
    assert ws.per_person(1000.0, 2011, 10, 2011) == 100.0
    with pytest.raises(ValueError):
        ws.per_person(1000.0, 2011, 10, 2022)
    with pytest.raises(ValueError, match="integer 2011 or 2022"):
        ws.per_person(1000.0, "DZ2011", 10, "DZ2011")


@pytest.mark.parametrize("bad", ["DZ2011", "2011", 2011.0, True, 2015, None])
def test_to_db_row_refuses_non_integer_vintage(make_valuation_row, bad):
    """Text 'DZ2011' (Valuation 687cf43's label) is refused, never mapped to 2011."""
    row = {**make_valuation_row(250_000), "vintage": bad}
    with pytest.raises(ValueError, match="vintage must be the integer 2011 or 2022"):
        ws.to_db_row(row)


def test_to_db_row_refuses_code_from_other_vintage(make_valuation_row):
    row = {**make_valuation_row(250_000), "code": "S01016000"}  # a 2022 code labelled 2011
    with pytest.raises(ValueError, match="not a 2011 data zone code"):
        ws.to_db_row(row)


def test_reconciliation_ceiling_is_valuations_mean_x_dwellings_x_gross():
    """Rules 4.2 v0.3: ceiling = MEAN price x dwellings x GROSS yield, same vintage (Valuation owns it)."""
    rec = sr.reconciliation_check(
        module_rents={"surface": (100.0, 150.0, 200.0)},
        observed_total_value_gbp=200_000 * 400,
        gross_yield_value=0.05,
    )
    assert rec.ceiling_rent_gbp == pytest.approx(200_000 * 400 * 0.05)


def test_yield_provenance_tags_config_fallback_as_placeholder():
    from georgist.wealth_schema import yield_provenance

    p = yield_provenance({"yield_source": "config_fallback", "yield_land": 0.05, "proxy_tags": []})
    assert p["status"] == "placeholder" and "placeholder" in p["note"] and p["yield_land"] == 0.05
    assert yield_provenance({"yield_source": None, "yield_land": 0.05,
                             "proxy_tags": ["yield_fallback:config"]})["status"] == "placeholder"
    assert yield_provenance({"yield_source": "cell", "yield_land": 0.03, "proxy_tags": []})["status"] == "evidence"
    assert yield_provenance({"yield_source": None, "yield_land": None, "proxy_tags": None})["status"] == "none"
