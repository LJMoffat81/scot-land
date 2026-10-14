"""DZ2022 value-weighted crosswalk + SG roll-up (internal / unpublished). SYNTHETIC only."""

from __future__ import annotations

import pytest

from georgist import surface_dz2022 as dz22
from georgist import surface_rollup as roll


def _src(
    code="S01013401",
    *,
    rent=1000.0,
    price_year=2025,
    valuation_date="2025-04-01",
    **over,
):
    row = {
        "code": code,
        "vintage": 2011,
        "valuation_date": valuation_date,
        "price_year": price_year,
        "measured_rent": rent,
        "uncertainty_low": rent * 0.8,
        "uncertainty_high": rent * 1.2,
        "land_value_zone_total": rent * 20,
        "infra_share": rent * 0.1,
        "planning_uplift": None,
        "policy_rent": rent * 0.7,
        "value_tier": "proxy",
        "quality": "derived",
        "fill_method": "observed_pooled",
        "publish_level": "public_zone",
        "publication_status": "ok",
        "commons_class": "surface",
        "crosswalk_method": "none",
        "source_id": "SYNTHETIC",
        "licence": "synthetic-test-only",
        "method": "residual_drc_surface_v1",
        "proxy_tags": ["pooled_3y"],
        "dwellings": 100,
        "measured_rent_per_dwelling": rent / 100,
    }
    row.update(over)
    return row


def _spine(code, iz, la):
    return {
        "code": code,
        "vintage": 2022,
        "name": "SYNTHETIC",
        "iz_code": iz,
        "la_code": la,
        "la_name": "SYNTHETIC",
    }


def test_validate_value_crosswalk_sums_and_ranges():
    pairs = [
        {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 0.6, "method": "value_weighted"},
        {"dz2011": "S01013401", "dz2022": "S01020871", "weight": 0.4, "method": "value_weighted"},
    ]
    by = dz22.validate_value_crosswalk(pairs)
    assert set(by) == {"S01013401"}
    assert sum(w for _, w in by["S01013401"]) == pytest.approx(1.0)


def test_population_crosswalk_refused():
    with pytest.raises(dz22.CrosswalkError, match="pop_hhres_2022"):
        dz22.validate_value_crosswalk(
            [
                {
                    "dz2011": "S01013401",
                    "dz2022": "S01020870",
                    "weight": 1.0,
                    "method": "pop_hhres_2022",
                }
            ]
        )


def test_weights_must_sum_to_one():
    with pytest.raises(dz22.CrosswalkError, match="sum to"):
        dz22.validate_value_crosswalk(
            [
                {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 0.5},
                {"dz2011": "S01013401", "dz2022": "S01020871", "weight": 0.3},
            ]
        )


def test_one_to_one_topology_ignores_splits():
    people = [
        {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0},  # 1:1
        {"dz2011": "S01013402", "dz2022": "S01020871", "weight": 0.5},  # split
        {"dz2011": "S01013402", "dz2022": "S01020872", "weight": 0.5},
    ]
    out = dz22.one_to_one_value_crosswalk(people)
    assert out == [
        {
            "dz2011": "S01013401",
            "dz2022": "S01020870",
            "weight": 1.0,
            "method": "value_weighted",
        }
    ]


def test_require_complete_fails_loudly_without_value_weights_for_splits():
    people = [
        {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0},
        {"dz2011": "S01013402", "dz2022": "S01020871", "weight": 0.5},
        {"dz2011": "S01013402", "dz2022": "S01020872", "weight": 0.5},
    ]
    with pytest.raises(dz22.CrosswalkError, match="explicit value_weighted"):
        dz22.require_complete_value_crosswalk(people)


