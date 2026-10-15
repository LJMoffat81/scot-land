"""ILLUSTRATIVE national run: residual land share by urban-rural class.

Not a result. Rows are INTERNAL (diagnostic) and never served. Inputs:
RoS DZ2011 mean prices pooled over configured years -> council UK HPI to Apr-2025;
Data Zones dwellings_by_year 2025 (council tax, Sept); GIS EPC rollup (DZ2011 rows only)
for mix, age and floor area; SGUR 2020 6-fold on DZ2011; OPEN_ESTIMATE rebuild band at
the 2025 price base.
"""

from __future__ import annotations

import csv
import dataclasses
import logging
from pathlib import Path

from typing import Callable, Iterable, Mapping, Sequence

from georgist import surface_holdout as sh
from georgist import surface_rent as sr
from georgist.surface_zones import vintage_int

UR6_NAMES = {1: "Large Urban Areas", 2: "Other Urban Areas", 3: "Accessible Small Towns",
             4: "Remote Small Towns", 5: "Accessible Rural", 6: "Remote Rural"}
LABEL = "ILLUSTRATIVE - not a result; internal diagnostic rows, never served"
LOG = logging.getLogger(__name__)

# Pre-pooling null-fill baseline (single-year RoS-2023 spine accounting). Post-pooling
# remaining empty is recomputed from the hash-pinned sales_n extract; config constant
# update lands in methods M3 (#84 DZ2022 path still documents 727).
VALUATION_OLD_NULL_DZ_FILL_TARGET_N = 727
METHODS_PR1_EXTRACT = Path(__file__).resolve().parents[2] / (
    "data/processed/methods_code_1/pr1/ros_dz2011_sales_n_2019_2023.csv"
)
METHODS_PR1_EXTRACT_META = Path(__file__).resolve().parents[2] / (
    "data/processed/methods_code_1/pr1/ros_dz2011_sales_n_2019_2023.sha256.json"
)
METHODS_LOCAL_PCT_RUN = Path(__file__).resolve().parents[2] / (
    "data/external/methods_runs/pr1_scotland_pct_change.json"
)


def _load_sales_n_extract(extract_csv: Path | str) -> dict[str, dict[int, dict]]:
    """{code: {year: {sales_n, suppressed}}} from count-only RoS extract (no £)."""
    by: dict[str, dict[int, dict]] = {}
    with Path(extract_csv).open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            code = row["code"].strip()
            year = int(row["year"])
            suppressed = str(row.get("suppressed") or "").strip().lower() == "true"
            sales_raw = str(row.get("sales_n") or "").strip()
            sales_n = None if suppressed or not sales_raw else int(float(sales_raw))
            by.setdefault(code, {})[year] = {"sales_n": sales_n, "suppressed": suppressed}
    return by


def _published_sales_n_extract(by_year: Mapping[int, Mapping], years: Sequence[int]) -> int:
    """Sum sales_n only for non-suppressed published years (never infer suppressed)."""
    total = 0
    for year in years:
        cell = by_year.get(int(year))
        if not cell or cell.get("suppressed") or not cell.get("sales_n"):
            continue
        total += int(cell["sales_n"])
    return total


