"""Natural capital ledger catalog: rows, checks, excluded, benchmarks, zone grain."""

from __future__ import annotations

from fastapi.testclient import TestClient

from georgist.ledger import (
    CHECK_ORDER,
    C_CAP_RATIO,
    ECONOMIC_RULES_APPROVED,
    ROW_ORDER,
    ledger_catalog,
    ledger_rows,
    ledger_totals_policy,
    ledger_zone_payload,
)


def _app(monkeypatch):
    from api.main import create_app

    monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    return create_app()


def test_ledger_catalog_shape():
    payload = ledger_catalog()
    assert payload["kind"] == "natural_capital_ledger"
    assert payload["version"] == 2
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


def test_ledger_rows_1_to_10_and_nested_1a():
    rows = ledger_rows()
    assert [r["id"] for r in rows] == list(ROW_ORDER)
    by_id = {r["id"]: r for r in rows}
    required = ("status", "tag", "source", "licence", "vintage", "coverage_pct", "range")
    for row in rows:
        for key in required:
            assert key in row
        assert row["tag"] in ("market", "proxy", "shadow", "reported")
        assert row["status"] in ("counted", "partial", "not_yet", "excluded")
        if row["status"] == "not_yet":
            assert row["range"] is None  # never £0 for not_yet
    assert by_id["1a"]["nested_under"] == "1"
    assert by_id["1a"]["never_added"] is True
    assert by_id["9"]["outside_scottish_total"] is True
    assert by_id["9"]["stack"] == "outside"
    assert by_id["5"]["stack"] == "shadow"
    assert by_id["7"]["status"] == "not_yet" and by_id["7"]["range"] is None
    assert ECONOMIC_RULES_APPROVED is False
    catalog = ledger_catalog()
    assert catalog["economic_rules"]["modelled_agr_gbp_public"] is False
    assert all(r.get("range") is None for r in catalog["rows"] if r["status"] == "not_yet")


def test_ledger_totals_headline_shadow_outside():
    totals = ledger_totals_policy()
    assert totals["headline"]["tiers"] == ["market", "proxy"]
    assert totals["headline"]["status"] == "not_yet"
    assert totals["headline"]["range"] is None
    assert "1a" not in totals["headline"]["row_ids"]
    assert totals["shadow"]["never_summed_into_headline"] is True
    assert totals["shadow"]["status"] == "not_yet"
    assert totals["shadow"]["range"] is None
    assert "9" in totals["outside"]["oil_gas"]["row_ids"]
    assert totals["outside"]["benchmarks"] == "benchmark only, not inputs"
    # Shadow rows must not appear in headline ids
    assert not set(totals["shadow"]["row_ids"]) & set(totals["headline"]["row_ids"])
    assert "9" not in totals["headline"]["row_ids"]
    assert "9" not in totals["shadow"]["row_ids"]


def test_ledger_run_hashes_stable():
    a = ledger_catalog()
    b = ledger_catalog()
    assert [c["run_hash"] for c in a["checks"]] == [c["run_hash"] for c in b["checks"]]


def test_blocked_zone_publishes_nothing():
    payload = ledger_zone_payload(
        "S01008677",
        zone_status={
            "code": "S01008677",
            "vintage": 2011,
            "publication_status": "blocked",
            "publish_level": "public_zone",
            "quality": "derived",
        },
    )
    assert payload["published"] is False
    assert payload["rows"] == []
    assert payload["totals"] is None
    assert payload["checks"] == []
    assert "0" not in str(payload.get("totals"))
    assert payload["zone"]["publication_status"] == "blocked"


def test_ok_zone_returns_rows_without_modelled_pounds():
    payload = ledger_zone_payload(
        "S01008677",
        zone_status={
            "code": "S01008677",
            "vintage": 2011,
            "publication_status": "ok",
            "publish_level": "public_zone",
            "quality": "derived",
        },
    )
    assert payload["published"] is True
    assert [r["id"] for r in payload["rows"]] == list(ROW_ORDER)
    assert payload["totals"]["headline"]["range"] is None
    assert all(
        r["range"] is None for r in payload["rows"] if r["status"] in ("not_yet", "partial")
    )


def test_api_ledger_json(monkeypatch):
    client = TestClient(_app(monkeypatch))
    response = client.get("/api/ledger.json")
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "natural_capital_ledger"
    assert body["version"] == 2
    assert [r["id"] for r in body["rows"]] == list(ROW_ORDER)
    assert len(body["checks"]) == len(CHECK_ORDER)
    assert body["checks"][0]["id"] == "C-hectare"
    assert body["checks"][-1]["id"] == "C-cap"
    assert body["benchmark_label"] == "benchmark only, not inputs"
    assert body["totals"]["shadow"]["never_summed_into_headline"] is True
    assert "stamp" in body
    assert "layers" not in body


def test_api_ledger_zone_blocked(monkeypatch):
    monkeypatch.setattr(
        "georgist.ledger._zone_surface_status",
        lambda code, vintage: {
            "code": code,
            "vintage": vintage,
            "publication_status": "blocked",
            "publish_level": "public_zone",
            "quality": "derived",
        },
    )
    client = TestClient(_app(monkeypatch))
    response = client.get("/api/ledger.json", params={"zone_id": "S01008677"})
    assert response.status_code == 200
    body = response.json()
    assert body["published"] is False
    assert body["rows"] == []
    assert body["totals"] is None


def test_api_ledger_zone_invalid(monkeypatch):
    client = TestClient(_app(monkeypatch))
    response = client.get("/api/ledger.json", params={"zone_id": "unknown"})
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_zone_id"
