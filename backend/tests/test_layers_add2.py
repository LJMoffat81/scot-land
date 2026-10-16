"""LAYERS-ADD-2 acceptance checks A1–A13 and council-direct D1–D7.

Mutation notes sit next to the assertion they protect. Do not weaken these.
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.platform_routes import router
from georgist.surface_v14 import v14_config
from harvesters.council_direct import ingest_council_features
from layers.layer_flags import derive_public
from layers.layers_add2_catalog import (
    DROPPED_LAYER_IDS,
    DZ2022_COUNT,
    LICENCE_STATUSES,
    council_source_entries,
    dz2022_zone_ids,
    layers_add2_entries,
    public_sweep_entries,
    sweep_entries,
    validate_entry,
)
from layers.layers_add2_pipeline import (
    AGG_COLUMNS,
    EPC_COLUMN_ALLOWLIST,
    aggregate_point_density,
    assert_full_dz2022,
    assert_no_currency_columns,
    assert_no_uprn_export,
    assert_style_urls_free,
    coverage_legend,
    filter_tile_properties,
    public_site_export,
    rollup_council_measure,
    rollup_ofcom,
    run_epc_job,
    serve_lonlat,
)
from layers.layers_add_catalog import layers_add_entries

REPO = Path(__file__).resolve().parents[2]
FRONTEND_CREDITS = REPO / "frontend" / "lib" / "layersAdd2Credits.ts"
STATUSES = ("ogl", "confirmed", "unconfirmed", "open_other", "prohibited")


def test_a1_catalog_completeness():
    rows = layers_add2_entries()
    assert rows
    for row in rows:
        problems = validate_entry(row)
        assert not problems, f"{row['layer_id']}: {problems}"
        assert row["licence_status"] in LICENCE_STATUSES
        assert row["licence_url"]
        assert row["attribution"]
        assert "internal_only" in row


def test_a1_rejects_open_and_missing_internal_only():
    # Mutation: licence_status "open", or dropping internal_only, fails validation.
    row = dict(sweep_entries()[0])
    row["licence_status"] = "open"
    row["public"] = True
    problems = validate_entry(row)
    assert any("licence_status" in problem for problem in problems)
    incomplete = dict(sweep_entries()[0])
    del incomplete["internal_only"]
    problems = validate_entry(incomplete)
    assert any("internal_only" in problem for problem in problems)


def test_a1_dropped_rows_are_absent():
    ids = {row["layer_id"] for row in layers_add2_entries()}
    assert "os_open_zoomstack" not in ids
    assert "ts_trunk_rail_ferry" not in ids
    assert set(DROPPED_LAYER_IDS) == {"os_open_zoomstack", "ts_trunk_rail_ferry"}


def test_a2_public_derivation_matrix():
    # Mutation: drop the `not internal_only` clause and the True cases go public.
    for status in STATUSES:
        for flag_on in (False, True):
            for internal_only in (False, True):
                got = derive_public(
                    status,
                    "LAYER_X_ENABLED",
                    flag_on=flag_on,
                    internal_only=internal_only,
                )
                if internal_only or status in {"prohibited", "unconfirmed"}:
                    assert got is False
                elif status in {"ogl", "confirmed", "open_other"}:
                    assert got is flag_on
                else:
                    assert got is False
    uprn = next(row for row in sweep_entries() if row["layer_id"] == "os_open_uprn")
    assert uprn["internal_only"] is True
    assert uprn["public"] is False
    assert derive_public("prohibited", None, internal_only=False) is False
    assert derive_public("ogl", None, internal_only=True) is False


def _epc_fixture() -> tuple[list[dict], dict[str, str], list[str]]:
    zones = dz2022_zone_ids()
    small = zones[0]
    large = zones[1]
    lookup = {"EH1 1AA": small, "G1 1AA": large}
    records = []
    for _ in range(3):
        records.append(
            {
                "ADDRESS1": "1 High Street",
                "ADDRESS2": "Flat 2",
                "POSTTOWN": "Edinburgh",
                "POSTCODE": "EH1 1AA",
                "UPRN": "123456789",
                "OSG_REFERENCE_NUMBER": "NT2573",
                "BUILDING_REFERENCE_NUMBER": "B-9",
                "REPORT_REFERENCE_NUMBER": "R-9",
                "LODGEMENT_NOTES": "free text about the kitchen",
                "TOTAL_FLOOR_AREA": "80",
                "PROPERTY_TYPE": "Flat",
                "CONSTRUCTION_AGE_BAND": "1990-1999",
                "CURRENT_ENERGY_RATING": "C",
            }
        )
    for index in range(5):
        records.append(
            {
                "ADDRESS1": "2 High Street",
                "POSTCODE": "G1 1AA",
                "UPRN": "987654321",
                "TOTAL_FLOOR_AREA": str(50 + index),
                "PROPERTY_TYPE": "House",
                "CONSTRUCTION_AGE_BAND": "2000-2009",
                "CURRENT_ENERGY_RATING": "B",
            }
        )
    return records, lookup, zones


def test_a3_epc_address_strip_before_write():
    # Mutation: add POSTCODE to EPC_COLUMN_ALLOWLIST and this assertion fails.
    assert "POSTCODE" not in EPC_COLUMN_ALLOWLIST
    records, lookup, zones = _epc_fixture()
    raw_blob = "1 High Street, EH1 1AA, UPRN 123456789"
    conn = run_epc_job(records, lookup, zones=zones[:2], raw_blob=raw_blob)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "epc_staging" not in tables
    stored = " ".join(
        str(value)
        for row in conn.execute("SELECT * FROM agg_epc")
        for value in row
        if value is not None
    )
    for banned in (
        "High Street",
        "EH1 1AA",
        "123456789",
        "NT2573",
        "free text",
        raw_blob,
    ):
        assert banned not in stored


def test_a4_epc_aggregates_only_and_small_cells_suppressed():
    records, lookup, zones = _epc_fixture()
    conn = run_epc_job(records, lookup, zones=zones[:4])
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"agg_epc"}
    small = conn.execute(
        "SELECT * FROM agg_epc WHERE zone_id = ?",
        (zones[0],),
    ).fetchone()
    assert small["suppressed"] == 1
    assert small["certificate_count"] is None
    assert small["median_floor_area_m2"] is None
    assert small["median_epc_band"] is None
    large = conn.execute(
        "SELECT * FROM agg_epc WHERE zone_id = ?",
        (zones[1],),
    ).fetchone()
    assert large["suppressed"] == 0
    assert large["certificate_count"] == 5
    assert large["median_epc_band"] == "B"
    assert_full_dz2022(
        [
            {"zone_id": row["zone_id"], "dz_vintage": row["dz_vintage"]}
            for row in run_epc_job(records, lookup).execute("SELECT zone_id, dz_vintage FROM agg_epc")
        ]
    )


def test_a5_uprn_never_published():
    # Mutation: set os_open_uprn internal_only false and the public assertion fails.
    uprn = next(row for row in sweep_entries() if row["layer_id"] == "os_open_uprn")
    assert uprn["internal_only"] is True
    assert uprn["public"] is False
    rows = aggregate_point_density({}, {})
    assert_no_uprn_export(AGG_COLUMNS["agg_uprn_density"], rows)
    leaked = [{"zone_id": "S01013482", "uprn": "123456"}]
    with pytest.raises(ValueError):
        assert_no_uprn_export(["zone_id", "uprn"], leaked)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/tiles/os_open_uprn/10/1/1").status_code == 404
    assert client.get("/layers/add/viewport/os_open_uprn?south=55&west=-4&north=56&east=-3").status_code == 404
    assert client.get("/layers/add/agg/agg_uprn_density").status_code == 404


def test_a6_tile_allowlist_rejects_extra_properties():
    kept = filter_tile_properties("os_open_roads", {"road_class": "A"})
    assert kept == {"road_class": "A"}
    with pytest.raises(ValueError):
        filter_tile_properties("os_open_roads", {"road_class": "A", "address": "1 High Street"})
    for layer_id, allow in (
        ("os_open_greenspace", frozenset({"function_code"})),
        ("os_open_rivers", frozenset({"watercourse_type"})),
        ("fls_estate", frozenset({"estate_part"})),
        ("ces_assets", frozenset({"asset_class"})),
    ):
        assert filter_tile_properties(layer_id, {next(iter(allow)): "x"})


def test_a7_strict_keys_cover_7392_zones():
    zones = dz2022_zone_ids()
    assert len(zones) == DZ2022_COUNT == 7392
    rows = [
        {"zone_id": zone_id, "dz_vintage": 2022, "coverage": "uncovered", "source_council": "S12000049"}
        for zone_id in zones
    ]
    assert_full_dz2022(rows)
    with pytest.raises(ValueError):
        assert_full_dz2022([{"zone_id": "unknown", "dz_vintage": 2022}])
    with pytest.raises(ValueError):
        assert_full_dz2022([{"zone_id": None, "dz_vintage": 2022}])


def test_a8_ofcom_split_oa_weights():
    weights = [
        ("S00000001", dz2022_zone_ids()[0], 0.4),
        ("S00000001", dz2022_zone_ids()[1], 0.6),
    ]
    rows = rollup_ofcom(
        [{"oa": "S00000001", "premises": 100, "full_fibre": 0.5, "gigabit": 0.2, "below_10": 0.1}],
        weights,
    )
    by_zone = {row["zone_id"]: row for row in rows}
    assert abs(by_zone[dz2022_zone_ids()[0]]["premises"] - 40) < 1e-9
    assert abs(by_zone[dz2022_zone_ids()[1]]["premises"] - 60) < 1e-9
    assert abs(sum(row["premises"] for row in rows) - 100) < 1e-6
    with pytest.raises(ValueError):
        rollup_ofcom(
            [{"oa": "S00000001", "premises": 100, "full_fibre": 1, "gigabit": 1, "below_10": 0}],
            [("S00000001", dz2022_zone_ids()[0], 0.4)],
        )


def test_a9_served_coordinates_are_lonlat():
    lon, lat = serve_lonlat(327000, 673000, 27700)
    assert abs(lon) <= 180
    assert abs(lat) <= 90
    assert abs(lon - 327000) > 1
    with pytest.raises(ValueError):
        serve_lonlat(327000, 673000, 4326)


def test_a10_public_layers_have_credits_when_visible():
    text = FRONTEND_CREDITS.read_text(encoding="utf-8")
    attribution_line = (REPO / "frontend" / "lib" / "mapAttributionLine.ts").read_text(encoding="utf-8")
    licences = (REPO / "frontend" / "lib" / "layerLicenceCredits.ts").read_text(encoding="utf-8")
    assert "layersAdd2Credit" in attribution_line
    assert "LAYERS_ADD2_CREDITS" in licences
    for row in public_sweep_entries():
        assert row["attribution"] in text, row["layer_id"]
    uprn = next(row for row in sweep_entries() if row["layer_id"] == "os_open_uprn")
    assert f'{uprn["layer_id"]}:' not in text


def test_a11_no_currency_and_v14_snapshot_unchanged():
    assert_no_currency_columns()
    before = json.dumps(v14_config(), sort_keys=True, default=str)
    records, lookup, zones = _epc_fixture()
    run_epc_job(records, lookup, zones=zones[:2])
    after = json.dumps(v14_config(), sort_keys=True, default=str)
    assert before == after
    migration = (
        REPO / "backend" / "alembic" / "versions" / "20261016_0024_candidates_v15_add2.py"
    ).read_text(encoding="utf-8")
    assert "candidates_v15" in migration
    for token in ("gbp", "rent", "price"):
        assert token not in migration.lower()


def test_a12_external_ignored_and_harvester_has_no_terms_automation():
    result = subprocess.run(
        ["git", "check-ignore", "data/external/epc_domestic/raw.7z"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files", "data/external"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    assert tracked.stdout.strip() == ""
    path = REPO / "backend" / "harvesters" / "council_direct.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in {"httpx", "requests", "urllib", "aiohttp"}
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in {"httpx", "requests", "urllib", "aiohttp"}
    text = path.read_text(encoding="utf-8").lower()
    for banned in ("import httpx", "import requests", "urllib.request", "/login", "authkey"):
        assert banned not in text


def test_a13_style_rejects_keyed_endpoint():
    assert_style_urls_free(
        [
            "https://tiles.openfreemap.org/styles/positron",
            "https://tiles.openfreemap.org/styles/liberty",
        ]
    )
    with pytest.raises(ValueError):
        assert_style_urls_free(["https://tiles.example/style.json?key=secret"])


def test_spatial_hub_ldp_and_hls_stay_flagged():
    flagged = {
        row["layer_id"]
        for row in layers_add_entries()
        if row.get("flag_name") and not row["public"]
    }
    assert "ldp_allocations" in flagged
    assert "housing_land_supply" in flagged
    assert "sepa_frm_maps" in flagged


def test_d1_prohibited_licence_is_not_loaded():
    # Mutation: skip licence_status_from_license_info and loaded becomes true.
    result = ingest_council_features(
        {"licenseInfo": "© Council, all rights reserved, no reuse"},
        [{"vintage": "2024", "zone_id": "S01013482", "hectares": 1}],
    )
    assert result["loaded"] is False
    assert result["licence_status"] == "prohibited"
    assert result["features"] == []
    blank = ingest_council_features(
        {"licenseInfo": ""},
        [{"vintage": "2024", "zone_id": "S01013482"}],
    )
    assert blank["loaded"] is True
    assert blank["licence_status"] == "open_other"


def test_d2_uncovered_is_not_zero():
    # Mutation: fillna(0) makes hectares 0 and this fails.
    zones = dz2022_zone_ids()[:2]
    rows = rollup_council_measure(
        zones_by_council={"S12000033": zones},
        covered_councils=set(),
        sites=[],
    )
    assert rows
    for row in rows:
        assert row["coverage"] == "uncovered"
        assert row["hectares"] is None
        assert row["site_count_label"] is None
        legend = coverage_legend(row)
        assert legend["label"] == "no open data"
        assert legend["fill"] == "#bdbdbd"
        assert legend["label"] != "no allocation"


def test_d3_covered_empty_zone_is_zero():
    zone = dz2022_zone_ids()[0]
    rows = rollup_council_measure(
        zones_by_council={"S12000049": [zone]},
        covered_councils={"S12000049"},
        sites=[],
    )
    assert len(rows) == 1
    assert rows[0]["coverage"] == "covered"
    assert rows[0]["site_count_label"] == "0"
    assert rows[0]["hectares"] == 0.0


def test_d4_small_counts_hide_area_for_vdl_and_contaminated():
    # Mutation: SMALL_SITE_MIN 3 → 2 lets the 2-site zone publish hectares.
    zones = dz2022_zone_ids()
    zone_a = zones[0]
    zone_b = zones[1]
    sites = [
        {"zone_id": zone_a, "hectares": 1.0, "site_name": "Secret yard", "site_ref": "V1"},
        {"zone_id": zone_a, "hectares": 2.1, "site_name": "Other yard", "owner": "A Person"},
        {"zone_id": zone_b, "hectares": 1.0},
        {"zone_id": zone_b, "hectares": 1.0},
        {"zone_id": zone_b, "hectares": 1.5},
    ]
    rows = rollup_council_measure(
        zones_by_council={"S12000049": [zone_a, zone_b]},
        covered_councils={"S12000049"},
        sites=sites,
    )
    by_zone = {row["zone_id"]: row for row in rows}
    assert by_zone[zone_a]["site_count_label"] == "<3"
    assert by_zone[zone_a]["hectares"] is None
    assert by_zone[zone_b]["site_count_label"] == "3"
    assert by_zone[zone_b]["hectares"] == 3.5
    exported = json.dumps(public_site_export(rows))
    assert "3.1" not in exported
    assert "Secret yard" not in exported
    assert "site_name" not in exported
    contam = rollup_council_measure(
        zones_by_council={"S12000049": [zone_a]},
        covered_councils={"S12000049"},
        sites=sites[:2],
    )
    assert contam[0]["hectares"] is None
    assert contam[0]["site_count_label"] == "<3"


def test_use_class_two_sites_hides_area():
    """A class with 2 sites is "<3" and a null area. V&DL and contaminated cannot skip it."""
    zone = dz2022_zone_ids()[0]
    sites = [
        {"zone_id": zone, "hectares": 1.25, "use_class": "derelict"},
        {"zone_id": zone, "hectares": 2.0, "use_class": "derelict"},
    ]
    for measure in ("vdl", "contaminated"):
        rows = rollup_council_measure(
            zones_by_council={"S12000049": [zone]},
            covered_councils={"S12000049"},
            sites=sites,
            use_class=True,
            measure=measure,
        )
        assert len(rows) == 1
        assert rows[0]["use_class"] == "derelict"
        assert rows[0]["site_count_label"] == "<3"
        assert rows[0]["hectares"] is None
        assert rows[0]["total_hectares"] is None


def test_class_rollup_hides_total_when_one_class_is_hidden():
    """One hidden class nulls the zone total. None hidden, and the total shows.

    Site counts stay as published. Unconditional: fixture zones only.
    """
    zone = dz2022_zone_ids()[0]
    hidden = rollup_council_measure(
        zones_by_council={"S12000049": [zone]},
        covered_councils={"S12000049"},
        sites=[
            {"zone_id": zone, "hectares": 4.0, "use_class": "vacant"},
            {"zone_id": zone, "hectares": 4.0, "use_class": "vacant"},
            {"zone_id": zone, "hectares": 4.0, "use_class": "vacant"},
            {"zone_id": zone, "hectares": 1.25, "use_class": "derelict"},
        ],
        use_class=True,
        measure="vdl",
    )
    by_class = {row["use_class"]: row for row in hidden}
    assert by_class["derelict"]["site_count_label"] == "<3"
    assert by_class["derelict"]["hectares"] is None
    assert by_class["vacant"]["site_count_label"] == "3"
    assert by_class["vacant"]["hectares"] == 12.0
    assert by_class["vacant"]["total_hectares"] is None
    assert by_class["derelict"]["total_hectares"] is None

    shown = rollup_council_measure(
        zones_by_council={"S12000049": [zone]},
        covered_councils={"S12000049"},
        sites=[
            {"zone_id": zone, "hectares": 4.0, "use_class": "vacant"},
            {"zone_id": zone, "hectares": 4.0, "use_class": "vacant"},
            {"zone_id": zone, "hectares": 4.0, "use_class": "vacant"},
            {"zone_id": zone, "hectares": 1.0, "use_class": "derelict"},
            {"zone_id": zone, "hectares": 1.0, "use_class": "derelict"},
            {"zone_id": zone, "hectares": 1.0, "use_class": "derelict"},
        ],
        use_class=True,
        measure="vdl",
    )
    by_class = {row["use_class"]: row for row in shown}
    assert by_class["vacant"]["site_count_label"] == "3"
    assert by_class["derelict"]["site_count_label"] == "3"
    assert by_class["vacant"]["hectares"] == 12.0
    assert by_class["derelict"]["hectares"] == 3.0
    assert by_class["vacant"]["total_hectares"] == 15.0
    assert by_class["derelict"]["total_hectares"] == 15.0


def test_d5_no_site_polygons_or_site_fields():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/tiles/vdl_glasgow_city/10/1/1").status_code == 404
    assert client.get("/tiles/ldp_highland/10/1/1").status_code == 404
    exported = public_site_export(
        [
            {
                "zone_id": "S01013482",
                "hectares": 1.0,
                "site_name": "Yard",
                "site_ref": "1",
                "owner": "Someone",
                "address": "1 High Street",
                "geometry": {"type": "Polygon"},
            }
        ]
    )
    assert set(exported[0]) == {"zone_id", "hectares"}


def test_d6_latest_vintage_only():
    result = ingest_council_features(
        {"licenseInfo": "Open Government Licence 3.0"},
        [
            {"vintage": "2020", "zone_id": "S01013482", "hectares": 9},
            {"vintage": "2020", "zone_id": "S01013482", "hectares": 9},
            {"vintage": "2024", "zone_id": "S01013482", "hectares": 1},
        ],
    )
    assert result["loaded"] is True
    assert result["licence_status"] == "ogl"
    assert len(result["features"]) == 1
    assert result["features"][0]["vintage"] == "2024"
    rolled = rollup_council_measure(
        zones_by_council={"S12000049": ["S01013482"]},
        covered_councils={"S12000049"},
        sites=result["features"],
    )
    assert rolled[0]["site_count_label"] == "<3"
    assert rolled[0]["hectares"] is None


def test_d7_every_zone_is_covered_or_uncovered():
    zones = dz2022_zone_ids()
    covered_zones = zones[:10]
    rows = rollup_council_measure(
        zones_by_council={
            "S12000049": covered_zones,
            "S12000033": zones[10:],
        },
        covered_councils={"S12000049"},
        sites=[],
    )
    assert len(rows) == DZ2022_COUNT
    assert_full_dz2022(rows)
    for row in rows:
        assert row["coverage"] in {"covered", "uncovered"}
        assert row["source_council"]
    covered = [row for row in rows if row["coverage"] == "covered"]
    assert len(covered) == 10
    assert all(row["site_count_label"] == "0" for row in covered)


def test_council_sources_match_the_indexed_table():
    rows = council_source_entries()
    ldp = [row for row in rows if row["source_kind"] == "ldp"]
    vdl = [row for row in rows if row["source_kind"] == "vdl"]
    assert len(ldp) == 4
    assert len(vdl) == 10
    assert all(row["internal_only"] is True and row["public"] is False for row in rows)
    partial = [row for row in ldp if row["partial"]]
    assert len(partial) == 1
    assert partial[0]["layer_id"] == "ldp_north_ayrshire"
    assert "dtechtive" not in json.dumps(rows).lower()
    highland = next(row for row in ldp if row["layer_id"] == "ldp_highland")
    assert highland["licence_status"] == "ogl"
    argyll = next(row for row in ldp if row["layer_id"] == "ldp_argyll_and_bute")
    assert argyll["licence_status"] == "open_other"


def test_no_new_switches_without_loaded_data():
    registry = (REPO / "frontend" / "lib" / "mapLayerRegistry.ts").read_text(encoding="utf-8")
    for layer_id in (
        "epc_domestic",
        "os_open_uprn",
        "ofcom_cn_fixed",
        "os_open_roads",
        "ldp_highland",
        "vdl_glasgow_city",
    ):
        assert f'id: "{layer_id}"' not in registry
