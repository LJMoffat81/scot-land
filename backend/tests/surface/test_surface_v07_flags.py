"""Rules v0.7: zero-dwelling zones, sample exclusion, per-resident suppression, EPC over-count proxy. SYNTHETIC data
except the three published zero-dwelling DZ2011 codes (Data Zones dwellings_by_year)."""

import pytest

from georgist import surface_holdout as ho
from georgist import surface_rent as sr

KW = dict(n_min=5, n_full=15, shrinkage_k=8)
S27 = "S01010227"  # Sighthill-03: zero dwellings 2018+, still has RoS price rows


def test_zero_dwellings_codes_spine_then_fallback():
    spine = [{"code": "S01013401", "vintage": 2011, "flags": "absent_from_ros_price_file;zero_dwellings"},
             {"code": "S01013402", "vintage": 2011, "flags": "population_zero"},
             {"code": "S01020801", "vintage": 2022, "flags": "zero_dwellings"}]
    codes, src = sr.zero_dwellings_codes(spine)
    assert codes == {"S01013401"} and src == "zone_spine"
    codes, src = sr.zero_dwellings_codes([{"code": "S01013402", "vintage": 2011, "flags": "population_zero"}])
    assert src == "fallback_codes" and codes == {"S01010206", "S01010226", S27}
    assert sr.zero_dwellings_codes(None)[0] == set(sr.ZERO_DWELLINGS_FALLBACK)
    cfg = sr.load_config()
    assert set(cfg["zero_dwellings"]["fallback_codes"]) == set(sr.ZERO_DWELLINGS_FALLBACK)


def test_zero_dwellings_overrides_price_null_never_zero():
    obs = sr.residual_land_value(150_000.0, 100_000.0)
    lv = sr.resolve_land_value(dwellings=0, observed=obs, sales_n=30, model_gbp=40_000, zero_dwellings=True, **KW)
    assert lv.land_value is None and lv.fill_method == "not_applicable" and "zero_dwellings" in lv.tags
    lv2 = sr.resolve_land_value(dwellings=0, observed=None, sales_n=0, model_gbp=None, absent_from_price_file=True,
                                zero_dwellings=True, **KW)
    assert lv2.fill_method == "not_applicable"   # flag beats absent-from-price-file model fill


def test_zero_dwellings_excluded_from_every_sample():
    rows = {S27: {"code": S27, "price_gbp": 90_000, "sales_n": 12, "dwellings": 0},
            "S01013401": {"code": "S01013401", "price_gbp": 150_000, "sales_n": 20, "dwellings": 400},
            "S01013402": {"code": "S01013402", "price_gbp": 160_000, "sales_n": 20, "dwellings": 300, "flags": "zero_dwellings"}}
    for purpose in sr.SAMPLE_PURPOSES:
        assert set(sr.sample_for(purpose, rows)) == {"S01013401"}
        assert [r["code"] for r in sr.sample_for(purpose, list(rows.values()))] == ["S01013401"]
    with pytest.raises(ValueError):
        sr.sample_for("anything", rows)
    ev = sr.cell_price_evidence(rows.values(), cell_of=lambda z: ("B", 1))
    assert ev[("B", 1)] == {"price_n": 20, "mean_price": 150_000}
    strata = {c: (1,) for c in rows}
    for split in (ho.stratified_zone_holdout(strata, frac=0.5, seed=1),
                  ho.suppression_mimic({c: 7 for c in rows}),
                  ho.block_holdout({c: "IZ1" for c in rows}, frac=1.0, seed=1)):
        assert S27 not in split.train + split.test
    seen = {}

    def fit_predict(train, test):
        seen["train"] = [r["code"] for r in train]
        seen["test"] = [r["code"] for r in test]
        return [(r["price_gbp"], r["price_gbp"], r["price_gbp"]) for r in test]

    ho.run_holdout(ho.Split("x", [S27, "S01013401"], [S27, "S01013401"], 0), rows, fit_predict)
    assert seen == {"train": ["S01013401"], "test": ["S01013401"]}
    g = ho.per_hectare_gradient_check(
        [{"code": S27, "vintage": 2011, "ur6_class": 1, "fill_method": "observed_pooled", "sales_n": 12,
          "observed_land_value": 1.0, "dwellings": 0}],
        residential_land_rows=None, access_rows=None, expected_order=[], min_zones_per_class=30, access_rho_max=-0.1)
    assert g["n_excluded_zero_dwellings"] == 1 and g["n_observed"] == 0


