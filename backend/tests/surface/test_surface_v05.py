"""Rules v0.5: total dwellings, BRMA dwelling shares with half-widths, rent per residential hectare. SYNTHETIC."""

import pandas as pd
import pytest

from georgist import surface_harvester as hv
from georgist import surface_rent as sr

from .test_surface_output import _row


def test_brma_dwelling_shares_single_and_split():
    single = [{"brma_id": "B1", "household_share": 1.0}]
    assert sr.brma_dwelling_shares(single, []) == ({"B1": 1.0}, {"B1": 0.0}, "single_brma")
    hh = [{"brma_id": "B1", "household_share": 0.9}, {"brma_id": "B2", "household_share": 0.1}]
    bounds = [{"brma_id": "B1", "share_mid": 0.85, "share_halfwidth": 0.05}, {"brma_id": "B2", "share_mid": 0.15, "share_halfwidth": 0.05}]
    mid, hw, basis = sr.brma_dwelling_shares(hh, bounds)
    assert mid == {"B1": 0.85, "B2": 0.15} and hw["B2"] == 0.05 and basis == "share_mid_bounds"
    with pytest.raises(ValueError):  # household_share never stands in for dwellings
        sr.brma_dwelling_shares(hh, [])
    with pytest.raises(ValueError):
        sr.brma_dwelling_shares(hh, bounds[:1])


def test_yield_band_from_share_halfwidth():
    cells = {"B1": sr.YieldCell("B1", 2, 0.03, "cell"), "B2": sr.YieldCell("B2", 2, 0.05, "cell")}
    z = sr.blend_zone_yield({"B1": 0.85, "B2": 0.15}, cells, halfwidths={"B1": 0.05, "B2": 0.05})
    assert z.y_land == pytest.approx(0.85 * 0.03 + 0.15 * 0.05)
    assert z.y_low == pytest.approx(0.90 * 0.03 + 0.10 * 0.05) and z.y_high == pytest.approx(0.80 * 0.03 + 0.20 * 0.05)
    assert "brma_share_bounds_in_band" in z.tags
    assert sr.blend_zone_yield({"B1": 1.0}, cells, halfwidths={"B1": 0.0}).y_low is None


def test_share_halfwidth_and_config_yield_bands(cfg, band):
    """No halfwidths → Georgist config yield band; halfwidths → BRMA share-bounds band."""
    cells = {"B1": sr.YieldCell("B1", 2, 0.03, "cell"), "B2": sr.YieldCell("B2", 2, 0.05, "cell")}
    config_band = _row(cfg, band, zone_yield=sr.blend_zone_yield({"B1": 0.85, "B2": 0.15}, cells))
    share_band = _row(
        cfg, band,
        zone_yield=sr.blend_zone_yield(
            {"B1": 0.85, "B2": 0.15}, cells, halfwidths={"B1": 0.05, "B2": 0.05},
        ),
    )
    assert share_band["measured_rent"] == pytest.approx(config_band["measured_rent"])
    assert "yield_band_from_config" in config_band["proxy_tags"]
    assert "brma_share_bounds_in_band" in share_band["proxy_tags"]
    assert config_band["uncertainty_low"] < config_band["measured_rent"] < config_band["uncertainty_high"]
    assert share_band["uncertainty_low"] < share_band["measured_rent"] < share_band["uncertainty_high"]


def test_rent_per_residential_hectare(cfg, band):
    row = _row(cfg, band)
    assert row["rent_per_res_ha"] is None and row["residential_land_ha"] is None and "pending_residential_land" in row["proxy_tags"]
    gis = _row(cfg, band, residential_land_ha=20.0, residential_land_source="gis_residential_land")
    assert gis["rent_per_res_ha"] == pytest.approx(gis["measured_rent"] / 20.0, abs=0.01)
    assert gis["measured_rent_per_dwelling"] is not None  # per dwelling stays as the second view
    rough = _row(cfg, band, residential_land_ha=50.0, residential_land_source="settlement_area")
    assert "res_land_settlement_area_rough" in rough["proxy_tags"]
    for bad in ("zone_area", "data_zone_area", None):
        with pytest.raises(ValueError):
            _row(cfg, band, residential_land_ha=300.0, residential_land_source=bad)


def test_vacancy_and_second_homes_carried_not_in_rent(cfg, band):
    d = sr.dwellings_for({("S01013401", 2011, 2025): {"dwellings_total": 500, "vacant_share": 0.05, "second_home_share": 0.2}},
                         "S01013401", 2011, 2025, source="SYNTHETIC")
    row = _row(cfg, band, dwellings=d)
    base = _row(cfg, band)
    assert row["vacant_share"] == 0.05 and row["second_home_share"] == 0.2
    assert row["measured_rent"] == pytest.approx(base["measured_rent"])  # occupancy doesn't change rent


