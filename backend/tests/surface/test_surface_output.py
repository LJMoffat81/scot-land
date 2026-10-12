import pytest

from georgist import surface_rent as sr


SYN_FACTOR = 1.05  # SYNTHETIC index factor 2023 -> 2025, not a real UK HPI figure


def _row(cfg, rbband, price=150_000, fill_obs=True, pooled=None, indexed=None, dwellings=None, **over):
    mix = [sr.MixComponent("semi_detached", 1.0, 90.0, "1965-1975")]
    rbs = sr.depreciated_rebuild_band(mix, band=rbband, depreciation=cfg["depreciation"], valuation_year=2025, region=1.0)
    pooled = pooled or sr.PooledPrice(price, 30, "2021-2023", "mean", ("pooled_3y",), 2023)
    indexed = indexed or sr.index_price(pooled, price_year=2025, factor=SYN_FACTOR, series="SYNTHETIC council index",
                                        tags=("indexed_council_hpi",))
    rb = sr.residual_band(indexed.price_indexed_gbp, rbs)
    land = (
        sr.resolve_land_value(dwellings=500, observed=rb.central, sales_n=30, model_gbp=None, n_min=5, n_full=15, shrinkage_k=8)
        if fill_obs else sr.resolve_land_value(dwellings=500, observed=None, sales_n=0, model_gbp=30_000, n_min=5, n_full=15, shrinkage_k=8)
    )
    zy = sr.blend_zone_yield({"SYN-B": 1.0}, {"SYN-B": sr.YieldCell("SYN-B", 2, 0.03, "cell")})
    kw = dict(
        code="S01013401", vintage=2011, valuation_date="2025-04-01", ur6_class=2, ur8_class=2,
        dwellings=dwellings or sr.DwellingCount(500, 2025, 2011, ("dwellings_datazones_by_year",), "SYNTHETIC"),
        pooled=pooled, indexed=indexed, typical_sale_gbp=pooled.price_gbp * 0.9 if pooled.price_gbp else None,
        rebuild_mix_basis="sold", rebuilds=rbs, band=rb, land=land, zone_yield=zy, gross_yield_value=0.05,
        config=cfg, source_id="SYNTHETIC", licence="synthetic-test-only", crosswalk_method="none",
        net_of=["eco_externality"],
    )
    kw.update(over)
    return sr.build_output_row(**kw)


def test_no_rent_by_area_field(cfg, band):
    row = _row(cfg, band)
    # rules 6.4 (v0.5): the only per-area figure is rent per hectare of RESIDENTIAL land
    allowed = {"floor_area_basis", "residential_land_ha", "rent_per_res_ha"}
    assert "floor_area_basis" in sr.INTERNAL_ONLY_COLUMNS
    for col in set(list(row) + list(sr.OUTPUT_COLUMNS)) - allowed:
        assert not any(tok in col for tok in sr.AREA_TOKENS), col


def test_row_carries_rules_fields(cfg, band):
    row = _row(cfg, band)
    for col in ("commons_class", "value_tier", "uncertainty_low", "uncertainty_high", "net_of", "use_basis",
                "crosswalk_method", "source_id", "licence", "price_year", "quality", "publish_level", "raw_residual"):
        assert row[col] not in (None, ""), col
    assert row["value_tier"] == "proxy" and row["commons_class"] == "surface"
    assert row["quality"] == "derived" and row["publish_level"] == "public_zone"
    assert row["price_measure"] == "mean" and row["publication_status"] == "ok"
    assert row["rebuild_status"] == "OPEN_ESTIMATE" and "rebuild_open_estimate" in row["proxy_tags"]
    assert row["measured_rent_per_dwelling"] == pytest.approx(row["land_value"] * 0.03, abs=0.01)
    assert row["measured_rent"] == pytest.approx(row["measured_rent_per_dwelling"] * 500, abs=0.5)


def test_rebuild_band_carried_as_uncertainty(cfg, band):
    row = _row(cfg, band)
    assert row["drc_low_gbp"] < row["drc_gbp"] < row["drc_high_gbp"]
    assert row["land_value_low"] < row["land_value"] < row["land_value_high"]
    assert row["uncertainty_low"] < row["measured_rent"] < row["uncertainty_high"]