def test_per_resident_hidden_on_pop_dwellings_mismatch():
    assert sr.per_resident(1000.0, 8, "absent_from_ros_price_file;pop_dwellings_mismatch") is None
    assert sr.per_resident(1000.0, 8, ["pop_dwellings_mismatch"]) is None
    assert sr.per_resident(1000.0, 0, "") is None
    assert sr.per_resident(1000.0, 500, "") == pytest.approx(2.0)


def test_output_row_zero_dwellings_and_per_resident():
    from tests.surface.test_surface_output import _row  # reuse the synthetic row builder
    cfg = sr.load_config()
    band = sr.rebuild_band(cfg)
    ok = _row(cfg, band, population=1000)
    assert ok["measured_rent_per_resident"] == pytest.approx(ok["measured_rent"] / 1000)
    hidden = _row(cfg, band, population=1000, zone_flags="pop_dwellings_mismatch")
    assert hidden["measured_rent_per_resident"] is None and hidden["measured_rent"] is not None
    assert "per_resident_hidden_pop_dwellings_mismatch" in hidden["proxy_tags"]
    na = _row(cfg, band, land=sr.LandValue(None, "not_applicable", ("zero_dwellings", "not_applicable")))
    assert na["land_value"] is None and na["measured_rent"] is None and na["raw_residual"] is None
    assert na["quality"] == "placeholder" and "zero_dwellings" in na["proxy_tags"]


def _inp(source):
    return sr.ZoneRebuildInputs({**dict.fromkeys(sr.DWELLING_TYPES, 0.0), "terraced": 1.0}, {"before 1919": 1.0}, 90.0,
                                "mean", "all_stock", source, ())


def test_epc_overcount_uses_matching_ratio_and_threshold():
    cfg = sr.load_config()
    th = cfg["epc_overcount"]["threshold"]
    assert th == 1.25
    row = {"coverage_share": 1.30, "recent10_coverage_share": 0.9}
    a = sr.tag_epc_overcount(_inp("epc_all_time"), row, threshold=th)
    assert {"epc_overcount_proxy", "floor_area_proxy_epc_overcount", "age_proxy_epc_overcount",
            "epc_overcount_basis=coverage_share"} <= set(a.tags)
    assert "epc_overcount_proxy" not in sr.tag_epc_overcount(_inp("epc_recent10"), row, threshold=th).tags
    assert "epc_overcount_proxy" not in sr.tag_epc_overcount(_inp("epc_all_time"), {"coverage_share": 1.25}, threshold=th).tags
    n = sr.tag_epc_overcount(_inp("nrs2017"), row, threshold=th)
    assert "age_proxy_epc_overcount" in n.tags and "floor_area_proxy_epc_overcount" not in n.tags
    f = sr.tag_epc_overcount(_inp("epc_all_time"), {**row, "res_uprn_exceeds_dwellings": False}, threshold=th)
    assert "epc_overcount_proxy" not in f.tags   # GIS flag preferred over the ratio once present
    f = sr.tag_epc_overcount(_inp("epc_recent10"), {**row, "res_uprn_exceeds_dwellings": "True"}, threshold=th)
    assert "epc_overcount_basis=res_uprn_exceeds_dwellings" in f.tags


SPINE_ROWS = [
    {"code": "S01013401", "vintage": 2011, "flags": "absent_from_ros_price_file;population_zero;zero_dwellings"},
    {"code": "S01013402", "vintage": 2011, "flags": "pop_dwellings_mismatch;zero_dwellings"},   # both: zero wins
    {"code": "S01013403", "vintage": 2011, "flags": "absent_from_ros_price_file;pop_dwellings_mismatch"},
    {"code": "S01013404", "vintage": 2011, "flags": "not_zero_dwellings_note"},                   # membership, not substring
    {"code": "S01013405", "vintage": 2011, "flags": ""},
    {"code": "S01020801", "vintage": 2022, "flags": "zero_dwellings"},                           # other vintage ignored
]


