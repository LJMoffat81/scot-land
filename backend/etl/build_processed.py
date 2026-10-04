"""Download UK HPI data and build data/processed/councils.json.

Run from repo root:
    cd backend && python -m etl.build_processed
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import httpx
import yaml

from etl.centroids import COUNCIL_CENTROIDS

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "data" / "config" / "sources.yaml"
CACHE_DIR = REPO_ROOT / "data" / "cache"
OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "councils.json"


def load_sources() -> dict:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _download_csv(client: httpx.Client, url: str, cache_name: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / cache_name
    response = client.get(url, timeout=60.0)
    response.raise_for_status()
    cache_path.write_text(response.text, encoding="utf-8")
    return response.text


def _latest_scotland_index(csv_text: str, scotland_code: str, period: str) -> float | None:
    reader = csv.DictReader(StringIO(csv_text))
    for row in reader:
        if row["Area_Code"] == scotland_code and row["Date"].startswith(period):
            return float(row["Index"])
    return None


def _scottish_councils_from_hpi(csv_text: str, period: str) -> list[dict]:
    reader = csv.DictReader(StringIO(csv_text))
    councils: list[dict] = []
    for row in reader:
        code = row["Area_Code"]
        if not code.startswith("S12") or not row["Date"].startswith(period):
            continue
        if code not in COUNCIL_CENTROIDS:
            continue
        lat, lng = COUNCIL_CENTROIDS[code]
        councils.append(
            {
                "code": code,
                "name": row["Region_Name"],
                "centroid": {"lat": lat, "lng": lng},
                "average_price_gbp": int(float(row["Average_Price"])),
                "annual_change_pct": float(row["Annual_Change"]) if row["Annual_Change"] else None,
            }
        )
    councils.sort(key=lambda item: item["name"])
    return councils


def build_processed_data() -> dict:
    sources = load_sources()
    hpi_cfg = sources["hpi"]
    council_cfg = sources["councils"]
    period = hpi_cfg["period"]
    base = hpi_cfg["base_url"]

    avg_url = f"{base}/{hpi_cfg['average_prices_template'].format(period=period)}"
    idx_url = f"{base}/{hpi_cfg['indices_template'].format(period=period)}"

    with httpx.Client() as client:
        avg_csv = _download_csv(client, avg_url, f"hpi_avg_{period}.csv")
        idx_csv = _download_csv(client, idx_url, f"hpi_idx_{period}.csv")

    councils = _scottish_councils_from_hpi(avg_csv, period)
    scotland_index = _latest_scotland_index(
        idx_csv, hpi_cfg["scotland_region_code"], period
    )

    rural_codes = set(council_cfg.get("rural_codes") or [])
    for council in councils:
        # Method is chosen per point. The old list is context only.
        council["rural_context"] = council["code"] in rural_codes
        council["rural"] = False

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hpi_period": period,
        "scotland_hpi_index": scotland_index,
        "sources": {
            "average_prices_url": avg_url,
            "indices_url": idx_url,
        },
        "councils": councils,
    }


def main() -> None:
    payload = build_processed_data()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(payload['councils'])} councils to {OUTPUT_PATH}")
    # Town market value is the indexed 2023 median, not this HPI average.
    # Rural flags set just above are left as they are.
    from scripts.build_council_prices import main as apply_council_prices

    apply_council_prices()


if __name__ == "__main__":
    main()