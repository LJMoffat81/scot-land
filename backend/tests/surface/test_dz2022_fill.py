"""DZ2022 empty-zone fill — fixture cases A/B/C/D, island, neighbours, gate."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from georgist import dz2022_fill as fill
from georgist import surface_dz2022 as dz22
from georgist import surface_rollup as roll

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dz2022_fill"
RENT = FIXTURES / "rent_2011.csv"
UR6 = FIXTURES / "ur6_dz2022.csv"
WEIGHTS = FIXTURES / "weights.csv"
SPINE = FIXTURES / "spine_councils.csv"


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
    # Recompute weights from counts per 2011 source (loader contract).
    from collections import defaultdict

    by = defaultdict(list)
    for r in rows:
        by[r["dz2011"]].append(r)
    out = []
    for src, edges in by.items():
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


@pytest.fixture(scope="module")
def neighbours():
    return fill.load_neighbouring_councils()


@pytest.fixture(scope="module")
def filled(neighbours):
    rent = fill.load_2011_rent_table(RENT)
    ur6_2022 = fill.load_ur6_dz2022(UR6)
    # 2011 UR6 from the rent table itself
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
    # class_min=10 would force Scotland/neighbour for thin Glasgow cells — use 10 as production.
    result = fill.fill_dz2022_empty_zones(
        rent,
        weights,
        council_by_2011=c11,
        council_by_2022=c22,
        ur6_by_2011=ur6_2011,
        ur6_by_2022=ur6_2022,
        neighbours=neighbours,
        dwellings_by_2022=dwellings,
        class_min=10,
    )
    return result


def test_neighbours_committed_60_pairs_no_islands(neighbours):
    rows = list(csv.DictReader(fill.NEIGHBOURS_PATH.open(encoding="utf-8")))
    assert len(rows) == 60
    assert fill.ISLAND_COUNCILS.isdisjoint(neighbours)
    # Glasgow touches Renfrewshire / others from appendix
    assert "S12000049" in neighbours
    assert "S12000013" not in neighbours


def test_reconciled_facts():
    facts = fill.reconciled_facts()
    assert facts["suppressed_n"] == 723
    assert facts["not_in_price_file"] == sorted(fill.NOT_IN_PRICE_FILE_CODES)
    assert facts["zero_dwellings_n"] == 3
    assert facts["empty_to_fill_n"] == 727
    assert "S01010206" not in facts["not_in_price_file"]


def test_classification_unaffected_a_b_c_d(filled):
    cls = filled.classifications
    assert cls["S01020870"].fill_class == fill.CLASS_UNAFFECTED
    assert cls["S01020871"].fill_class == fill.CLASS_A
    assert cls["S01020872"].fill_class == fill.CLASS_B
    assert cls["S01020873"].fill_class == fill.CLASS_C
    assert cls["S01017360"].fill_class == fill.CLASS_D
    assert cls["S01020005"].fill_class == fill.CLASS_B
    assert cls["S01020005"].measured_share < 0.05


def test_unaffected_pass_through_exact(filled):
    row = next(r for r in filled.rows_2022 if r["code"] == "S01020870")
    assert row["measured_rent"] == pytest.approx(1000.0)
    assert row["estimate_label"] == fill.ESTIMATE_MEASURED
    assert row["publication_status"] == "blocked"
    assert row["value_tier"] == "proxy"
    assert fill.PROXY_TAG in row["proxy_tags"]


def test_class_a_scale_up_exact_and_widen(filled):
    # S01013402 (measured 2000, weight 1.0) + S01013403 empty 30 UPRNs.
    # rent/AP of measured × total APs: (2000/70)*100
    row = next(r for r in filled.rows_2022 if r["code"] == "S01020871")
    assert row["estimate_label"] == fill.ESTIMATE_PARTLY
    central = (2000.0 / 70) * 100
    assert row["measured_rent"] == pytest.approx(central)
    # Range widened by empty_share 0.3
    assert row["uncertainty_low"] < row["measured_rent"]
    assert row["uncertainty_high"] > row["measured_rent"]
    assert row["fill_method"] == "model_filled"


def test_class_b_partly_and_fully(filled):
    b = next(r for r in filled.rows_2022 if r["code"] == "S01020872")
    assert b["estimate_label"] == fill.ESTIMATE_PARTLY
    assert b["fill_step"]  # recorded on B
    assert b["measured_rent"] > 0

    fully = next(r for r in filled.rows_2022 if r["code"] == "S01020005")
    assert fully["estimate_label"] == fill.ESTIMATE_FULLY
    assert fully["fill_step"]
    assert fully["measured_rent"] > 0


def test_class_c_fully_estimated_with_fill_step(filled):
    row = next(r for r in filled.rows_2022 if r["code"] == "S01020873")
    assert row["estimate_label"] == fill.ESTIMATE_FULLY
    assert row["fill_method"] == "model_filled"
    assert row["fill_step"] in {
        fill.STEP_OWN,
        fill.STEP_NEXT_UR,
        fill.STEP_NEIGHBOUR,
        fill.STEP_SCOTLAND,
    }
    assert row["uncertainty_low"] <= row["measured_rent"] <= row["uncertainty_high"]


def test_class_c_neighbour_or_next_class_borrow(filled):
    # Edinburgh UR3 C zone has no own measured UR3 → must borrow.
    row = next(r for r in filled.rows_2022 if r["code"] == "S01020002")
    assert row["estimate_label"] == fill.ESTIMATE_FULLY
    assert row["fill_step"] != fill.STEP_OWN
    assert row.get("borrowed_class") or row["fill_step"] in {
        fill.STEP_NEXT_UR,
        fill.STEP_NEIGHBOUR,
        fill.STEP_SCOTLAND,
    }


def test_island_group_borrow(filled):
    row = next(r for r in filled.rows_2022 if r["code"] == "S01020003")
    assert row["la_code"] == "S12000027"
    assert row["estimate_label"] == fill.ESTIMATE_FULLY
    assert row["fill_step"] in {fill.STEP_ISLAND, fill.STEP_SCOTLAND, fill.STEP_OWN}
    # Shetland empty → borrows Orkney / Western Isles before mainland
    if row["fill_step"] == fill.STEP_ISLAND:
        assert any(str(t).startswith("island:") for t in (row.get("borrowed_class") or []))


def test_class_d_zero_dwellings_not_applicable(filled):
    row = next(r for r in filled.rows_2022 if r["code"] == "S01017360")
    assert row["estimate_label"] == fill.ESTIMATE_NA
    assert row["fill_method"] == fill.FILL_METHOD_NA
    assert row["measured_rent"] == 0.0
    assert "zero_dwellings" in row["proxy_tags"]


def test_post_fill_gate_conserved_and_blocked(filled):
    fill.assert_post_fill_gate(filled.rows_2011_for_conservation, filled.rows_2022)
    t11 = sum(float(r["measured_rent"]) for r in filled.rows_2011_for_conservation)
    t22 = sum(float(r["measured_rent"]) for r in filled.rows_2022)
    assert abs(t11 - t22) <= dz22.PENNY


def test_label_refusal_on_rollup_missing_estimate_label(filled):
    rows = [dict(r) for r in filled.rows_2022 if r["estimate_label"] != fill.ESTIMATE_NA]
    # Strip one label → roll-up refuses (existing rule).
    rows[0]["estimate_label"] = ""
    spine = []
    with SPINE.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if int(r["vintage"]) == 2022:
                spine.append(
                    {
                        "code": r["code"],
                        "vintage": 2022,
                        "iz_code": "S02000001",
                        "la_code": r["la_code"],
                    }
                )
    # Only include spine rows that match our filled set; pad IZ uniquely per council.
    by_la = {}
    for i, s in enumerate(spine):
        la = s["la_code"]
        by_la.setdefault(la, f"S02000{100 + len(by_la):03d}")
        s["iz_code"] = by_la[la]
    present = {r["code"] for r in rows}
    spine = [s for s in spine if s["code"] in present]
    # Attach required rollup fields
    for r in rows:
        r.setdefault("price_year", 2025)
        r.setdefault("valuation_date", "2025-04-01")
        r.setdefault("source_id", "x")
        r.setdefault("licence", "x")
        r.setdefault("method", "x")
        r.setdefault("crosswalk_method", "address_uprn")
    with pytest.raises(roll.RollupError, match="estimate_label"):
        roll.rollup_surface_rent_dz2022(rows, spine)


def test_ur6_missing_raises_todo():
    with pytest.raises(fill.MissingLookupError, match="Urban Rural 6 Fold"):
        fill.load_ur6_dz2022("/tmp/does-not-exist-ur6-lookup.csv")


def test_rent_table_missing_raises():
    with pytest.raises(fill.MissingLookupError, match="2011 rent table"):
        fill.load_2011_rent_table("/tmp/does-not-exist-rent.csv")


def test_widen_on_holdout_errors_no_refit():
    low, c, high = fill.widen_bands_from_holdout_errors(
        90.0, 100.0, 110.0, abs_log_errors=[0.05, 0.2, 0.4]
    )
    assert low <= 90.0
    assert high >= 110.0
    assert c == 100.0
