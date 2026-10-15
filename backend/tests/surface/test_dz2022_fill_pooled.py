"""FILL-POOLED acceptance T1–T7 (fail on unpooled / pre-pooling 723/727 main)."""

from __future__ import annotations

import csv
import logging
import subprocess
from pathlib import Path

import pytest

from georgist import dz2022_fill as fill
from georgist import rent_table_pooled as rtp
from georgist import surface_illustrative as si
from georgist import surface_rent as sr
from georgist.surface_paths import REPO_ROOT

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dz2022_fill"
RENT = FIXTURES / "rent_2011.csv"
UR6 = FIXTURES / "ur6_dz2022.csv"
WEIGHTS = FIXTURES / "weights.csv"
SPINE = FIXTURES / "spine_councils.csv"
EXTRACT = si.METHODS_PR1_EXTRACT
ZONE_SPINE = REPO_ROOT / "data" / "processed" / "datazones" / "zone_spine.csv"
GUARD = REPO_ROOT / "scripts" / "check_publishable.py"


def _load_weights():
    rows = []
    with WEIGHTS.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(
                {
                    "dz2011": r["dz2011"],
                    "dz2022": r["dz2022"],
                    "uprn_count": int(r["uprn_count"]),
                    "weight": float(r["weight"]),
                    "method": r["method"],
                }
            )
    from collections import defaultdict

    by = defaultdict(list)
    for r in rows:
        by[r["dz2011"]].append(r)
    out = []
    for _src, edges in by.items():
        tot = sum(e["uprn_count"] for e in edges)
        for e in edges:
            e = dict(e)
            e["weight"] = e["uprn_count"] / tot
            out.append(e)
    return out


def _spine_maps():
    c11, c22 = {}, {}
    with SPINE.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if int(r["vintage"]) == 2011:
                c11[r["code"]] = r["la_code"]
            else:
                c22[r["code"]] = r["la_code"]
    return c11, c22


# --- T1 ------------------------------------------------------------------


def test_t1_pooled_3y_zone_left_measured_not_model_filled(neighbours):
    """Empty in 2023 but ≥5 sales over 2021–23 → measured pooled_3y, not C."""
    sha = fill.pooling_config_sha256()
    # S01013403 was empty/pending in the base fixture; give it a pooled_3y price.
    rent = fill.load_2011_rent_table(RENT)
    by = {r["code"]: r for r in rent}
    assert by["S01013403"]["fill_method"] == "model_fill_pending"
    by["S01013403"].update(
        {
            "measured_rent": 400.0,
            "uncertainty_low": 320.0,
            "uncertainty_high": 480.0,
            "fill_method": "observed_pooled",
            "sales_n": 6,
            "evidence_window": "pooled_3y",
            "evidence_oldest_year": 2021,
            "pooling_config_sha256": sha,
        }
    )
    # Confirm pool_zone_price would accept ≥5 over 2021–23 with empty 2023.
    obs = [
        sr.YearPrice(2021, 3, 200_000.0, 195_000.0),
        sr.YearPrice(2022, 3, 210_000.0, 205_000.0),
        sr.YearPrice(2023, None, None, None),
    ]
    pooled = si.pool_zone_price(
        obs,
        latest_year=2023,
        price_cfg=sr.load_config()["price"],
        index_factor={2021: 1.1, 2022: 1.05, 2023: 1.0},
        index_to_year=2023,
    )
    assert pooled.sales_n >= 5
    assert "pooled_3y" in pooled.tags
    assert rtp.evidence_window_for_pooled(
        latest_year=2023, pooled=pooled, published_latest_n=0, n_min=5
    ) == "pooled_3y"

    ur6_2022 = fill.load_ur6_dz2022(UR6)
    ur6_2011 = {r["code"]: int(r["ur6_class"]) for r in rent if r.get("ur6_class") is not None}
    c11, c22 = _spine_maps()
    weights = _load_weights()
    dwellings = {
        "S01020870": 100,
        "S01020871": 120,
        "S01020872": 100,
        "S01020873": 80,
        "S01020001": 30,
        "S01020002": 25,
        "S01020003": 20,
        "S01020005": 100,
        "S01017360": 0,
    }
    result = fill.fill_dz2022_empty_zones(
        list(by.values()),
        weights,
        council_by_2011=c11,
        council_by_2022=c22,
        ur6_by_2011=ur6_2011,
        ur6_by_2022=ur6_2022,
        neighbours=neighbours,
        dwellings_by_2022=dwellings,
        class_min=10,
    )
    # Destination that was pure-C from S01013403 alone must now be measured.
    # UPRN weight S01013403→S01020873 is 50/70 (also feeds S01020871).
    row = next(r for r in result.rows_2022 if r["code"] == "S01020873")
    assert row["estimate_label"] == fill.ESTIMATE_MEASURED
    assert row["fill_step"] == fill.STEP_POOLED_3Y
    assert row["fill_method"] == "observed_pooled"
    assert row["measured_rent"] == 400.0 * 50 / 70
    assert result.classifications["S01020873"].fill_class == fill.CLASS_UNAFFECTED


