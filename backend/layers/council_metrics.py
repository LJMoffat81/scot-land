"""
Multi-metric council choropleth for the AGR map.

One assessment pass attaches every value metric (AGR, HPI, land intensity,
capture ratio, land share, method) plus open context (SIMD, population density).
The frontend switches paint property without re-fetching.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

from agr.fiscal import place_fiscal
from agr.service import ValuationService
from layers.vdl import by_council_hectares

REPO_ROOT = Path(__file__).resolve().parents[2]
BOUNDARIES = REPO_ROOT / "data" / "processed" / "scotland_councils.geojson"
CONTEXT = REPO_ROOT / "data" / "processed" / "context_by_council.json"

# Public choropleth metrics the UI may colour by
METRIC_DEFS: dict[str, dict[str, Any]] = {
    "agr_plot": {
        "property": "annual_ground_rent_plot_gbp",
        "label": "AGR (typical plot)",
        "unit": "£/year",
        "group": "value",
        "description": "Notional plot Annual Ground Rent — primary SLRG residual estimate.",
    },
    "rent_per_sqm": {
        "property": "site_rental_per_sqm_gbp",
        "label": "Land rent intensity",
        "unit": "£/m²/year",
        "group": "value",
        "description": "Economic site rent per square metre — comparable across places.",
    },
    "house_price": {
        "property": "average_price_gbp",
        "label": "House prices (HPI)",
        "unit": "£",
        "group": "value",
        "description": "UK HPI average house price by council (OGL) — market value context for residual.",
    },
    "agr_price_pct": {
        "property": "agr_as_pct_of_price",
        "label": "AGR as % of house price",
        "unit": "%",
        "group": "value",
        "description": "Plot AGR ÷ HPI average price — how large the land rent is relative to local prices.",
    },
    "land_share": {
        "property": "site_share_pct",
        "label": "Land share of value",
        "unit": "%",
        "group": "value",
        "description": "Implied residual land share of market value (MV − DRC) / MV.",
    },
    "site_capital": {
        "property": "site_capital_per_sqm_gbp",
        "label": "Site capital",
        "unit": "£/m²",
        "group": "value",
        "description": "Economic (Pickard-adjusted) site capital per m².",
    },
    "simd": {
        "property": "simd_pct_20most_deprived",
        "label": "Deprivation (SIMD)",
        "unit": "% zones in 20% most deprived",
        "group": "context",
        "description": "SIMD 2020v2 share of data zones in Scotland’s 20% most deprived — equity context.",
    },
    "pop_density": {
        "property": "population_density_per_km2",
        "label": "Population density",
        "unit": "people/km²",
        "group": "context",
        "description": "NRS population ÷ council land area — pressure on land.",
    },
    "net_contribution": {
        "property": "net_contribution_plot_gbp",
        "label": "Net fiscal position",
        "unit": "£/year net",
        "group": "fiscal",
        "description": (
            "Plot gross AGR − equal dividend − remote credit. "
            "Positive = funds the state; negative = net receiver (remote/low rent)."
        ),
    },
    "gross_liability": {
        "property": "gross_plot_liability_gbp",
        "label": "Who pays most (gross)",
        "unit": "£/year gross",
        "group": "fiscal",
        "description": "Gross plot AGR under active scenario — highest-rent places pay most.",
    },
    "vacant_residual": {
        "property": "vacant_full_agr_gbp",
        "label": "Vacant land residual",
        "unit": "£/year on SVDLS ha",
        "group": "context",
        "description": (
            "Illustrative full AGR on SVDLS vacant/derelict hectares. "
            "Survey polygons, not a bill."
        ),
    },
}


def _project_area_km2(geometry: dict) -> float:
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)

    def project(x, y, z=None):
        return transformer.transform(x, y)

    return float(transform(project, shape(geometry)).area) / 1_000_000.0


@lru_cache(maxsize=1)
def _load_context() -> dict[str, Any]:
    if not CONTEXT.exists():
        return {}
    with CONTEXT.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload.get("councils") or {}


@lru_cache(maxsize=4)
def build_council_metrics_geojson(scenario: str = "full_agr") -> dict[str, Any]:
    if not BOUNDARIES.exists():
        raise FileNotFoundError(f"Missing {BOUNDARIES}")

    with BOUNDARIES.open(encoding="utf-8") as handle:
        geo = json.load(handle)

    context = _load_context()
    vacant = by_council_hectares()
    service = ValuationService.default()
    features_out: list[dict[str, Any]] = []

    for feature in geo.get("features", []):
        props = dict(feature.get("properties") or {})
        raw_code = props.get("hpi_code") or props.get("boundary_code") or props.get("code")
        name = props.get("name") or props.get("NAME")
        geom = feature.get("geometry") or {}
        if not geom.get("coordinates"):
            continue

        try:
            ring = geom["coordinates"][0][0] if geom.get("type") == "MultiPolygon" else geom["coordinates"][0]
            clat = sum(p[1] for p in ring) / len(ring)
            clng = sum(p[0] for p in ring) / len(ring)
            area_km2 = _project_area_km2(geom)
        except Exception:
            continue

        code = str(raw_code or "")
        try:
            # Urban home plot for the council, not the class at this centroid.
            breakdown = service.assess_council_layer(code, clat, clng, scenario)
        except Exception:
            continue
        price = breakdown.average_price_gbp or breakdown.market_value_gbp
        plot = breakdown.roll_annual_rent_notional_plot_gbp
        agr_pct = None
        if price and price > 0 and plot is not None:
            agr_pct = round(100.0 * float(plot) / float(price), 3)

        site_share_pct = None
        if breakdown.site_share_used is not None:
            site_share_pct = round(100.0 * float(breakdown.site_share_used), 1)

        # Scenario-scaled plot liability + net fiscal position
        cell_full = float(breakdown.economic_annual_rent_gbp or 0)
        active_cell = float(breakdown.annual_ground_rent_gbp or 0)
        scale = (active_cell / cell_full) if cell_full > 0 else 1.0
        gross_plot = float(plot or 0) * scale
        fiscal_place = place_fiscal(
            gross_plot_gbp=gross_plot,
            council_code=code,
            scenario=scenario,
        )

        ctx = context.get(str(code)) or {}
        vdl = vacant.get(str(code)) or {"vacantHa": 0.0, "vacantSites": 0}
        vacant_ha = float(vdl["vacantHa"])
        vacant_agr = round(
            vacant_ha * 10_000.0 * float(breakdown.site_rental_per_sqm_gbp or 0),
            0,
        )
        population = ctx.get("population")
        simd = ctx.get("simd_pct_20most_deprived")
        density = None
        if population and area_km2 > 0:
            density = round(float(population) / area_km2, 1)

        features_out.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "code": code,
                    "name": breakdown.council_name or name,
                    "scenario": scenario,
                    "method": breakdown.method,
                    "rural": breakdown.method == "productive_land_use",
                    "confidence": breakdown.confidence,
                    "vacantHa": vacant_ha,
                    "vacantSites": vdl["vacantSites"],
                    "vacant_full_agr_gbp": vacant_agr,
                    # Value metrics
                    "annual_ground_rent_cell_gbp": breakdown.annual_ground_rent_gbp,
                    "annual_ground_rent_plot_gbp": plot,
                    "site_rental_per_sqm_gbp": round(float(breakdown.site_rental_per_sqm_gbp), 3),
                    "average_price_gbp": price,
                    "agr_as_pct_of_price": agr_pct,
                    "site_share_pct": site_share_pct,
                    "site_capital_per_sqm_gbp": round(
                        float(breakdown.despeculated_site_capital_per_sqm_gbp), 2
                    ),
                    "site_capital_market_per_sqm_gbp": round(
                        float(
                            breakdown.site_capital_market_per_sqm_gbp
                            or breakdown.site_capital_per_sqm_gbp
                        ),
                        2,
                    ),
                    # Fiscal metrics
                    "gross_plot_liability_gbp": fiscal_place["gross_plot_gbp"],
                    "net_contribution_plot_gbp": fiscal_place["net_gbp"],
                    "fiscal_role": fiscal_place["role"],
                    "dividend_gbp": fiscal_place["dividend_gbp"],
                    "remote_credit_gbp": fiscal_place["remote_credit_gbp"],
                    # Context metrics
                    "population": population,
                    "area_km2": round(area_km2, 1),
                    "population_density_per_km2": density,
                    "simd_pct_20most_deprived": simd,
                    "simd_note": ctx.get("simd_rank_note"),
                },
            }
        )

    def _stats(prop: str) -> dict[str, float | None]:
        vals = [
            f["properties"].get(prop)
            for f in features_out
            if f["properties"].get(prop) is not None
        ]
        if not vals:
            return {"min": None, "max": None}
        return {"min": min(vals), "max": max(vals)}

    metrics_meta = {}
    for mid, defn in METRIC_DEFS.items():
        prop = defn["property"]
        st = _stats(prop)
        metrics_meta[mid] = {**defn, **st}

    return {
        "type": "FeatureCollection",
        "features": features_out,
        "meta": {
            "layer": "council_metrics",
            "scenario": scenario,
            "feature_count": len(features_out),
            "metrics": metrics_meta,
            "status": "research_estimate",
            "note": (
                "Council-level residual at boundary centroid. "
                "HPI OGL; SIMD/population open statistics; AGR is SLRG residual research."
            ),
        },
    }


def layer_catalog() -> dict[str, Any]:
    """Machine-readable layer list for the UI."""
    return {
        "version": 1,
        "choropleth_metrics": [
            {"id": mid, **{k: v for k, v in defn.items() if k != "property"}, "property": defn["property"]}
            for mid, defn in METRIC_DEFS.items()
        ],
        "overlays": [
            {
                "id": "boundaries",
                "label": "Property boundaries",
                "type": "raster",
                "source": "ROS INSPIRE CP.CadastralParcel",
                "minzoom": 14,
                "description": "Cadastral parcel outlines (geometry only — no owners or prices).",
            },
            {
                "id": "cell_grid",
                "label": "Scot-LAND squares",
                "type": "geojson",
                "minzoom": 12,
                "description": "Viewport Scot-LAND squares with AGR (capped sample).",
            },
            {
                "id": "method",
                "label": "Valuation method",
                "type": "categorical",
                "property": "rural",
                "description": "Urban residual (MV−DRC) vs rural productive land method.",
            },
        ],
        "data_policy": {
            "portal_scraping": False,
            "owners_in_boundaries": False,
            "purchase_prices_in_boundaries": False,
            "sales": "ROS licensed extract only (scaffolded)",
        },
    }


def clear_metrics_cache() -> None:
    build_council_metrics_geojson.cache_clear()
    _load_context.cache_clear()
