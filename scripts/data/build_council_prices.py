"""Replace each council's town market value with the indexed 2023 median.

Reads the pinned data-zone price file and the UK HPI council slice, and writes
average_price_gbp on data/processed/councils.json. Rural flags and the Scotland
HPI index used by the farmland path are left as they are.

    python backend/scripts/build_council_prices.py

Price = 2023 council median x (that council's April 2025 Index / the mean of
its 12 monthly Index values in 2023). The join is on AreaCode. The result is
rounded to whole pounds. Glasgow City is 187858 and Highland is 209114.
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COUNCILS_PATH = REPO / "data" / "processed" / "councils.json"
DZ_PRICES_PATH = REPO / "data" / "processed" / "dz2011_prices.csv"
HPI_PATH = REPO / "data" / "processed" / "council_hpi.csv"

PRICE_BASIS = "council_median_2023_indexed_2025-04-01"
PRICE_YEAR = 2023
SALE_YEAR = 2023
APRIL_2025 = "01/04/2025"

# Engine reference values (job 034). A mismatch means the inputs or the rounding moved.
REFERENCE = {
    "S12000049": 187_858,  # Glasgow City
    "S12000017": 209_114,  # Highland
}


def _round_pounds(value: float) -> int:
    """Whole pounds. Half rounds to even, which is what hits the reference prices."""
    return round(value)


def council_medians_2023(path: Path = DZ_PRICES_PATH) -> dict[str, float]:
    found: dict[str, set[str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            found.setdefault(row["council"], set()).add(row["ca_med2023"])
    medians: dict[str, float] = {}
    for code, values in found.items():
        if len(values) != 1 or "" in values:
            raise SystemExit(f"{code} has no single 2023 council median: {values}")
        medians[code] = float(next(iter(values)))
    return medians


def _month_key(year: int, month: int) -> str:
    return f"01/{month:02d}/{year}"


def index_factors(path: Path = HPI_PATH) -> dict[str, float]:
    series: dict[str, dict[str, float]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            series.setdefault(row["AreaCode"], {})[row["Date"]] = float(row["Index"])
    factors: dict[str, float] = {}
    year_keys = [_month_key(SALE_YEAR, month) for month in range(1, 13)]
    for code, points in series.items():
        if APRIL_2025 not in points or any(key not in points for key in year_keys):
            raise SystemExit(f"{code} is missing April 2025 or a 2023 month in {path.name}")
        mean = statistics.fmean(points[key] for key in year_keys)
        factors[code] = points[APRIL_2025] / mean
    return factors


def indexed_council_prices(
    dz_path: Path = DZ_PRICES_PATH,
    hpi_path: Path = HPI_PATH,
) -> dict[str, int]:
    medians = council_medians_2023(dz_path)
    factors = index_factors(hpi_path)
    missing = set(medians) ^ set(factors)
    if missing:
        raise SystemExit(f"council codes differ between price file and HPI slice: {sorted(missing)}")
    prices = {
        code: _round_pounds(medians[code] * factors[code])
        for code in medians
    }
    for code, expected in REFERENCE.items():
        if prices.get(code) != expected:
            raise SystemExit(f"{code} indexed to {prices.get(code)}, reference is {expected}")
    return prices


def apply_prices(payload: dict, prices: dict[str, int]) -> dict:
    """Set the town market value. Do not recompute rural and do not touch scotland_hpi_index."""
    for council in payload["councils"]:
        code = council["code"]
        if code not in prices:
            raise SystemExit(f"no indexed price for {code}")
        council["average_price_gbp"] = prices[code]
        council["price_basis"] = PRICE_BASIS
        council["price_year_basis"] = PRICE_YEAR
    return payload


def main() -> None:
    prices = indexed_council_prices()
    payload = json.loads(COUNCILS_PATH.read_text(encoding="utf-8"))
    apply_prices(payload, prices)
    COUNCILS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(prices)} council prices to {COUNCILS_PATH}")


if __name__ == "__main__":
    main()
