"""ILLUSTRATIVE national run: residual land share by urban-rural class.

Not a result. Rows are INTERNAL (diagnostic) and never served. Inputs:
RoS 2023 DZ2011 mean prices -> council UK HPI to Apr-2025; Data Zones
dwellings_by_year 2025 (council tax, Sept); GIS EPC rollup (DZ2011 rows only) for mix, age and floor area;
SGUR 2020 6-fold on DZ2011; OPEN_ESTIMATE rebuild band at the 2025 price base.
"""

from __future__ import annotations

import dataclasses

from typing import Callable, Iterable, Mapping, Sequence

from georgist import surface_holdout as sh
from georgist import surface_rent as sr
from georgist.surface_zones import vintage_int

UR6_NAMES = {1: "Large Urban Areas", 2: "Other Urban Areas", 3: "Accessible Small Towns",
             4: "Remote Small Towns", 5: "Accessible Rural", 6: "Remote Rural"}
LABEL = "ILLUSTRATIVE - not a result; internal diagnostic rows, never served"


def class_table(zones: Sequence[Mapping], scenario: str) -> list[dict]:
    """Per UR6 class plus a national row.

    pct_zones_negative: share of zones with raw_residual < 0 (mean P - mean DRC).
    dw_pct_negative: the same weighted by dwellings.
    land_share: Σ max(0, P - DRC)·dw / Σ P·dw (indexed means; land floored at 0 as published).
    """
    groups: dict[object, list[Mapping]] = {}
    for z in zones:
        groups.setdefault(int(z["ur6_class"]), []).append(z)
    out = []
    for key, rows in sorted(groups.items()) + [("Scotland", list(zones))]:
        dw = sum(int(z["dwellings"]) for z in rows)
        neg = [z for z in rows if z["price_indexed"] - z["drc"][scenario] < 0]
        land = sum(max(0.0, z["price_indexed"] - z["drc"][scenario]) * int(z["dwellings"]) for z in rows)
        value = sum(z["price_indexed"] * int(z["dwellings"]) for z in rows)
        vs = [(z.get("vacant_share"), int(z["dwellings"])) for z in rows if z.get("vacant_share") is not None]
        ss = [(z.get("second_home_share"), int(z["dwellings"])) for z in rows if z.get("second_home_share") is not None]
        out.append({
            "ur6_class": key, "name": UR6_NAMES.get(key, "National"), "zones": len(rows), "dwellings": dw,
            "vacant_share": sum(v * w for v, w in vs) / sum(w for _, w in vs) if vs else None,
            "second_home_share": sum(v * w for v, w in ss) / sum(w for _, w in ss) if ss else None,
            "pct_zones_negative": 100.0 * len(neg) / len(rows) if rows else None,
            "dw_pct_negative": 100.0 * sum(int(z["dwellings"]) for z in neg) / dw if dw else None,
            "land_share": land / value if value else None,
        })
    return out


def zone_land_shares(zones: Iterable[Mapping], scenario: str) -> dict[int, list[float]]:
    out: dict[int, list[float]] = {}
    for z in zones:
        out.setdefault(int(z["ur6_class"]), []).append(max(0.0, z["price_indexed"] - z["drc"][scenario]) / z["price_indexed"])
    return out


def obsolescence_grid(
    inp: "sr.ZoneRebuildInputs", price: float, *, band, depreciation, valuation_year: int, rebuild: str = "high",
    floors=("low", "central", "high"), lives=("low", "central", "high"),
) -> dict:
    """Rules 6.2 (v0.6) review for large old homes: residual per dwelling at one rebuild level across
    remaining-value floor x building life. Returns {(life, floor): {floor, life, drc, residual}}."""
    out = {}
    for lv in lives:
        for fl in floors:
            dep = sr.depreciation_at(depreciation, life=lv, floor=fl)
            scalar = {**dep, "band_combination": {"rule": "corner"}}
            r = sr.zone_rebuild_band(inp, band={t: {s: b[rebuild] for s in sr.SCENARIOS} for t, b in band.items()},
                                     depreciation=scalar, valuation_year=valuation_year, default_remaining_factor=None)
            out[(lv, fl)] = {"life_years": dep["life_years"], "floor": dep["remaining_min"], "drc": r["central"].drc_gbp,
                             "residual": price - r["central"].drc_gbp}
    return out


