"""Hydro sites + SEPA CAR natural-capital layers (catalog, routes, PostGIS)."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2
import pytest
from fastapi.testclient import TestClient

from api.main import app
from layers.platform import platform_catalog
from layers import sepa_car as sepa_car_layer

client = TestClient(app)

SCOTLAND_BBOX = {
    "south": 55.0,
    "west": -5.5,
    "north": 56.5,
    "east": -3.5,
    "max_features": 40,
}

SCHEMA_SQL = (
    Path(__file__).resolve().parents[1] / "db" / "schema" / "006_hydro_sepa_car.sql"
)
OGL_URL = "open-government-licence"
SEPA_ENV = "sepa.org.uk/environment/environmental-data"


def _dsn() -> str | None:
    return (
        (
            os.environ.get("DATABASE_URL")
            or os.environ.get("WEALTH_TEST_DATABASE_URL")
            or ""
        ).strip()
        or None
    )


def test_catalog_lists_hydro_and_sepa_car_ogl_with_tiers():
    layers = {row["id"]: row for row in platform_catalog()["layers"]}
    hydro = layers["hydro_sites"]
    car = layers["sepa_car"]
    assert hydro["status"] == "live"
    assert car["status"] == "live"
    assert hydro["endpoint"] == "/layers/open/hydro"
    assert car["endpoint"] == "/layers/open/sepa-car"
    assert hydro["licence"] == "OGL-3.0"
    assert car["licence"] == "OGL-3.0"
    assert OGL_URL in (car.get("licence_url") or "")
    assert SEPA_ENV in (car.get("source_url") or "")
    assert "map.sepa.org.uk" in (car.get("mapserver_url") or "")
    assert car["value_tier"] == "market"
    assert car["commons_class"] == "extractive"
    assert car["publication_status"] == "ok"
    assert car.get("adds_to_surface_rent") is False
    desc = car.get("description") or ""
    assert "194" in desc and "195" in desc
    assert "never prox" in desc.lower() or "PostGIS only" in desc
    assert "No £" in desc or "no £" in desc
    assert "surface rent" in desc.lower()


def test_publication_rules_declare_hydro_and_car_routes():
    from georgist.publication_rules import PUBLIC_ROUTE_RULES

    assert "/layers/open/hydro" in PUBLIC_ROUTE_RULES
    assert "/layers/open/sepa-car" in PUBLIC_ROUTE_RULES
    assert PUBLIC_ROUTE_RULES["/layers/open/hydro"].value_basis == "none"
    assert PUBLIC_ROUTE_RULES["/layers/open/sepa-car"].value_basis == "none"


def test_sepa_car_layer_module_never_imports_httpx():
    """Request path must not proxy MapServer — PostGIS only."""
    import inspect

    source = inspect.getsource(sepa_car_layer)
    assert "httpx" not in source
    assert "MapServer" in source  # documented ingest source only
    assert "query_bbox" in source


def _truncate_tables() -> None:
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
            cur.execute("TRUNCATE hydro_sites")
            cur.execute("TRUNCATE sepa_car_licences")
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def test_open_hydro_503_when_unloaded():
    _truncate_tables()
    r = client.get("/layers/open/hydro", params=SCOTLAND_BBOX)
    assert r.status_code == 503
    detail = r.json().get("detail", "").lower()
    assert "hydro" in detail
    assert "ingest" in detail or "atom" in detail or "ogl" in detail


def test_open_sepa_car_503_when_unloaded():
    _truncate_tables()
    r = client.get("/layers/open/sepa-car", params=SCOTLAND_BBOX)
    assert r.status_code == 503
    detail = r.json().get("detail", "").lower()
    assert "car" in detail
    assert "ingest_sepa_car" in detail or "python -m etl.ingest_sepa_car" in detail
    assert "mapserver" in detail
    assert "never prox" in detail or "postgis" in detail


def test_sepa_car_bbox_after_fixture_load():
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
            cur.execute("TRUNCATE sepa_car_licences")
            cur.execute(
                """
                INSERT INTO sepa_car_licences (
                  authorisation_no, car_layer, authorisation_level,
                  regulatory_area, geom, value_tier, publication_status
                ) VALUES (
                  'CAR/S/TEST1',
                  'simple',
                  'CAR Simple Licence',
                  'Water',
                  ST_SetSRID(ST_MakePoint(-4.20, 55.90), 4326),
                  'market',
                  'ok'
                )
                """
            )
        conn.commit()
    finally:
        conn.close()

    r = client.get("/layers/open/sepa-car", params=SCOTLAND_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["ok"] is True
    assert body["meta"]["licence"] == "OGL-3.0"
    assert OGL_URL in (body["meta"].get("licence_url") or "")
    assert SEPA_ENV in (body["meta"].get("source_url") or "")
    assert body["meta"]["value_tier"] == "market"
    assert body["meta"]["publication_status"] == "ok"
    assert "proxy" in (body["meta"].get("note") or "").lower()
    assert any(
        f.get("properties", {}).get("authorisation_no") == "CAR/S/TEST1"
        for f in body["features"]
    )


def test_downloads_list_sepa_car_mapserver_path():
    r = client.get("/downloads")
    assert r.status_code == 200
    items = {row["id"]: row for row in r.json()["items"]}
    assert items["sepa_car"]["licence"] == "OGL-3.0"
    assert SEPA_ENV in (items["sepa_car"].get("url") or "")
    note = (items["sepa_car"].get("note") or "").lower()
    assert "mapserver" in note or "194" in note
    assert "ingest_sepa_car" in note or "postgis" in note
