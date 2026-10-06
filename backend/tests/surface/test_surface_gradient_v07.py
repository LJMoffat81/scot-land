"""Rules 12.2 v0.7 PRE-REGISTERED job-access gradient. SYNTHETIC fixtures only (dz_access.csv not used)."""

import random

import pytest

from georgist import surface_holdout as ho
from georgist import surface_rent as sr


@pytest.fixture(scope="module")
def cfg():
    return sr.load_config()


def test_pre_registration_fixed_in_config(cfg):
    g = cfg["gradient_v07"]
    assert g["status"] == "pre_registered" and g["rules_sha256_prefix"] == "23df6297"
    assert g["primary"] == {"driver": "job_access", "rho_min": 0.10}
    assert g["secondary"]["driver"] == "road_km_nearest_luc"
    assert g["input"]["columns"] == {"job_access": "job_access", "centre_km": "road_km_nearest_luc", "flags": "flags"}
    assert g["input"]["island_flag_token"] == "luc_distance_euclid_x1.3"
    assert g["input"]["flag_tokens"] == ["luc_distance_euclid_x1.3", "job_access_partly_euclid_x1.3",
                                         "off_mainland_network", "nearest_emp_point_gt_5km"]
    assert g["sample"]["exclude_on_access_flags"] is False
    assert g["secondary"]["rho_max"] == -0.10
    m = g["expected_metadata"]
    assert (m["employment_source"], m["employment_geography"], m["decay"], m["decay_scale_km"], m["cutoff_km"]) == \
        ("BRES", "DZ2011", "exponential", 10, 60)
    assert m["own_zone_jobs_included"] is True and m["network"] == "OS Open Roads"
    assert sorted(m["large_urban_centres"]) == ["Aberdeen", "Dundee", "Edinburgh", "Glasgow"]
    assert m["island_rule"] == "straight_line_x1.3" and m["island_flagged"] is True
    assert m["employment_year"] == 2023 and m["centre_point_basis"] == "documented_landmarks"
    assert m["centre_landmarks"]["Glasgow"] == "George Square" and m["centre_landmarks"]["Dundee"].startswith("City Square")
    assert {c["field"].split(" ")[0] for c in g["metadata_corrections"]} == {"employment_year", "centre_point_basis"}
    assert all(c["accepted_by"].startswith("Georgist") for c in g["metadata_corrections"])
    assert set(g["sample"]["exclude"]) == {"weak_match", "mask_too_big_parcel", "res_uprn_exceeds_dwellings", "zero_dwellings"}
    assert g["sample"]["min_sales"] == 5
    assert g["on_class_fail"]["multiplier_status"] == "PLACEHOLDER_GEORGIST_SIGNOFF"
    assert cfg["gradient"]["label"] == "superseded driver, reported"


def _meta(cfg, **over):
    return {**cfg["gradient_v07"]["expected_metadata"], **over}


def test_metadata_assertion(cfg):
    exp = cfg["gradient_v07"]["expected_metadata"]
    assert ho.check_access_metadata(_meta(cfg), exp)["status"] == "verified"
    as_text = {**_meta(cfg), "decay_scale_km": "10", "own_zone_jobs_included": "True",
               "large_urban_centres": "Glasgow;Edinburgh;Dundee;Aberdeen"}
    assert ho.check_access_metadata(as_text, exp)["status"] == "verified"
    with pytest.raises(ho.AccessMetadataMismatch):
        ho.check_access_metadata(_meta(cfg, decay_scale_km=12), exp)
    with pytest.raises(ho.AccessMetadataMismatch):
        ho.check_access_metadata(_meta(cfg, cutoff_km=45), exp)
    partial = {k: v for k, v in _meta(cfg).items() if k != "island_rule"}
    r = ho.check_access_metadata(partial, exp)
    assert r["status"] == "incomplete" and r["missing"] == ["island_rule"]


def _data(cfg, n=60, flip_class=2):
    rnd = random.Random(7)
    cols = cfg["gradient_v07"]["input"]["columns"]
    zones, land, acc = [], [], []
    for c in (1, 2, 3):
        for i in range(n):
            code = f"S0101{3000 + 100 * c + i}"
            job = rnd.uniform(1_000, 100_000)
            km = rnd.uniform(1, 60)
            sign = -1 if c == flip_class else 1
            lv = 50_000 + sign * job * 0.5 + rnd.gauss(0, 5_000)
            zones.append({"code": code, "vintage": 2011, "ur6_class": c, "fill_method": "observed_pooled", "sales_n": 12,
                          "observed_land_value": lv, "dwellings": 300})
            land.append({"code": code, "vintage": 2011, "residential_land_ha": 10.0, "method": "parcel_based",
                         "gradient_exclude": (), "low_confidence": ()})
            fl = "luc_distance_euclid_x1.3;off_mainland_network" if i % 10 == 0 else ("nearest_emp_point_gt_5km" if i % 7 == 0 else "")
            acc.append({"code": code, "vintage": 2011, cols["job_access"]: job, cols["centre_km"]: km, cols["flags"]: fl})
    return zones, land, acc


