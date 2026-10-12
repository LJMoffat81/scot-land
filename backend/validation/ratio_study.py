"""Compare primary residual AGR to sales-extraction cross-check (research).

Not a full IAAO ratio study until production sales exist; provides the
professional structure and Ward 18 / point-sample reporting.
"""

from __future__ import annotations

from statistics import mean, median
from typing import Any

from agr.service import ValuationService
from spatial.grid import snap_to_w3w_grid


def ratio_study_points(
    points: list[tuple[float, float]],
    *,
    service: ValuationService | None = None,
    scenario: str = "full_agr",
) -> dict[str, Any]:
    service = service or ValuationService.default()
    rows: list[dict[str, Any]] = []

    for lat, lng in points:
        square = snap_to_w3w_grid(lat, lng)
        breakdown = service.assess_square(square, scenario=scenario)
        sales = service.sales_context(square.lat, square.lng)
        cr = (sales or {}).get("comp_report") or {}

        residual_psqm = breakdown.site_rental_per_sqm_gbp
        comps_psqm = cr.get("median_annual_rent_per_sqm_gbp")
        ratio = None
        if comps_psqm and comps_psqm > 0:
            ratio = residual_psqm / comps_psqm

        rows.append(
            {
                "lat": square.lat,
                "lng": square.lng,
                "residual_annual_rent_per_sqm_gbp": residual_psqm,
                "residual_cell_agr_gbp": breakdown.annual_ground_rent_gbp,
                "comps_median_annual_rent_per_sqm_gbp": comps_psqm,
                "residual_to_comps_ratio": round(ratio, 4) if ratio is not None else None,
                "comps_sample_count": cr.get("sample_count"),
                "comps_synthetic_count": cr.get("synthetic_count"),
                "comps_production_ready": cr.get("production_ready"),
                "confidence": breakdown.confidence,
                "method": breakdown.method,
            }
        )

    ratios = [r["residual_to_comps_ratio"] for r in rows if r["residual_to_comps_ratio"] is not None]
    return {
        "scenario": scenario,
        "samples": len(rows),
        "ratios_available": len(ratios),
        "ratio_median": round(median(ratios), 4) if ratios else None,
        "ratio_mean": round(mean(ratios), 4) if ratios else None,
        "interpretation": (
            "Ratio = residual £/m² annual rent ÷ sales-comp extraction £/m². "
            "Values near 1.0 indicate agreement. Synthetic sales invalidate production use."
        ),
        "production_ready": all(r.get("comps_production_ready") for r in rows) and bool(ratios),
        "rows": rows,
    }
