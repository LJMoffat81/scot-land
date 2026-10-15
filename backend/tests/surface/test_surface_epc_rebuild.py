"""EPC-rollup rebuild inputs, GIS manifest checks and illustrative tables. SYNTHETIC rows only."""

import hashlib

import pandas as pd
import pytest

from georgist import surface_harvester as hv
from georgist import surface_illustrative as si
from georgist import surface_rent as sr


def _epc(**over):
    """SYNTHETIC rollup row in the GIS column layout (all-time and recent10_ families)."""
    base = {
        "pt_house_share": 0.5, "pt_flat_share": 0.4, "pt_bungalow_share": 0.0, "pt_maisonette_share": 0.0,
        "pt_park_home_share": 0.0, "pt_unknown_share": 0.1,
        "bf_detached_share": 0.2, "bf_semi_detached_share": 0.2, "bf_mid_terrace_share": 0.3, "bf_end_terrace_share": 0.1,
        "bf_enclosed_mid_terrace_share": 0.0, "bf_enclosed_end_terrace_share": 0.0, "bf_unknown_share": 0.2,
        "age_pre1919_share": 0.5, "age_2008_on_share": 0.4, "age_unknown_share": 0.1,
        "tfa_n": 100, "tfa_median_m2": 80.0, "tfa_mean_m2": 88.0, "tfa_n_house": 50, "tfa_mean_house_m2": 110.0,
        "tfa_n_flat": 40, "tfa_mean_flat_m2": 60.0, "suppressed": False, "coverage_share": 0.7,
    }
    for k in list(base):
        if k not in ("coverage_share",):
            base[f"recent10_{k}"] = base[k]
    base["recent10_tfa_mean_m2"] = 85.0
    base.update(over)
    return base


def test_epc_type_mapping_from_marginals():
    t = sr.epc_type_shares(_epc())
    assert t["flat_purpose_built"] == pytest.approx(0.4) and t["other"] == pytest.approx(0.1)
    known = 0.2 + 0.2 + 0.4  # unknown built form dropped
    assert t["detached"] == pytest.approx(0.5 * 0.2 / known) and t["terraced"] == pytest.approx(0.5 * 0.4 / known)
    assert sum(t.values()) == pytest.approx(1.0) and t["flat_conversion"] == 0.0


def test_all_time_primary_mean_house_flat_areas():
    inp = sr.zone_rebuild_inputs(_epc(), None, default_area_m2=97)
    assert inp.source == "epc_all_time" and inp.floor_area_basis == "mean" and inp.floor_area_m2 == 88.0
    assert inp.area_for("detached") == 110.0 and inp.area_for("flat_purpose_built") == 60.0 and inp.area_for("other") == 88.0
    assert {"floor_area_basis=mean", "floor_area_by_house_flat", "rebuild_mix_all_stock"} <= set(inp.tags)
    r10 = sr.zone_rebuild_inputs(_epc(), None, default_area_m2=97, primary="recent10")
    assert r10.source == "epc_recent10" and r10.mix_basis == "sold" and r10.floor_area_m2 == 85.0


def test_coverage_over_100_uses_recent_certificates():
    inp = sr.zone_rebuild_inputs(_epc(coverage_share=1.3), None, default_area_m2=97)
    assert inp.source == "epc_recent10" and "epc_coverage_over_100_recent_only" in inp.tags


def test_group_mean_blank_falls_back_to_zone_mean_then_default():
    inp = sr.zone_rebuild_inputs(_epc(tfa_n_flat=3, tfa_mean_flat_m2=None), None, default_area_m2=97)
    assert inp.area_for("flat_purpose_built") == 88.0 and inp.area_for("detached") == 110.0
    none = sr.zone_rebuild_inputs(_epc(tfa_mean_m2=None, tfa_mean_house_m2=None, tfa_mean_flat_m2=None), None, default_area_m2=97)
    assert none.floor_area_m2 == 97 and "floor_area_default" in none.tags and none.floor_area_basis == "mean"


