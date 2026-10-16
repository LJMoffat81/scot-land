#!/usr/bin/env python3
"""Write v1.4 depreciated replacement cost per DZ2011.

Each zone is valued with ``surface_costs`` inputs through ``zone_drc_v14``.
``depreciation.method`` must be ``straight_line_v14``. A zone with no age mix
uses the frozen 0.762 remaining factor. No price column is read.

Usage (from ``backend/``)::

    python -m scripts.build_v14_drc --drc-json /tmp/drc.json --components components.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from georgist import surface_costs as sc
from georgist import surface_rent as sr
from georgist.v14_primary_inputs import (
    DepreciationMethodError,
    remaining_factor_at_age,
    v14_depreciation,
    zone_drc_v14,
)


def assert_straight_line_v14(depreciation: dict | None = None) -> dict:
    """Return v1.4 depreciation, or raise when the method is anything else."""
    if depreciation is not None and str(depreciation.get("method")) != "straight_line_v14":
        method = depreciation.get("method")
        raise DepreciationMethodError(
            f"depreciation.method must be straight_line_v14, got {method!r}"
        )
    return v14_depreciation()


def remaining_factors(depreciation: dict | None = None) -> dict[str, float]:
    """Remaining factor at 0, 20, 68 and 100 years."""
    dep = assert_straight_line_v14(depreciation)
    return {str(age): remaining_factor_at_age(age, dep) for age in (0, 20, 68, 100)}


def _has_age_mix(epc_row: dict | None) -> bool:
    if not epc_row:
        return False
    return any(
        "age_" in str(key) and str(key).endswith("_share") and float(epc_row[key] or 0) > 0
        for key in epc_row
    )


def drc_for_zone(
    *,
    code: str,
    epc_row: dict | None,
    nrs2017_row: dict | None,
    estate_row: dict | None,
    cfg: dict | None = None,
    valuation_year: int = 2025,
) -> dict:
    """One DZ2011 zone via ``zone_drc_v14`` after the method assert."""
    loaded = cfg if cfg is not None else sr.load_config()
    dep = assert_straight_line_v14()
    defaults = sc.agr_aligned_defaults(loaded)
    band = sr.rebuild_band(loaded, sr.rebuild_price_base_year(loaded))
    central = zone_drc_v14(
        code=code,
        epc_row=epc_row,
        nrs2017_row=nrs2017_row,
        estate_row=estate_row,
        cfg=loaded,
        band=band,
        valuation_year=valuation_year,
        defaults=defaults,
    )
    if not _has_age_mix(epc_row):
        frozen = sr.no_age_mix_remaining_factor(dep)
        if central.remaining_factor != frozen:
            raise DepreciationMethodError("no-age-mix zone did not use the frozen remaining factor")
    return {"dz2011": code, "remaining_factor": central.remaining_factor, "drc": central.drc_gbp}


def write_drc_json(path: Path, rows: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def drc_map_from_components(components: list[dict], cfg: dict | None = None) -> dict[str, float]:
    """Value each component with surface-cost defaults and ``zone_drc_v14``."""
    out: dict[str, float] = {}
    for row in components:
        valued = drc_for_zone(
            code=str(row["dz2011"]),
            epc_row=row.get("epc_row"),
            nrs2017_row=row.get("nrs2017_row"),
            estate_row=row.get("estate_row"),
            cfg=cfg,
        )
        out[str(row["dz2011"])] = float(valued["drc"])
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drc-json", type=Path, required=True)
    parser.add_argument("--components", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        factors = remaining_factors()
        if factors["0"] != 1.0:
            raise DepreciationMethodError("age 0 remaining factor is not 1")
        if args.components is None:
            raise DepreciationMethodError("pass --components")
        components = json.loads(args.components.read_text(encoding="utf-8"))
        payload = drc_map_from_components(list(components))
        write_drc_json(args.drc_json, payload)
    except (DepreciationMethodError, FileNotFoundError, ValueError, KeyError) as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stdout.write(f"zones={len(payload)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
