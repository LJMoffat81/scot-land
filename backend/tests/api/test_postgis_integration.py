"""End-to-end against a real PostGIS. Skipped unless WEALTH_TEST_DATABASE_URL is set.

    WEALTH_TEST_DATABASE_URL=postgresql://user@127.0.0.1:54329/wealth_it pytest tests/api

Uses a THROWAWAY database: it applies the schema and truncates Wealth tables.
All rows are SYNTHETIC.
"""

import os

import pytest

URL = os.getenv("WEALTH_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="WEALTH_TEST_DATABASE_URL not set")

ZONE = "S01008677"  # real-format 2011 zone code; the row is SYNTHETIC


@pytest.fixture
def pg(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    from etl.migrate_to_postgis import apply_schema
    from georgist import db

    conn = db.connect()
    with conn.cursor() as cur:  # throwaway DB: rebuild so schema changes always apply
        cur.execute(
            "DROP TABLE IF EXISTS alembic_version, inspire_parcels_meta, inspire_parcels, nrs_settlements, nrs_localities, "
            "surface_rent_rollup, surface_rent_dz, "
            "resource_wealth, eco_wealth, planning_sites, dz_spine, dz_boundaries, "
            "dz_denominators, dz_dwelling_counts, dz_population_counts CASCADE"
        )
        cur.execute("DROP SCHEMA IF EXISTS processed CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS processed_internal CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS datazones CASCADE")
    conn.commit()
    apply_schema(conn)  # alembic upgrade head (uses DATABASE_URL)
    yield conn
    conn.close()


def _dz_zone(pg, code, vintage, *, population=None, pop_year=None):
    """SYNTHETIC datazones.zone_spine row (the parent of every Data Zones table)."""
    with pg.cursor() as cur:
        cur.execute("INSERT INTO datazones.zone_spine (code, vintage, name, iz_code, la_code, la_name, population, "
                    "pop_year) VALUES (%s, %s, 'SYNTHETIC', 'S02000001', 'S12000036', 'SYNTHETIC', %s, %s) "
                    "ON CONFLICT (code, vintage) DO UPDATE SET population = EXCLUDED.population, "
                    "pop_year = EXCLUDED.pop_year", (code, vintage, population, pop_year))


def _dz_dwellings(pg, code, vintage, year, total, *, assessor=None):
    """SYNTHETIC datazones.dwellings_by_year row."""
    with pg.cursor() as cur:
        cur.execute("INSERT INTO datazones.dwellings_by_year (code, vintage, count_year, dwellings_total, "
                    "assessor_dwellings_dec) VALUES (%s, %s, %s, %s, %s)", (code, vintage, year, total, assessor))


@pytest.fixture
def surface_row(make_valuation_row):
    from georgist.wealth_schema import to_db_row

    def _make(zone=ZONE, **over):
        row = to_db_row(make_valuation_row(250_000, code=zone, infra_share=200_000.0))
        row.update(over)
        return row

    return _make


def test_full_path_totals_by_tier_and_placeholder_absent(pg, client, surface_row):
    from etl.migrate_to_postgis import upsert_surface_rent

    row = surface_row()
    assert upsert_surface_rent(pg, [row]) == 1
    with pg.cursor() as cur:
        # Mock offshore polygon, but placed over Edinburgh so the point query hits it.
        cur.execute("""
            INSERT INTO resource_wealth (name, annual_rent_gbp, price_year, value_tier, quality, geom)
            VALUES ('MOCK', 750000, 2025, 'proxy', 'placeholder',
              ST_Multi(ST_Transform(ST_SetSRID(ST_MakeEnvelope(-3.3, 55.9, -3.1, 56.0), 4326), 27700)))
        """)
    pg.commit()
    r = client.get("/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": ZONE})
    assert r.status_code == 200, r.text
    w = r.json()["wealth"]
    assert w["totals_by_tier"]["proxy"]["total_gbp"] == pytest.approx(row["measured_rent"])  # mock excluded
    # price_year = money year (indexed); evidence_year = raw sales year (rules section 2).
    assert w["totals_by_tier"]["proxy"]["price_year"] == row["price_year"] == 2025
    assert w["components"][0]["evidence_year"] == row["evidence_year"] == 2023
    assert w["attribution"]["infra_share"] == 200_000.0
    assert w["attribution"]["planning_uplift"] is None
    assert w["policy"]["policy_rent"] == pytest.approx(row["policy_rent"])
    assert w["policy"]["policy_rent"] != w["totals_by_tier"]["proxy"]["total_gbp"]
    assert [c["layer"] for c in w["components"]] == ["surface"]  # the mock is absent, not flagged
    assert w["attributions"][0]["dataset"] == "gis/epc_dz_rollup.csv"
    assert "Royal Mail" in w["attributions"][0]["attribution"]
    assert "MOCK" not in r.text and "750000" not in r.text
    for diag in ("raw_residual", "typical_sale_gbp", "drc_low_gbp", "rebuild_mix_basis", "price_skew_flag"):
        assert diag not in r.text
    h = client.get("/health").json()
    assert h["db"]["status"] == "ok"


def test_zone_without_surface_row_is_flagged(pg, client):
    r = client.get("/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": "S01008678"})
    assert r.status_code == 200
    assert "surface_not_found" in r.json()["wealth"]["flags"]
    assert r.json()["wealth"]["totals_by_tier"] == {}