def test_negative_residual_visible_in_row(cfg, band):
    row = _row(cfg, band, price=40_000)
    assert row["negative_residual"] is True and row["raw_residual"] < 0
    assert row["land_value"] == 0.0 and row["measured_rent"] == 0.0
    assert "negative_residual" in row["proxy_tags"]


def test_policy_separate_from_measured(cfg, band):
    row = _row(cfg, band)
    assert row["policy_despec_factor"] == 0.70
    assert row["policy_rent"] == pytest.approx(row["measured_rent"] * 0.70, abs=0.01)
    assert row["measured_rent"] == pytest.approx(row["land_value"] * 0.03 * 500, abs=1)  # not despeculated


def test_crosswalk_enum_exact_and_surface_restricted(cfg, band):
    assert sr.CROSSWALK_METHODS == ("none", "pop_hhres_2022", "address_uprn", "value_weighted", "footprint_area")
    assert tuple(cfg["crosswalk_methods"]) == sr.CROSSWALK_METHODS
    for ok in ("none", "address_uprn", "value_weighted"):
        assert _row(cfg, band, crosswalk_method=ok)["crosswalk_method"] == ok
    for bad in ("footprint_area", "pop_hhres_2022", "area_weighted"):
        with pytest.raises(ValueError):
            _row(cfg, band, crosswalk_method=bad)
    with pytest.raises(ValueError):
        _row(cfg, band, net_of=["neighbour_harm"])


def test_attribution_and_policy_cannot_be_totalled(cfg, band):
    rows = [_row(cfg, band, infra_share=0.2), _row(cfg, band, code="S01013402")]
    assert rows[0]["infra_share"] == 0.2 and rows[0]["planning_uplift"] is None
    totals = sr.total_measured_rent(rows)
    assert totals == {"proxy": pytest.approx(rows[0]["measured_rent"] + rows[1]["measured_rent"])}
    for col in ("infra_share", "planning_uplift", "policy_rent", "land_value"):
        with pytest.raises(sr.AttributionOnlyError):
            sr.total_measured_rent(rows, column=col)
    assert sr.total_policy_rent(rows) == pytest.approx(rows[0]["policy_rent"] * 2)


def test_reconciliation_breach_blocks_and_excludes(cfg, band):
    breach = sr.reconciliation_check(module_rents={"surface": (10**9, 10**9, 10**9)}, observed_total_value_gbp=1.0, gross_yield_value=0.05)
    row = _row(cfg, band, reconciliation=breach)
    assert row["publication_status"] == "blocked" and "reconciliation_breach" in row["proxy_tags"]
    assert row["publish_level"] == "public_zone"  # licence level unchanged; clearing the block restores it
    assert sr.total_measured_rent([row]) == {} and sr.public_view([row]) == []


def test_model_filled_quality_and_publish(cfg, band):
    row = _row(cfg, band, fill_obs=False, band=None, model_interval=(20_000, 40_000))
    assert row["quality"] == "modelled" and row["publish_level"] == "public_zone"
    assert row["land_value_low"] == 20_000 and row["land_value_high"] == 40_000


def test_uncertainty_levels(cfg):
    u = cfg["uncertainty"]
    assert sr.uncertainty_level(100, 90, 110, u) == "low"
    assert sr.uncertainty_level(100, 70, 120, u) == "medium"
    assert sr.uncertainty_level(100, 20, 200, u) == "high"
    assert sr.uncertainty_level(None, None, None, u) == "high"


def test_apportion_by_addresses_not_area():
    out = sr.apportion_by_addresses(1000.0, {"p1": 3, "p2": 1})
    assert out == {"p1": 750.0, "p2": 250.0}