def test_zone_flag_sets_split_membership_zero_wins():
    f = sr.zone_flag_sets(SPINE_ROWS)
    assert f["source"] == "zone_spine"
    assert f["zero_dwellings"] == {"S01013401", "S01013402"}
    assert f["pop_dwellings_mismatch"] == {"S01013403"}
    assert sr.per_resident(10.0, 5, "pop_dwellings_mismatch;zero_dwellings") is None
    missing = sr.zone_flag_sets(None)
    assert missing["source"] == "fallback_codes" and missing["zero_dwellings"] == set(sr.ZERO_DWELLINGS_FALLBACK)
    assert missing["pop_dwellings_mismatch"] == set()


def _spine_dir(tmp_path):
    import hashlib
    import pandas as pd
    p = tmp_path / "zone_spine.csv"
    pd.DataFrame([{"code": r["code"], "vintage": r["vintage"], "name": "SYNTHETIC", "flags": r["flags"]} for r in SPINE_ROWS]).to_csv(p, index=False)
    pd.DataFrame([{"file": "zone_spine.csv", "owner": "datazones", "source": "SYNTHETIC", "licence": "synthetic",
                   "publish_level": "public_zone", "zone_vintage": "DZ2011;DZ2022", "key": "(code, vintage)",
                   "rows": len(SPINE_ROWS), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}]).to_csv(tmp_path / "manifest.csv", index=False)
    return p


def test_load_zone_spine_converters_and_checks(tmp_path):
    from georgist import surface_harvester as hv
    p = _spine_dir(tmp_path)
    df = hv.load_zone_spine(p, expected_sha_prefix=None)
    assert df.loc[df["code"] == "S01013405", "flags"].iloc[0] == ""          # empty cell is '' not NaN
    row = df[(df["code"] == "S01013402") & (df["vintage"] == 2011)].iloc[0]  # join on (code, vintage)
    assert "zero_dwellings" in row["flags"].split(";") and "pop_dwellings_mismatch" in row["flags"].split(";")
    f = sr.zone_flag_sets(df.to_dict("records"))
    assert f["zero_dwellings"] == {"S01013401", "S01013402"} and f["pop_dwellings_mismatch"] == {"S01013403"}
    with pytest.raises(ValueError):
        hv.load_zone_spine(p, expected_sha_prefix="00000000")
    assert hv.load_zone_spine(tmp_path / "absent.csv") is None


def _real_spine():
    from georgist import surface_paths as sp
    return sp.data_dir("datazones") / "zone_spine.csv"


@pytest.mark.skipif(not _real_spine().exists(), reason="local Data Zones zone_spine not present (CI)")
def test_real_zone_spine_flags():
    from georgist import surface_harvester as hv
    df = hv.load_zone_spine(_real_spine())   # verifies the a11cf5b5 prefix and the Data Zones manifest
    f = sr.zone_flag_sets(df.to_dict("records"))
    assert f["zero_dwellings"] == {"S01010206", "S01010226", "S01010227"}
    assert f["pop_dwellings_mismatch"] == {"S01011598"}   # S01010227 carries both; zero_dwellings wins
    raw = {c for c, fl in zip(df["code"], df["flags"]) if "pop_dwellings_mismatch" in fl.split(";")}
    assert raw == {"S01011598", "S01010227"}


def test_load_gis_checked_sha_prefix_and_publish_level(tmp_path):
    from georgist import surface_harvester as hv
    p = _spine_dir(tmp_path)
    assert len(hv.load_gis_checked(p, sha_prefix=None, publish_level="public_zone")) == len(SPINE_ROWS)
    with pytest.raises(ValueError):          # plot bands must be declared INTERNAL in the manifest
        hv.load_gis_checked(p, sha_prefix=None, publish_level="internal")
    with pytest.raises(ValueError):
        hv.load_gis_checked(p, sha_prefix="ffffffff")
    assert len(hv.load_gis_checked(p, sha_prefix=None, publish_level=("internal", "public_zone"))) == len(SPINE_ROWS)
