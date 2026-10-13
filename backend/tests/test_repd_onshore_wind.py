"""Natural-capital REPD onshore wind layer (catalog, routes, no £ rent)."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import psycopg2
import pytest

from georgist.publication_rules import PUBLIC_ROUTE_RULES
from layers.platform import platform_catalog

SCOTLAND_BBOX = {
    "south": 55.0,
    "west": -5.5,
    "north": 56.5,
    "east": -3.5,
    "max_features": 40,
}

SCHEMA_SQL = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "schema"
    / "020_nc_repd_onshore_wind.sql"
)


def _dsn() -> str | None:
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("WEALTH_TEST_DATABASE_URL")
        or ""
    ).strip() or None


def test_catalog_lists_repd_onshore_wind_live_ogl_with_licence_url():
    layers = {row["id"]: row for row in platform_catalog()["layers"]}
    layer = layers["repd_onshore_wind"]
    assert layer["status"] == "live"
    assert layer["endpoint"] == "/layers/open/repd-onshore-wind"
    assert "OGL" in (layer.get("licence") or "")
    assert "nationalarchives.gov.uk" in (layer.get("licence_url") or "")
    assert "gov.uk" in (layer.get("source_url") or "")
    assert layer.get("value_tier") == "market"
    assert layer.get("adds_to_surface_rent") is False
    assert layer.get("group") == "natural_capital"
    assert layer.get("ledger_role") == "ledger-row"
    assert layer.get("ledger_row") == "3"
    assert layer.get("ui_surface") == "ledger"


def test_publication_rule_declares_no_rent():
    rule = PUBLIC_ROUTE_RULES["/layers/open/repd-onshore-wind"]
    assert rule.value_basis == "none"
    assert rule.geometry_level == "site"


def _ensure_empty_table() -> None:
    dsn = _dsn()
    if not dsn:
        return
    try:
        conn = psycopg2.connect(dsn)
    except Exception:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
            cur.execute("TRUNCATE repd_onshore_wind")
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def test_open_repd_onshore_wind_503_when_unloaded(client):
    _ensure_empty_table()
    r = client.get("/layers/open/repd-onshore-wind", params=SCOTLAND_BBOX)
    assert r.status_code == 503
    detail = r.json().get("detail", "").lower()
    assert "repd" in detail or "onshore" in detail
    assert "ingest" in detail or "ogl" in detail
    assert "features" not in r.json()


def test_bbox_serves_mw_status_not_rent(client):
    dsn = _dsn()
    if not dsn:
        pytest.skip("No DATABASE_URL for PostGIS fixture load")
    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:
        pytest.skip(f"PostGIS unavailable: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
            cur.execute("TRUNCATE repd_onshore_wind")
            cur.execute(
                """
                INSERT INTO repd_onshore_wind (
                  ref_id, site_name, operator_name, technology_type,
                  development_status_short, installed_capacity_mw,
                  country, value_tier, publication_status, publish_level,
                  geom, retrieved_at
                ) VALUES (
                  'SYN-OW-1', 'SYNTHETIC Wind', 'Test Co', 'Wind Onshore',
                  'Operational', 24.5,
                  'Scotland', 'market', 'ok', 'public_site',
                  ST_SetSRID(ST_MakePoint(-4.25, 55.86), 4326), %s
                ), (
                  'SYN-OW-BLOCKED', 'Thin Wind', 'Test Co', 'Wind Onshore',
                  NULL, NULL,
                  'Scotland', 'market', 'blocked', 'public_site',
                  ST_SetSRID(ST_MakePoint(-4.24, 55.87), 4326), %s
                )
                """,
                (date.today(), date.today()),
            )
        conn.commit()
    finally:
        conn.close()

    r = client.get("/layers/open/repd-onshore-wind", params=SCOTLAND_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["ok"] is True
    assert body["meta"]["adds_to_surface_rent"] is False
    assert body["meta"]["value_tier"] == "market"
    assert "OGL" in body["meta"]["licence"]
    assert body["meta"].get("licence_url")
    refs = {f["properties"]["ref_id"] for f in body["features"]}
    assert refs == {"SYN-OW-1"}
    props = body["features"][0]["properties"]
    assert props["capacity_mw"] == 24.5
    assert props["status"] == "Operational"
    assert props["value_tier"] == "market"
    assert props["publication_status"] == "ok"
    assert props["adds_to_surface_rent"] is False
    assert "annual_rent" not in r.text.lower()
    assert "measured_rent" not in r.text.lower()
    assert "gbp" not in r.text.lower()
    assert "24.5" in r.text
    # Blocked thin row must not leak onto the public layer
    assert "SYN-OW-BLOCKED" not in r.text
    assert body["meta"]["adds_to_surface_rent"] is False
