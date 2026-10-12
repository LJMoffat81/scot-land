"""Tax scenario tools: internal-only, blocked, £ at Data Zone only; yield from shared config."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from georgist.surface_settings import yield_placeholder
from georgist.tax_scenarios import (
    BLOCKED_REASON,
    CAPTURE_NOTE,
    DISCLAIMER,
    INTERNAL_WARNING,
    LENS,
    MONEY_GRAIN,
    POLICY_CONFIG,
    PUBLICATION_STATUS,
    TaxScenarioError,
    ZoneRentRow,
    aggregate_by_council,
    assert_no_aggregate_gbp,
    illustrated_collection,
    parse_capture_rate,
    stamp_blocked,
    zone_illustration,
    zone_row_from_db,
)

API_DIR = Path(__file__).resolve().parents[2] / "api"
PUBLIC_TAX_PATHS = ("/georgist/tax-scenario", "/georgist/tax-scenario/zone")
INTERNAL_TAX_PATHS = (
    "/internal/georgist/tax-scenario",
    "/internal/georgist/tax-scenario/zone",
)
FRONTEND_ROOT = Path(__file__).resolve().parents[3] / "frontend"
GBP_KEYS = ("measured_rent_total_gbp", "illustrated_collection_gbp", "measured_rent_gbp")


def _row(
    code: str = "S01008677",
    la_code: str = "S12000036",
    la_name: str = "City of Edinburgh",
    rent: float = 100_000.0,
    price_year: int = 2025,
) -> ZoneRentRow:
    return ZoneRentRow(
        code=code,
        vintage=2011,
        la_code=la_code,
        la_name=la_name,
        measured_rent=rent,
        price_year=price_year,
    )


def _internal_client(monkeypatch, *, enabled=True, token: str | None = "test-secret-token"):
    from fastapi.testclient import TestClient

    from api.main import create_app

    if enabled:
        monkeypatch.setenv("ENABLE_INTERNAL_ENDPOINTS", "1")
    else:
        monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
    if token is None:
        monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("INTERNAL_API_TOKEN", token)
    return TestClient(create_app())


def test_parse_capture_rate_bounds():
    assert parse_capture_rate(0) == 0.0
    assert parse_capture_rate("0.5") == 0.5
    assert parse_capture_rate(1) == 1.0
    with pytest.raises(TaxScenarioError) as exc:
        parse_capture_rate(1.01)
    assert exc.value.code == "invalid_capture_rate"


def test_illustrated_collection_is_product():
    assert illustrated_collection(100_000.0, 0.25) == 25_000.0


def test_aggregate_money_is_data_zone_only_not_council_sums():
    rows = [
        _row("S01008677", rent=100_000.0),
        _row("S01008678", rent=50_000.0),
        _row("S01009000", la_code="S12000049", la_name="Glasgow City", rent=200_000.0),
    ]
    out = aggregate_by_council(rows, capture_rate=0.5)
    assert out["lens"] == LENS
    assert out["disclaimer"] == DISCLAIMER
    assert out["capture_note"] == CAPTURE_NOTE
    assert out["publication_status"] == PUBLICATION_STATUS == "blocked"
    assert out["internal"] is True
    assert out["money_grain"] == MONEY_GRAIN == "data_zone"
    assert "surface.yaml" in out["blocked_reason"]
    assert "hardcode" in out["blocked_reason"]
    shared = yield_placeholder()
    assert out["yield_placeholder"]["status"] == "placeholder"
    assert out["yield_placeholder"]["land_yield"] == shared["land_yield"]
    assert out["yield_placeholder"]["owner"] == "Valuation"
    assert out["yield_placeholder"]["source"] == "data/config/surface.yaml yield.land_yield"
    assert "PLACEHOLDER" in out["yield_placeholder"]["note"]
    assert out["warning"] == INTERNAL_WARNING
    assert out["policy_config"]["status"] == "not_finalised"
    assert out["policy_config"]["owner"] == "Georgist"
    assert out["policy_config"]["separate_from_measured_land_values"] is True
    assert set(out["policy_config"]["topics"]) == {
        "rates", "exemptions", "phase_in", "revenue_sharing",
    }
    # Policy knobs must not be folded into measured rent fields
    assert "exemptions" not in out["by_zone"][0]
    assert "phase_in" not in out["by_zone"][0]
    assert "revenue_sharing" not in out["by_zone"][0]

    # National / council: counts only — no £
    assert out["national"]["zone_count"] == 3
    for key in GBP_KEYS:
        assert key not in out["national"]
    for c in out["by_council"]:
        for key in GBP_KEYS:
            assert key not in c
        assert c["zone_count"] >= 1
        assert c["zone_codes"]

    # £ only on by_zone (Data Zone grain)
    by_code = {z["code"]: z for z in out["by_zone"]}
    assert by_code["S01008677"]["illustrated_collection_gbp"] == 50_000.0
    assert by_code["S01008677"]["measured_rent_gbp"] == 100_000.0
    assert by_code["S01008677"]["money_grain"] == "data_zone"
    assert by_code["S01008677"]["yield_placeholder"]["land_yield"] == shared["land_yield"]
    assert_no_aggregate_gbp(out)


def test_zone_illustration_gbp_on_zone_only():
    z = _row(rent=25_000.0)
    out = zone_illustration(z, capture_rate=0.2, council_zone_count=4)
    assert out["zone"]["illustrated_collection_gbp"] == 5_000.0
    assert out["zone"]["measured_rent_gbp"] == 25_000.0
    assert out["publication_status"] == "blocked"
    assert out["money_grain"] == "data_zone"
    assert out["yield_placeholder"] == yield_placeholder()
    for key in GBP_KEYS:
        assert key not in out["council"]
    assert out["council"]["zone_count"] == 4
    assert "share_of_council_measured_rent" not in out["zone"]
    assert_no_aggregate_gbp(out)


def test_assert_no_aggregate_gbp_refuses_council_money():
    with pytest.raises(TaxScenarioError) as exc:
        assert_no_aggregate_gbp({"council": {"illustrated_collection_gbp": 1.0}})
    assert exc.value.code == "aggregate_gbp_forbidden"


def test_stamp_blocked_includes_yield_placeholder_and_policy_config():
    stamped = stamp_blocked({"national": {}, "by_council": [{"la_code": "S"}]})
    assert stamped["publication_status"] == "blocked"
    assert stamped["yield_placeholder"] == yield_placeholder()
    assert "yield_calibration_pending" in stamped["blocked_reason"]
    assert BLOCKED_REASON == stamped["blocked_reason"]
    assert stamped["policy_config"] == POLICY_CONFIG
    assert stamped["policy_config"]["status"] == "not_finalised"
    assert "not finalised" in CAPTURE_NOTE.lower() or "not finalised" in POLICY_CONFIG["note"].lower()


def test_tax_scenarios_does_not_hardcode_land_yield():
    """Defer to shared surface.yaml; do not embed a numeric yield rate in this module."""
    src = (API_DIR.parent / "georgist" / "tax_scenarios.py").read_text(encoding="utf-8")
    assert "land_yield\": 0.05" not in src
    assert "land_yield\": 0.0399" not in src
    assert '"land_yield": 0.05' not in src
    assert "configured 5%" not in src
    assert "yield_placeholder" in src and "from georgist.surface_settings import yield_placeholder" in src


def test_yield_placeholder_reads_shared_config_and_optional_band():
    from georgist.surface_settings import yield_placeholder as yp_fn

    base = yp_fn()
    assert base["status"] == "placeholder" and base["owner"] == "Valuation"
    assert isinstance(base["land_yield"], float) and base["land_yield"] > 0
    # Live shared config may still be the pre-calibration figure until Valuation's PR lands.
    assert "result_hash" not in base or isinstance(base.get("result_hash"), str)
    # Optional Georgist/Valuation metadata: pass through when published; never invent.
    with_meta = yp_fn({
        "yield": {
            "land_yield": 0.0399,
            "land_yield_band": [0.0352, 0.0450],
            "clipped_at_cap": True,
            "result_hash": "b3442d47",
            "components": {"r": 0.0262, "p": 0.0237, "g": 0.01},
        },
    })
    assert with_meta["land_yield"] == pytest.approx(0.0399)
    assert with_meta["land_yield_band"] == [0.0352, 0.0450]
    assert with_meta["clipped_at_cap"] is True
    assert with_meta["result_hash"] == "b3442d47"
    assert with_meta["status"] == "placeholder"


def test_aggregate_refuses_mixed_price_years():
    rows = [_row(price_year=2025), _row("S01008678", price_year=2024)]
    with pytest.raises(TaxScenarioError) as exc:
        aggregate_by_council(rows, capture_rate=1.0)
    assert exc.value.code == "mixed_price_years"


def test_aggregate_la_filter():
    rows = [
        _row(rent=10_000.0),
        _row("S01009000", la_code="S12000049", la_name="Glasgow City", rent=99_000.0),
    ]
    out = aggregate_by_council(rows, capture_rate=1.0, la_code="S12000036")
    assert out["national"]["zone_count"] == 1
    assert len(out["by_zone"]) == 1
    assert out["by_zone"][0]["measured_rent_gbp"] == 10_000.0


def test_zone_row_from_db_filters_unpublishable_and_zero_dwellings():
    base = {
        "code": "S01008677",
        "vintage": 2011,
        "measured_rent": 12_000.0,
        "price_year": 2025,
        "quality": "derived",
        "publish_level": "public_zone",
        "publication_status": "ok",
        "la_code": "S12000036",
        "la_name": "City of Edinburgh",
        "flags": "",
    }
    assert zone_row_from_db(base) is not None
    assert zone_row_from_db({**base, "quality": "placeholder"}) is None
    assert zone_row_from_db({**base, "flags": "zero_dwellings"}) is None


def test_public_tax_scenario_paths_absent_from_default_app():
    from api.main import app, registered_routes

    paths = {p for _, p in registered_routes(app)}
    for path in PUBLIC_TAX_PATHS:
        assert path not in paths
    for path in INTERNAL_TAX_PATHS:
        assert path not in paths


def test_public_tax_scenario_paths_not_declared_as_public_layers():
    from georgist import publication_rules as pr

    for path in PUBLIC_TAX_PATHS:
        assert path not in pr.PUBLIC_ROUTE_RULES
    assert pr.undeclared(list(INTERNAL_TAX_PATHS)) == []


def test_wealth_routes_source_has_no_tax_scenario_decorators():
    tree = ast.parse((API_DIR / "wealth_routes.py").read_text(encoding="utf-8"))
    decorated = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                    and isinstance(dec.args[0].value, str)
                    and "tax-scenario" in dec.args[0].value
                ):
                    decorated.append(dec.args[0].value)
    assert decorated == []


def test_internal_tax_routes_registered_when_enabled(monkeypatch):
    from api.main import registered_routes

    c = _internal_client(monkeypatch, enabled=True, token="tok")
    paths = {p for _, p in registered_routes(c.app)}
    for path in INTERNAL_TAX_PATHS:
        assert path in paths
    for path in PUBLIC_TAX_PATHS:
        assert path not in paths


def test_public_paths_404_even_when_internal_enabled(monkeypatch):
    c = _internal_client(monkeypatch, enabled=True, token="tok")
    for path in PUBLIC_TAX_PATHS:
        r = c.get(path, headers={"Authorization": "Bearer tok"})
        assert r.status_code == 404, path


def test_internal_tax_scenario_requires_auth(monkeypatch):
    c = _internal_client(monkeypatch, enabled=True, token="correct")
    r = c.get("/internal/georgist/tax-scenario")
    assert r.status_code == 401


def test_internal_tax_scenario_flag_off_is_404(monkeypatch):
    c = _internal_client(monkeypatch, enabled=False, token="correct")
    assert c.get("/internal/georgist/tax-scenario", headers={"Authorization": "Bearer correct"}).status_code == 404


def test_internal_tax_scenario_503_without_db(monkeypatch):
    c = _internal_client(monkeypatch, enabled=True, token="correct")
    bad = c.get(
        "/internal/georgist/tax-scenario",
        params={"capture_rate": 2},
        headers={"Authorization": "Bearer correct"},
    )
    assert bad.status_code == 422
    r = c.get(
        "/internal/georgist/tax-scenario",
        params={"vintage": "2011", "capture_rate": 0.5},
        headers={"Authorization": "Bearer correct"},
    )
    assert r.status_code == 503


def test_internal_tax_scenario_zone_rejects_unknown_zone(monkeypatch):
    c = _internal_client(monkeypatch, enabled=True, token="correct")
    r = c.get(
        "/internal/georgist/tax-scenario/zone",
        params={"zone_id": "unknown"},
        headers={"Authorization": "Bearer correct"},
    )
    assert r.status_code == 422


def test_frontend_has_no_public_tax_scenario_panel():
    inspector = (FRONTEND_ROOT / "components" / "WealthInspector.tsx").read_text(encoding="utf-8")
    assert "TaxScenarioPanel" not in inspector
    assert not (FRONTEND_ROOT / "components" / "TaxScenarioPanel.tsx").exists()
    wealth_api = (FRONTEND_ROOT / "lib" / "useWealthApi.ts").read_text(encoding="utf-8")
    assert "/georgist/tax-scenario" not in wealth_api
    assert "fetchTaxScenario" not in wealth_api