def test_dwelling_loader_is_pluggable(tmp_path):
    """Data Zones dwellings_by_year schema (code, vintage 2011|2022, count_year, ...); joins on price_year."""
    p = tmp_path / "dz_dwellings_by_year_SYNTHETIC.csv"
    pd.DataFrame({"code": ["S01013401", "S01020801", "S01013402"], "vintage": [2011, 2022, 2011], "count_year": [2025, 2025, 2024],
                  "dwellings_total": [500, 480, 300], "vacant": [25, 20, 3], "second_homes": [5, 4, 0]}).to_csv(p, index=False)
    df = hv.load_dwelling_counts("datazones_ct_table", p, price_year=2025, vintage=2011, synthetic=True, verify_manifest=False)
    assert tuple(df.columns) == hv.DWELLING_FRAME and len(df) == 1   # S01013402 has no 2025 count: absent, not filled from 2024
    assert df.loc[0, "dwellings_total"] == 500 and df.loc[0, "vacant_share"] == pytest.approx(0.05)
    assert df.loc[0, "count_year"] == 2025 and df.loc[0, "vintage"] == 2011
    counts = {(r.code, r.vintage, int(r.count_year)): int(r.dwellings_total) for r in df.itertuples()}
    gap = sr.dwellings_for(counts, "S01013402", 2011, 2025)
    assert gap.count is None and "dwellings_missing_year" in gap.tags
    with pytest.raises(ValueError):
        hv.load_dwelling_counts("census_households", p, price_year=2025, vintage=2011)
    bad = tmp_path / "dz_hh_SYNTHETIC.csv"
    pd.DataFrame({"code": ["S01013401"], "vintage": [2011], "count_year": [2025], "households": [480]}).to_csv(bad, index=False)
    with pytest.raises(ValueError):  # households are not dwellings
        hv.load_dwelling_counts("datazones_ct_table", bad, price_year=2025, vintage=2011, verify_manifest=False)


def test_schema_names_and_years(cfg, band):
    row = _row(cfg, band)
    assert row["code"] == "S01013401" and row["vintage"] == 2011
    assert row["price_year"] == 2025 and row["evidence_year"] == 2023 and row["count_year"] == 2025
    for old in ("zone_code", "zone_vintage", "price_base_year", "dwelling_year", "price_years"):
        assert old not in row


def test_totals_refuse_differing_price_year(cfg, band):
    a = _row(cfg, band)
    b = {**a, "code": "S01013402", "price_year": 2024}
    with pytest.raises(sr.YearMismatchError):
        sr.total_measured_rent([a, b])
    with pytest.raises(sr.YearMismatchError):
        sr.total_policy_rent([a, b])
    assert sr.total_measured_rent([a, {**a, "code": "S01013402"}])["proxy"] == pytest.approx(2 * a["measured_rent"])


def test_integer_vintage_and_code_ranges(cfg, band):
    from georgist import surface_zones as sz
    assert sz.vintage_int("DZ2011") == 2011 and sz.vintage_int(2022) == 2022
    with pytest.raises(ValueError):
        sz.vintage_int("DZ2001")
    assert sz.code_in_vintage("S01006506", 2011) and sz.code_in_vintage("S01013481", 2011)
    assert not sz.code_in_vintage("S01013482", 2011) and sz.code_in_vintage("S01013482", 2022)
    assert sz.code_in_vintage("S01020873", 2022) and not sz.code_in_vintage("S01020874", 2022)
    assert not sz.code_in_vintage("S01006505", 2011) and not sz.code_in_vintage("S01999901", 2011)
    assert _row(cfg, band)["vintage"] == 2011
    with pytest.raises(ValueError):  # string vintage refused on output rows
        _row(cfg, band, vintage="DZ2011")
    with pytest.raises(ValueError):  # 2022 code on a 2011 row
        _row(cfg, band, code="S01013500")
    assert sz.manifest_vintage_label([2022, 2011, 2011]) == "DZ2011;DZ2022"


def test_datazones_dwellings_verified_against_manifest(tmp_path):
    import hashlib
    p = tmp_path / "dwellings_by_year.csv"
    pd.DataFrame({"code": ["S01013401", "S01013401", "S01020801"], "vintage": [2011, 2011, 2022], "count_year": [2024, 2025, 2025],
                  "dwellings_total": [490, 500, 300], "occupied": [470, 480, 290], "vacant": [15, 15, 8], "second_homes": [5, 5, 2],
                  "assessor_dwellings_dec": [999, 999, 999]}).to_csv(p, index=False)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    man = {"file": p.name, "owner": "datazones", "source": "SYNTHETIC", "licence": "OGL v3", "publish_level": "public_zone",
           "zone_vintage": "DZ2011;DZ2022", "key": "(code, vintage, count_year)", "rows": 3, "sha256": sha}
    pd.DataFrame([man]).to_csv(tmp_path / "manifest.csv", index=False)
    df = hv.load_dwelling_counts("datazones_ct_table", p, price_year=2025, vintage=2011)
    assert len(df) == 1 and df.loc[0, "dwellings_total"] == 500 and df.loc[0, "vintage"] == 2011   # never assessor_dwellings_dec
    assert df.loc[0, "second_home_share"] == pytest.approx(0.01)
    pd.DataFrame([{**man, "sha256": "0" * 64}]).to_csv(tmp_path / "manifest.csv", index=False)
    with pytest.raises(ValueError):
        hv.load_dwelling_counts("datazones_ct_table", p, price_year=2025, vintage=2011)


def test_absent_from_price_file_is_no_price_not_zero():
    lv = sr.resolve_land_value(dwellings=300, observed=None, sales_n=0, model_gbp=None, n_min=5, n_full=15, shrinkage_k=8,
                               absent_from_price_file=True)
    assert lv.land_value is None and lv.fill_method == "model_filled" and "absent_from_ros_price_file" in lv.tags
    lv2 = sr.resolve_land_value(dwellings=300, observed=None, sales_n=0, model_gbp=20_000.0, n_min=5, n_full=15, shrinkage_k=8,
                                absent_from_price_file=True)
    assert lv2.land_value == 20_000.0 and "model_fill_pending" not in lv2.tags
