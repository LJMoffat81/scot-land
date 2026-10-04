#!/usr/bin/env python3
"""IAAO-style ratio of the engine's typical home to each council's house price.

Reported only. The script reads the engine and writes a CSV. It does not
change a config, a council file, or a live figure.

The typical home is the engine's coded residual: land value of the notional
plot plus depreciated rebuild cost of the typical dwelling. Councils whose
map rent is the farmland rate still get that home sum here, because the
comparison is with the council's average house price.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from agr.areas import CouncilArea, _load_councils  # noqa: E402
from agr.config import load_config  # noqa: E402
from agr.valuation import _urban_residual_drc  # noqa: E402

OUT = ROOT / "reports" / "ratio_study.csv"
NOTE = "needs sale-level data"
FIELDS = (
    "council_code",
    "name",
    "ratio",
    "pass_0_90_1_10",
    "cod",
    "prd",
    "note",
)


def build_rows() -> list[dict[str, str]]:
    config = load_config()
    rows: list[dict[str, str]] = []
    for raw in _load_councils():
        council = CouncilArea(
            code=raw["code"],
            name=raw["name"],
            average_price_gbp=int(raw["average_price_gbp"]),
            annual_change_pct=raw.get("annual_change_pct"),
            rural=bool(raw["rural"]),
            distance_km=0.0,
            lookup_method="boundary",
        )
        assessment = _urban_residual_drc(council, config, None)
        land = float(assessment.site_capital_market_gbp or 0.0)
        rebuild = float(assessment.drc_improvements_gbp or 0.0)
        price = float(council.average_price_gbp)
        ratio = (land + rebuild) / price if price else None
        passed = ratio is not None and 0.90 <= ratio <= 1.10
        rows.append(
            {
                "council_code": council.code,
                "name": council.name,
                "ratio": "" if ratio is None else f"{ratio:.6f}",
                "pass_0_90_1_10": "true" if passed else "false",
                "cod": "",
                "prd": "",
                "note": NOTE,
            }
        )
    rows.sort(key=lambda row: row["name"])
    return rows


def write_report(path: Path | None = None) -> Path:
    destination = path or OUT
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(build_rows())
    return destination


def main() -> None:
    write_report()


if __name__ == "__main__":
    main()