def empty_zone_pooling_coverage_from_ros_extract(
    extract_csv: Path | str,
    spine_csv: Path | str,
    *,
    latest_year: int = 2023,
    pool_years: int = 3,
    pool_years_max: int = 5,
    n_min: int = 5,
) -> dict:
    """R4.7 coverage from hash-pinned RoS sales_n extract + zone spine (no £).

    Empty-with-dwellings = spine DZ2011 minus zero_dwellings, with no published
    price in ``latest_year`` (suppressed or absent from extract). Then 3y then 5y.
    """
    extract_path, spine_path = Path(extract_csv), Path(spine_csv)
    by_code = _load_sales_n_extract(extract_path)
    spine = {
        r["code"]: r
        for r in csv.DictReader(spine_path.open(encoding="utf-8"))
        if str(r.get("vintage")) == "2011"
    }
    zero = {c for c, r in spine.items() if "zero_dwellings" in (r.get("flags") or "")}
    absent = {c for c, r in spine.items() if "absent_from_ros_price_file" in (r.get("flags") or "")}

    def is_empty(code: str) -> bool:
        if code in absent or code not in by_code:
            return True
        cell = by_code[code].get(int(latest_year))
        return cell is None or bool(cell.get("suppressed"))

    empty_with_dwellings = sorted(c for c in spine if c not in zero and is_empty(c))
    win3 = tuple(range(latest_year - pool_years + 1, latest_year + 1))
    win5 = tuple(range(latest_year - pool_years_max + 1, latest_year + 1))
    gained_3y, gained_5y, remaining = [], [], []
    for code in empty_with_dwellings:
        years = by_code.get(code, {})
        if _published_sales_n_extract(years, win3) >= n_min:
            gained_3y.append(code)
        elif _published_sales_n_extract(years, win5) >= n_min:
            gained_5y.append(code)
        else:
            remaining.append(code)
    return {
        "empty_with_dwellings": len(empty_with_dwellings),
        "gained_pooled_3y": len(gained_3y),
        "gained_pooled_5y": len(gained_5y),
        "gained_observed": len(gained_3y) + len(gained_5y),
        "remaining_model_fill": len(remaining),
        "zero_dwellings": len(zero),
        "absent_from_ros": len(absent),
        "pool_years": pool_years,
        "pool_years_max": pool_years_max,
        "n_min": n_min,
        "latest_year": latest_year,
        "gained_pooled_3y_codes": gained_3y,
        "gained_pooled_5y_codes": gained_5y,
        "remaining_model_fill_codes": remaining,
        "null_dz_fill_target_n_old": VALUATION_OLD_NULL_DZ_FILL_TARGET_N,
        "null_dz_fill_target_n_new": len(remaining),
    }


def empty_zone_pooling_coverage_from_dz_prices(
    prices_csv: Path | str,
    spine_csv: Path | str,
    *,
    latest_year: int = 2023,
    pool_years: int = 3,
    n_min: int = 5,
) -> dict:
    """3y-only coverage from committed dz2011_prices + spine (diagnostic)."""
    prices_path, spine_path = Path(prices_csv), Path(spine_csv)
    rows = list(csv.DictReader(prices_path.open(encoding="utf-8")))
    spine = {
        r["code"]: r
        for r in csv.DictReader(spine_path.open(encoding="utf-8"))
        if str(r.get("vintage")) == "2011"
    }
    zero = {c for c, r in spine.items() if "zero_dwellings" in (r.get("flags") or "")}
    empty = [r for r in rows if not str(r.get(f"dz_med{latest_year}") or "").strip()]
    empty_with_dwellings = [r for r in empty if r.get("dz2011") not in zero]
    window = tuple(range(latest_year - pool_years + 1, latest_year + 1))

    def pub_n(row: Mapping) -> int:
        total = 0
        for year in window:
            med = str(row.get(f"dz_med{year}") or "").strip()
            n_raw = row.get(f"dz_n{year}")
            if not med or n_raw is None or str(n_raw).strip() == "":
                continue
            total += int(float(n_raw))
        return total

    gained_3y = [r for r in empty_with_dwellings if pub_n(r) >= n_min]
    still_empty = [r for r in empty_with_dwellings if pub_n(r) < n_min]
    return {
        "empty_with_dwellings": len(empty_with_dwellings),
        "gained_pooled_3y": len(gained_3y),
        "still_empty_after_3y": len(still_empty),
        "zero_dwellings_in_empty": len(empty) - len(empty_with_dwellings),
        "pool_years": pool_years,
        "n_min": n_min,
        "latest_year": latest_year,
    }