@pytest.fixture(scope="module")
def neighbours():
    return fill.load_neighbouring_councils()


# --- T2 ------------------------------------------------------------------


def test_t2_missing_pooling_stamp_raises_unless_override(caplog, neighbours):
    rent = fill.load_2011_rent_table(RENT)
    for r in rent:
        r.pop("evidence_window", None)
        r.pop("pooling_config_sha256", None)
    with pytest.raises(fill.UnpooledTableError, match="pooling stamp"):
        fill.fill_dz2022_empty_zones(
            rent,
            _load_weights(),
            council_by_2011=_spine_maps()[0],
            council_by_2022=_spine_maps()[1],
            ur6_by_2011={r["code"]: 1 for r in rent},
            ur6_by_2022=fill.load_ur6_dz2022(UR6),
            neighbours=neighbours,
            dwellings_by_2022={"S01020870": 100},
            require_pooling_stamp=True,
        )
    with caplog.at_level(logging.WARNING):
        # Override with reason must run (may fail later on thin dwellings map — stamp only).
        try:
            fill.ensure_pooling_stamp(
                rent, override=True, reason="ci fixture without stamp for T2"
            )
        except fill.FillError:
            pytest.fail("override+reason must not raise FillError")
    assert any("override" in rec.message.lower() for rec in caplog.records)
    with pytest.raises(fill.FillError, match="reason"):
        fill.ensure_pooling_stamp(rent, override=True, reason="")


# --- T3 ------------------------------------------------------------------


def test_t3_gate_from_config_and_extract_129_rejects_723_727():
    assert EXTRACT.is_file() and ZONE_SPINE.is_file()
    cov = si.empty_zone_pooling_coverage_from_ros_extract(EXTRACT, ZONE_SPINE)
    assert cov["remaining_model_fill"] == 129
    assert fill.null_dz_fill_target_from_config() == 129
    assert cov["remaining_model_fill"] == fill.null_dz_fill_target_from_config()

    # Build inventory: remaining model-fill codes + zeros (4 not-in-price inside 129).
    remaining = set(cov["remaining_model_fill_codes"])
    assert fill.NOT_IN_PRICE_FILE_CODES <= remaining
    rows = []
    for code in sorted(remaining):
        flags = (
            "absent_from_ros_price_file"
            if code in fill.NOT_IN_PRICE_FILE_CODES
            else ""
        )
        rows.append(
            {
                "code": code,
                "fill_method": "model_fill_pending",
                "measured_rent": None,
                "dwellings": 40,
                "flags": flags,
            }
        )
    for code in sorted(fill.ZERO_DWELLING_CODES):
        rows.append(
            {
                "code": code,
                "fill_method": "not_applicable",
                "measured_rent": 0.0,
                "dwellings": 0,
                "flags": "zero_dwellings",
            }
        )
    counts = fill.count_reconciled_sources(rows)
    assert counts == {
        "model_fill_n": 129,
        "not_in_price_file_n": 4,
        "zero_dwellings_n": 3,
    }
    fill.assert_reconciled_source_counts(rows)

    # Feeding pre-pooling 723/727 inventory must FAIL.
    legacy = []
    for i in range(723):
        legacy.append(
            {
                "code": f"S010{8000 + i:05d}",
                "fill_method": "model_fill_pending",
                "measured_rent": None,
                "dwellings": 50,
                "flags": "",
            }
        )
    for code in sorted(fill.NOT_IN_PRICE_FILE_CODES):
        legacy.append(
            {
                "code": code,
                "fill_method": "model_fill_pending",
                "measured_rent": None,
                "dwellings": 40,
                "flags": "absent_from_ros_price_file",
            }
        )
    for code in sorted(fill.ZERO_DWELLING_CODES):
        legacy.append(
            {
                "code": code,
                "fill_method": "not_applicable",
                "measured_rent": 0.0,
                "dwellings": 0,
                "flags": "zero_dwellings",
            }
        )
    legacy_counts = fill.count_reconciled_sources(legacy)
    assert legacy_counts["model_fill_n"] == 727
    with pytest.raises(fill.FillError, match="129"):
        fill.assert_reconciled_source_counts(legacy)


# --- T4 ------------------------------------------------------------------


def test_t4_every_zone_one_step_and_c_substeps_sum(filled_pooled):
    fill.assert_fill_step_inventory(filled_pooled.rows_2022)
    counts = fill.count_fill_steps(filled_pooled.rows_2022)
    assert counts["n_with_step"] == counts["n_rows"]
    assert counts["c_sub_step_sum"] == counts["c_model_n"]
    table = fill.format_step_count_table(filled_pooled.rows_2022)
    assert "fill_step,count" in table
    assert "C_model," in table or "A_rescale," in table or "measured_2023," in table
    # Every DZ2022 zone with dwellings has rent > 0 or not_applicable.
    for r in filled_pooled.rows_2022:
        dwell = r.get("dwellings")
        if dwell is not None and int(dwell) > 0:
            assert r["fill_method"] != fill.FILL_METHOD_NA
            assert float(r["measured_rent"]) > 0
        else:
            assert r["estimate_label"] == fill.ESTIMATE_NA
    # Every DZ2011 with dwellings: rent > 0 or pending/NA on conservation companion.
    for r in filled_pooled.rows_2011_for_conservation:
        dwell = r.get("dwellings")
        if dwell is None:
            continue
        if int(dwell) <= 0:
            continue
        rent = r.get("measured_rent")
        assert rent is not None


