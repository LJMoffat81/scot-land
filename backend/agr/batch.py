"""Batch assessment for professional mini-roll exports."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agr.export_stamp import current_stamp, stamp_comment
from agr.service import ValuationService
from spatial.grid import snap_to_w3w_grid


def assess_points(
    points: Iterable[tuple[float, float]],
    *,
    scenario: str = "full_agr",
    service: ValuationService | None = None,
    include_sales: bool = False,
) -> list[dict[str, Any]]:
    service = service or ValuationService.default()
    rows: list[dict[str, Any]] = []
    for lat, lng in points:
        square = snap_to_w3w_grid(lat, lng)
        breakdown = service.assess_square(square, scenario=scenario)
        row: dict[str, Any] = {
            "lat": square.lat,
            "lng": square.lng,
            "area_sqm": square.area_sqm,
            "scenario": scenario,
            "annual_ground_rent_gbp": breakdown.annual_ground_rent_gbp,
            "economic_annual_rent_gbp": breakdown.economic_annual_rent_gbp,
            "roll_notional_plot_gbp": breakdown.roll_annual_rent_notional_plot_gbp,
            "site_rental_per_sqm_gbp": breakdown.site_rental_per_sqm_gbp,
            "site_capital_economic_per_sqm_gbp": breakdown.despeculated_site_capital_per_sqm_gbp,
            "yield_rate": breakdown.yield_rate,
            "method": breakdown.method,
            "confidence": breakdown.confidence,
            "habu": breakdown.habu,
            "council_code": breakdown.council_code,
            "council_name": breakdown.council_name,
            "ward_name": breakdown.ward_name,
            "parcel_id": breakdown.parcel_id,
        }
        if include_sales:
            ctx = service.sales_context(square.lat, square.lng, limit=5)
            cr = ctx.get("comp_report") or {}
            row["comps_median_rent_per_sqm"] = cr.get("median_annual_rent_per_sqm_gbp")
            row["comps_sample_count"] = cr.get("sample_count")
            row["comps_production_ready"] = cr.get("production_ready")
        rows.append(row)
    return rows


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"stamp": current_stamp()}, ensure_ascii=False) + "\n")
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    comment = stamp_comment(current_stamp()) + "\n"
    if not rows:
        path.write_text(comment, encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(comment)
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def batch_meta(rows: list[dict[str, Any]], *, scenario: str) -> dict[str, Any]:
    rents = [r["annual_ground_rent_gbp"] for r in rows]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario,
        "count": len(rows),
        "agr_min_gbp": min(rents) if rents else None,
        "agr_max_gbp": max(rents) if rents else None,
        "agr_mean_gbp": round(sum(rents) / len(rents), 2) if rents else None,
        "status": "research_estimate",
        "not_statutory": True,
        "stamp": current_stamp(),
    }