def gradient_by_scenario(zones: Sequence[Mapping], cfg: Mapping) -> dict[str, dict]:
    """LEGACY land-share ordering + negatives + national share. Rules v0.6 12.2: the
    location gradient is per residential hectare (surface_holdout.per_hectare_gradient_check);
    the land-share ordering here is a diagnostic only, not a v0.6 check."""
    c = cfg["land_share_checks"]
    res = {}
    for s in sr.SCENARIOS:
        g = sh.gradient_check(zone_land_shares(zones, s), expected_order=c["ur6_expected_order"],
                              tolerance=c.get("gradient_tolerance", 0.0))
        agg = {r["ur6_class"]: [r["land_share"]] for r in class_table(zones, s) if r["ur6_class"] != "Scotland"}
        ga = sh.gradient_check(agg, expected_order=c["ur6_expected_order"])
        neg = sh.negative_by_class_check(
            [{"ur6_class": z["ur6_class"], "negative_residual": z["price_indexed"] - z["drc"][s] < 0} for z in zones],
            high_demand_ur6=c["negative_high_demand_ur6"], max_share_high_demand=c["negative_max_share_high_demand"])
        nat = class_table(zones, s)[-1]["land_share"]
        lo, hi = c["national_range"]
        res[s] = {"gradient_zone_median_pass": g["pass"], "gradient_zone_median_violations": g["violations"],
                  "gradient_aggregate_pass": ga["pass"], "gradient_aggregate_violations": ga["violations"],
                  "negatives_high_demand_pass": neg["pass"], "negatives_high_demand": neg["breaches"],
                  "national_share": nat,
                  "national_share_in_range": (lo - c["national_tolerance"]) <= nat <= (hi + c["national_tolerance"])}
    return res


def most_negative(zones: Sequence[Mapping], *, ur6: int = 1, scenario: str = "high", n: int = 10) -> list[dict]:
    rows = [z for z in zones if int(z["ur6_class"]) == ur6]
    rows.sort(key=lambda z: z["price_indexed"] - z["drc"][scenario])
    return [{"code": z["code"], "council": z.get("council_name"), "price_raw_2023": z.get("price_raw"),
             "price_indexed_2025": z["price_indexed"], "rebuild_new": z["rebuild_new"][scenario], "drc": z["drc"][scenario],
             "raw_residual": z["price_indexed"] - z["drc"][scenario], "floor_area_m2": z.get("floor_area_m2"),
             "sales_n": z.get("sales_n")} for z in rows[:n]]


def markdown_table(rows: Sequence[Mapping]) -> str:
    head = "| UR6 | Class | Zones | Dwellings | % zones negative | % dwellings negative | Land share |\n|---|---|---:|---:|---:|---:|---:|"
    body = [f"| {r['ur6_class']} | {r['name']} | {r['zones']:,} | {r['dwellings']:,} | {r['pct_zones_negative']:.1f} | "
            f"{r['dw_pct_negative']:.1f} | {r['land_share']:.3f} |" for r in rows]
    return "\n".join([head] + body)


def build_zones(
    *, prices: Iterable[Mapping], dwellings: Mapping[str, int], ur6: Mapping[str, int], rebuild_for: Callable[[str], tuple],
    occupancy: Mapping[str, tuple] | None = None,
) -> list[dict]:
    """Join on exact DZ2011 codes only. `rebuild_for(code) -> (inputs | None, {scenario: RebuildResult})`.

    A zone missing a dwelling count or a UR6 class is dropped and counted, never guessed.
    """
    out = []
    for p in prices:
        code = p["code"]
        if code not in dwellings or code not in ur6 or dwellings[code] is None:
            continue
        inp, rbs = rebuild_for(code)
        vac, sec = (occupancy or {}).get(code, (None, None))
        out.append({**p, "dwellings": int(dwellings[code]), "ur6_class": int(ur6[code]),
                    "vacant_share": vac, "second_home_share": sec,
                    "drc": {s: rbs[s].drc_gbp for s in sr.SCENARIOS},
                    "rebuild_new": {s: rbs[s].rebuild_new_gbp for s in sr.SCENARIOS},
                    "floor_area_m2": inp.floor_area_m2 if inp else None,
                    "rebuild_source": inp.source if inp else "archetype",
                    "floor_area_basis": inp.floor_area_basis if inp else "archetype"})
    return out


