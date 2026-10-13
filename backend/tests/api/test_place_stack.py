"""Place per-hectare stack: nested 1a, shadow separate, no public AGR £."""

from __future__ import annotations

from fastapi.testclient import TestClient

from georgist.place_stack import (
    AMOUNT_PH,
    CONSTRAINT_RULE,
    headline_sum_row_ids,
    place_hectare_stack,
    shadow_sum_row_ids,
)


def _app(monkeypatch):
    from api.main import create_app

    monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    return create_app()


def test_place_hectare_stack_nested_and_shadow_rules():
    body = place_hectare_stack("S01010264", zone_name="City Centre South")
    assert body["contract"] == "place_hectare_stack_v1"
    assert body["published"] is True
    assert body["zone"]["code"] == "S01010264"

    headline = body["headline"]
    shadow = body["shadow"]
    outside = body["outside"]
    assert headline is not None and shadow is not None and outside is not None

    h_ids = [r["id"] for r in headline["rows"]]
    assert h_ids == ["1", "1a", "2", "3", "4"]
    nested = next(r for r in headline["rows"] if r["id"] == "1a")
    assert nested["nested"] is True
    assert nested["parent_id"] == "1"
    assert nested["in_total"] is False

    sum_ids = headline["sum_row_ids"]
    assert sum_ids == ["1", "2", "3", "4"]
    assert "1a" not in sum_ids
    assert headline_sum_row_ids(headline["rows"]) == sum_ids

    s_ids = [r["id"] for r in shadow["rows"]]
    assert s_ids == ["5", "6", "7", "8", "10"]
    assert shadow["sum_row_ids"] == shadow_sum_row_ids(shadow["rows"])
    # Shadow never overlaps headline sum ids (C-totals).
    assert set(sum_ids).isdisjoint(set(shadow["sum_row_ids"]))

    oil = next(r for r in outside["rows"] if r["id"] == "9")
    assert oil["outside_scottish_total"] is True
    assert oil["in_total"] is False
    assert oil["id"] not in sum_ids
    assert oil["id"] not in shadow["sum_row_ids"]

    labels = {b["label"] for b in outside["benchmarks"]}
    assert "Spectrum / airspace" in labels
    assert "Wightman" in labels
    assert outside["benchmark_label"] == "benchmark only, not inputs"

    for c in body["constraints"]:
        assert c["rule"] == CONSTRAINT_RULE

    # Public: placeholders only — no modelled AGR £.
    for stack in (headline, shadow):
        assert stack["total_placeholder"] == AMOUNT_PH
        for row in stack["rows"]:
            assert row["amount_placeholder"] == AMOUNT_PH
            assert row["amount_gbp_per_ha"] is None
            assert "£" not in row["amount_placeholder"]
    for row in outside["rows"]:
        assert row["amount_gbp_per_ha"] is None


def test_blocked_zone_publishes_nothing():
    body = place_hectare_stack("S01008680", publication_status="blocked")
    assert body["published"] is False
    assert body["reason"] == "blocked"
    assert body["headline"] is None
    assert body["shadow"] is None
    assert body["outside"] is None
    assert body["constraints"] is None
    blob = str(body).lower()
    assert "annual_ground_rent" not in blob
    assert "plot_gbp" not in blob


def test_invalid_zone_code_raises():
    try:
        place_hectare_stack("not-a-zone")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Data Zone" in str(exc)


def test_api_place_stack_json(monkeypatch):
    monkeypatch.setattr(
        "api.platform_routes.lookup_zone_publication_status",
        lambda code: "ok",
    )
    client = TestClient(_app(monkeypatch))
    response = client.get("/api/place-stack.json", params={"zone": "S01010264"})
    assert response.status_code == 200
    body = response.json()
    assert body["contract"] == "place_hectare_stack_v1"
    assert body["published"] is True
    assert body["headline"]["sum_row_ids"] == ["1", "2", "3", "4"]
    assert "1a" not in body["headline"]["sum_row_ids"]
    nested = next(r for r in body["headline"]["rows"] if r["id"] == "1a")
    assert nested["nested"] is True
    assert body["shadow"]["sum_row_ids"] == ["5", "6", "7", "8", "10"]
    assert "stamp" in body
    dumped = response.text
    assert "annual_ground_rent" not in dumped
    assert "site_rental_per_sqm" not in dumped
    for row in body["headline"]["rows"] + body["shadow"]["rows"]:
        assert row["amount_placeholder"] == "—"
        assert row["amount_gbp_per_ha"] is None


def test_api_place_stack_blocked(monkeypatch):
    monkeypatch.setattr(
        "api.platform_routes.lookup_zone_publication_status",
        lambda code: "blocked",
    )
    client = TestClient(_app(monkeypatch))
    response = client.get("/api/place-stack.json", params={"zone": "S01008680"})
    assert response.status_code == 200
    body = response.json()
    assert body["published"] is False
    assert body["reason"] == "blocked"
    assert body["headline"] is None


def test_api_place_stack_requires_zone_or_point(monkeypatch):
    client = TestClient(_app(monkeypatch))
    response = client.get("/api/place-stack.json")
    assert response.status_code == 400
