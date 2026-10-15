"""Build a pooled 2011 rent table for DZ2022 fill (FILL-POOLED C1).

Runs the #115 pooling path (``pool_zone_price`` + ``index_price`` + residual /
``resolve_land_value``) and writes a gitignored CSV that ``load_2011_rent_table``
reads, plus ``evidence_window``, ``evidence_oldest_year``, ``sales_n``, and
``pooling_config_sha256``.

Outputs never commit: ``data/external/methods_runs/`` or ``valuation_out``.
No public £; publication_status stays blocked / value_tier proxy on fill.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from georgist import dz2022_fill as fill
from georgist import surface_illustrative as si
from georgist import surface_rent as sr
from georgist.surface_paths import REPO_ROOT, data_dir

LOG = logging.getLogger(__name__)

RENT_TABLE_COLUMNS = (
    "zone_id",
    "central",
    "low",
    "high",
    "status",
    "dwellings",
    "la_code",
    "ur6_class",
    "sales_n",
    "flags",
    "evidence_window",
    "evidence_oldest_year",
    "pooling_config_sha256",
)

DEFAULT_OUT_NAME = "rent_table_2011_pooled.csv"


def default_output_path() -> Path:
    """Gitignored methods_runs path (falls back to valuation_out)."""
    methods = REPO_ROOT / "data" / "external" / "methods_runs"
    return methods / DEFAULT_OUT_NAME


def evidence_window_for_pooled(
    *,
    latest_year: int,
    pooled: sr.PooledPrice,
    published_latest_n: int | None,
    n_min: int,
) -> str | None:
    """Classify window: 2023 if latest year alone publishes; else pooled_3y / pooled_5y."""
    if pooled.price_gbp is None or pooled.sales_n <= 0:
        return None
    if published_latest_n is not None and int(published_latest_n) >= int(n_min):
        return "2023"
    tags = set(pooled.tags)
    if "pooled_3y" in tags:
        return "pooled_3y"
    if "pooled_5y" in tags:
        return "pooled_5y"
    # Single-year pool inside the first window still counts as measured latest year.
    if pooled.evidence_oldest_year == int(latest_year):
        return "2023"
    return "pooled_3y"


def rent_row_from_resolved(
    *,
    code: str,
    land: sr.LandValue,
    dwellings: int | None,
    la_code: str | None,
    ur6_class: int | None,
    sales_n: int,
    evidence_window: str | None,
    evidence_oldest_year: int | None,
    pooling_sha: str,
    flags: str = "",
    low: float | None = None,
    high: float | None = None,
) -> dict:
    """One CSV row; central/low/high are land-rent figures (research estimates)."""
    central = land.land_value
    status = land.fill_method
    if status == "not_applicable":
        central = 0.0
        low = 0.0
        high = 0.0
    elif central is None:
        status = "model_fill_pending"
        central = None
        low = None
        high = None
    else:
        if low is None:
            low = float(central)
        if high is None:
            high = float(central)
    return {
        "zone_id": code,
        "central": "" if central is None else f"{float(central):.6f}",
        "low": "" if low is None else f"{float(low):.6f}",
        "high": "" if high is None else f"{float(high):.6f}",
        "status": status,
        "dwellings": "" if dwellings is None else int(dwellings),
        "la_code": la_code or "",
        "ur6_class": "" if ur6_class is None else int(ur6_class),
        "sales_n": int(sales_n),
        "flags": flags,
        "evidence_window": evidence_window or "",
        "evidence_oldest_year": (
            "" if evidence_oldest_year is None else int(evidence_oldest_year)
        ),
        "pooling_config_sha256": pooling_sha,
    }


def write_rent_table(rows: Sequence[Mapping], path: Path | str) -> Path:
    """Write the pooled rent table; parent dirs created. Path must be gitignored."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(RENT_TABLE_COLUMNS))
        writer.writeheader()
        for raw in rows:
            writer.writerow({k: raw.get(k, "") for k in RENT_TABLE_COLUMNS})
    return out