def test_surface_layer_hides_internal_blocked_and_placeholder_rows(pg, client, surface_row):
    from etl.migrate_to_postgis import upsert_surface_rent

    from georgist.wealth_schema import INTERNAL_ONLY_COLUMNS

    upsert_surface_rent(pg, [surface_row()])
    upsert_surface_rent(pg, [surface_row(zone="S01008679", publish_level="internal")])
    upsert_surface_rent(pg, [surface_row(zone="S01008680", publication_status="blocked")])
    upsert_surface_rent(pg, [surface_row(zone="S01008681", quality="placeholder")])
    r = client.get("/layers/georgist/surface-rent")
    assert r.status_code == 200
    body = r.json()
    assert set(body["data"]) == {ZONE}
    assert body["withheld"] == 3
    assert body["withheld_by_reason"] == {"not_publishable": 1, "blocked": 1, "placeholder": 1}
    assert not set(body["data"][ZONE]) & set(INTERNAL_ONLY_COLUMNS)
    # EPC rollup feeds surface rent: the public layer carries its licence + attribution.
    epc = [a for a in body["attributions"] if a["dataset"] == "gis/epc_dz_rollup.csv"]
    assert epc and "PAF®" in epc[0]["attribution"] and "non-commercial" in epc[0]["licence"]
    # The blocked zone keeps its licence level in the DB; clearing the block restores it.
    with pg.cursor() as cur:
        cur.execute("SELECT publish_level FROM surface_rent_dz WHERE code = 'S01008680'")
        assert cur.fetchone()[0] == "public_zone"
        cur.execute("UPDATE surface_rent_dz SET publication_status = 'ok' WHERE code = 'S01008680'")
    pg.commit()
    assert "S01008680" in client.get("/layers/georgist/surface-rent").json()["data"]


def test_blocked_zone_withheld_from_wealth(pg, client, surface_row):
    from etl.migrate_to_postgis import upsert_surface_rent

    upsert_surface_rent(pg, [surface_row(publication_status="blocked")])
    w = client.get("/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": ZONE}).json()["wealth"]
    c = w["components"][0]
    assert c["excluded_reason"] == "blocked" and c["measured_rent_gbp"] is None
    assert c["publish_level"] == "public_zone"
    assert w["totals_by_tier"] == {}


def test_public_point_layers_never_serve_placeholders(pg, client):
    with pg.cursor() as cur:
        cur.execute("""
            INSERT INTO resource_wealth (name, annual_rent_gbp, price_year, value_tier, quality, publish_level, geom)
            VALUES ('MOCK', 750000, 2025, 'proxy', 'placeholder', 'public_site',
              ST_Multi(ST_Transform(ST_SetSRID(ST_MakeEnvelope(-3.3, 55.9, -3.1, 56.0), 4326), 27700)))
        """)
    pg.commit()
    r = client.get("/layers/georgist/resource-rent")
    assert r.status_code == 503 and "MOCK" not in r.text
    with pg.cursor() as cur:
        cur.execute("""
            INSERT INTO resource_wealth (name, annual_rent_gbp, price_year, value_tier, quality, publish_level,
                                         source_id, geom)
            VALUES ('SYNTHETIC LEASE', 20000, 2023, 'market', 'live', 'public_site', 'business_rates',
              ST_Multi(ST_Transform(ST_SetSRID(ST_MakeEnvelope(-3.3, 55.9, -3.1, 56.0), 4326), 27700)))
        """)
    pg.commit()
    body = client.get("/layers/georgist/resource-rent").json()
    assert [f["properties"]["name"] for f in body["features"]] == ["SYNTHETIC LEASE"]
    assert body["features"][0]["geometry"]["type"] == "MultiPolygon"