def _run(cfg, zones, land, acc, meta="ok"):
    return ho.job_access_gradient_check(zones, residential_land_rows=land, access_rows=acc, gcfg=cfg["gradient_v07"],
                                        expected_order=[], access_metadata=_meta(cfg) if meta == "ok" else meta)


def test_primary_decides_secondary_reported_failed_not_inconclusive(cfg):
    zones, land, acc = _data(cfg)
    r = _run(cfg, zones, land, acc)
    assert r["classes"][1]["status"] == "pass" and r["classes"][3]["status"] == "pass"
    assert r["classes"][2]["status"] == "failed" and r["failed_classes"] == [2] and r["status"] == "fail"
    # km is random noise: the secondary does not pass, but class 1 still passes (secondary never decides)
    assert r["classes"][1]["secondary_pass_reported"] in (True, False) and r["classes"][1]["primary_pass"] is True
    ok = _run(cfg, *_data(cfg, flip_class=None))
    assert ok["status"] == "pass" and ok["failed_classes"] == []


def test_sample_rules_and_pending(cfg):
    zones, land, acc = _data(cfg, flip_class=None)
    zones[0] = {**zones[0], "sales_n": 4}
    zones[1] = {**zones[1], "fill_method": "model_filled"}
    land[2] = {**land[2], "gradient_exclude": ("weak_match",)}
    land[3] = {**land[3], "gradient_exclude": ("mask_too_big_parcel",)}
    land[4] = {**land[4], "gradient_exclude": ("res_uprn_exceeds_dwellings", "zero_dwellings")}
    zones.append({**zones[5], "code": "S01010227"})           # zero-dwelling zone with a price: never sampled
    r = _run(cfg, zones, land, acc)
    assert r["n_excluded_not_observed"] == 2 and r["n_excluded_zero_dwellings"] == 1
    assert r["excluded_res_land_by_reason"] == {"weak_match": 1, "mask_too_big_parcel": 1, "res_uprn_exceeds_dwellings": 1, "zero_dwellings": 1}
    assert r["n_used"] == 180 - 5
    small = _run(cfg, zones[:20], land, acc)
    assert small["classes"][1]["status"] == "insufficient_n" and small["status"] == "pending"
    assert _run(cfg, zones, land, None)["reason"].startswith("dz_access_missing")
    assert _run(cfg, zones, None, acc)["status"] == "pending"
    assert "unverified" in _run(cfg, zones, land, acc, meta={})["reason"]
    with pytest.raises(ho.AccessMetadataMismatch):
        _run(cfg, zones, land, acc, meta=_meta(cfg, decay="power"))


def test_job_access_rows_refuse_ranks(cfg):
    with pytest.raises(ValueError):
        ho.job_access_rows([], {"job_access": "job_access_rank", "centre_km": "km"})


def test_failed_class_widens_model_filled_bands_only(cfg):
    oc = cfg["gradient_v07"]["on_class_fail"]
    kw = dict(failed_classes=[2], multiplier=oc["model_filled_band_multiplier"], multiplier_status=oc["multiplier_status"])
    lo, hi, tags = ho.widen_failed_class_band(100.0, 80.0, 130.0, fill_method="model_filled", ur6_class=2, **kw)
    m = oc["model_filled_band_multiplier"]
    assert (lo, hi) == (pytest.approx(100 - 20 * m), pytest.approx(100 + 30 * m)) and "band_multiplier_placeholder" in tags
    assert ho.widen_failed_class_band(100.0, 80.0, 130.0, fill_method="observed_pooled", ur6_class=2, **kw) == (80.0, 130.0, ())
    assert ho.widen_failed_class_band(100.0, 80.0, 130.0, fill_method="model_filled", ur6_class=1, **kw) == (80.0, 130.0, ())
    lo, _, _ = ho.widen_failed_class_band(10.0, 0.0, 30.0, fill_method="model_filled", ur6_class=2, **kw)
    assert lo == 0.0


