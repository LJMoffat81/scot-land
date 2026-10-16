"""PR-C2: V9, V13 and V14.

Synthetic fixtures only. No 2024 price cell is read. No scored run.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from georgist import surface_v14 as v14
from georgist.surface_v14_checks import GATING_MARKS
from georgist.v14_hedonic import (
    D7_SHA256,
    MEDIAN_2024_REASON,
    PriceYearError,
    S_G1_REASON,
    SENSITIVITY_IDS,
    sensitivity_manifest,
    sensitivity_table,
)
from georgist.v14_score_report import code_text_disagreements, predeclared_not_run
from scripts.build_v14_check_inputs import (
    ALLOWED_ZONE_FIELDS,
    SOURCES,
    CheckInputError,
    assert_pinned,
    build_v14_check_inputs,
    load_source,
    main as check_main,
    sha256_file,
)
from scripts.build_v14_hedonic_rows import (
    COLUMN_MAP,
    OMITTED_CONTROLS,
    PINNED_SHA256,
    HedonicRowError,
    assert_pinned as assert_hedonic_pins,
    build_v14_hedonic_rows,
    main as hedonic_main,
    missing_pins,
    screen_years,
)
from test_v14_pipeline_b import _rows, _zone

BACKEND = Path(__file__).resolve().parents[1]
SENTINEL = "SENTINEL_TV_9f3a"


def test_requirements_pin_statsmodels_exactly():
    text = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    assert "statsmodels==0.15.0" in text
    assert "statsmodels>=" not in text


def test_pending_check_records_the_error_and_fail_closed_uses_the_master_list():
    source = (BACKEND / "georgist" / "surface_v14.py").read_text(encoding="utf-8")
    assert '("1a", "1b", "3", "4", "6")' not in source
    assert "GATING_MARKS" in source
    zone = _zone("A")
    del zone["dz2022"]
    scored = v14.score_estimators(
        primary_shares=[0.2],
        secondary_shares=[0.2],
        primary_zones=[zone],
        secondary_zones=[dict(zone)],
    )
    for block in (scored["primary"], scored["secondary"]):
        pending = block["gating"]["6"]
        assert pending["status"] == "pending"
        assert "dz2022" in pending["error"]
        assert block["gating_pass"] is False
        for name in GATING_MARKS:
            if block["gating"][name]["status"] == "pending":
                assert block["gating"][name]["error"]
    assert scored["publication"]["publish_primary"] is False
    assert scored["publication"]["publish_secondary"] is False


def test_v9_manifest_and_computed_statuses_do_not_gate():
    manifest = sensitivity_manifest()
    assert [item["id"] for item in manifest] == list(SENSITIVITY_IDS)
    for item in manifest:
        assert item["status"] in {"fit", "NOT_RUN"}
        assert item["gates"] is False
        assert item["swapped_in"] is False
        if item["status"] == "NOT_RUN":
            assert item["reason"]
    assert next(item for item in manifest if item["id"] == "S-g1")["reason"] == S_G1_REASON
    rows = []
    for base in _rows():
        row = dict(base)
        row["ur6"] = 1 if row["zone"] in {"Z1", "Z2"} else 5
        row["itl3"] = "TLM"
        row["ur3"] = "urban" if row["ur6"] == 1 else "rural"
        row["iz2011"] = row["iz"]
        row["median_price"] = row["price"] * 0.9
        row["a_r20"] = row["a_m2"] * 0.8
        row["a_r40"] = row["a_m2"] * 1.2
        row["flat_share"] = 0.2 if row["zone"] in {"Z1", "Z2"} else 0.8
        row["other_land_per_home"] = 1.0
        row["ratio_mean"] = 1.0
        row["low_parcel_coverage"] = 0.0
        rows.append(row)
    # Two cells so S-c1 has something to fit. Headline cell stays "c".
    headline = {"c": 0.3}
    table = sensitivity_table(rows, headline, d7_sha256=D7_SHA256)
    by_id = {item["id"]: item for item in table}
    assert set(SENSITIVITY_IDS) <= set(by_id)
    for name in SENSITIVITY_IDS:
        item = by_id[name]
        assert item["status"] in {"fit", "NOT_RUN", "NOT_CONVERGED"}
        assert item["gates"] is False
        assert item["swapped_in"] is False
        if item["status"] != "fit":
            assert item["reason"]
    assert by_id["S-g1"]["status"] == "NOT_RUN"
    assert by_id["S-g1"]["reason"] == S_G1_REASON
    assert by_id["S-x4"]["internal_only"] is True
    assert by_id["S-x4"]["publish"] is False
    assert by_id["S-x2"]["status"] == "fit"
    refused = sensitivity_table(rows, headline, d7_sha256="not-the-pin")
    missed = next(item for item in refused if item["id"] == "S-x2")
    assert missed["status"] == "NOT_RUN"
    assert "D7" in missed["reason"]
    later = [dict(row, year=2024, price=SENTINEL) for row in rows[:1]]
    with pytest.raises(PriceYearError, match="2024") as raised:
        sensitivity_table(later, headline)
    assert SENTINEL not in str(raised.value)
    assert MEDIAN_2024_REASON == "not_crosswalkable"


def test_v13_refuses_unpinned_and_missing_fields_and_unknown_fields(tmp_path: Path):
    def write(name: str, payload) -> tuple[Path, str]:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path, sha256_file(path)

    zone = "S01000001"
    tables = {
        "builder_output": {"zones": [{"zone": zone, "price": 10.0}]},
        "primary_estimates": {"zones": [{"zone": zone, "share": 0.2, "land_per_home": 2.0}]},
        "fitted_hedonic": {"zones": [{"zone": zone, "share": 0.25, "land_per_home": 2.5}]},
        "check3_plot_passes": {"zones": [{"zone": zone, "pass_at": {"30": True, "20": True, "40": True}}]},
        "check4_rent_route": {"zones": [{"zone": zone, "residual_land": 4.0, "capitalised_land": 4.0}]},
        "dz2022_keys": {
            "zones": [{"zone": zone, "dz2022": "S02000001", "share_low": 0.1, "share_central": 0.2, "share_high": 0.3}]
        },
        "ur6": {"zones": [{"zone": zone, "ur6": 1}]},
    }
    paths = {}
    pins = {}
    for name, payload in tables.items():
        path, digest = write(name, payload)
        paths[name] = path
        pins[name] = digest
    assert_pinned(paths, pins)
    loaded = {name: load_source(paths[name], name) for name in SOURCES}
    built = build_v14_check_inputs(loaded)
    assert set(built) == {"primary_zones", "secondary_zones"}
    assert built["primary_zones"][0]["share"] == 0.2
    assert built["secondary_zones"][0]["share"] == 0.25
    assert "ledger" not in json.dumps(built)
    for zone_row in built["primary_zones"] + built["secondary_zones"]:
        assert set(zone_row) <= ALLOWED_ZONE_FIELDS
    broken = dict(pins)
    del broken["ur6"]
    with pytest.raises(CheckInputError, match="ur6"):
        assert_pinned(paths, broken)
    out = tmp_path / "out.json"
    assert check_main(["--out", str(out)]) == 1
    assert not out.exists()
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps({"zones": [{"zone": zone, "invented": 1}]}), encoding="utf-8")
    with pytest.raises(CheckInputError, match="frozen text"):
        load_source(unknown, "builder_output")
    short = {name: dict(table) for name, table in loaded.items()}
    del short["dz2022_keys"][zone]["share_high"]
    with pytest.raises(CheckInputError, match="missing fields"):
        build_v14_check_inputs(short)


def test_v14_sha_mismatch_aborts_and_2024_row_is_refused_before_the_price(tmp_path: Path):
    paths = {name: None for name in PINNED_SHA256}
    assert missing_pins(paths) == list(PINNED_SHA256)
    with pytest.raises(HedonicRowError, match="without a pinned sha"):
        assert_hedonic_pins(paths)
    house = tmp_path / "house_sales.csv"
    house.write_text("zone,year,n_sales,price,median_price\nS01000001,2021,6,10,9\n", encoding="utf-8")
    paths = {name: house for name in PINNED_SHA256}
    with pytest.raises(HedonicRowError, match="sha256"):
        assert_hedonic_pins(paths)
    poisoned = tmp_path / "poison.csv"
    poisoned.write_text(
        f"zone,year,n_sales,price,median_price\nS01000001,2024,6,{SENTINEL},9\n",
        encoding="utf-8",
    )
    with pytest.raises(HedonicRowError, match="2024") as raised:
        screen_years(poisoned)
    assert SENTINEL not in str(raised.value)
    assert hedonic_main(["--out", str(tmp_path / "rows.json")]) == 1
    assert not (tmp_path / "rows.json").exists()


def test_v14_column_map_matches_section_3_6():
    assert "x_bf_mid_terrace_share" not in COLUMN_MAP
    assert "x_age_unknown_share" not in COLUMN_MAP
    assert "x_bed_share_2" not in COLUMN_MAP
    assert "simd" not in COLUMN_MAP
    for name in (
        "x_bf_detached_share",
        "x_flat_share",
        "x_age_pre1919_share",
        "x_age_1919_1949_share",
        "x_age_1950_1982_share",
        "x_age_1983_2002_share",
        "x_age_2003_share",
        "x_bed_share_1",
        "x_bed_share_3",
        "x_bed_share_4plus",
        "x_log_job_access",
        "x_coverage_share",
        "x_share_lodged_last_10y",
        "x_low_parcel_coverage",
        "x_other_land_share",
        "a_m2",
        "a_r20",
        "a_r40",
        "f_m2",
        "price",
        "median_price",
    ):
        assert name in COLUMN_MAP
    for omitted in OMITTED_CONTROLS:
        assert omitted not in COLUMN_MAP
    zone = "S01000001"
    certificate = {
        "bf_detached_share": 0.2,
        "bf_semi_detached_share": 0.2,
        "bf_end_terrace_share": 0.1,
        "bf_enclosed_end_terrace_share": 0.1,
        "bf_enclosed_mid_terrace_share": 0.1,
        "pt_flat_share": 0.2,
        "pt_maisonette_share": 0.1,
        "coverage_share": 0.5,
        "share_lodged_last_10y": 0.4,
        "age_pre1919_share": 0.1,
        "age_1919_1929_share": 0.1,
        "age_1930_1949_share": 0.1,
        "age_1950_1964_share": 0.1,
        "age_1965_1975_share": 0.1,
        "age_1976_1983_share": 0.1,
        "age_1984_1991_share": 0.1,
        "age_1992_1998_share": 0.05,
        "age_1999_2002_share": 0.05,
        "age_2003_2007_share": 0.05,
        "age_2008_on_share": 0.05,
    }
    rows = build_v14_hedonic_rows(
        sales=[{"zone": zone, "year": 2021, "n_sales": 6, "price": 10.0, "median_price": 9.0}],
        areas={zone: {"a_m2": 100.0, "a_r20": 80.0, "a_r40": 120.0, "low_parcel_coverage": 0.0, "other_land_share": 0.1}},
        epc={zone: certificate},
        merge={zone: {"cell": "CA1|urban", "ur6": 1, "itl3": "TLM", "ca2019": "S12000033"}},
        sold_tfa={(zone, 2021): {"f_m2": 80.0, "f_imputed": 0}},
        bedrooms={zone: {"share_1": 0.2, "share_3": 0.3, "share_4plus": 0.1}},
        access={zone: {"log_job_access": 1.0}},
    )
    assert list(rows[0]) == list(COLUMN_MAP)
    assert rows[0]["window"] == "fit"
    assert math.isclose(rows[0]["x_flat_share"], 0.3)
    with pytest.raises(HedonicRowError, match="2024"):
        build_v14_hedonic_rows(
            sales=[{"zone": zone, "year": 2024, "n_sales": 6, "price": 10.0, "median_price": 9.0}],
            areas={zone: {"a_m2": 1, "a_r20": 1, "a_r40": 1, "low_parcel_coverage": 0, "other_land_share": 0}},
            epc={zone: certificate},
            merge={zone: {"cell": "c", "ur6": 1, "itl3": "T", "ca2019": "C"}},
            sold_tfa={(zone, 2024): {"f_m2": 1, "f_imputed": 0}},
            bedrooms={zone: {"share_1": 0, "share_3": 0, "share_4plus": 0}},
            access={zone: {"log_job_access": 0}},
        )


def test_c2_disagreement_table_has_zero_open_rows():
    rows = code_text_disagreements()
    assert [row["id"] for row in rows if row["status"] in {"open", "pending"}] == []
    by_id = {row["id"]: row["status"] for row in rows}
    assert by_id["V9"] == "fixed"
    assert by_id["V13"] == "fixed"
    assert by_id["V14"] == "fixed"
    assert by_id["V3"] == "limitation_disclosed"
    predeclared = {item["id"]: item for item in predeclared_not_run()}
    assert predeclared["S-g1"]["status"] == "NOT_RUN"
    assert predeclared["HBU"]["status"] == "NOT_RUN"
    assert predeclared["median_price_2024"]["reason"] == MEDIAN_2024_REASON


def test_new_c2_files_have_no_currency_symbol():
    for name in ("build_v14_check_inputs.py", "build_v14_hedonic_rows.py"):
        text = (BACKEND / "scripts" / name).read_text(encoding="utf-8")
        assert "£" not in text
        assert "ledger" not in text
    hedonic = (BACKEND / "georgist" / "v14_hedonic.py").read_text(encoding="utf-8")
    assert "£" not in hedonic


def test_share_only_pass_still_does_not_publish():
    shares = [0.2, 0.25, 0.3]
    scored = v14.score_estimators(primary_shares=shares, secondary_shares=list(shares))
    assert scored["publication"]["outcome"] == "both_fail_publish_neither"
    assert math.isfinite(scored["primary"]["gating"]["1"]["median"])