def test_public_site_layers_refuse_modelled_or_non_site_sources_loudly(pg, client):
    """Publication geometry rule: a proxy/modelled figure on site geometry fails the layer (500), never served."""
    with pg.cursor() as cur:
        cur.execute("""
            INSERT INTO eco_wealth (name, annual_rent_gbp, price_year, value_tier, quality, publish_level, geom)
            VALUES ('SYNTHETIC MODELLED PEAT', 5000, 2023, 'shadow', 'modelled', 'public_site',
              ST_Multi(ST_Transform(ST_SetSRID(ST_MakeEnvelope(-3.3, 55.9, -3.1, 56.0), 4326), 27700)))
        """)
    pg.commit()
    r = client.get("/layers/georgist/eco-rent")
    assert r.status_code == 500 and r.json()["detail"]["error"] == "publication_rule_violation"
    assert "5000" not in r.text
    w = client.get("/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": ZONE})
    assert w.status_code == 500 and w.json()["detail"]["error"] == "publication_rule_violation"
    with pg.cursor() as cur:
        cur.execute("UPDATE eco_wealth SET value_tier = 'market', quality = 'live', source_id = 'private_feed'")
    pg.commit()
    assert client.get("/layers/georgist/eco-rent").status_code == 500
    with pg.cursor() as cur:
        cur.execute("UPDATE eco_wealth SET source_id = 'svdls'")
    pg.commit()
    assert client.get("/layers/georgist/eco-rent").status_code == 200


def test_internal_endpoints_show_diagnostics_when_enabled(pg, surface_row, monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import create_app
    from etl.migrate_to_postgis import upsert_surface_rent

    upsert_surface_rent(pg, [surface_row()])
    monkeypatch.setenv("ENABLE_INTERNAL_ENDPOINTS", "1")
    monkeypatch.setenv("INTERNAL_API_TOKEN", "test-internal-token")
    auth = {"Authorization": "Bearer test-internal-token"}
    c = TestClient(create_app())
    row = c.get(f"/internal/georgist/surface-rent/{ZONE}", headers=auth).json()["row"]
    assert "raw_residual" in row and "typical_sale_gbp" in row
    w = c.get(
        "/internal/georgist/wealth",
        params={"lat": 55.95, "lng": -3.19, "zone_id": ZONE},
        headers=auth,
    ).json()
    assert "raw_residual" in w["wealth"]["components"][0]["diagnostics"]


def test_blocked_internal_v1_output_shape_never_reaches_public(pg, client, surface_row, monkeypatch):
    """SYNTHETIC rows shaped like Valuation's blocked v1 file: every row publication_status
    blocked, measured rows publish_level internal on a config-fallback (placeholder) yield,
    model-fill rows placeholders. Public endpoints show no value; internal views (only with
    ENABLE_INTERNAL_ENDPOINTS) show it with the yield tagged placeholder."""
    from fastapi.testclient import TestClient

    from api.main import create_app
    from etl.migrate_to_postgis import upsert_surface_rent

    def blocked(zone, **over):
        row = surface_row(zone=zone, **{"publication_status": "blocked", "publish_level": "internal",
                                        "yield_source": "config_fallback", "yield_land": 0.05, **over})
        row["proxy_tags"] = list(row["proxy_tags"] or []) + ["yield_fallback:config", "publication_blocked_surface_v1"]
        return row

    measured = blocked(ZONE)
    pending = blocked("S01008678", quality="placeholder", publish_level="public_zone", measured_rent=None,
                      measured_rent_per_dwelling=None, rent_per_res_ha=None, uncertainty_low=None,
                      uncertainty_high=None, yield_land=None)
    upsert_surface_rent(pg, [measured, pending])
    rent = f"{measured['measured_rent']:.0f}"

    layer = client.get("/layers/georgist/surface-rent")
    assert layer.status_code == 503  # nothing publishable: "not built", with the reasons and no values
    detail = layer.json()["detail"]
    assert detail["error"] == "surface_rent_not_built"
    assert detail["withheld_by_reason"] == {"blocked": 1, "placeholder": 1}
    assert rent not in layer.text

    r = client.get("/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": ZONE})
    w = r.json()["wealth"]
    c = w["components"][0]
    assert c["excluded_reason"] == "blocked" and c["withheld"] is True
    assert c["measured_rent_gbp"] is None and c["uncertainty_low"] is None and c["uncertainty_high"] is None
    assert w["totals_by_tier"] == {} and w["policy"]["policy_rent"] is None
    assert all(v["value"] is None for v in w["display"]["views"].values())
    assert "yield" not in c and "yield_land" not in r.text and "config_fallback" not in r.text
    assert rent not in r.text
    pw = client.get("/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": "S01008678"}).json()["wealth"]
    assert "surface_not_measured" in pw["flags"] and pw["totals_by_tier"] == {}

    # Internal endpoints are not mounted without the flag.
    assert client.get(f"/internal/georgist/surface-rent/{ZONE}").status_code == 404
    monkeypatch.setenv("ENABLE_INTERNAL_ENDPOINTS", "1")
    monkeypatch.setenv("INTERNAL_API_TOKEN", "test-internal-token")
    auth = {"Authorization": "Bearer test-internal-token"}
    ic = TestClient(create_app())
    row = ic.get(f"/internal/georgist/surface-rent/{ZONE}", headers=auth).json()
    assert row["yield"]["status"] == "placeholder" and row["yield"]["yield_land"] == pytest.approx(0.05)
    assert row["row"]["publication_status"] == "blocked"
    iw = ic.get(
        "/internal/georgist/wealth",
        params={"lat": 55.95, "lng": -3.19, "zone_id": ZONE},
        headers=auth,
    ).json()["wealth"]
    ic0 = iw["components"][0]
    assert ic0["yield"]["status"] == "placeholder" and "yield_placeholder_internal_only" in iw["flags"]
    assert ic0["excluded_reason"] == "blocked" and iw["totals_by_tier"] == {}  # same totals as public