def build_rows_from_zone_pools(
    zones: Iterable[Mapping],
    *,
    config: Mapping | None = None,
    latest_year: int = 2023,
) -> list[dict]:
    """Build stamped rent-table rows from already-pooled zone dicts (tests / local).

    Each zone mapping needs: code, sales_n, price or land_value (optional),
    fill_method/status, dwellings, la_code, ur6_class, evidence_window,
    evidence_oldest_year, flags; optional uncertainty_low/high.
    """
    cfg = config if config is not None else sr.load_config()
    price_cfg = cfg["price"]
    sha = fill.pooling_config_sha256(cfg)
    n_min = int(price_cfg["n_min"])
    rows: list[dict] = []
    for z in zones:
        code = str(z["code"]).strip()
        sales_n = int(z.get("sales_n") or 0)
        window = str(z.get("evidence_window") or "").strip() or None
        if window is None and sales_n >= n_min:
            # Infer from optional pooled tags / latest-year sales.
            latest_n = z.get("sales_n_latest_year")
            tags = z.get("proxy_tags") or z.get("tags") or ()
            fake = sr.PooledPrice(
                price_gbp=1.0,
                sales_n=sales_n,
                years=None,
                measure=str(price_cfg["measure"]),
                tags=tuple(tags) if not isinstance(tags, tuple) else tags,
                evidence_year=latest_year,
                evidence_oldest_year=z.get("evidence_oldest_year"),
            )
            window = evidence_window_for_pooled(
                latest_year=latest_year,
                pooled=fake,
                published_latest_n=int(latest_n) if latest_n is not None else None,
                n_min=n_min,
            )
        land_val = z.get("land_value")
        if land_val is None:
            land_val = z.get("measured_rent")
        if land_val is None:
            land_val = z.get("central")
        status = str(z.get("status") or z.get("fill_method") or "").strip()
        zero = code in fill.ZERO_DWELLING_CODES or "zero_dwellings" in str(
            z.get("flags") or ""
        )
        if zero:
            land = sr.LandValue(None, "not_applicable", ("zero_dwellings", "not_applicable"))
        elif land_val is None or land_val == "":
            land = sr.LandValue(None, status or "model_fill_pending", ("model_fill_pending",))
        else:
            land = sr.LandValue(
                float(land_val),
                status or "observed_pooled",
                tuple(z.get("proxy_tags") or ()),
            )
        rows.append(
            rent_row_from_resolved(
                code=code,
                land=land,
                dwellings=z.get("dwellings"),
                la_code=z.get("la_code"),
                ur6_class=z.get("ur6_class"),
                sales_n=sales_n,
                evidence_window=window,
                evidence_oldest_year=z.get("evidence_oldest_year"),
                pooling_sha=sha,
                flags=str(z.get("flags") or ""),
                low=_opt_float(z.get("uncertainty_low") or z.get("low")),
                high=_opt_float(z.get("uncertainty_high") or z.get("high")),
            )
        )
    return rows


def _opt_float(v) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def pool_observations_to_rent_row(
    *,
    code: str,
    observations: Sequence[sr.YearPrice],
    price_cfg: Mapping,
    index_factor: Mapping[int, float],
    index_to_year: int,
    latest_year: int,
    dwellings: int,
    la_code: str | None,
    ur6_class: int | None,
    rebuild_drc: float | None,
    model_gbp: float | None,
    pooling_sha: str,
    flags: str = "",
    absent_from_price_file: bool = False,
    zero_dwellings: bool = False,
) -> dict:
    """One zone: pool → index → residual → resolve → stamped rent row."""
    n_min = int(price_cfg["n_min"])
    pooled = si.pool_zone_price(
        observations,
        latest_year=int(latest_year),
        price_cfg=price_cfg,
        index_factor=index_factor,
        index_to_year=int(index_to_year),
    )
    latest_obs = next((o for o in observations if o.year == latest_year), None)
    latest_n = None
    if latest_obs is not None and latest_obs.sales_n and latest_obs.mean_gbp:
        latest_n = int(latest_obs.sales_n)
    window = evidence_window_for_pooled(
        latest_year=latest_year,
        pooled=pooled,
        published_latest_n=latest_n,
        n_min=n_min,
    )
    observed = None
    if pooled.price_gbp is not None and rebuild_drc is not None:
        indexed = sr.index_price(
            pooled,
            price_year=int(index_to_year),
            factor=1.0,
            series="none",
            tags=(),
        )
        # When index_to_year == evidence_year, factor 1.0 is a no-op.
        observed = sr.residual_land_value(indexed.price_indexed_gbp, float(rebuild_drc))
    land = sr.resolve_land_value(
        dwellings=int(dwellings),
        observed=observed,
        sales_n=int(pooled.sales_n),
        model_gbp=model_gbp,
        n_min=n_min,
        n_full=int(price_cfg["n_full"]),
        shrinkage_k=float(price_cfg["shrinkage_k"]),
        absent_from_price_file=absent_from_price_file,
        zero_dwellings=zero_dwellings,
    )
    return rent_row_from_resolved(
        code=code,
        land=land,
        dwellings=dwellings,
        la_code=la_code,
        ur6_class=ur6_class,
        sales_n=int(pooled.sales_n),
        evidence_window=window,
        evidence_oldest_year=pooled.evidence_oldest_year,
        pooling_sha=pooling_sha,
        flags=flags,
    )


def build_and_write(
    rows: Sequence[Mapping],
    *,
    out_path: Path | str | None = None,
) -> Path:
    path = Path(out_path) if out_path is not None else default_output_path()
    return write_rent_table(rows, path)
