"""DZ2022 address-UPRN crosswalk (PR B). Uses committed weights + SYNTHETIC rents."""

from __future__ import annotations

from pathlib import Path

import pytest

from georgist import surface_dz2022 as dz22

DATAZONES = Path(__file__).resolve().parents[3] / "data" / "processed" / "datazones"
WEIGHTS = DATAZONES / "dz2011_dz2022_uprn_weights.csv"
ZERO = DATAZONES / "dz_crosswalk_zero_uprn.csv"


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
    pairs, stats = dz22.load_uprn_weight_rows(WEIGHTS, apply_min_share=True)
    return pairs, stats


@pytest.fixture(scope="module")
def uprn_pairs_raw():
    pairs, stats = dz22.load_uprn_weight_rows(WEIGHTS, apply_min_share=False)
    return pairs, stats


def test_os_ogl_attribution_on_load(uprn_pairs_filtered):
    _, stats = uprn_pairs_filtered
    assert "Contains OS data © Crown copyright and database right 2026" in stats["attribution"]
    assert "Open Government Licence v3.0" in stats["attribution"]
    assert "National Records of Scotland" in stats["attribution"]
    assert "Scottish Government" in stats["attribution"]


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


def test_min_share_defaults_on_expected_drops(uprn_pairs_filtered):
    pairs, stats = uprn_pairs_filtered
    assert stats["apply_min_share"] is True
    assert stats["raw_pairs"] == dz22.EXPECTED_RAW_PAIRS == 14458
    assert stats["dropped_pairs"] == dz22.EXPECTED_MIN_SHARE_DROPPED_PAIRS == 2848
    assert stats["dropped_uprns"] == dz22.EXPECTED_MIN_SHARE_DROPPED_UPRNS == 5197
    assert stats["kept_pairs"] == 14458 - 2848
    assert stats["dz2011"] == dz22.EXPECTED_DZ2011 == 6976
    assert stats["dz2022"] == dz22.EXPECTED_DZ2022 == 7392
    # Shares still sum to 1 per 2011 zone.
    by = dz22.validate_value_crosswalk(pairs)
    assert len(by) == 6976
    for src, edges in by.items():
        assert sum(w for _, w in edges) == pytest.approx(1.0, abs=dz22.WEIGHT_TOL)


def test_min_share_can_be_disabled(uprn_pairs_raw):
    pairs, stats = uprn_pairs_raw
    assert stats["dropped_pairs"] == 0
    assert len(pairs) == 14458


def test_zero_overlap_pairs_get_no_rent(uprn_pairs_filtered):
    pairs, _ = uprn_pairs_filtered
    zero = dz22.load_zero_uprn_overlap_pairs(ZERO)
    assert zero
    assert all(z["kind"] == "overlap_pair" for z in zero)
    main = {(p["dz2011"], p["dz2022"]) for p in pairs}
    # Also check against raw file contents via loader without filter.
    raw, _ = dz22.load_uprn_weight_rows(WEIGHTS, apply_min_share=False)
    raw_pairs = {(p["dz2011"], p["dz2022"]) for p in raw}
    for z in zero:
        key = (z["dz2011"], z["dz2022"])
        assert key not in raw_pairs
        assert key not in main
    # Synthetic rent on a 2011 zone: zero-overlap 2022 targets receive nothing.
    sample = zero[0]
    # Find any weight edges for that 2011 zone (if present).
    edges = [p for p in pairs if p["dz2011"] == sample["dz2011"]]
    if not edges:
        pytest.skip("sample zero-pair 2011 zone not in filtered weights")
    src_rent = 1000.0
    out = dz22.crosswalk_surface_to_dz2022(
        [_src(code=sample["dz2011"], rent=src_rent)],
        edges,
        uprn_totals_2022=dz22.uprn_totals_by_dz2022(edges),
    )
    by = {r["code"]: r for r in out}
    assert sample["dz2022"] not in by
    assert sum(r["measured_rent"] for r in out) == pytest.approx(src_rent)


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


def test_no_zero_uprn_dz2022_in_committed_weights(uprn_pairs_raw):
    pairs, _ = uprn_pairs_raw
    totals = dz22.uprn_totals_by_dz2022(pairs)
    assert all(v > 0 for v in totals.values())
    assert len(totals) == 7392