def test_db_rejects_bad_enums_and_area_crosswalk(pg, surface_row):
    import psycopg2

    from etl.migrate_to_postgis import upsert_surface_rent

    for bad in ({"value_tier": "guess"}, {"quality": "mock"}, {"crosswalk_method": "footprint_area"},
                {"crosswalk_method": "pop_hhres_2022"}, {"use_basis": "hope_value"},
                {"publish_level": "public"}, {"publish_level": "blocked"}, {"publication_status": "hidden"},
                {"net_of": ["anything"]}):
        with pytest.raises(psycopg2.errors.CheckViolation):
            upsert_surface_rent(pg, [surface_row(**bad)])
        pg.rollback()


def test_planning_site_geometry_rules(pg):
    import psycopg2

    with pg.cursor() as cur:
        cur.execute("""
            INSERT INTO planning_sites (site_id, source, geom_source, geom, publish_level, dz2011_code)
            VALUES ('SYN1', 'svdls', 'point', ST_SetSRID(ST_MakePoint(325000, 673000), 27700), 'internal', 'S01008677')
        """)
    pg.commit()
    with pytest.raises(psycopg2.errors.CheckViolation):
        with pg.cursor() as cur:  # point geometry claimed as surveyed outline
            cur.execute("""
                INSERT INTO planning_sites (site_id, source, geom_source, geom, publish_level)
                VALUES ('SYN2', 'hla', 'surveyed', ST_SetSRID(ST_MakePoint(325000, 673000), 27700), 'public_zone')
            """)
    pg.rollback()


# --------------------------------------------------------------------------- zone lookup

def _insert_square(conn, code, vintage, x0, y0, size=1_000, name=None):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO dz_boundaries (code, vintage, name, geom, source_id, licence) VALUES "
            "(%s, %s, %s, ST_Multi(ST_MakeEnvelope(%s, %s, %s, %s, 27700)), 'SYNTHETIC', 'synthetic-test-only')",
            (code, vintage, name, x0, y0, x0 + size, y0 + size),
        )
    conn.commit()


