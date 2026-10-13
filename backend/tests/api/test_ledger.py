"""Natural capital ledger catalog: checks, excluded, benchmarks."""

from __future__ import annotations

from fastapi.testclient import TestClient

from georgist.ledger import CHECK_ORDER, C_CAP_RATIO, ledger_catalog


def _app(monkeypatch):
    from api.main import create_app

    monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    return create_app()


def test_ledger_catalog_shape():
    payload = ledger_catalog()
    assert payload["kind"] == "natural_capital_ledger"
    assert payload["benchmark_label"] == "benchmark only, not inputs"
    assert [c["id"] for c in payload["checks"]] == list(CHECK_ORDER)
    assert all(c["result"] in ("pass", "fail", "pending") for c in payload["checks"])
    assert all(len(c["run_hash"]) == 64 for c in payload["checks"])
    assert all(c["test_log"] for c in payload["checks"])
    cap = next(c for c in payload["checks"] if c["id"] == "C-cap")
    assert cap["result"] == "pass"
    assert C_CAP_RATIO == 0.494
    assert any(e["status"] == "fail" for e in cap["test_log"])
    hectare = next(c for c in payload["checks"] if c["id"] == "C-hectare")
    assert any(e["id"] == "ur6_class_2_job_access_gradient" for e in hectare["test_log"])
    assert any(e["status"] == "fail" for e in hectare["test_log"])
    assert payload["excluded"]
    assert all(e.get("reason") for e in payload["excluded"])
    labels = {b["label"] for b in payload["benchmarks"]}
    assert "Spectrum / airspace" in labels
    assert "Wightman" in labels
    assert all(b["note"] == "benchmark only, not inputs" for b in payload["benchmarks"])
    # Not a map-panel layer dump
    assert "layers" not in payload


def test_ledger_run_hashes_stable():
    a = ledger_catalog()
    b = ledger_catalog()
    assert [c["run_hash"] for c in a["checks"]] == [c["run_hash"] for c in b["checks"]]


def test_api_ledger_json(monkeypatch):
    client = TestClient(_app(monkeypatch))
    response = client.get("/api/ledger.json")
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "natural_capital_ledger"
    assert len(body["checks"]) == len(CHECK_ORDER)
    assert body["checks"][0]["id"] == "C-hectare"
    assert body["checks"][-1]["id"] == "C-cap"
    assert body["benchmark_label"] == "benchmark only, not inputs"
    assert "stamp" in body
    assert "layers" not in body
