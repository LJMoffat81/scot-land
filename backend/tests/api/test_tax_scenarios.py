"""Tax scenario tools: internal-only, publication_status=blocked until yield calibration."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from georgist.tax_scenarios import (
    BLOCKED_REASON,
    CAPTURE_NOTE,
    DISCLAIMER,
    INTERNAL_WARNING,
    LENS,
    PUBLICATION_STATUS,
    TaxScenarioError,
    ZoneRentRow,
    aggregate_by_council,
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
    with pytest.raises(TaxScenarioError):
        parse_capture_rate("nope")


def test_illustrated_collection_is_product():
    assert illustrated_collection(100_000.0, 0.25) == 25_000.0
    assert illustrated_collection(80_000.0, 0.0) == 0.0


def test_aggregate_by_council_sums_and_is_blocked():
    rows = [
        _row("S01008677", rent=100_000.0),
        _row("S01008678", rent=50_000.0),
        _row("S01009000", la_code="S12000049", la_name="Glasgow City", rent=200_000.0),
    ]
    out = aggregate_by_council(rows, capture_rate=0.5)
    assert out["lens"] == LENS
    assert out["disclaimer"] == DISCLAIMER
    assert out["capture_note"] == CAPTURE_NOTE
    assert out["status"] == "experimental_research_estimate"
    assert out["publication_status"] == PUBLICATION_STATUS == "blocked"
    assert out["internal"] is True
    assert "yield_calibration_pending" in out["blocked_reason"]
    assert "5%" in out["blocked_reason"]
    assert out["warning"] == INTERNAL_WARNING
    assert out["national"]["zone_count"] == 3
    assert out["national"]["measured_rent_total_gbp"] == 350_000.0
    assert out["national"]["illustrated_collection_gbp"] == 175_000.0
    assert out["national"]["publication_status"] == "blocked"
    by_name = {c["la_name"]: c for c in out["by_council"]}
    assert by_name["City of Edinburgh"]["illustrated_collection_gbp"] == 75_000.0
    assert by_name["City of Edinburgh"]["publication_status"] == "blocked"
    assert by_name["Glasgow City"]["blocked_reason"] == BLOCKED_REASON
    assert "AGR" in out["lens_note"]


def test_zone_illustration_is_blocked():
    z = _row(rent=25_000.0)
    out = zone_illustration(z, capture_rate=0.2, council_measured_total=100_000.0, council_zone_count=4)
    assert out["zone"]["illustrated_collection_gbp"] == 5_000.0
    assert out["publication_status"] == "blocked"
    assert out["zone"]["publication_status"] == "blocked"
    assert out["council"]["publication_status"] == "blocked"
    assert out["internal"] is True


def test_stamp_blocked_idempotent_fields():
    stamped = stamp_blocked({"national": {}, "by_council": [{"la_code": "S"}]})
    assert stamped["publication_status"] == "blocked"
    assert stamped["national"]["publication_status"] == "blocked"
    assert stamped["by_council"][0]["publication_status"] == "blocked"


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
    assert out["publication_status"] == "blocked"


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
    assert zone_row_from_db({**base, "publish_level": "internal"}) is None
    assert zone_row_from_db({**base, "publication_status": "blocked"}) is None
    assert zone_row_from_db({**base, "flags": "zero_dwellings"}) is None


def test_public_tax_scenario_paths_absent_from_default_app():
    from api.main import app, registered_routes

    paths = {p for _, p in registered_routes(app)}
    for path in PUBLIC_TAX_PATHS:
        assert path not in paths
    # Internal flag off by default → internal tax routes also absent
    for path in INTERNAL_TAX_PATHS:
        assert path not in paths


def test_public_tax_scenario_paths_not_declared_as_public_layers():
    from georgist import publication_rules as pr

    for path in PUBLIC_TAX_PATHS:
        assert path not in pr.PUBLIC_ROUTE_RULES
    # /internal is exempt from public declarations
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
    assert r.json()["detail"]["error"] == "unauthorized"


def test_internal_tax_scenario_flag_off_is_404(monkeypatch):
    c = _internal_client(monkeypatch, enabled=False, token="correct")
    assert c.get("/internal/georgist/tax-scenario", headers={"Authorization": "Bearer correct"}).status_code == 404
    assert c.get(
        "/internal/georgist/tax-scenario/zone",
        params={"zone_id": "S01008677"},
        headers={"Authorization": "Bearer correct"},
    ).status_code == 404


def test_internal_tax_scenario_503_without_db_and_blocked_headers(monkeypatch):
    c = _internal_client(monkeypatch, enabled=True, token="correct")
    # Validation before DB: bad capture rate
    bad = c.get(
        "/internal/georgist/tax-scenario",
        params={"capture_rate": 2},
        headers={"Authorization": "Bearer correct"},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["error"] == "invalid_capture_rate"

    r = c.get(
        "/internal/georgist/tax-scenario",
        params={"vintage": "2011", "capture_rate": 0.5},
        headers={"Authorization": "Bearer correct"},
    )
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "wealth_database_unavailable"


def test_internal_tax_scenario_zone_rejects_unknown_zone(monkeypatch):
    c = _internal_client(monkeypatch, enabled=True, token="correct")
    r = c.get(
        "/internal/georgist/tax-scenario/zone",
        params={"zone_id": "unknown"},
        headers={"Authorization": "Bearer correct"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "invalid_zone_id"


def test_frontend_has_no_public_tax_scenario_panel():
    """Tax scenario UI must stay off public pages until yield calibration."""
    inspector = (FRONTEND_ROOT / "components" / "WealthInspector.tsx").read_text(encoding="utf-8")
    assert "TaxScenarioPanel" not in inspector
    assert not (FRONTEND_ROOT / "components" / "TaxScenarioPanel.tsx").exists()
    wealth_api = (FRONTEND_ROOT / "lib" / "useWealthApi.ts").read_text(encoding="utf-8")
    assert "/georgist/tax-scenario" not in wealth_api
    assert "fetchTaxScenario" not in wealth_api