def test_postgis_zone_lookup(pg, client):
    from pyproj import Transformer

    lat, lon = 55.9533, -3.1883
    x, y = Transformer.from_crs(4326, 27700, always_xy=True).transform(lon, lat)
    _insert_square(pg, "S01008677", 2011, x - 500, y - 500, name="Synthetic A")
    _insert_square(pg, "S01016000", 2022, x - 500, y - 500, name="Synthetic B")
    r = client.get("/layers/context/data-zones/at", params={"lat": lat, "lon": lon})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "postgis:dz_boundaries"
    assert (body["code"], body["vintage"], body["name"]) == ("S01008677", 2011, "Synthetic A")
    assert body["dz2022"]["code"] == "S01016000"
    assert body["dz2011"]["on_boundary"] is False

    # Miss -> 404 (boundaries loaded, nothing there)
    r = client.get("/layers/context/data-zones/at", params={"lat": 57.5, "lon": -4.2})
    assert r.status_code == 404


def test_postgis_zone_lookup_on_boundary_and_db_constraint(pg, client):
    import psycopg2.errors
    from pyproj import Transformer

    lat, lon = 55.9533, -3.1883
    x, y = Transformer.from_crs(4326, 27700, always_xy=True).transform(lon, lat)
    _insert_square(pg, "S01008677", 2011, x - 1_000, y - 500)
    _insert_square(pg, "S01008678", 2011, x, y - 500)
    body = client.get("/layers/context/data-zones/at", params={"lat": lat, "lon": lon}).json()
    assert body["dz2011"]["on_boundary"] is True
    # A 2022-range code labelled 2011 is refused by the table itself.
    with pytest.raises(psycopg2.errors.CheckViolation):
        _insert_square(pg, "S01016000", 2011, 0, 0)
    pg.rollback()


def test_empty_boundaries_table_falls_through_to_503(pg, client, tmp_path, monkeypatch):
    from georgist import dz_lookup

    monkeypatch.setattr(dz_lookup, "PROCESSED_DIR", tmp_path)
    r = client.get("/layers/context/data-zones/at", params={"lat": 55.95, "lon": -3.19})
    assert r.status_code == 503
    assert "db: dz_boundaries is empty" in r.json()["detail"]["reasons"]


def test_display_views_from_dz_denominators(pg, client, surface_row):
    from etl.migrate_to_postgis import upsert_surface_rent

    row = surface_row()
    upsert_surface_rent(pg, [row, surface_row(zone="S01008679")])
    with pg.cursor() as cur:
        cur.execute("INSERT INTO dz_denominators (code, vintage, settlement_area_ha) VALUES (%s, 2011, 40)", (ZONE,))
    _dz_zone(pg, ZONE, 2011, population=900, pop_year=2025)  # SYNTHETIC: real 2025 population does not exist
    _dz_dwellings(pg, ZONE, 2011, 2025, row["dwellings"])
    pg.commit()
    w = client.get("/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": ZONE}).json()["wealth"]
    views = w["display"]["views"]
    assert views["per_residential_hectare"]["status"] == "interim_rough"
    assert views["per_residential_hectare"]["value"] == pytest.approx(row["measured_rent"] / 40, abs=0.01)
    assert views["per_dwelling"]["value"] == pytest.approx(row["measured_rent"] / row["dwellings"], abs=0.01)
    assert views["per_resident"]["value"] == pytest.approx(row["measured_rent"] / 900, abs=0.01)
    layer = client.get("/layers/georgist/surface-rent").json()
    assert layer["views"]["default"] == "per_residential_hectare"
    assert layer["data"][ZONE]["rent_per_residential_ha_status"] == "interim_rough"
    assert layer["data"]["S01008679"]["rent_per_residential_ha_status"] == "denominator_pending"
    assert layer["data"]["S01008679"]["rent_per_residential_ha"] is None
    assert layer["views"]["status_counts"]["per_residential_hectare"] == {"interim_rough": 1, "denominator_pending": 1}