def test_totals_use_mean_and_per_home_is_total_over_count(cfg, band):
    row = _row(cfg, band)
    assert row["land_value_zone_total"] == pytest.approx(row["land_value"] * 500)
    assert row["measured_rent"] == pytest.approx(row["land_value_zone_total"] * 0.03, abs=0.01)
    assert row["measured_rent_per_dwelling"] == pytest.approx(row["measured_rent"] / 500, abs=0.01)
    assert row["typical_sale_gbp"] == pytest.approx(150_000 * 0.9)  # median: display only
    with pytest.raises(ValueError):
        _row(cfg, band, pooled=sr.PooledPrice(150_000, 30, "2021-2023", "median", (), 2023))


def test_indexed_price_columns_raw_untouched(cfg, band):
    row = _row(cfg, band)
    assert row["price_gbp"] == 150_000 and row["evidence_year"] == 2023  # raw RoS kept (sales year)
    assert row["price_indexed_gbp"] == pytest.approx(150_000 * SYN_FACTOR)
    assert row["price_index_factor"] == SYN_FACTOR and row["price_year"] == 2025
    assert row["price_index_series"] == "SYNTHETIC council index" and "indexed_council_hpi" in row["proxy_tags"]
    assert row["raw_residual"] == pytest.approx(150_000 * SYN_FACTOR - row["drc_gbp"])  # residual on the indexed price


def test_unindexed_year_gap_refused(cfg, band):
    pooled = sr.PooledPrice(150_000, 30, "2021-2023", "mean", (), 2023)
    with pytest.raises(sr.YearMismatchError):
        sr.index_price(pooled, price_year=2025)  # no recorded index
    same = sr.index_price(sr.PooledPrice(150_000, 30, "2025", "mean", (), 2025), price_year=2025)
    assert same.factor == 1.0 and same.series == "none"
    with pytest.raises(sr.YearMismatchError):  # forged IndexedPrice without a series
        _row(cfg, band, pooled=pooled, indexed=sr.IndexedPrice(150_000, 2023, 157_500, 2025, 1.05, "none"))
    assert "index_factor_extreme" in sr.index_price(pooled, price_year=2025, factor=1.25, series="S", extreme_log_abs=0.15).tags


def test_index_base_must_equal_rebuild_base_and_dwelling_year(cfg, band):
    pooled = sr.PooledPrice(150_000, 30, "2021-2023", "mean", (), 2023)
    to_2024 = sr.index_price(pooled, price_year=2024, factor=1.02, series="SYNTHETIC")
    with pytest.raises(sr.YearMismatchError):  # index base 2024 != rebuild base 2025
        _row(cfg, band, pooled=pooled, indexed=to_2024, dwellings=sr.DwellingCount(500, 2024, 2011))
    with pytest.raises(sr.YearMismatchError):  # strict: dwellings must be 2025
        _row(cfg, band, dwellings=sr.DwellingCount(500, 2024, 2011))
    with pytest.raises(sr.VintageMismatchError):
        _row(cfg, band, dwellings=sr.DwellingCount(500, 2025, 2022))


def test_dwelling_year_lag_policy(cfg, band):
    assert cfg["dwellings"]["year_policy"] == "strict"  # default
    cfg["dwellings"]["year_policy"], cfg["dwellings"]["max_lag_years"] = "lag_allowed", 1
    strict_row = _row(cfg, band)
    lag_row = _row(cfg, band, dwellings=sr.DwellingCount(480, 2024, 2011))
    assert lag_row["count_year_lag"] == 1 and "dwelling_year_lag" in lag_row["proxy_tags"]
    assert lag_row["measured_rent_per_dwelling"] == pytest.approx(strict_row["measured_rent_per_dwelling"], abs=0.01)
    assert lag_row["measured_rent"] == pytest.approx(lag_row["measured_rent_per_dwelling"] * 480, abs=1)
    with pytest.raises(sr.YearMismatchError):  # beyond max lag
        _row(cfg, band, dwellings=sr.DwellingCount(470, 2023, 2011))
    with pytest.raises(sr.YearMismatchError):  # never a later year
        _row(cfg, band, dwellings=sr.DwellingCount(470, 2026, 2011))