def verify_gis_manifest(gis_dir: str) -> list[dict]:
    """Re-verify every file listed in the GIS manifest (sha256 and row count)."""
    import csv
    import hashlib
    from pathlib import Path

    g = Path(gis_dir)
    out = []
    with (g / "manifest.csv").open(encoding="utf-8") as f:
        for e in csv.DictReader(f):
            fp = g / e["file"]
            sha = hashlib.sha256(fp.read_bytes()).hexdigest() if fp.exists() else None
            rows = sum(1 for _ in fp.open(encoding="utf-8")) - 1 if fp.exists() else None
            out.append({"file": e["file"], "sha_ok": sha == e["sha256"], "rows_ok": rows == int(e["rows"]),
                        "rows": rows, "sha256": sha, "licence": e["licence"], "vintage": e["zone_vintage"], "key": e["key"]})
    return out


def swing_table(zones: Sequence[Mapping]) -> dict:
    """Rules 6.2 v0.7: one-at-a-time swings (each of rebuild, life, floor at low/high, others central).
    National and UR6-class land share and % zones negative per swing. Internal."""
    keys = list(zones[0]["drc_swing"]) if zones else []
    out = {}
    for k in keys:
        rows = {}
        for scope in ["Scotland"] + sorted({int(z["ur6_class"]) for z in zones}):
            zs = zones if scope == "Scotland" else [z for z in zones if int(z["ur6_class"]) == scope]
            val = sum(z["price_indexed"] * z["dwellings"] for z in zs)
            land = sum(max(0.0, z["price_indexed"] - z["drc_swing"][k]) * z["dwellings"] for z in zs)
            neg = sum(z["price_indexed"] - z["drc_swing"][k] < 0 for z in zs)
            rows[scope] = {"land_share": land / val if val else None, "pct_zones_negative": 100.0 * neg / len(zs) if zs else None}
        out[k] = rows
    return out


def plausibility_v07(zones: Sequence[Mapping], cfg: Mapping, swings: Mapping | None = None) -> dict:
    """Rules 12 v0.7: pass/fail on CENTRAL only; corners reported as stress."""
    c = cfg["land_share_checks"]
    cases = {s: [{"code": z["code"], "land_value": max(0.0, z["price_indexed"] - z["drc"][s]), "mean_price": z["price_indexed"],
                  "dwellings": z["dwellings"], "ur6_class": z["ur6_class"],
                  "negative_residual": z["price_indexed"] - z["drc"][s] < 0} for z in zones]
             for s in sr.SCENARIOS}
    return sh.plausibility_checks(cases, plausible_range=c["national_range"], tolerance=c["national_tolerance"],
                                  high_demand_ur6=c["negative_high_demand_ur6"],
                                  max_share_high_demand=c["negative_max_share_high_demand"],
                                  sources=c.get("national_range_sources", ()), swings=swings)