def test_median_only_rollup_is_tagged_biased_low():
    row = {k: v for k, v in _epc().items() if "tfa_mean" not in k}
    inp = sr.zone_rebuild_inputs(row, None, default_area_m2=97)
    assert inp.floor_area_basis == "median" and inp.floor_area_m2 == 80.0
    assert {"floor_area_basis=median", "floor_area_median_biased_low"} <= set(inp.tags)


def test_nrs2017_fallback_tagged():
    nrs = {"type_detached": 10, "type_semi_detached": 10, "type_terraced": 20, "type_flat": 60, "type_unknown": 0}
    inp = sr.zone_rebuild_inputs(None, nrs, default_area_m2=97)
    assert inp.source == "nrs2017" and inp.floor_area_basis == "default" and inp.floor_area_m2 == 97
    assert "rebuild_mix_nrs2017_fallback" in inp.tags and inp.type_shares["flat_purpose_built"] == pytest.approx(0.6)
    with pytest.raises(ValueError):
        sr.zone_rebuild_inputs(None, None, default_area_m2=97)


def test_zone_rebuild_band_uses_type_areas(cfg, band):
    inp = sr.ZoneRebuildInputs({**dict.fromkeys(sr.DWELLING_TYPES, 0.0), "detached": 0.5, "flat_purpose_built": 0.5},
                               None, 90.0, "mean", "all_stock", "epc_all_time", (), {"house": 120.0, "flat": 60.0})
    rbs = sr.zone_rebuild_band(inp, band=band, depreciation=cfg["depreciation"], valuation_year=2025, default_remaining_factor=0.5)
    new_c = 0.5 * 120 * band["detached"]["central"] + 0.5 * 60 * band["flat_purpose_built"]["central"]
    assert rbs["central"].rebuild_new_gbp == pytest.approx(new_c) and rbs["central"].drc_gbp == pytest.approx(0.5 * new_c)
    with pytest.raises(sr.PendingSourceError):
        sr.zone_rebuild_band(inp, band=band, depreciation=cfg["depreciation"], valuation_year=2025)
    aged = sr.ZoneRebuildInputs(inp.type_shares, {"2008 onwards": 1.0}, 90.0, "mean", "all_stock", "x", (), inp.area_by_group)
    r2 = sr.zone_rebuild_band(aged, band=band, depreciation=cfg["depreciation"], valuation_year=2025)
    r_b = 0.00137 / 0.497
    assert r2["central"].drc_gbp == pytest.approx(new_c * (1 - r_b) ** 9)


def _gis_dir(tmp_path, rows, key="(code, vintage)", tamper=False):
    p = tmp_path / "epc_dz_rollup.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    pd.DataFrame([{"file": p.name, "owner": "gis", "source": "SYNTHETIC", "licence": "synthetic", "publish_level": "public_zone",
                   "zone_vintage": "DZ2011;DZ2022", "key": key, "rows": len(rows), "sha256": "0" * 64 if tamper else sha}]
                 ).to_csv(tmp_path / "manifest.csv", index=False)
    return p


def test_gis_manifest_verification(tmp_path):
    rows = [{"code": "S01013401", "vintage": 2011, "x": 1}, {"code": "S01020801", "vintage": 2022, "x": 2}]
    df = hv.load_gis_output(_gis_dir(tmp_path, rows), vintage=2011)
    assert list(df["code"]) == ["S01013401"] and df.attrs["provenance"]["vintage_used"] == 2011
    with pytest.raises(ValueError):
        hv.load_gis_output(_gis_dir(tmp_path, rows, tamper=True))
    with pytest.raises(ValueError):
        hv.load_gis_output(_gis_dir(tmp_path, rows + [{"code": "unknown", "vintage": 2011, "x": 3}]))
    with pytest.raises(ValueError):  # duplicate key
        hv.load_gis_output(_gis_dir(tmp_path, rows + [rows[0]]))