def pool_zone_price(
    observations: Sequence[sr.YearPrice],
    *,
    latest_year: int,
    price_cfg: Mapping,
    index_factor: Mapping[int, float],
    index_to_year: int,
) -> sr.PooledPrice:
    """Wire ``pool_prices`` with surface.yaml price knobs (R3.1–R3.5)."""
    return sr.pool_prices(
        observations,
        latest_year=int(latest_year),
        measure=str(price_cfg["measure"]),
        pool_years=int(price_cfg["pool_years"]),
        pool_years_max=int(price_cfg["pool_years_max"]),
        n_min=int(price_cfg["n_min"]),
        index_factor=index_factor,
        index_to_year=int(index_to_year),
    )


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
    rates=("low", "central", "high"),
    # legacy aliases
    floors=None, lives=None,
) -> dict:
    """v1.3 F7 review for large old homes: residual per dwelling at one rebuild level
    across rate_building corners (unmaintained / central / maintained).

    Returns {(rate, rate): {rate_building, remaining, drc, residual}}. Legacy
    ``floors``/``lives`` kwargs are accepted as aliases for ``rates``.
    """
    levels = tuple(rates)
    if lives is not None:
        levels = tuple(lives)
    if floors is not None and lives is None:
        levels = tuple(floors)
    out = {}
    for rate in levels:
        dep = sr.depreciation_at(depreciation, rate=rate)
        scalar = {**dep, "band_combination": {"rule": "corner"}}
        r = sr.zone_rebuild_band(
            inp,
            band={t: {s: b[rebuild] for s in sr.SCENARIOS} for t, b in band.items()},
            depreciation=scalar,
            valuation_year=valuation_year,
            default_remaining_factor=None,
        )
        rem = r["central"].remaining_factor
        out[(rate, rate)] = {
            "rate_building": dep.get("rate_building"),
            "remaining": rem,
            "drc": r["central"].drc_gbp,
            "residual": price - r["central"].drc_gbp,
        }
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


def gradient_v07(zones: Sequence[Mapping], cfg: Mapping, *, land_rows: list | None, access_path: str | None = None,
                 access_metadata: Mapping | None = None, override: bool = False, reason: str = "") -> dict:
    """Pre-registered rules 12.2 v0.7 job-access gradient. Without dz_access it reports pending and reads
    nothing. A scored run records (dz_access sha256, config hash) in the internal run log first and refuses
    a repeat on the same input without override."""
    from georgist import surface_harvester as hv
    from georgist import surface_paths as sp

    g = cfg["gradient_v07"]
    if not access_path:
        return sh.job_access_gradient_check([], residential_land_rows=land_rows, access_rows=None, gcfg=g,
                                            expected_order=cfg["land_share_checks"]["ur6_expected_order"], access_metadata=None)
    sha = hv.sha256_file(Path(access_path))
    frozen = str(g["input"].get("frozen_sha256_prefix") or "")
    if frozen and not sha.startswith(frozen):
        raise ValueError(f"dz_access sha256 {sha[:8]} is not the frozen input {frozen}")
    meta = sh.check_access_metadata(access_metadata, g["expected_metadata"])   # before the run is logged
    if meta["status"] != "verified":
        raise sh.AccessMetadataMismatch(f"dz_access metadata incomplete {meta['missing']}; scored run not started")
    guard = sh.RunGuard(sp.expand(g["run_guard"]["log"]))
    entry = guard.register(access_sha256=sha, cfg_hash=sh.config_hash(g), override=override, reason=reason)
    acc = hv.load_gis_output(access_path).to_dict("records")
    obs = [{"code": z["code"], "vintage": 2011, "ur6_class": z["ur6_class"], "fill_method": "observed_pooled",
            "sales_n": z["sales_n"], "observed_land_value": z["price_indexed"] - z["drc"]["central"], "dwellings": z["dwellings"]}
           for z in zones]
    res = sh.job_access_gradient_check(obs, residential_land_rows=land_rows, access_rows=acc, gcfg=g,
                                       expected_order=cfg["land_share_checks"]["ur6_expected_order"], access_metadata=access_metadata)
    return {**res, "run_log_entry": entry}


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
    return {"label": g.get("label", "superseded driver, reported"), **sh.per_hectare_gradient_check(obs, residential_land_rows=land, access_rows=acc,
                                         expected_order=cfg["land_share_checks"]["ur6_expected_order"],
                                         min_zones_per_class=g["min_zones_per_class"], access_rho_max=g["access_rho_max"],
                                         min_sales=g["min_sales"], max_missing_share=g["max_missing_share"],
                                         methods_ok=tuple(g["residential_land"]["methods_ok"]))}