@pytest.fixture(scope="module")
def filled_pooled(neighbours):
    rent = fill.load_2011_rent_table(RENT)
    ur6_2022 = fill.load_ur6_dz2022(UR6)
    ur6_2011 = {r["code"]: int(r["ur6_class"]) for r in rent if r.get("ur6_class") is not None}
    c11, c22 = _spine_maps()
    dwellings = {
        "S01020870": 100,
        "S01020871": 120,
        "S01020872": 100,
        "S01020873": 80,
        "S01020001": 30,
        "S01020002": 25,
        "S01020003": 20,
        "S01020005": 100,
        "S01017360": 0,
    }
    return fill.fill_dz2022_empty_zones(
        rent,
        _load_weights(),
        council_by_2011=c11,
        council_by_2022=c22,
        ur6_by_2011=ur6_2011,
        ur6_by_2022=ur6_2022,
        neighbours=neighbours,
        dwellings_by_2022=dwellings,
        class_min=10,
    )


# --- T5 ------------------------------------------------------------------


def test_t5_scotland_total_conserved(filled_pooled):
    fill.assert_post_fill_gate(
        filled_pooled.rows_2011_for_conservation, filled_pooled.rows_2022
    )
    t11 = sum(float(r["measured_rent"]) for r in filled_pooled.rows_2011_for_conservation)
    t22 = sum(float(r["measured_rent"]) for r in filled_pooled.rows_2022)
    assert t11 == t22


# --- T6 ------------------------------------------------------------------


def test_t6_no_gbp_keys_outputs_gitignored(tmp_path):
    # Written rent-table columns must not include *_gbp or £ (guard + gitignore).
    assert set(rtp.RENT_TABLE_COLUMNS) == {
        "zone_id",
        "central",
        "low",
        "high",
        "status",
        "dwellings",
        "la_code",
        "ur6_class",
        "sales_n",
        "flags",
        "evidence_window",
        "evidence_oldest_year",
        "pooling_config_sha256",
    }
    assert not any("gbp" in c.lower() for c in rtp.RENT_TABLE_COLUMNS)

    sha = fill.pooling_config_sha256()
    rows = rtp.build_rows_from_zone_pools(
        [
            {
                "code": "S01013401",
                "land_value": 1000.0,
                "status": "observed_pooled",
                "dwellings": 100,
                "la_code": "S12000049",
                "ur6_class": 1,
                "sales_n": 20,
                "evidence_window": "2023",
                "evidence_oldest_year": 2023,
                "flags": "",
            }
        ]
    )
    assert rows[0]["pooling_config_sha256"] == sha
    assert not any(k.endswith("_gbp") for k in rows[0])
    out = tmp_path / "methods_runs" / "rent_table_2011_pooled.csv"
    rtp.write_rent_table(rows, out)
    # Default output path is under gitignored data/external/methods_runs/
    default = rtp.default_output_path()
    rel = str(default.relative_to(REPO_ROOT))
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", rel],
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert ignored.returncode == 0, f"{rel} must be gitignored"
    body = out.read_text(encoding="utf-8")
    assert "gbp" not in body.lower() and "£" not in body
    assert GUARD.is_file()


# --- T7 ------------------------------------------------------------------


def test_t7_holdout_oneshot_still_refuses_second_scored_run(tmp_path):
    from scripts import run_dz2022_fill_holdout_oneshot as oneshot
    from georgist import dz2022_fill_holdout as ho

    log_path = tmp_path / "run_log" / "dz2022_fill_runs.jsonl"
    oneshot.preregister_run(rent_table=RENT, ur6_lookup=UR6, log_path=log_path)
    oneshot.run_scored(
        rent_table=RENT,
        ur6_lookup=UR6,
        log_path=log_path,
        class_min=3,
    )
    with pytest.raises(ho.RepeatScoredRunError, match="already recorded"):
        oneshot.run_scored(
            rent_table=RENT,
            ur6_lookup=UR6,
            log_path=log_path,
            class_min=3,
        )


def test_entrypoint_demo_writes_pooled_3y(tmp_path):
    from scripts import build_rent_table_2011_pooled as cli

    out = tmp_path / "rent.csv"
    assert cli.main(["--demo-fixture", "--out", str(out)]) == 0
    rows = fill.load_2011_rent_table(out)
    assert len(rows) == 1
    assert rows[0]["evidence_window"] == "pooled_3y"
    assert fill.table_has_pooling_stamp(rows)
    assert rows[0]["publication_status"] == "blocked"
    assert rows[0]["value_tier"] == "proxy"