def plot_size_diag_v07(zones: Sequence[Mapping], inputs: Mapping[str, "sr.ZoneRebuildInputs"], cfg: Mapping, *,
                       dep_kw: Mapping, land_rows: list | None, estate_rows: Mapping[str, Mapping] | None) -> dict:
    """Georgist guard diagnostic: actual (blended estate/one-off) vs UNIFORM-RATE counterfactual, where every
    post-1980 detached home takes the national dwelling-weighted mean estate fraction. Internal."""
    from georgist import surface_harvester as hv

    ecfg = cfg["estate"]
    land = land_rows
    # own plot evidence only: borrowed zones carry no median parcel size and are excluded
    with_e = [z for z in zones if z.get("estate_fraction") is not None and "plot_bands_filled" in inputs[z["code"]].tags]
    if not estate_rows or not with_e:
        return sh.plot_size_rate_diagnostic([], residential_land_rows=land, estate_rows=None, estate_columns=ecfg["columns"])
    ebar = sum(z["estate_fraction"] * z["dwellings"] for z in with_e) / sum(z["dwellings"] for z in with_e)
    obs = []
    for z in with_e:
        uni = dataclasses.replace(inputs[z["code"]], estate_fraction=ebar, estate_bands=tuple(ecfg["post_1980_bands"]))
        drc_u = sr.zone_rebuild_band(uni, **dep_kw)["central"].drc_gbp
        obs.append({"code": z["code"], "vintage": 2011, "ur6_class": z["ur6_class"], "fill_method": "observed_pooled",
                    "sales_n": z["sales_n"], "dwellings": z["dwellings"], "oneoff_share": z.get("oneoff_share"),
                    "observed_land_value": z["price_indexed"] - z["drc"]["central"],
                    "observed_land_value_uniform_rate": z["price_indexed"] - drc_u})
    rows = [{**r, "code": c, "vintage": 2011} for c, r in estate_rows.items() if r.get("_plot_bands_source") == "filled"]
    res = sh.plot_size_rate_diagnostic(obs, residential_land_rows=land, estate_rows=rows, estate_columns=ecfg["columns"],
                                       min_zones_per_class=cfg["gradient"]["min_zones_per_class"],
                                       rho_flag=cfg["gradient"]["access_rho_max"], min_sales=cfg["gradient"]["min_sales"])
    return {**res, "uniform_estate_fraction": ebar, "n_zones_own_plot_evidence": len(with_e)}


def gradient_v06(zones: Sequence[Mapping], cfg: Mapping, *, access_path: str, land_rows: list | None) -> dict:
    """Rules 12.2 (v0.6) per-residential-hectare gradient on OBSERVED zones (central DRC).
    Access minutes from Data Zones (verified vs its manifest); residential land from GIS when posted."""
    from georgist import surface_harvester as hv

    g = cfg["gradient"]
    obs = [{"code": z["code"], "vintage": 2011, "ur6_class": z["ur6_class"], "fill_method": "observed_pooled",
            "sales_n": z["sales_n"], "observed_land_value": z["price_indexed"] - z["drc"]["central"], "dwellings": z["dwellings"]}
           for z in zones]
    acc = hv.load_gis_output(access_path).to_dict("records")
    land = land_rows
    return sh.per_hectare_gradient_check(obs, residential_land_rows=land, access_rows=acc,
                                         expected_order=cfg["land_share_checks"]["ur6_expected_order"],
                                         min_zones_per_class=g["min_zones_per_class"], access_rho_max=g["access_rho_max"],
                                         min_sales=g["min_sales"], max_missing_share=g["max_missing_share"],
                                         methods_ok=tuple(g["residential_land"]["methods_ok"]))