def test_urban_rural_2020_loader(tmp_path):
    p = tmp_path / "ur_SYNTHETIC.csv"
    pd.DataFrame({"DataZone": ["S01013401", "S01013402"], "UR2FOLD": [1, 2], "UR3FOLD": [1, 3], "UR6FOLD": [1, 6], "UR8FOLD": [1, 8]}).to_csv(p, index=False)
    with pytest.raises(ValueError):
        hv.load_urban_rural_2020_dz2011(p)  # pinned sha
    df = hv.load_urban_rural_2020_dz2011(p, expected_sha256=None, synthetic=True)
    assert list(df["ur6_class"]) == [1, 6] and set(df["vintage"]) == {2011}


def _zone(code, ur6, price, drc_h, dw=100, vac=0.02):
    return {"code": code, "ur6_class": ur6, "dwellings": dw, "price_indexed": price, "vacant_share": vac, "second_home_share": 0.0,
            "drc": {"low": drc_h * 0.5, "central": drc_h * 0.75, "high": drc_h}, "rebuild_new": {"low": 1, "central": 1, "high": 1}}


def test_class_table_and_most_negative():
    zones = [_zone("A", 1, 200_000, 100_000), _zone("B", 1, 100_000, 150_000, dw=300), _zone("C", 6, 100_000, 50_000)]
    t = {r["ur6_class"]: r for r in si.class_table(zones, "high")}
    assert t[1]["zones"] == 2 and t[1]["pct_zones_negative"] == 50.0 and t[1]["dw_pct_negative"] == 75.0
    assert t[1]["land_share"] == pytest.approx((100_000 * 100 + 0) / (200_000 * 100 + 100_000 * 300))
    assert t["Scotland"]["zones"] == 3 and t["Scotland"]["dwellings"] == 500
    assert si.most_negative(zones, ur6=1, scenario="high", n=1)[0]["code"] == "B"
    assert "| Scotland |" in si.markdown_table(si.class_table(zones, "central"))


def test_build_zones_drops_unjoined_never_guesses():
    rb = {s: sr.RebuildResult(100.0, 50.0, 0.5) for s in sr.SCENARIOS}
    prices = [{"code": "S01013401", "price_indexed": 1000.0}, {"code": "S01013402", "price_indexed": 1000.0}]
    out = si.build_zones(prices=prices, dwellings={"S01013401": 10}, ur6={"S01013401": 2, "S01013402": 3},
                         rebuild_for=lambda c: (None, rb))
    assert [z["code"] for z in out] == ["S01013401"]


def test_internal_table_manifest(tmp_path):
    from georgist import surface_manifest as sm
    e = sm.write_internal_table([{"code": "S01013401", "vintage": 2011, "v": 1}], tmp_path,
                                name="diag_SYNTHETIC.csv", columns=["code", "vintage", "v"], source="SYNTHETIC", licence="synthetic")
    m = pd.read_csv(tmp_path / "manifest.csv")
    assert e["publish_level"] == "internal" and list(m["publish_level"]) == ["internal"]
    assert m.loc[0, "sha256"] == hashlib.sha256((tmp_path / "diag_SYNTHETIC.csv").read_bytes()).hexdigest()


def test_obsolescence_grid_moves_old_stock_with_rate(cfg, band):
    old = sr.ZoneRebuildInputs({**dict.fromkeys(sr.DWELLING_TYPES, 0.0), "terraced": 1.0}, {"before 1919": 1.0}, 120.0, "mean",
                               "all_stock", "epc_all_time", (), None)
    g = si.obsolescence_grid(old, 200_000, band=band, depreciation=cfg["depreciation"], valuation_year=2025, rebuild="high")
    new_cost = 120.0 * band["terraced"]["high"]
    r_c = 0.00137 / 0.497
    # Cap 68: unmaintained < central < maintained (remaining 1.0)
    assert g[("high", "high")]["residual"] == pytest.approx(200_000 - 1.0 * new_cost)
    assert g[("central", "central")]["residual"] == pytest.approx(200_000 - (1 - r_c) ** 68 * new_cost)
    assert g[("low", "low")]["residual"] > g[("central", "central")]["residual"]  # lower DRC → higher residual