def test_run_guard_once_per_input(tmp_path, cfg):
    g = ho.RunGuard(tmp_path / "run_log" / "gradient_v07_runs.jsonl")
    h = ho.config_hash(cfg["gradient_v07"])
    e = g.register(access_sha256="a" * 64, cfg_hash=h)
    assert e["config_hash"] == h and not e["override"]
    with pytest.raises(ho.RepeatScoredRunError):
        g.register(access_sha256="a" * 64, cfg_hash=h)
    with pytest.raises(ValueError):
        g.register(access_sha256="a" * 64, cfg_hash=h, override=True)
    e2 = g.register(access_sha256="a" * 64, cfg_hash=h, override=True, reason="SYNTHETIC test of override")
    assert e2["n_prior"] == 1 and len(g.entries()) == 2
    assert g.register(access_sha256="b" * 64, cfg_hash=h)["n_prior"] == 0
    assert ho.config_hash(cfg["gradient_v07"]) == h    # stable hash of the pre-registered section


def test_flags_reported_never_excluded(cfg):
    zones, land, acc = _data(cfg, flip_class=None)
    r = _run(cfg, zones, land, acc)
    assert r["n_used"] == 180                                   # flagged zones stay in the sample
    assert r["n_islands_used"] == 18 and r["access_flag_counts_used_reported_only"]["off_mainland_network"] == 18
    assert r["access_flag_counts_used_reported_only"]["luc_distance_euclid_x1.3"] == 18
    rows = ho.job_access_rows(acc, cfg["gradient_v07"]["input"]["columns"], island_flag_token="luc_distance_euclid_x1.3")
    assert rows[acc[0]["code"]]["island"] is True and rows[acc[1]["code"]]["island"] is False
    assert ho.access_flags(float("nan")) == () and ho.access_flags("a; b") == ("a", "b")


SYNTH_ACCESS_CONFIG = {   # SYNTHETIC mirror of the structure of GIS scripts/access_config.json
    "origins": {"origin_method": "sg_popweighted_centroid"},
    "employment": {"source": "ONS Business Register and Employment Survey (BRES) open access", "bres_year": 2023,
                   "geography": "2011 scottish datazones within Scotland"},
    "network": {"source": "OS Open Roads, GeoPackage, version X", "euclid_factor": 1.3,
                "pair_distance": "network km ...; otherwise Euclidean km between the original points x 1.3"},
    "job_access": {"falloff": "negative_exponential", "scale_km": 10, "cutoff_km": 60, "own_zone": "included (d_ii = 0)"},
    "large_urban_centres": {"point_source": "documented landmark grid references", "centres": {
        "Glasgow": {"landmark": "George Square"}, "Edinburgh": {"landmark": "Waverley Bridge / Princes St"},
        "Aberdeen": {"landmark": "Castlegate (Mercat Cross), Union St east end"}, "Dundee": {"landmark": "City Square (Caird Hall)"}}},
}
SYNTH_MANIFEST = {"file": "dz_access.csv", "source": "... ONS BRES open access 2023 ...", "source_year": "2023"}
SYNTH_HEADER = ["code", "vintage", "job_access", "road_km_nearest_luc", "distance_method", "flags"]


def test_metadata_from_gis_manifest_and_config(cfg):
    import copy
    exp = cfg["gradient_v07"]["expected_metadata"]
    meta = ho.access_metadata_from_gis(SYNTH_MANIFEST, SYNTH_ACCESS_CONFIG, SYNTH_HEADER)
    assert ho.check_access_metadata(meta, exp)["status"] == "verified"
    bad = copy.deepcopy(SYNTH_ACCESS_CONFIG)
    bad["job_access"]["scale_km"] = 8
    with pytest.raises(ho.AccessMetadataMismatch):
        ho.check_access_metadata(ho.access_metadata_from_gis(SYNTH_MANIFEST, bad, SYNTH_HEADER), exp)
    with pytest.raises(ho.AccessMetadataMismatch):        # employment year disagreement between config and manifest
        ho.check_access_metadata(ho.access_metadata_from_gis({**SYNTH_MANIFEST, "source_year": "2024"}, SYNTH_ACCESS_CONFIG, SYNTH_HEADER), exp)
    bad = copy.deepcopy(SYNTH_ACCESS_CONFIG)
    bad["large_urban_centres"]["centres"]["Glasgow"]["landmark"] = "Glasgow Central"
    with pytest.raises(ho.AccessMetadataMismatch):
        ho.check_access_metadata(ho.access_metadata_from_gis(SYNTH_MANIFEST, bad, SYNTH_HEADER), exp)
