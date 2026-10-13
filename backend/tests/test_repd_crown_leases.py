"""REPD + Crown Estate Scotland lease layers (catalog, routes, PostGIS)."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import psycopg2
import pytest
from fastapi.testclient import TestClient

from api.main import app
from layers.platform import platform_catalog

client = TestClient(app)

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
    / "017_open_energy_leases.sql"
)


def _dsn() -> str | None:
    return (os.environ.get("DATABASE_URL") or os.environ.get("WEALTH_TEST_DATABASE_URL") or "").strip() or None


def test_catalog_lists_repd_and_crown_leases_as_live_ogl():
    layers = {row["id"]: row for row in platform_catalog()["layers"]}
    repd = layers["repd"]
    ces = layers["crown_estate_leases"]
    assert repd["status"] == "live"
    assert ces["status"] == "live"
    assert repd["endpoint"] == "/layers/open/repd"
    assert ces["endpoint"] == "/layers/open/crown-estate-leases"
    assert "OGL" in (repd.get("licence") or "")
    assert "OGL" in (ces.get("licence") or "")
    assert "licence_url" in repd and "open-government-licence" in repd["licence_url"]
    assert "licence_url" in ces and "open-government-licence" in ces["licence_url"]
    assert "gov.uk" in (repd.get("source_url") or "")
    assert "crown-estate-scotland" in (ces.get("source_url") or "")
    assert "offshore" in (ces.get("label") or "").lower() or "offshore" in (
        ces.get("description") or ""
    ).lower()
    assert "aquaculture" not in (ces.get("description") or "").lower() or "separate" in (
        ces.get("description") or ""
    ).lower()
    assert repd.get("ledger_role") == "ledger-row"
    assert repd.get("ledger_row") == "3"
    assert repd.get("ui_surface") == "ledger"
    assert ces.get("ledger_role") == "ledger-row"
    assert ces.get("ledger_row") == "4"
    assert ces.get("ui_surface") == "ledger"


def _truncate_open_energy_tables() -> None:
    """Keep 503 tests honest even if a prior PostGIS fixture left rows."""
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
            cur.execute("TRUNCATE repd_sites")
            cur.execute("TRUNCATE crown_estate_leases")
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def test_open_repd_503_when_unloaded():
    _truncate_open_energy_tables()
    r = client.get("/layers/open/repd", params=SCOTLAND_BBOX)
    assert r.status_code == 503
    detail = r.json().get("detail", "").lower()
    assert "repd" in detail
    assert "ingest" in detail or "ogl" in detail


def test_open_crown_estate_leases_503_when_unloaded():
    _truncate_open_energy_tables()
    r = client.get("/layers/open/crown-estate-leases", params=SCOTLAND_BBOX)
    assert r.status_code == 503
    detail = r.json().get("detail", "").lower()
    assert "crown" in detail
    assert "ingest" in detail or "ogl" in detail


def test_publication_rules_declare_new_open_routes():
    from georgist.publication_rules import PUBLIC_ROUTE_RULES

    assert "/layers/open/repd" in PUBLIC_ROUTE_RULES
    assert "/layers/open/crown-estate-leases" in PUBLIC_ROUTE_RULES
    assert PUBLIC_ROUTE_RULES["/layers/open/repd"].value_basis == "none"
    assert PUBLIC_ROUTE_RULES["/layers/open/crown-estate-leases"].value_basis == "none"


def test_repd_bbox_after_fixture_load():
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
            cur.execute("TRUNCATE repd_sites")
            cur.execute(
                """
                INSERT INTO repd_sites (
                  ref_id, site_name, operator_name, technology_type,
                  development_status_short, installed_capacity_mw,
                  country, geom, retrieved_at
                ) VALUES (
                  'TEST1', 'Fixture Wind', 'Test Co', 'Wind Onshore',
                  'Operational', 12.5, 'Scotland',
                  ST_SetSRID(ST_MakePoint(-4.25, 55.86), 4326), %s
                )
                """,
                (date.today(),),
            )
        conn.commit()
    finally:
        conn.close()

    r = client.get("/layers/open/repd", params=SCOTLAND_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["meta"]["ok"] is True
    assert "OGL" in body["meta"]["licence"]
    assert any(f["properties"].get("ref_id") == "TEST1" for f in body["features"])


def test_crown_leases_bbox_after_fixture_load():
    dsn = _dsn()
    if not dsn:
        pytest.skip("No DATABASE_URL for PostGIS fixture load")
    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:
        pytest.skip(f"PostGIS unavailable: {exc}")

    square = {
        "type": "Polygon",
        "coordinates": [
            [
                [-4.3, 55.8],
                [-4.2, 55.8],
                [-4.2, 55.9],
                [-4.3, 55.9],
                [-4.3, 55.8],
            ]
        ],
    }
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
            cur.execute("TRUNCATE crown_estate_leases")
            cur.execute(
                """
                INSERT INTO crown_estate_leases (
                  id, lease_theme, description, tenant_name, agreement_type,
                  capacity_mw, geom, retrieved_at
                ) VALUES (
                  'offshore_wind:1', 'offshore_wind', 'Fixture Lease', 'Test Tenant',
                  'Lease Marine', 100,
                  ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s
                )
                """,
                (json.dumps(square), date.today()),
            )
        conn.commit()
    finally:
        conn.close()

    r = client.get("/layers/open/crown-estate-leases", params=SCOTLAND_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["ok"] is True
    assert "OGL" in body["meta"]["licence"]
    assert any(
        f["properties"].get("lease_theme") == "offshore_wind" for f in body["features"]
    )
