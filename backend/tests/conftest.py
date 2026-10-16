"""Shared fixtures for the backend suite.

Stubs the data-zone network seam so unit tests stay offline.
PostGIS-dependent tests may skip when WEALTH_TEST_DATABASE_URL is unset.
Also provides Data Zones / surface-rent synthetic fixtures for Valuation tests.
"""

from __future__ import annotations

import os

import pytest

from layers.naturescot import clear_low_zoom_cache
from paths import PROCESSED_DIR


def pytest_configure(config):
    """CI sets WEALTH_REQUIRE_POSTGIS=1 so the PostGIS suites run rather than silently skip."""
    if os.getenv("WEALTH_REQUIRE_POSTGIS") == "1" and not os.getenv(
        "WEALTH_TEST_DATABASE_URL", ""
    ).strip():
        raise pytest.UsageError(
            "WEALTH_REQUIRE_POSTGIS=1 but WEALTH_TEST_DATABASE_URL is not set"
        )


@pytest.fixture(autouse=True)
def _offline_data_zone(monkeypatch):
    monkeypatch.setattr("agr.engine.zone_code_at", lambda lat, lng: None)


@pytest.fixture(autouse=True)
def _clear_designation_zoom_cache():
    """Each test starts cold so a cached z6 body cannot leak into the next one."""
    clear_low_zoom_cache()
    yield
    clear_low_zoom_cache()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)


@pytest.fixture(scope="session")
def datazones_root():
    """Root holding the committed `datazones/` folder (Data Zones' manifest carries attribution)."""
    if not (PROCESSED_DIR / "datazones" / "manifest.csv").is_file():
        pytest.skip("data/processed/datazones not present")
    return PROCESSED_DIR


SYNTHETIC_BAND = {  # SYNTHETIC £/m², test-only. Not a rebuild cost estimate.
    t: {"low": r * 0.8, "central": r, "high": r * 1.3}
    for t, r in {
        "detached": 2000.0,
        "semi_detached": 1800.0,
        "terraced": 1700.0,
        "flat_purpose_built": 1900.0,
        "flat_conversion": 2100.0,
        "other": 1850.0,
    }.items()
}


@pytest.fixture
def make_valuation_row():
    """Build a real `surface_rent.build_output_row` row from SYNTHETIC inputs."""
    import copy

    from georgist import surface_rent as sr

    cfg = copy.deepcopy(sr.load_config())

    def _make(
        price=250_000,
        *,
        code="S01008677",
        vintage=2011,
        fill_obs=True,
        dwellings=500,
        second_home_share=None,
        vacant_share=None,
        **over,
    ):
        mix = [sr.MixComponent("semi_detached", 1.0, 90.0, "1965-1975")]
        rbs = sr.depreciated_rebuild_band(
            mix,
            band=SYNTHETIC_BAND,
            depreciation=cfg["depreciation"],
            valuation_year=2025,
            region=1.0,
        )
        pooled = sr.PooledPrice(price, 30, "2021-2023", "mean", ("pooled_3y",), 2023)
        # SYNTHETIC index factor 2023 -> 2025 (not a real UK HPI figure)
        indexed = sr.index_price(
            pooled,
            price_year=2025,
            factor=1.05,
            series="SYNTHETIC index",
            tags=("indexed_council_hpi",),
        )
        rb = sr.residual_band(indexed.price_indexed_gbp, rbs)
        land = (
            sr.resolve_land_value(
                dwellings=dwellings,
                observed=rb.central,
                sales_n=30,
                model_gbp=None,
                n_min=5,
                n_full=15,
                shrinkage_k=8,
            )
            if fill_obs
            else sr.resolve_land_value(
                dwellings=dwellings,
                observed=None,
                sales_n=0,
                model_gbp=30_000,
                n_min=5,
                n_full=15,
                shrinkage_k=8,
            )
        )
        zy = sr.blend_zone_yield(
            {"SYN-B": 1.0}, {"SYN-B": sr.YieldCell("SYN-B", 2, 0.03, "cell")}
        )
        kw = dict(
            code=code,
            vintage=vintage,
            valuation_date="2025-04-01",
            ur6_class=2,
            ur8_class=2,
            dwellings=sr.DwellingCount(
                dwellings,
                2025,
                vintage,
                (),
                "SYNTHETIC",
                vacant_share=vacant_share,
                second_home_share=second_home_share,
            ),
            pooled=pooled,
            indexed=indexed,
            typical_sale_gbp=price * 0.9,
            rebuild_mix_basis="sold",
            rebuilds=rbs,
            band=rb,
            land=land,
            zone_yield=zy,
            gross_yield_value=0.05,
            config=cfg,
            source_id="SYNTHETIC",
            licence="synthetic-test-only",
            crosswalk_method="none",
            net_of=[],
        )
        kw.update(over)
        return sr.build_output_row(**kw)

    return _make