def test_crosswalk_one_to_one_forces_internal_unpublished(make_valuation_row):
    src = make_valuation_row(200_000, code="S01013401", vintage=2011)
    assert src["publish_level"] == "public_zone"
    pairs = [{"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0}]
    out = dz22.crosswalk_surface_to_dz2022([src], pairs, dwellings_by_code={"S01020870": 500})
    assert len(out) == 1
    row = out[0]
    assert row["code"] == "S01020870" and row["vintage"] == 2022
    assert row["publish_level"] == "internal"
    assert row["publication_status"] == "blocked"
    assert row["crosswalk_method"] == "value_weighted"
    assert row["measured_rent"] == pytest.approx(src["measured_rent"])
    assert "unpublished_pending_economic_rules" in row["proxy_tags"]
    assert "crosswalked_from_dz2011" in row["proxy_tags"]


def test_crosswalk_publication_status_blocked_wins_over_source_ok():
    """Every new DZ2022 row is blocked; source ok / missing status never unblocks."""
    pairs = [{"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0}]
    sources = [
        _src(publication_status="ok"),
        _src(publication_status="blocked"),
        {k: v for k, v in _src().items() if k != "publication_status"},
    ]
    for src in sources:
        out = dz22.crosswalk_surface_to_dz2022(
            [src], pairs, dwellings_by_code={"S01020870": 500}
        )
        assert out[0]["publication_status"] == dz22.PUBLICATION_STATUS == "blocked"
        assert out[0]["publish_level"] == "internal"


def test_crosswalk_split_scales_rent_and_recomputes_per_dwelling():
    src = _src(rent=1000.0)
    pairs = [
        {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 0.25},
        {"dz2011": "S01013401", "dz2022": "S01020871", "weight": 0.75},
    ]
    out = dz22.crosswalk_surface_to_dz2022(
        [src], pairs, dwellings_by_code={"S01020870": 40, "S01020871": 120}
    )
    by = {r["code"]: r for r in out}
    assert by["S01020870"]["measured_rent"] == pytest.approx(250.0)
    assert by["S01020871"]["measured_rent"] == pytest.approx(750.0)
    assert by["S01020870"]["measured_rent_per_dwelling"] == pytest.approx(6.25)
    assert by["S01020870"]["publish_level"] == "internal"
    assert by["S01020870"]["price_gbp"] is None  # diagnostics cleared on split


def test_crosswalk_missing_source_fails():
    with pytest.raises(dz22.CrosswalkError, match="missing"):
        dz22.crosswalk_surface_to_dz2022(
            [],
            [{"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0}],
        )


def test_crosswalk_mixed_price_year_fails():
    with pytest.raises(dz22.CrosswalkError, match="price_year"):
        dz22.crosswalk_surface_to_dz2022(
            [_src(code="S01013401", price_year=2025), _src(code="S01013402", price_year=2024)],
            [
                {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0},
                {"dz2011": "S01013402", "dz2022": "S01020871", "weight": 1.0},
            ],
        )


def test_rollup_dz_iz_council_scotland_no_double_count():
    rows = [
        {
            **_src(code="S01020870", rent=100.0),
            "code": "S01020870",
            "vintage": 2022,
            "crosswalk_method": "value_weighted",
            "publish_level": "internal",
            "estimate_label": "measured",
        },
        {
            **_src(code="S01020871", rent=300.0),
            "code": "S01020871",
            "vintage": 2022,
            "crosswalk_method": "value_weighted",
            "publish_level": "internal",
            "estimate_label": "measured",
        },
        {
            **_src(code="S01020872", rent=50.0),
            "code": "S01020872",
            "vintage": 2022,
            "crosswalk_method": "value_weighted",
            "publish_level": "internal",
            "estimate_label": "fully_estimated",
        },
    ]
    spine = [
        _spine("S01020870", "S02000001", "S12000036"),
        _spine("S01020871", "S02000001", "S12000036"),
        _spine("S01020872", "S02000002", "S12000049"),
    ]
    out = roll.rollup_surface_rent_dz2022(rows, spine)
    by = {(r["geo_level"], r["code"]): r for r in out}
    assert by[("intermediate_zone", "S02000001")]["measured_rent"] == pytest.approx(400.0)
    assert by[("intermediate_zone", "S02000002")]["measured_rent"] == pytest.approx(50.0)
    assert by[("council", "S12000036")]["measured_rent"] == pytest.approx(400.0)
    assert by[("council", "S12000049")]["measured_rent"] == pytest.approx(50.0)
    assert by[("scotland", roll.SCOTLAND_CODE)]["measured_rent"] == pytest.approx(450.0)
    assert by[("council", "S12000036")]["estimate_label"] == "measured"
    assert by[("council", "S12000049")]["estimate_label"] == "fully_estimated"
    assert by[("scotland", roll.SCOTLAND_CODE)]["estimate_label"] == "partly_estimated"
    for r in out:
        assert r["publish_level"] == "internal"
        assert r["vintage"] == 2022
        assert r["estimate_label"] in ("measured", "partly_estimated", "fully_estimated")


def test_rollup_db_rows_drop_leaves_and_keep_internal():
    rows = [
        {
            **_src(code="S01020870", rent=10.0),
            "code": "S01020870",
            "vintage": 2022,
            "crosswalk_method": "value_weighted",
            "publish_level": "internal",
            "estimate_label": "measured",
        }
    ]
    spine = [_spine("S01020870", "S02000001", "S12000036")]
    full = roll.rollup_surface_rent_dz2022(rows, spine)
    db_rows = roll.rollup_db_rows(full)
    assert all(r["geo_level"] != "data_zone" for r in db_rows)
    assert {r["geo_level"] for r in db_rows} == {"intermediate_zone", "council", "scotland"}
    assert all(r["publish_level"] == "internal" for r in db_rows)
    assert all(tuple(r) == roll.ROLLUP_DB_COLUMNS for r in db_rows)


def test_rollup_refuses_dz2011_inputs():
    with pytest.raises(roll.RollupError, match="vintage 2022"):
        roll.rollup_surface_rent_dz2022([_src()], [_spine("S01020870", "S02000001", "S12000036")])


def test_rollup_refuses_missing_spine():
    row = {
        **_src(code="S01020870", rent=10.0),
        "code": "S01020870",
        "vintage": 2022,
        "crosswalk_method": "value_weighted",
        "publish_level": "internal",
        "estimate_label": "measured",
    }
    with pytest.raises(roll.RollupError, match="no DZ2022 rows in zone_spine"):
        roll.rollup_surface_rent_dz2022([row], [])
    other = [_spine("S01020872", "S02000001", "S12000036")]
    with pytest.raises(roll.RollupError, match="zone_spine missing"):
        roll.rollup_surface_rent_dz2022([row], other)


def test_rollup_refuses_iz_spanning_councils():
    rows = [
        {
            **_src(code="S01020870", rent=10.0),
            "code": "S01020870",
            "vintage": 2022,
            "crosswalk_method": "value_weighted",
            "publish_level": "internal",
            "estimate_label": "measured",
        },
        {
            **_src(code="S01020871", rent=20.0),
            "code": "S01020871",
            "vintage": 2022,
            "crosswalk_method": "value_weighted",
            "publish_level": "internal",
            "estimate_label": "measured",
        },
    ]
    spine = [
        _spine("S01020870", "S02000001", "S12000036"),
        _spine("S01020871", "S02000001", "S12000049"),  # same IZ, different LA
    ]
    with pytest.raises(roll.RollupError, match="spans multiple councils"):
        roll.rollup_surface_rent_dz2022(rows, spine)


def test_end_to_end_crosswalk_then_rollup_internal_only(make_valuation_row):
    a = make_valuation_row(150_000, code="S01013401", vintage=2011, dwellings=200)
    b = make_valuation_row(180_000, code="S01013402", vintage=2011, dwellings=300)
    pairs = [
        {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0},
        {"dz2011": "S01013402", "dz2022": "S01020871", "weight": 1.0},
    ]
    dz = dz22.crosswalk_surface_to_dz2022(
        [a, b], pairs, dwellings_by_code={"S01020870": 200, "S01020871": 300}
    )
    assert all(r["publish_level"] == "internal" for r in dz)
    spine = [
        _spine("S01020870", "S02000010", "S12000036"),
        _spine("S01020871", "S02000010", "S12000036"),
    ]
    rolled = roll.rollup_surface_rent_dz2022(dz, spine)
    scotland = next(r for r in rolled if r["geo_level"] == "scotland")
    assert scotland["measured_rent"] == pytest.approx(
        sum(r["measured_rent"] for r in dz)
    )
    assert scotland["code"] == "S92000003"
    assert scotland["publish_level"] == "internal"