def test_valuation_residential_land_and_second_homes_on_row(pg, client, make_valuation_row):
    """Valuation 687cf43 carries residential_land_ha / rent_per_res_ha / shares on the row; they win."""
    from etl.migrate_to_postgis import upsert_surface_rent
    from georgist.wealth_schema import to_db_row

    rough = to_db_row(make_valuation_row(250_000, code=ZONE, residential_land_ha=25.0,
                                         residential_land_source="settlement_area", second_home_share=0.3,
                                         vacant_share=0.05))
    upsert_surface_rent(pg, [rough])
    w = client.get("/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": ZONE}).json()["wealth"]
    v = w["display"]["views"]
    assert v["per_residential_hectare"]["status"] == "interim_rough"
    assert v["per_residential_hectare"]["value"] == pytest.approx(rough["rent_per_res_ha"], abs=0.01)
    assert v["per_resident"]["second_home_share"] == 0.3 and v["per_resident"]["vacant_share"] == 0.05
    layer = client.get("/layers/georgist/surface-rent").json()["data"][ZONE]
    assert layer["rent_per_residential_ha_status"] == "interim_rough"
    assert "proxy_tags" not in layer and "res_land_rough" in layer


def test_counts_join_count_year_equals_price_year_and_vintage(pg, client, make_valuation_row):
    """Dwellings and population: count_year = price_year, same vintage; never another year."""
    import psycopg2.errors

    from etl.migrate_to_postgis import upsert_surface_rent
    from georgist.wealth_schema import to_db_row

    row = to_db_row(make_valuation_row(250_000, code=ZONE))  # price_year 2025
    upsert_surface_rent(pg, [row])
    # Wrong-year counts only: must NOT be used.
    _dz_zone(pg, ZONE, 2011, population=950, pop_year=2022)
    _dz_dwellings(pg, ZONE, 2011, 2024, 480)
    pg.commit()
    params = {"lat": 55.95, "lng": -3.19, "zone_id": ZONE}
    w = client.get("/georgist/wealth", params=params).json()["wealth"]
    assert w["display"]["views"]["per_dwelling"]["value"] is None
    assert w["display"]["views"]["per_resident"]["value"] is None
    assert {"dwellings_count_missing_for_price_year", "population_count_missing_for_price_year"} <= set(w["flags"])
    layer = client.get("/layers/georgist/surface-rent").json()["data"][ZONE]
    assert layer["rent_per_dwelling"] is None and layer["rent_per_resident"] is None
    assert set(layer["denominator_flags"]) == {"dwellings_count_missing_for_price_year",
                                               "population_count_missing_for_price_year"}
    # A count labelled with the other vintage cannot exist for this code (CHECK), so no cross-vintage fill;
    # a text vintage cannot be stored at all.
    for bad in (2022, "DZ2011"):
        with pytest.raises((psycopg2.errors.CheckViolation, psycopg2.errors.InvalidTextRepresentation,
                            psycopg2.errors.ForeignKeyViolation)):
            _dz_dwellings(pg, ZONE, bad, 2025, 1)
        pg.rollback()
    # Same-year, same-vintage counts are used.
    _dz_zone(pg, ZONE, 2011, population=1000, pop_year=2025)  # SYNTHETIC 2025 population
    _dz_dwellings(pg, ZONE, 2011, 2025, 500, assessor=777)
    pg.commit()
    w = client.get("/georgist/wealth", params=params).json()["wealth"]
    v = w["display"]["views"]
    assert v["per_dwelling"]["value"] == pytest.approx(row["measured_rent"] / 500, abs=0.01)  # not 777
    assert v["per_dwelling"]["denominator_source"] == "datazones.dwellings_by_year.dwellings_total"
    assert v["per_resident"]["value"] == pytest.approx(row["measured_rent"] / 1000, abs=0.01)
    assert not {"dwellings_count_missing_for_price_year", "population_count_missing_for_price_year"} & set(w["flags"])


