"""DZ2022 address-UPRN crosswalk (PR B). Synthetic fixtures + zero-overlap file."""

from __future__ import annotations

from pathlib import Path

import pytest

from georgist import surface_dz2022 as dz22
from georgist import surface_rollup as roll

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "dz_crosswalk_uprn"
WEIGHTS = FIXTURES / "dz2011_dz2022_uprn_weights.csv"
ZERO = FIXTURES / "dz_crosswalk_zero_uprn.csv"


def _src(
    code="S01013401",
    *,
    rent=1000.0,
    fill_method="observed_pooled",
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
        "fill_method": fill_method,
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


@pytest.fixture(scope="module")
def uprn_pairs_filtered():
    pairs, stats = dz22.load_uprn_weight_rows(
        WEIGHTS, apply_min_share=True, require_full_scotland=False
    )
    return pairs, stats


@pytest.fixture(scope="module")
def uprn_pairs_raw():
    pairs, stats = dz22.load_uprn_weight_rows(
        WEIGHTS, apply_min_share=False, require_full_scotland=False
    )
    return pairs, stats


def test_os_ogl_attribution_on_load(uprn_pairs_filtered):
    _, stats = uprn_pairs_filtered
    assert "Contains OS data © Crown copyright and database right 2026" in stats["attribution"]
    assert "Open Government Licence v3.0" in stats["attribution"]
    assert "National Records of Scotland" in stats["attribution"]
    assert "Scottish Government" in stats["attribution"]


def test_fixture_readme_credits():
    text = (FIXTURES / "README.md").read_text(encoding="utf-8")
    assert "Contains OS data © Crown copyright and database right 2026" in text


def test_uprn_method_stamped_not_value_weighted():
    pairs = [
        {
            "dz2011": "S01013401",
            "dz2022": "S01020870",
            "weight": 1.0,
            "method": "uprn_point_in_polygon",
            "uprn_count": 10,
        }
    ]
    out = dz22.crosswalk_surface_to_dz2022([_src()], pairs)
    assert out[0]["crosswalk_method"] == "address_uprn"
    assert out[0]["crosswalk_method"] != "value_weighted"
    assert out[0]["publication_status"] == "blocked"


def test_area_and_population_weighting_refused():
    for method in ("pop_hhres_2022", "footprint_area", "area_weighted", "population", "area"):
        with pytest.raises(dz22.CrosswalkError, match=method):
            dz22.validate_value_crosswalk(
                [
                    {
                        "dz2011": "S01013401",
                        "dz2022": "S01020870",
                        "weight": 1.0,
                        "method": method,
                    }
                ]
            )


def test_min_share_defaults_on_drops_and_redistributes(uprn_pairs_filtered, uprn_pairs_raw):
    raw, raw_stats = uprn_pairs_raw
    pairs, stats = uprn_pairs_filtered
    assert stats["apply_min_share"] is True
    assert stats["dropped_pairs"] >= 1
    assert stats["dropped_uprns"] >= 1
    assert stats["kept_pairs"] == len(raw) - stats["dropped_pairs"]
    # Synthetic: S01013402 drops the 1-UPRN sliver; S01013404 drops the 1-UPRN sliver.
    assert stats["dropped_pairs"] == 2
    assert stats["dropped_uprns"] == 2
    by = dz22.validate_value_crosswalk(pairs)
    for src, edges in by.items():
        assert sum(w for _, w in edges) == pytest.approx(1.0, abs=dz22.WEIGHT_TOL)
    # Dropped destinations must not appear.
    kept_keys = {(p["dz2011"], p["dz2022"]) for p in pairs}
    assert ("S01013402", "S01020872") not in kept_keys
    assert ("S01013404", "S01020873") not in kept_keys
    assert raw_stats["dropped_pairs"] == 0


def test_zero_overlap_pairs_all_1069_get_zero_rent_no_error(uprn_pairs_raw):
    """Every overlap_pair gets £0 and raises nothing — no skip."""
    pairs, _ = uprn_pairs_raw
    zero = dz22.load_zero_uprn_overlap_pairs(ZERO)
    assert len(zero) == 1069
    assert all(z["kind"] == "overlap_pair" for z in zero)
    weight_keys = {(p["dz2011"], p["dz2022"]) for p in pairs}
    for z in zero:
        assert (z["dz2011"], z["dz2022"]) not in weight_keys

    alt = "S01020870"
    for z in zero:
        dst = alt if z["dz2022"] != alt else "S01020871"
        edges = [
            {
                "dz2011": z["dz2011"],
                "dz2022": dst,
                "weight": 1.0,
                "method": "address_uprn",
                "uprn_count": 10,
            }
        ]
        out = dz22.crosswalk_surface_to_dz2022(
            [_src(code=z["dz2011"], rent=100.0)],
            edges,
            uprn_totals_2022={dst: 10},
        )
        by = {r["code"]: r["measured_rent"] for r in out}
        assert z["dz2022"] not in by
        assert by.get(z["dz2022"], 0.0) == 0.0
        assert sum(by.values()) == pytest.approx(100.0)


def test_zero_address_dz2022_errors_with_fixture():
    """Error only when rent would land on a 2022 zone with no address points (fixture)."""
    pairs = [
        {
            "dz2011": "S01013401",
            "dz2022": "S01020870",
            "weight": 1.0,
            "method": "address_uprn",
            "uprn_count": 0,
        }
    ]
    with pytest.raises(dz22.CrosswalkError, match="no address points"):
        dz22.crosswalk_surface_to_dz2022(
            [_src()],
            pairs,
            uprn_totals_2022={"S01020870": 0},
        )


def test_zero_dwellings_raises_not_blank():
    pairs = [
        {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0, "method": "address_uprn"}
    ]
    with pytest.raises(dz22.CrosswalkError, match="zero dwellings"):
        dz22.crosswalk_surface_to_dz2022(
            [_src()], pairs, dwellings_by_code={"S01020870": 0}
        )


def test_rent_zone_missing_from_crosswalk_raises():
    pairs = [
        {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0, "method": "address_uprn"}
    ]
    with pytest.raises(dz22.CrosswalkError, match="missing from crosswalk"):
        dz22.crosswalk_surface_to_dz2022(
            [_src(code="S01013401"), _src(code="S01013402", rent=50.0)],
            pairs,
        )


def test_census_disagree_flags_passthrough(uprn_pairs_raw):
    pairs, stats = uprn_pairs_raw
    assert stats["flagged_pairs"] == 1  # synthetic sample
    flagged = [p for p in pairs if p["share_diff_flag"]]
    assert flagged
    sample = flagged[0]
    out = dz22.crosswalk_surface_to_dz2022(
        [_src(code=sample["dz2011"], rent=100.0)],
        [p for p in pairs if p["dz2011"] == sample["dz2011"]],
    )
    assert any("share_diff_flag" in r["proxy_tags"] for r in out)
    assert all(r["publication_status"] == "blocked" for r in out)


def test_no_household_share_row_ok(uprn_pairs_raw):
    pairs, stats = uprn_pairs_raw
    assert stats["hh_share_missing_rows"] >= 1
    no_hh = [p for p in pairs if p["hh2022_share"] is None]
    assert any(p["dz2011"] == "S01010206" for p in no_hh)
    edges = [p for p in pairs if p["dz2011"] == "S01010206"]
    out = dz22.crosswalk_surface_to_dz2022([_src(code="S01010206", rent=50.0)], edges)
    assert out and all(r["crosswalk_method"] == "address_uprn" for r in out)


def test_estimate_labels_measured_partly_fully():
    pairs = [
        {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0, "method": "address_uprn"}
    ]
    out = dz22.crosswalk_surface_to_dz2022(
        [_src(fill_method="observed_pooled")], pairs
    )
    assert out[0]["estimate_label"] == "measured"

    out = dz22.crosswalk_surface_to_dz2022(
        [_src(fill_method="model_filled")], pairs
    )
    assert out[0]["estimate_label"] == "fully_estimated"

    mix_pairs = [
        {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0, "method": "address_uprn"},
        {"dz2011": "S01013402", "dz2022": "S01020870", "weight": 1.0, "method": "address_uprn"},
    ]
    out = dz22.crosswalk_surface_to_dz2022(
        [
            _src(code="S01013401", fill_method="observed_pooled", rent=100.0),
            _src(code="S01013402", fill_method="model_filled", rent=100.0),
        ],
        mix_pairs,
    )
    assert out[0]["estimate_label"] == "partly_estimated"


def test_estimate_label_carried_through_rollup_to_scotland():
    pairs = [
        {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0, "method": "address_uprn"},
        {"dz2011": "S01013402", "dz2022": "S01020871", "weight": 1.0, "method": "address_uprn"},
    ]
    dz = dz22.crosswalk_surface_to_dz2022(
        [
            _src(code="S01013401", fill_method="observed_pooled", rent=100.0),
            _src(code="S01013402", fill_method="model_filled", rent=200.0),
        ],
        pairs,
        dwellings_by_code={"S01020870": 10, "S01020871": 20},
    )
    spine = [
        {
            "code": "S01020870",
            "vintage": 2022,
            "name": "SYNTHETIC",
            "iz_code": "S02000001",
            "la_code": "S12000036",
            "la_name": "SYNTHETIC",
        },
        {
            "code": "S01020871",
            "vintage": 2022,
            "name": "SYNTHETIC",
            "iz_code": "S02000001",
            "la_code": "S12000036",
            "la_name": "SYNTHETIC",
        },
    ]
    rolled = roll.rollup_surface_rent_dz2022(dz, spine)
    scotland = next(r for r in rolled if r["geo_level"] == "scotland")
    council = next(r for r in rolled if r["geo_level"] == "council")
    assert scotland["estimate_label"] == "partly_estimated"
    assert council["estimate_label"] == "partly_estimated"


def test_scotland_total_exact_to_penny(uprn_pairs_filtered):
    pairs, _ = uprn_pairs_filtered
    sources = sorted({p["dz2011"] for p in pairs})
    rows = [_src(code=c, rent=12.34) for c in sources]
    out = dz22.crosswalk_surface_to_dz2022(rows, pairs)
    dz22.assert_scotland_total_conserved(rows, out)


def test_missing_2011_zone_from_weights_raises(uprn_pairs_filtered):
    pairs, _ = uprn_pairs_filtered
    src = pairs[0]["dz2011"]
    edges = [p for p in pairs if p["dz2011"] == src]
    with pytest.raises(dz22.CrosswalkError, match="missing"):
        dz22.crosswalk_surface_to_dz2022([], edges)


def test_configured_path_helpers():
    assert dz22.WEIGHTS_FILENAME in str(dz22.default_uprn_weights_path())
    assert dz22.ZERO_FILENAME in str(dz22.default_zero_uprn_path())