def test_census_disagree_flags_passthrough(uprn_pairs_raw):
    pairs, stats = uprn_pairs_raw
    assert stats["flagged_pairs"] == 379
    flagged = [p for p in pairs if p["share_diff_flag"]]
    assert len(flagged) == 379
    # Keep address-point shares; flags do not break conversion.
    sample = flagged[0]
    out = dz22.crosswalk_surface_to_dz2022(
        [_src(code=sample["dz2011"], rent=100.0)],
        [p for p in pairs if p["dz2011"] == sample["dz2011"]],
    )
    assert any("share_diff_flag" in r["proxy_tags"] for r in out)
    assert all(r["publication_status"] == "blocked" for r in out)


def test_five_no_household_share_rows_ok(uprn_pairs_raw):
    pairs, stats = uprn_pairs_raw
    assert stats["hh_share_missing_rows"] == 5
    no_hh = [p for p in pairs if p["hh2022_share"] is None]
    assert len(no_hh) == 5
    codes = sorted({p["dz2011"] for p in no_hh})
    assert codes == ["S01010206", "S01010226", "S01010227", "S01011598"]
    # Conversion still works (zero-dwelling / mismatch zones may have null rent elsewhere).
    for src in codes:
        edges = [p for p in pairs if p["dz2011"] == src]
        out = dz22.crosswalk_surface_to_dz2022([_src(code=src, rent=50.0)], edges)
        assert out
        assert all(r["crosswalk_method"] == "address_uprn" for r in out)


def test_estimate_labels_measured_partly_fully():
    # measured → measured
    pairs = [
        {"dz2011": "S01013401", "dz2022": "S01020870", "weight": 1.0, "method": "address_uprn"}
    ]
    out = dz22.crosswalk_surface_to_dz2022(
        [_src(fill_method="observed_pooled")], pairs
    )
    assert out[0]["estimate_label"] == "measured"

    # fully estimated source → fully estimated
    out = dz22.crosswalk_surface_to_dz2022(
        [_src(fill_method="model_filled")], pairs
    )
    assert out[0]["estimate_label"] == "fully_estimated"

    # mix → partly estimated; estimated 2011 part keeps estimated on 2022
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
    assert "estimate_label=partly_estimated" in out[0]["proxy_tags"]


def test_scotland_total_exact_to_penny(uprn_pairs_filtered):
    pairs, _ = uprn_pairs_filtered
    # Unit rent on every 2011 zone covered by the filtered weights.
    sources = sorted({p["dz2011"] for p in pairs})
    rows = [_src(code=c, rent=1.0) for c in sources]
    # Use a thin subset for speed: first 50 zones + assert helper on full synthetic.
    subset_src = sources[:80]
    subset_pairs = [p for p in pairs if p["dz2011"] in set(subset_src)]
    subset_rows = [_src(code=c, rent=12.34) for c in subset_src]
    out = dz22.crosswalk_surface_to_dz2022(subset_rows, subset_pairs)
    dz22.assert_scotland_total_conserved(subset_rows, out)
    # Full Scotland pin: every 2011 zone, £1 — exact conservation.
    out_all = dz22.crosswalk_surface_to_dz2022(rows, pairs)
    assert len(out_all) == 7392
    dz22.assert_scotland_total_conserved(rows, out_all)
    assert abs(sum(r["measured_rent"] for r in out_all) - 6976.0) <= dz22.PENNY


def test_missing_2011_zone_from_weights_raises(uprn_pairs_filtered):
    pairs, _ = uprn_pairs_filtered
    # Drop one source that the crosswalk lists.
    src = pairs[0]["dz2011"]
    edges = [p for p in pairs if p["dz2011"] == src]
    with pytest.raises(dz22.CrosswalkError, match="missing"):
        dz22.crosswalk_surface_to_dz2022([], edges)


def test_readme_credits_present():
    text = (DATAZONES / "README_dz_crosswalk_uprn.md").read_text(encoding="utf-8")
    assert "Contains OS data © Crown copyright and database right 2026" in text
    assert "Open Government Licence v3.0" in text