def _dwellings_total(code, vintage, year):
    import csv

    from paths import PROCESSED_DIR

    with open(PROCESSED_DIR / "datazones" / "dwellings_by_year.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            if (r["code"], r["vintage"], r["count_year"]) == (code, str(vintage), str(year)):
                return int(r["dwellings_total"]), int(r["assessor_dwellings_dec"])
    raise AssertionError(f"no dwellings_by_year row for {code} {vintage} {year}")


def test_real_datazones_dwellings_at_price_year_and_population_pending(pg, client, make_valuation_row,
                                                                      datazones_root):
    """REAL Data Zones data (loaded with etl.load_processed): 2025 money year.

    * per dwelling divides by dwellings_by_year.dwellings_total for count_year 2025 (not assessor_dwellings_dec);
    * per resident is PENDING: population exists only for mid-2022 (2011 zones) and mid-2024 (2022 zones),
      and is never borrowed from another year;
    * 2022 zones have dwellings for 2024-2025 only, so a 2023 money year on a 2022 zone is flagged.
    The surface rows are SYNTHETIC.
    """
    from etl import load_processed as lp
    from etl.migrate_to_postgis import upsert_surface_rent
    from georgist.wealth_schema import to_db_row
    from paths import PROCESSED_DIR

    lp.load(pg, lp.validate(datazones_root, "datazones"))
    z22 = "S01016000"  # a 2022 zone (Dunbar West - 06)
    r11 = to_db_row(make_valuation_row(250_000, code=ZONE))
    r22 = {**r11, "code": z22, "vintage": 2022}  # SYNTHETIC copy on a 2022 zone
    assert r11["price_year"] == r22["price_year"] == 2025 and r22["vintage"] == 2022
    upsert_surface_rent(pg, [r11, r22])
    pg.commit()
    for code, vintage, row in ((ZONE, 2011, r11), (z22, 2022, r22)):
        total, assessor = _dwellings_total(code, vintage, 2025)
        assert total != assessor  # the test can tell the two series apart
        body = client.get("/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": code}).json()
        assert body["zone"]["vintage"] == vintage
        w = body["wealth"]
        v = w["display"]["views"]
        assert v["per_dwelling"]["status"] == "ok" and v["per_dwelling"]["denominator_value"] == total
        assert v["per_dwelling"]["value"] == pytest.approx(row["measured_rent"] / total, abs=0.01)
        assert v["per_dwelling"]["denominator_year"] == 2025
        assert v["per_resident"]["status"] == "denominator_pending" and v["per_resident"]["value"] is None
        assert "population_count_missing_for_price_year" in w["flags"]
        assert "dwellings_count_missing_for_price_year" not in w["flags"]
    layer = client.get("/layers/georgist/surface-rent", params={"vintage": 2022}).json()
    assert layer["vintage"] == 2022 and layer["data"][z22]["rent_per_resident"] is None
    flags22 = layer["data"][z22]["denominator_flags"]
    assert "population_count_missing_for_price_year" in flags22
    assert "dwellings_count_missing_for_price_year" not in flags22
    assert "dwellings_differ_from_valuation_row" in flags22  # SYNTHETIC own count 500 vs Data Zones 329
    # 2023 money year on a 2022 zone: no 2023 dwellings exist for 2022 zones; never taken from 2024.
    with pg.cursor() as cur:
        cur.execute("UPDATE surface_rent_dz SET price_year = 2023 WHERE code = %s", (z22,))
    pg.commit()
    w = client.get("/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": z22}).json()["wealth"]
    assert w["display"]["views"]["per_dwelling"]["value"] is None
    assert {"dwellings_count_missing_for_price_year", "population_count_missing_for_price_year"} <= set(w["flags"])


def test_mixed_price_years_fail_loudly_via_api(pg, client, surface_row):
    from etl.migrate_to_postgis import upsert_surface_rent

    upsert_surface_rent(pg, [surface_row()])  # proxy tier, price_year 2025
    with pg.cursor() as cur:  # two measured site rows (site-public sources), market tier, different years
        for name, year, src in (("SYNTHETIC RATES", 2025, "business_rates"), ("SYNTHETIC SITE", 2023, "svdls")):
            cur.execute("""
                INSERT INTO eco_wealth (name, annual_rent_gbp, price_year, value_tier, quality, publish_level,
                                        source_id, geom)
                VALUES (%s, 5000, %s, 'market', 'live', 'public_site', %s,
                  ST_Multi(ST_Transform(ST_SetSRID(ST_MakeEnvelope(-3.3, 55.9, -3.1, 56.0), 4326), 27700)))
            """, (name, year, src))
    pg.commit()
    r = client.get("/georgist/wealth", params={"lat": 55.95, "lng": -3.19, "zone_id": ZONE})
    assert r.status_code == 500
    assert r.json()["detail"]["error"] == "mixed_price_years"
    assert r.json()["detail"]["price_years"] == [2023, 2025]