def run(*, raw_dir: str, gis_dir: str, dz_dir: str | None = None, residential_land_path: str | None = None, cfg: Mapping | None = None, area_fn: Callable[[Mapping, "sr.ZoneRebuildInputs"], float] | None = None,
        epc_primary: str = "all_time", estate_mode: str | None = None, estate_rows: Mapping[str, Mapping] | None = None,
        estate_mid_weight: float | None = None, swings: bool = True, plot_bands_path: str | None = None,
        res_land_low_coverage: str = "exclude", access_v07_path: str | None = None, access_v07_metadata: Mapping | None = None,
        access_v07_override: bool = False, access_v07_reason: str = "") -> dict:
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
    hpi_df = hv.load_uk_hpi(R + "hpi-2026-07.csv")
    price_cfg = cfg["price"]
    ros11 = ros[ros.vintage == 2011]
    latest_ros_year = int(ros11["year"].max())
    # Within-RoS pooling indexes sale years to the latest RoS year (surface.yaml price.index_to_valuation_year).
    index_to_year = latest_ros_year
    pool_years_max = int(price_cfg["pool_years_max"])
    pool_year_list = list(range(latest_ros_year - pool_years_max + 1, latest_ros_year + 1))
    annual_hpi = hv.council_annual_hpi(hpi_df, pool_year_list)
    pts = hv.council_hpi_points(hpi_df, base_year=index_to_year, target_month="2025-04")
    band = sr.rebuild_band(cfg, base_year)
    n17i = n17.set_index("code")
    n25i = n25.set_index("code")
    urc_codes = set(urc["code"])
    joins = {"epc_dz2011_rows": len(epc), "epc_dz2022_rows_not_used": int((epc_all["vintage"] == 2022).sum()),
             "nrs_zones": len(n25), "urc_zones": len(urc),
             "nrs_codes_equal_urc": set(n25["code"]) == urc_codes, "nrs_codes_equal_epc": set(n25["code"]) == set(epc.index)}
    ros_codes = set(ros11["code"])
    no_price = {"absent_from_ros_price_file": [c for c in absent if c not in ros_codes],
                "absent_flag_but_in_ros": [c for c in absent if c in ros_codes],
                "suppressed_2023_lt5_sales": int(((ros.vintage == 2011) & (ros.year == latest_ros_year) & ros.suppressed).sum())}
    # Model-fill target: recompute from data after pooling (log old hard-coded 727 against new).
    old_fill_target = int((cfg.get("model_fill") or {}).get("null_dz_fill_target_n", VALUATION_OLD_NULL_DZ_FILL_TARGET_N))
    prices, fallback = [], {}
    suppressed_all = []
    pool_tag_counts: dict[str, int] = {}
    for code in sorted(ros_codes):
        if code not in n25i.index:
            continue
        mixrow = n17i.loc[code] if code in n17i.index else None
        m = sr.nrs2017_type_shares(mixrow) if mixrow is not None else None
        hm = {"detached": m["detached"], "semi_detached": m["semi_detached"], "terraced": m["terraced"], "flat": m["flat_purpose_built"]} if m else None
        council = n25i.loc[code, "council_code"]
        observations = hv.ros_year_prices_for_zone(ros, code, vintage=2011)
        idx_factors = hv.pooling_index_factors(
            annual_hpi[str(council)], index_to_year=index_to_year, type_mix=hm, years=pool_year_list,
        )
        pooled = pool_zone_price(
            observations, latest_year=latest_ros_year, price_cfg=price_cfg,
            index_factor=idx_factors, index_to_year=index_to_year,
        )
        for t in pooled.tags:
            pool_tag_counts[t] = pool_tag_counts.get(t, 0) + 1
        if pooled.price_gbp is None:
            suppressed_all.append(code)
            continue
        f, series, tags = sr.hpi_factor(pts[council], hm)
        ip = sr.index_price(pooled, price_year=base_year, factor=f, series=series, tags=tags)
        # Pooled sales_n feeds resolve_land_value n_full / n_min / shrinkage_k.
        prices.append({
            "code": code, "council_code": council, "council_name": n25i.loc[code, "council_name"],
            "price_raw": pooled.price_gbp, "price_indexed": ip.price_indexed_gbp,
            "sales_n": int(pooled.sales_n),
            "proxy_tags": list(pooled.tags),
            "evidence_years": pooled.years,
            "evidence_year": pooled.evidence_year,
            "evidence_oldest_year": pooled.evidence_oldest_year,
        })
    # Absent-only codes are not in ros_codes; subtract zero dwellings that are absent or suppressed.
    absent_only = [c for c in absent if c not in ros_codes]
    null_codes = set(suppressed_all) | set(absent_only)
    new_fill_target = len(null_codes - zero_codes)
    LOG.info(
        "null_dz_fill_target_n old=%s new=%s (suppressed_all_years=%s absent_only=%s zero_in_null=%s)",
        old_fill_target, new_fill_target, len(suppressed_all), len(absent_only),
        len(null_codes & zero_codes),
    )
    zero_dropped = sorted(p["code"] for p in prices if p["code"] in zero_codes)  # rules v0.7: not applicable, overrides price
    prices = [p for p in prices if p["code"] not in zero_codes]
    pooling_meta = {
        "latest_ros_year": latest_ros_year,
        "index_to_year": index_to_year,
        "pool_years": int(price_cfg["pool_years"]),
        "pool_years_max": pool_years_max,
        "n_min": int(price_cfg["n_min"]),
        "n_full": int(price_cfg["n_full"]),
        "observed_pooled_zones": len(prices),
        "suppressed_all_years_zones": len(suppressed_all),
        "pool_tag_counts": pool_tag_counts,
        "null_dz_fill_target_n_old": old_fill_target,
        "null_dz_fill_target_n_new": new_fill_target,
    }
    dwell = {c: (int(v) if v == v else None) for c, v in zip(dw_tot["code"], dw_tot["dwellings_total"])}
    occupancy = {r.code: (None if r.vacant_share != r.vacant_share else float(r.vacant_share),
                               None if r.second_home_share != r.second_home_share else float(r.second_home_share))
                 for r in dw_occ.itertuples()}
    ur6 = dict(zip(urc["code"], urc["ur6_class"]))
    plot_raw = None
    if estate_mode in ("plot_bands", "gis_bands") and estate_rows is None:
        if not plot_bands_path:
            raise ValueError("estate mode plot_bands needs plot_bands_path (GIS dz_detached_plot_bands, internal)")
        pb = hv.load_gis_checked(plot_bands_path, sha_prefix=ecfg["source_sha256_prefix"], publish_level=tuple(ecfg.get("accepted_publish_levels", ["internal"])))
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
        "pooling": pooling_meta,
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
        "gradient_v07": gradient_v07(zones_epc, cfg, land_rows=land_rows, access_path=access_v07_path,
                                     access_metadata=access_v07_metadata, override=access_v07_override, reason=access_v07_reason),
        "zones_epc": zones_epc,
        "inputs": inputs_cache, "prices": {p["code"]: p for p in prices}, "band": band, "base_year": base_year,
        "epc_rows": epc,
    }
