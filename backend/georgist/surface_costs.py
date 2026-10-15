"""DZ2011 rebuild-cost step (SURFACE-COSTS-ALL).

Writes one per-dwelling depreciated replacement cost row (central / low / high)
for every 2011 data zone (6,976). Costs use the same surface.yaml rebuild rates
and depreciation for every zone — no price inputs and no job-access test.

Mix / age / floor area still come from the GIS EPC rollup (NRS 2017 fallback)
and estate plot-band shares, matching the measured surface residual path.
2011→2022 conversion is intentionally out of scope: E8 on main handles that
after pooling and the fill.

Defaults for floor area and stock remaining align with ``agr.yaml`` /
``agr.valuation`` (typical_dwelling_sqm, average_stock_remaining_factor).
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from agr import config as agr_config
from datasources.rebuild import blended_rebuild_per_m2, region_factor
from georgist import surface_harvester as hv
from georgist import surface_rent as sr
from georgist.surface_dz2022 import EXPECTED_DZ2011
from georgist.surface_paths import REPO_ROOT

LOG = logging.getLogger(__name__)

COST_COLUMNS = (
    "code",
    "dwellings",
    "rebuild_status",
    "rebuild_new_gbp",
    "remaining_factor",
    "drc_gbp",
    "drc_low_gbp",
    "drc_high_gbp",
)

NA_STATUS = "n/a"
DEFAULT_OUT_NAME = "surface_costs_dz2011.csv"

# SGUR 2020: official 8-fold → 6-fold collapse (Very Remote ST→Remote ST;
# Remote/Very Remote Rural→Remote Rural). Used when the repo processed lookup
# carries UR8 only (data/processed/dz2011_urban_rural_2020.csv).
UR8_TO_UR6 = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4, 6: 5, 7: 6, 8: 6}

PROCESSED_GIS = REPO_ROOT / "data" / "processed" / "gis"
PROCESSED_DZ = REPO_ROOT / "data" / "processed" / "datazones"
PROCESSED_UR = REPO_ROOT / "data" / "processed" / "dz2011_urban_rural_2020.csv"


def agr_aligned_defaults(
    surface_cfg: Mapping | None = None,
    agr_cfg: Mapping | None = None,
) -> dict[str, float]:
    """Shared floor-area / stock-remaining defaults from agr.yaml and surface.yaml.

    ``agr.valuation`` reads ``valuer_roll.typical_dwelling_sqm`` and
    ``valuer_roll.depreciation.average_stock_remaining_factor``. Surface
    ``rebuild_inputs`` mirrors those as ``default_floor_area_m2`` /
    ``default_remaining_factor``. Refuse silent drift.
    """
    scfg = dict(surface_cfg) if surface_cfg is not None else sr.load_config()
    acfg = dict(agr_cfg) if agr_cfg is not None else agr_config.load_config()
    valuer = acfg.get("valuer_roll") or {}
    agr_floor = float(
        valuer.get("typical_dwelling_sqm", (acfg.get("valuation") or {}).get("typical_dwelling_sqm", 97))
    )
    agr_remaining = float(
        (valuer.get("depreciation") or {}).get("average_stock_remaining_factor", 0.55)
    )
    ri = scfg.get("rebuild_inputs") or {}
    surf_floor = float(ri["default_floor_area_m2"])
    surf_remaining = float(ri["default_remaining_factor"])
    if surf_floor != agr_floor:
        raise ValueError(
            f"surface rebuild_inputs.default_floor_area_m2 {surf_floor} "
            f"!= agr typical_dwelling_sqm {agr_floor}"
        )
    if surf_remaining != agr_remaining:
        raise ValueError(
            f"surface rebuild_inputs.default_remaining_factor {surf_remaining} "
            f"!= agr average_stock_remaining_factor {agr_remaining}"
        )
    # Same blended £/m² helpers ``agr.valuation`` / ``agr.engine`` use via datasources.rebuild.
    if blended_rebuild_per_m2(acfg) <= 0:
        raise ValueError("agr blended rebuild £/m² must be positive")
    if region_factor("default", acfg) <= 0:
        raise ValueError("agr default region rebuild factor must be positive")
    return {
        "default_floor_area_m2": surf_floor,
        "default_remaining_factor": surf_remaining,
    }


def load_ur6_dz2011(path: Path | str | None = None) -> dict[str, int]:
    """Return ``{dz2011_code: ur6_class}`` from the processed SGUR lookup."""
    p = Path(path) if path is not None else PROCESSED_UR
    if not p.is_file():
        raise FileNotFoundError(f"DZ2011 urban-rural lookup missing: {p}")
    df = pd.read_csv(p, dtype=str)
    if {"dz2011", "ur8"} <= set(df.columns):
        out: dict[str, int] = {}
        for row in df.itertuples(index=False):
            code = str(row.dz2011).strip()
            ur8 = int(row.ur8)
            if ur8 not in UR8_TO_UR6:
                raise ValueError(f"UR8 class {ur8} out of range for {code}")
            out[code] = UR8_TO_UR6[ur8]
        return out
    # Official SG download shape (DataZone / UR6FOLD), when staged locally.
    if {"DataZone", "UR6FOLD"} <= set(df.columns):
        return {
            str(r.DataZone).strip(): int(r.UR6FOLD)
            for r in df.itertuples(index=False)
        }
    raise ValueError(f"urban-rural lookup {p} missing dz2011/ur8 or DataZone/UR6FOLD")


def _na_row(code: str, dwellings: int | None) -> dict:
    return {
        "code": code,
        "dwellings": 0 if dwellings is None else int(dwellings),
        "rebuild_status": NA_STATUS,
        "rebuild_new_gbp": None,
        "remaining_factor": None,
        "drc_gbp": None,
        "drc_low_gbp": None,
        "drc_high_gbp": None,
    }


def _cost_row(
    code: str,
    dwellings: int | None,
    *,
    rebuilds: Mapping[str, sr.RebuildResult],
    rebuild_status: str,
) -> dict:
    central = rebuilds["central"]
    return {
        "code": code,
        "dwellings": None if dwellings is None else int(dwellings),
        "rebuild_status": rebuild_status,
        "rebuild_new_gbp": central.rebuild_new_gbp,
        "remaining_factor": central.remaining_factor,
        "drc_gbp": central.drc_gbp,
        "drc_low_gbp": rebuilds["low"].drc_gbp,
        "drc_high_gbp": rebuilds["high"].drc_gbp,
    }


def zone_cost_rebuilds(
    code: str,
    *,
    epc_row: Mapping | None,
    nrs2017_row: Mapping | None,
    estate_row: Mapping | None,
    cfg: Mapping,
    band: Mapping,
    valuation_year: int,
    defaults: Mapping[str, float],
    ur6_class: int | None = None,
) -> dict[str, sr.RebuildResult]:
    """Per-dwelling rebuild band for one zone (same rates/depreciation as every other).

    v1.3: applies rural_uplift by UR6 class (F6) and flat GIA ×1.10 (F4).
    """
    ri = cfg["rebuild_inputs"]
    oc = cfg["epc_overcount"]
    ecfg = cfg["estate"]
    inp = sr.zone_rebuild_inputs(
        epc_row,
        nrs2017_row,
        default_area_m2=float(defaults["default_floor_area_m2"]),
        min_tfa_n=int(ri["min_tfa_n"]),
        primary=str(ri.get("epc_primary", "all_time")),
    )
    inp = sr.tag_epc_overcount(
        inp,
        epc_row,
        threshold=float(oc["threshold"]),
        flag_column=oc["prefer_flag_column"],
    )
    inp = sr.with_estate(inp, ecfg, mode=str(ecfg["mode"]), estate_row=estate_row)
    region = sr.rural_uplift_factor(cfg, ur6_class)
    return sr.zone_rebuild_band(
        inp,
        band=band,
        depreciation=cfg["depreciation"],
        valuation_year=int(valuation_year),
        region=region,
        default_remaining_factor=float(defaults["default_remaining_factor"]),
        flat_gia=sr.flat_gia_factor(cfg),
    )


def build_cost_rows(
    *,
    cfg: Mapping | None = None,
    gis_dir: Path | str | None = None,
    datazones_dir: Path | str | None = None,
    ur_path: Path | str | None = None,
    codes: Sequence[str] | None = None,
) -> list[dict]:
    """Build one cost row per DZ2011 zone (or ``codes`` when testing a subset)."""
    scfg = cfg if cfg is not None else sr.load_config()
    defaults = agr_aligned_defaults(scfg)
    base_year = sr.rebuild_price_base_year(scfg)
    band = sr.rebuild_band(scfg, base_year)
    rebuild_status = str(scfg["rebuild"]["status"])

    gis = Path(gis_dir) if gis_dir is not None else PROCESSED_GIS
    dz = Path(datazones_dir) if datazones_dir is not None else PROCESSED_DZ

    spine = hv.load_zone_spine(dz / "zone_spine.csv")
    if spine is None:
        raise FileNotFoundError(f"zone_spine missing under {dz}")
    spine11 = spine[spine["vintage"] == 2011]
    all_codes = sorted(str(c) for c in spine11["code"].tolist())
    if len(all_codes) != EXPECTED_DZ2011:
        raise ValueError(f"spine DZ2011 count {len(all_codes)} != {EXPECTED_DZ2011}")
    target = list(codes) if codes is not None else all_codes
    if codes is not None:
        missing = [c for c in target if c not in set(all_codes)]
        if missing:
            raise ValueError(f"codes not on DZ2011 spine: {missing[:5]}")

    la = dict(zip(spine11["code"].astype(str), spine11["la_code"].astype(str)))
    zero, zero_src = sr.zero_dwellings_codes(spine11.to_dict("records"))
    LOG.info("zero_dwellings n=%s source=%s", len(zero), zero_src)

    epc_all = hv.load_gis_output(gis / "epc_dz_rollup.csv")
    epc = epc_all[epc_all["vintage"] == 2011].set_index("code")
    nrs = pd.read_csv(dz / "nrs_dwelling_mix_2011_fallback.csv").set_index("code")
    dw = hv.load_dwelling_counts(
        "datazones_ct_table",
        dz / "dwellings_by_year.csv",
        price_year=base_year,
        vintage=2011,
    )
    dwell = {
        str(c): (int(v) if v == v else None)
        for c, v in zip(dw["code"], dw["dwellings_total"])
    }

    ur6 = load_ur6_dz2011(ur_path)
    ecfg = scfg["estate"]
    pb = hv.load_gis_checked(
        gis / "dz_detached_plot_bands.csv",
        sha_prefix=ecfg["source_sha256_prefix"],
        publish_level=tuple(ecfg.get("accepted_publish_levels", ["internal"])),
    )
    plot_raw = {
        str(r["code"]): r for r in pb[pb["vintage"] == 2011].to_dict("records")
    }
    meta = {c: (la[c], int(ur6[c])) for c in all_codes}
    estate_rows = sr.borrow_plot_bands(plot_raw, meta, ecfg)
    if len(estate_rows) != EXPECTED_DZ2011:
        raise ValueError(
            f"estate plot-band rows {len(estate_rows)} != {EXPECTED_DZ2011}"
        )

    rows: list[dict] = []
    for code in target:
        n = dwell.get(code)
        if code in zero or n == 0:
            rows.append(_na_row(code, n))
            continue
        erow = epc.loc[code].to_dict() if code in epc.index else None
        n17 = nrs.loc[code].to_dict() if code in nrs.index else None
        rebuilds = zone_cost_rebuilds(
            code,
            epc_row=erow,
            nrs2017_row=n17,
            estate_row=estate_rows.get(code),
            cfg=scfg,
            band=band,
            valuation_year=base_year,
            defaults=defaults,
            ur6_class=ur6.get(code),
        )
        rows.append(
            _cost_row(code, n, rebuilds=rebuilds, rebuild_status=rebuild_status)
        )
    return rows


def assert_one_row_per_zone(rows: Sequence[Mapping], *, expected_n: int = EXPECTED_DZ2011) -> None:
    codes = [str(r["code"]) for r in rows]
    if len(rows) != expected_n:
        raise AssertionError(f"cost rows {len(rows)} != expected {expected_n}")
    if len(set(codes)) != len(codes):
        raise AssertionError("duplicate DZ2011 codes in cost table")
    if len(codes) != expected_n:
        raise AssertionError(f"unique codes {len(set(codes))} != {expected_n}")


def write_cost_table(rows: Sequence[Mapping], path: Path | str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(COST_COLUMNS))
        writer.writeheader()
        for raw in rows:
            row = {k: raw.get(k, "") for k in COST_COLUMNS}
            for k in COST_COLUMNS:
                if row[k] is None:
                    # Zero-dwelling rows keep rebuild_status as the literal "n/a";
                    # numeric cost cells stay empty (not the string n/a).
                    row[k] = ""
            writer.writerow(row)
    return out


def read_cost_table(path: Path | str) -> list[dict]:
    """Read a cost CSV; literal ``n/a`` must round-trip (never become NaN).

    Pandas treats ``n/a`` as NA by default. Use ``keep_default_na=False`` so
    ``rebuild_status == "n/a"`` survives for zero-dwelling zones.
    """
    p = Path(path)
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    rows: list[dict] = []
    for raw in df.to_dict("records"):
        status = str(raw.get("rebuild_status") or "")
        dwellings_raw = str(raw.get("dwellings") or "").strip()
        if dwellings_raw == "" or dwellings_raw.lower() == NA_STATUS:
            dwellings: int | None = 0 if status == NA_STATUS else None
        else:
            dwellings = int(float(dwellings_raw))

        def _cost_cell(key: str) -> float | None:
            val = str(raw.get(key) or "").strip()
            if val == "" or val.lower() == NA_STATUS:
                return None
            return float(val)

        rows.append(
            {
                "code": str(raw.get("code") or "").strip(),
                "dwellings": dwellings,
                "rebuild_status": status,
                "rebuild_new_gbp": _cost_cell("rebuild_new_gbp"),
                "remaining_factor": _cost_cell("remaining_factor"),
                "drc_gbp": _cost_cell("drc_gbp"),
                "drc_low_gbp": _cost_cell("drc_low_gbp"),
                "drc_high_gbp": _cost_cell("drc_high_gbp"),
            }
        )
    return rows


def default_output_path() -> Path:
    return REPO_ROOT / "data" / "external" / "methods_runs" / DEFAULT_OUT_NAME


def build_and_write(
    *,
    out_path: Path | str | None = None,
    cfg: Mapping | None = None,
    codes: Sequence[str] | None = None,
) -> tuple[Path, list[dict]]:
    rows = build_cost_rows(cfg=cfg, codes=codes)
    if codes is None:
        assert_one_row_per_zone(rows)
    path = Path(out_path) if out_path is not None else default_output_path()
    return write_cost_table(rows, path), rows
