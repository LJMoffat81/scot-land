"""CLI: build a pooled 2011 rent table for DZ2022 fill (FILL-POOLED C1).

Writes a gitignored CSV under ``data/external/methods_runs/`` (or
``--out`` / valuation_out). Columns match ``load_2011_rent_table`` plus
``evidence_window``, ``evidence_oldest_year``, ``sales_n``,
``pooling_config_sha256``.

Usage (from ``backend/``)::

    python -m scripts.build_rent_table_2011_pooled \\
        --from-zones /path/pooled_zones.json
    python -m scripts.build_rent_table_2011_pooled --demo-fixture

Full RoS+HPI residual rebuild stays Valuation-local (not in git). The
``--from-zones`` path stamps already-pooled zone rows; ``pool_zone_price`` +
``index_price`` + ``resolve_land_value`` are exercised via the library helpers
and unit tests.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from georgist import dz2022_fill as fill
from georgist import rent_table_pooled as rtp
from georgist import surface_rent as sr
from georgist.surface_paths import data_dir

LOG = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def cmd_from_zones(args: argparse.Namespace) -> int:
    path = Path(args.from_zones)
    if not path.is_file():
        raise SystemExit(f"zones file missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    zones = payload if isinstance(payload, list) else payload.get("zones") or []
    rows = rtp.build_rows_from_zone_pools(zones, latest_year=int(args.latest_year))
    out = rtp.build_and_write(rows, out_path=args.out)
    LOG.info(
        "wrote %s rows to %s (pooling_config_sha256=%s)",
        len(rows),
        out,
        fill.pooling_config_sha256(),
    )
    return 0


def cmd_demo_fixture(args: argparse.Namespace) -> int:
    """Synthetic one-zone pooled_3y demo for path / stamp wiring (no production £)."""
    cfg = sr.load_config()
    price_cfg = cfg["price"]
    sha = fill.pooling_config_sha256(cfg)
    obs = [
        sr.YearPrice(2021, 3, 200_000.0, 195_000.0),
        sr.YearPrice(2022, 2, 210_000.0, 205_000.0),
        sr.YearPrice(2023, None, None, None),  # empty in latest year
    ]
    idx = {2021: 1.10, 2022: 1.05, 2023: 1.00}
    row = rtp.pool_observations_to_rent_row(
        code="S01019999",
        observations=obs,
        price_cfg=price_cfg,
        index_factor=idx,
        index_to_year=2023,
        latest_year=2023,
        dwellings=100,
        la_code="S12000049",
        ur6_class=1,
        rebuild_drc=80_000.0,
        model_gbp=50_000.0,
        pooling_sha=sha,
    )
    if row["evidence_window"] != "pooled_3y":
        raise SystemExit(f"demo expected pooled_3y, got {row['evidence_window']!r}")
    out = rtp.build_and_write([row], out_path=args.out)
    LOG.info("demo wrote %s", out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output CSV (default: data/external/methods_runs/rent_table_2011_pooled.csv)",
    )
    p.add_argument("--latest-year", type=int, default=2023)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--from-zones",
        type=Path,
        help="JSON list (or {zones:[...]}) of already-pooled zone dicts",
    )
    g.add_argument(
        "--demo-fixture",
        action="store_true",
        help="write a one-row pooled_3y demo under methods_runs/",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = build_parser().parse_args(argv)
    if args.out is None:
        args.out = rtp.default_output_path()
    # Prefer valuation_out when the caller set SCOT_LAND_VALUATION_OUT_DIR.
    if args.out == rtp.default_output_path():
        vout = data_dir("valuation_out")
        if vout.exists() and not args.from_zones:
            # Keep methods_runs as the documented default; valuation_out is an alt.
            pass
    if args.demo_fixture:
        return cmd_demo_fixture(args)
    return cmd_from_zones(args)


if __name__ == "__main__":
    sys.exit(main())