def run(*, raw_dir: str, gis_dir: str, dz_dir: str | None = None, residential_land_path: str | None = None, cfg: Mapping | None = None, area_fn: Callable[[Mapping, "sr.ZoneRebuildInputs"], float] | None = None,
        epc_primary: str = "all_time", estate_mode: str | None = None, estate_rows: Mapping[str, Mapping] | None = None,
        estate_mid_weight: float | None = None, swings: bool = True, plot_bands_path: str | None = None,
        res_land_low_coverage: str = "exclude") -> dict:
    """Run the illustrative tables on the real inputs (local files only)."""
    import pandas as pd

    from georgist import surface_harvester as hv

    cfg = cfg or sr.load_config()
    ecfg = cfg["estate"]
    estate_mode = estate_mode or ecfg["mode"]
    R, G = raw_dir.rstrip("/") + "/", gis_dir.rstrip("/") + "/"
    ri = cfg["rebuild_inputs"]
    ros = hv.load_ros_sales(R + "ros.csv")
    n25 = hv.load_nrs_dwellings(R + "dw11.xlsx", year=2025, vintage="DZ2011")  # names / council codes
    D = (dz_dir or hv.DATAZONES_DIR).rstrip("/") + "/"
    base_year = sr.rebuild_price_base_year(cfg)
    # rules 6.4: Data Zones canonical dwellings_by_year (council tax, Sept), count_year == price_year; verified vs manifest
    dw_tot = hv.load_dwelling_counts("datazones_ct_table", D + "dwellings_by_year.csv", price_year=base_year, vintage=2011)
    dw_occ = dw_tot
    spine = hv.load_zone_spine(D + "zone_spine.csv")  # verified (manifest + sha prefix); flags via converters=str
    spine11 = spine[spine["vintage"] == 2011] if spine is not None else None
    absent = (sorted(c for c, f in zip(spine11["code"], spine11["flags"]) if "absent_from_ros_price_file" in f.split(";"))
              if spine11 is not None else [])
    n17 = hv.load_nrs_dwellings(R + "dw11.xlsx", year=2017, vintage="DZ2011")
    urc = hv.load_urban_rural_2020_dz2011(R + "ur2020_dz2011.csv")
    epc_all = hv.load_gis_output(G + "epc_dz_rollup.csv")
    epc = epc_all[epc_all["vintage"] == vintage_int(ri["vintage_used"])].set_index("code")
    # GIS rebuild 06-Oct-2026: dwellings_nrs_2025 renamed dwellings_total_2025 (+ dwellings_flag)
    dw_col = "dwellings_total_2025" if "dwellings_total_2025" in epc.columns else "dwellings_nrs_2025"
    zcfg = cfg.get("zero_dwellings") or {}
    fsets = sr.zone_flag_sets(spine11.to_dict("records") if spine11 is not None else None,
                              fallback_zero=zcfg.get("fallback_codes", sr.ZERO_DWELLINGS_FALLBACK))
    zero_codes, zero_src = fsets["zero_dwellings"], fsets["source"]
    oc = cfg["epc_overcount"]
    rl_cfg = cfg["residential_land"]
    land_rows = None
    if residential_land_path:
        rl = hv.load_gis_checked(residential_land_path, sha_prefix=rl_cfg["source_sha256_prefix"], publish_level="public_zone")
        land_rows = sh.residential_land_rows_from_gis(rl[rl["vintage"] == 2011].to_dict("records"),
                                                      low_coverage=res_land_low_coverage, zero_codes=zero_codes,
                                                      min_share=rl_cfg["gradient_exclude"]["min_share_res_uprn_in_parcels"])
    pts = hv.council_hpi_points(hv.load_uk_hpi(R + "hpi-2026-07.csv"), base_year=2023, target_month="2025-04")
    band = sr.rebuild_band(cfg, base_year)
    n17i = n17.set_index("code")
    n25i = n25.set_index("code")
    urc_codes = set(urc["code"])
    joins = {"epc_dz2011_rows": len(epc), "epc_dz2022_rows_not_used": int((epc_all["vintage"] == 2022).sum()),
             "nrs_zones": len(n25), "urc_zones": len(urc),
             "nrs_codes_equal_urc": set(n25["code"]) == urc_codes, "nrs_codes_equal_epc": set(n25["code"]) == set(epc.index)}
    d = ros[(ros.vintage == 2011) & (ros.year == 2023) & (~ros.suppressed)]
    ros_codes = set(ros.loc[ros.vintage == 2011, "code"])
    no_price = {"absent_from_ros_price_file": [c for c in absent if c not in ros_codes],
                "absent_flag_but_in_ros": [c for c in absent if c in ros_codes],
                "suppressed_2023_lt5_sales": int(((ros.vintage == 2011) & (ros.year == 2023) & ros.suppressed).sum())}
    prices, fallback = [], {}
    for r in d.itertuples():
        mixrow = n17i.loc[r.code] if r.code in n17i.index else None
        m = sr.nrs2017_type_shares(mixrow) if mixrow is not None else None
        hm = {"detached": m["detached"], "semi_detached": m["semi_detached"], "terraced": m["terraced"], "flat": m["flat_purpose_built"]} if m else None
        council = n25i.loc[r.code, "council_code"]
        f, series, tags = sr.hpi_factor(pts[council], hm)
        pooled = sr.PooledPrice(float(r.price_mean_gbp), int(r.sales_n), "2023-2023", "mean", (), 2023)
        ip = sr.index_price(pooled, price_year=base_year, factor=f, series=series, tags=tags)
        prices.append({"code": r.code, "council_code": council, "council_name": n25i.loc[r.code, "council_name"],
                       "price_raw": pooled.price_gbp, "price_indexed": ip.price_indexed_gbp, "sales_n": int(r.sales_n)})
    zero_dropped = sorted(p["code"] for p in prices if p["code"] in zero_codes)  # rules v0.7: not applicable, overrides price
    prices = [p for p in prices if p["code"] not in zero_codes]
    dwell = {c: (int(v) if v == v else None) for c, v in zip(dw_tot["code"], dw_tot["dwellings_total"])}
    occupancy = {r.code: (None if r.vacant_share != r.vacant_share else float(r.vacant_share),
                               None if r.second_home_share != r.second_home_share else float(r.second_home_share))
                 for r in dw_occ.itertuples()}
    ur6 = dict(zip(urc["code"], urc["ur6_class"]))
    plot_raw = None
    if estate_mode in ("plot_bands", "gis_bands") and estate_rows is None:
        if not plot_bands_path:
            raise ValueError("estate mode plot_bands needs plot_bands_path (GIS dz_detached_plot_bands, internal)")
        pb = hv.load_gis_checked(plot_bands_path, sha_prefix=ecfg["source_sha256_prefix"], publish_level="internal")
        plot_raw = {r["code"]: r for r in pb[pb["vintage"] == 2011].to_dict("records")}
        meta = {c: (n25i.loc[c, "council_code"], int(ur6[c])) for c in ur6 if c in n25i.index}
        estate_rows = sr.borrow_plot_bands(plot_raw, meta, ecfg)

    inputs_cache: dict[str, sr.ZoneRebuildInputs] = {}

    def epc_rebuild(code):
        erow = epc.loc[code].to_dict() if code in epc.index else None
        inp = sr.zone_rebuild_inputs(erow, n17i.loc[code].to_dict() if code in n17i.index else None,
                                     default_area_m2=ri["default_floor_area_m2"], min_tfa_n=ri["min_tfa_n"], primary=epc_primary)
        if area_fn is not None:
            inp = dataclasses.replace(inp, floor_area_m2=area_fn(erow, inp), tags=inp.tags + ("floor_area_sensitivity",))
        inp = sr.tag_epc_overcount(inp, erow, threshold=float(oc["threshold"]), flag_column=oc["prefer_flag_column"])
        inp = sr.with_estate(inp, ecfg, mode=estate_mode, estate_row=(estate_rows or {}).get(code), mid_weight=estate_mid_weight)
        inputs_cache[code] = inp
        return inp, sr.zone_rebuild_band(inp, band=band, depreciation=cfg["depreciation"], valuation_year=base_year,
                                         default_remaining_factor=ri["default_remaining_factor"])

    def archetype(code):
        return None, {s: sr.RebuildResult(97 * band["other"][s], 97 * band["other"][s] * 0.55, 0.55) for s in sr.SCENARIOS}

    zones_epc = build_zones(prices=prices, dwellings=dwell, ur6=ur6, rebuild_for=epc_rebuild, occupancy=occupancy)
    dep_kw = dict(band=band, depreciation=cfg["depreciation"], valuation_year=base_year,
                  default_remaining_factor=ri["default_remaining_factor"])
    for z in zones_epc:
        inp = inputs_cache[z["code"]]
        z["oneoff_share"] = sr.oneoff_detached_share(inp)
        z["estate_fraction"] = inp.estate_fraction
        if swings:
            z["drc_swing"] = sr.one_at_a_time_drc(inp, **dep_kw)
    swing = swing_table(zones_epc) if swings else None
    zones_old = build_zones(prices=prices, dwellings=dwell, ur6=ur6, rebuild_for=archetype, occupancy=occupancy)
    src = pd.Series([i.source for i in inputs_cache.values()]).value_counts().to_dict()
    fab = pd.Series([i.floor_area_basis for i in inputs_cache.values()]).value_counts().to_dict()
    grp = sum(1 for i in inputs_cache.values() if i.area_by_group)
    cov = sum(1 for i in inputs_cache.values() if "epc_coverage_over_100_recent_only" in i.tags)
    return {
        "label": LABEL, "joins": joins, "epc_primary": epc_primary, "no_price_zones": no_price,
        "dwellings_source": dict(dw_tot.attrs.get("provenance", {})),
        "dwellings_total_scotland": int(dw_tot["dwellings_total"].sum()),

        "dw_pw_mean_floor_area": sum(z["floor_area_m2"] * z["dwellings"] for z in zones_epc) / sum(z["dwellings"] for z in zones_epc), "priced_zones": len(prices), "zones_used": len(zones_epc),
        "rebuild_source_counts": src, "floor_area_basis_counts": fab, "zones_house_flat_areas": grp,
        "epc_provenance": dict(epc_all.attrs.get("provenance", {})), "coverage_over_100_zones": cov,
        "epc_national_coverage": float(epc["cert_count"].sum() / epc[dw_col].sum()),
        "epc_recent10_national_coverage": float(epc["recent10_cert_count"].sum() / epc[dw_col].sum()),
        "epc_dwellings_column": dw_col,
        "epc_dwellings_flag_counts": epc["dwellings_flag"].fillna("").value_counts().to_dict() if "dwellings_flag" in epc else None,
        "zero_dwellings": {"codes": sorted(zero_codes), "source": zero_src, "dropped_priced_zones": zero_dropped},
        "pop_dwellings_mismatch": sorted(fsets["pop_dwellings_mismatch"]),
        "epc_overcount": {"threshold": oc["threshold"], "zones_tagged": sum("epc_overcount_proxy" in i.tags for i in inputs_cache.values()),
                          "by_basis": pd.Series([t for i in inputs_cache.values() for t in i.tags if t.startswith("epc_overcount_basis=")]).value_counts().to_dict(),
                          "priced_zones_tagged": sum("epc_overcount_proxy" in inputs_cache[z["code"]].tags for z in zones_epc)},
        "tables_epc": {s: class_table(zones_epc, s) for s in sr.SCENARIOS},
        "tables_archetype": {s: class_table(zones_old, s) for s in sr.SCENARIOS},
        "checks_epc": gradient_by_scenario(zones_epc, cfg),
        "checks_archetype": gradient_by_scenario(zones_old, cfg),
        "estate_mode": estate_mode, "estate_mid_weight": estate_mid_weight,
        "estate_tag_counts": pd.Series([t for i in inputs_cache.values() for t in i.tags if t.startswith("estate")]).value_counts().to_dict(),
        "swing_table": swing,
        "plausibility_v07": plausibility_v07(zones_epc, cfg, swings=({k: v["Scotland"] for k, v in swing.items()} if swing else None)),
        "most_negative_large_urban_high": most_negative(zones_epc, ur6=1, scenario="high"),
        "gradient_v06": gradient_v06(zones_epc, cfg, access_path=D + "simd2020v2_access_indicators_dz2011.csv",
                                     land_rows=land_rows),
        "plot_size_diagnostic": plot_size_diag_v07(zones_epc, inputs_cache, cfg, dep_kw=dep_kw,
                                                   land_rows=land_rows, estate_rows=estate_rows),
        "plot_band_source_counts_priced": pd.Series([next((t for t in inputs_cache[z["code"]].tags if t.startswith("plot_bands_")), "none")
                                                     for z in zones_epc]).value_counts().to_dict(),
        "plot_band_source_counts_all_zones": (pd.Series([r["_plot_bands_source"] for r in estate_rows.values()]).value_counts().to_dict()
                                              if estate_rows else None),
        "res_land_exclusions_priced": (pd.Series([x for r in land_rows if r["code"] in {z["code"] for z in zones_epc}
                                                  for x in (r["gradient_exclude"] or ("kept",))]).value_counts().to_dict()
                                       if land_rows else None),
        "zones_epc": zones_epc,
        "inputs": inputs_cache, "prices": {p["code"]: p for p in prices}, "band": band, "base_year": base_year,
        "epc_rows": epc,
    }