def test_skew_flag_in_row(cfg, band):
    pooled = sr.PooledPrice(300_000, 8, "2021-2023", "mean", (), 2023)
    row = _row(cfg, band, pooled=pooled, typical_sale_gbp=150_000)
    assert row["price_skew_flag"] is True and row["mean_median_ratio"] == pytest.approx(2.0)
    assert "price_skew_small_sample" in row["proxy_tags"]
    assert _row(cfg, band)["price_skew_flag"] is False


def test_rebuild_mix_basis_stamped(cfg, band):
    assert _row(cfg, band)["rebuild_mix_basis"] == "sold"
    stock = _row(cfg, band, rebuild_mix_basis="all_stock")
    assert stock["rebuild_mix_basis"] == "all_stock" and "rebuild_mix_all_stock" in stock["proxy_tags"]
    with pytest.raises(ValueError):
        _row(cfg, band, rebuild_mix_basis="epc")
    assert sr.epc_coverage_tags(1.2) == ("epc_coverage_over_100_recent_only",) and sr.epc_coverage_tags(0.8) == ()


def test_missing_dwelling_year_flagged_not_filled(cfg, band):
    gap = sr.dwellings_for({("S01013401", 2011, 2024): 500}, "S01013401", 2011, 2025)
    row = _row(cfg, band, dwellings=gap)
    assert row["dwellings"] is None and row["measured_rent"] is None and row["measured_rent_per_dwelling"] is None
    assert row["quality"] == "placeholder" and "dwellings_missing_year" in row["proxy_tags"]
    assert sr.total_measured_rent([row, _row(cfg, band)]) == {"proxy": pytest.approx(_row(cfg, band)["measured_rent"])}
    assert sr.public_view([row]) == []  # placeholders are not served


def test_public_view_drops_diagnostics_and_required_fields(cfg, band):
    row = _row(cfg, band)
    pub = sr.public_view([row])
    assert len(pub) == 1
    for col in sr.INTERNAL_ONLY_COLUMNS:
        assert col not in pub[0], col
    for col in sr.REQUIRED_FIELDS:
        assert col in pub[0], col
    bad = dict(row)
    del bad["licence"]
    with pytest.raises(sr.RowRejectedError):
        sr.public_view([bad])
    with pytest.raises(sr.RowRejectedError):
        sr.validate_required(dict(row, source_id=None))
    assert sr.public_view([dict(row, publish_level="internal")]) == []


def test_estate_gis_input_forces_internal_and_swing_internal(cfg, band):
    plain = _row(cfg, band)
    assert plain["publish_level"] != "internal" or "publish_internal_estate_input" not in plain["proxy_tags"]
    row = _row(cfg, band, extra_tags=("estate_share_gis",), drc_swing={"central": 1.0, "rebuild_low": 0.9})
    assert row["publish_level"] == "internal" and "publish_internal_estate_input" in row["proxy_tags"]
    assert row["drc_swing_gbp"]["rebuild_low"] == 0.9 and "drc_swing_gbp" in sr.INTERNAL_ONLY_COLUMNS


def test_residential_area_never_changes_totals_and_low_confidence_tags(cfg, band):
    base = _row(cfg, band)
    a = _row(cfg, band, residential_land_ha=12.5, residential_land_source="gis_residential_land")
    b = _row(cfg, band, residential_land_ha=0.4, residential_land_source="gis_residential_land",
             residential_land_low_confidence=("weak_match", "mask_too_big"))
    for col in ("measured_rent", "measured_rent_per_dwelling", "land_value", "land_value_zone_total", "uncertainty_low", "uncertainty_high"):
        assert base[col] == a[col] == b[col], col
    assert sr.total_measured_rent([base]) == sr.total_measured_rent([a]) == sr.total_measured_rent([b])
    assert a["rent_per_res_ha"] == pytest.approx(a["measured_rent"] / 12.5) and base["rent_per_res_ha"] is None
    assert {"res_land_low_confidence_weak_match", "res_land_low_confidence_mask_too_big"} <= set(b["proxy_tags"])
    assert not any(t.startswith("res_land_low_confidence") for t in a["proxy_tags"])
    with pytest.raises(ValueError):
        _row(cfg, band, residential_land_ha=1.0, residential_land_source="gis_residential_land",
             residential_land_low_confidence=("whatever",))