def test_zero_dwellings_zone_with_old_ros_sales_is_not_applicable(pg, client, make_valuation_row, datazones_root):
    """Rules v0.7: S01010227 (Sighthill - 03, cleared) has 0 dwellings but still has RoS price rows.

    REAL Data Zones data: its zone_spine `flags` cell is the multi-flag string
    'no_census2022_household_residents;zero_dwellings;pop_dwellings_mismatch'. The SYNTHETIC
    surface row carries a rent from old sales; the API must return null + 'not applicable', never a
    rent and never 0.
    """
    import csv

    from etl import load_processed as lp
    from etl.migrate_to_postgis import upsert_surface_rent
    from georgist.wealth_schema import to_db_row
    from paths import PROCESSED_DIR

    zone = "S01010227"
    with open(PROCESSED_DIR / "dz2011_prices.csv", newline="") as fh:
        assert any(r["dz2011"] == zone for r in csv.DictReader(fh))  # RoS price rows exist
    lp.load(pg, lp.validate(datazones_root, "datazones"))
    with pg.cursor() as cur:
        cur.execute("SELECT flags, dwellings FROM datazones.zone_spine WHERE code = %s AND vintage = 2011", (zone,))
        flags, dwellings = cur.fetchone()
        assert {"zero_dwellings", "pop_dwellings_mismatch"} <= set(flags.split(";")) and dwellings == 0
    row = to_db_row(make_valuation_row(180_000, code=zone))  # SYNTHETIC rent "from old sales"
    assert row["measured_rent"] > 0
    upsert_surface_rent(pg, [row, to_db_row(make_valuation_row(250_000, code=ZONE))])
    pg.commit()
    body = client.get("/georgist/wealth", params={"lat": 55.87, "lng": -4.24, "zone_id": zone}).json()
    w = body["wealth"]
    comp = next(c for c in w["components"] if c["layer"] == "surface")
    assert comp["measured_rent_gbp"] is None and comp["status"] == "not_applicable"
    assert comp["uncertainty_low"] is None and comp["in_totals"] is False and comp["excluded_reason"] == "zero_dwellings"
    assert "zero_dwellings" in w["flags"]
    assert all(t.get("total_gbp") in (None, 0.0) and t.get("components", 0) == 0
               for t in w["totals_by_tier"].values())  # nothing summed, no surface 0 counted
    assert all(v["status"] == "not_applicable" and v["value"] is None for v in w["display"]["views"].values())
    assert w["policy"]["policy_rent"] is None and w["attribution"]["infra_share"] is None
    layer = client.get("/layers/georgist/surface-rent").json()
    z = layer["data"][zone]
    assert z["status"] == "not_applicable" and z["measured_rent"] is None and z["measured_rent_per_dwelling"] is None
    assert z["rent_per_dwelling"] is None and z["rent_per_residential_ha"] is None and z["rent_per_res_ha"] is None
    assert z["denominator_flags"] == ["zero_dwellings"] and layer["zero_dwellings"] == [zone]
    assert layer["data"][ZONE]["status"] == "ok" and layer["data"][ZONE]["measured_rent"] > 0


def test_nrs_settlements_bbox_when_loaded(pg, client):
    """SYNTHETIC NRS settlement polygon → bbox 200 with features."""
    with pg.cursor() as cur:
        cur.execute(
            """
            INSERT INTO nrs_settlements (code, name, popcount, area_m2, geom)
            VALUES (
              'S53009999', 'SYNTHETIC Settlement', 1200, 500000,
              ST_Multi(ST_SetSRID(ST_MakeEnvelope(-4.30, 55.84, -4.22, 55.88), 4326))
            )
            ON CONFLICT (code) DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO nrs_localities (code, name, popcount, area_m2, geom)
            VALUES (
              'S52009999', 'SYNTHETIC Locality', 800, 200000,
              ST_Multi(ST_SetSRID(ST_MakeEnvelope(-4.29, 55.85, -4.23, 55.87), 4326))
            )
            ON CONFLICT (code) DO NOTHING
            """
        )
    pg.commit()
    r = client.get(
        "/layers/open/settlements",
        params={"south": 55.84, "west": -4.30, "north": 55.88, "east": -4.22},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["meta"]["ok"] is True
    assert any(f["properties"]["code"] == "S53009999" for f in body["features"])
    r2 = client.get(
        "/layers/open/localities",
        params={"south": 55.84, "west": -4.30, "north": 55.88, "east": -4.22},
    )
    assert r2.status_code == 200, r2.text
    assert any(
        f["properties"]["code"] == "S52009999" for f in r2.json()["features"]
    )
