"""Data Zone HPI / SIMD / population density context metrics."""

from __future__ import annotations

from pathlib import Path

from layers.dz_context import (
    METRIC_DEFS,
    build_metrics_payload,
    catalog_layers,
    load_metrics_rows,
    metrics_for_zone,
)
from layers.platform import platform_catalog

REPO = Path(__file__).resolve().parents[2]
CSV = REPO / "data" / "processed" / "gis" / "dz_context_metrics.csv"


def test_metrics_csv_staged():
    assert CSV.exists(), "run etl/gis/build_dz_context_metrics.py"
    rows = load_metrics_rows()
    assert len(rows) == 14368
    sample = metrics_for_zone("S01006506", 2011)
    assert sample is not None
    assert sample["population"] == 984
    assert sample["simd_decile"] == 7
    assert sample["population_density_per_km2"] is not None
    assert sample["average_price_gbp"] is not None


def test_payload_has_no_agr_fields():
    payload = build_metrics_payload(vintage=2011, include_geometry=False)
    assert payload["meta"]["geometry_status"] == "pending_boundaries"
    assert payload["meta"]["licence"] == "OGL v3.0"
    assert "sources" in payload["meta"]
    for key in ("simd", "population", "hpi_council", "ros_house_prices"):
        assert payload["meta"]["sources"][key]["url"]
        assert "OGL" in payload["meta"]["sources"][key]["licence"]
    forbidden = (
        "annual_ground_rent",
        "agr_",
        "site_rental",
        "net_contribution",
        "gross_plot",
    )
    for feat in payload["features"][:20]:
        props = feat["properties"]
        joined = " ".join(str(k) for k in props)
        for needle in forbidden:
            assert needle not in joined
        assert feat["geometry"] is None


def test_catalog_layers_live_with_sources():
    layers = {row["id"]: row for row in catalog_layers()}
    assert set(layers) == {"dz_house_price", "dz_simd", "dz_pop_density"}
    for row in layers.values():
        assert row["status"] == "live"
        assert row["endpoint"] == "/layers/open/dz-context"
        assert row["licence"] == "OGL v3.0"
        assert row["source_url"]
        assert row["ledger_role"] == "ledger-frame"
        assert row["ledger_row"] == "1"
        assert row["ui_surface"] == "ledger"
    catalog_ids = {row["id"] for row in platform_catalog()["layers"]}
    assert {"dz_house_price", "dz_simd", "dz_pop_density"} <= catalog_ids


def test_metric_defs_cover_three_lenses():
    assert set(METRIC_DEFS) == {"house_price", "simd", "pop_density"}
