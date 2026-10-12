"""Hydro sites + SEPA CAR natural-capital layers (catalog, routes, PostGIS)."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import psycopg2
import pytest
from fastapi.testclient import TestClient

from api.main import app
from etl.ingest_sepa_car import ngr_to_wgs84, parse_car_csv
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
    Path(__file__).resolve().parents[1] / "db" / "schema" / "006_hydro_sepa_car.sql"
)
OGL_URL = "open-government-licence"


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
    assert OGL_URL in (hydro.get("licence_url") or "")
    assert OGL_URL in (car.get("licence_url") or "")
    assert "data.gov.uk" in (hydro.get("source_url") or "")
    assert "sepa" in (car.get("source_url") or "").lower()
    assert hydro["value_tier"] == "proxy"
    assert car["value_tier"] == "proxy"
    assert hydro["commons_class"] == "extractive"
    assert car["commons_class"] == "extractive"
    assert hydro["publication_status"] == "ok"
    assert car["publication_status"] == "download_only"
    for blob in (hydro.get("description") or "", car.get("description") or ""):
        assert "£" not in blob or "No £" in blob
        assert "surface rent" in blob.lower()


def test_publication_rules_declare_hydro_and_car_routes():
    from georgist.publication_rules import PUBLIC_ROUTE_RULES

    assert "/layers/open/hydro" in PUBLIC_ROUTE_RULES
    assert "/layers/open/sepa-car" in PUBLIC_ROUTE_RULES
    assert PUBLIC_ROUTE_RULES["/layers/open/hydro"].value_basis == "none"
    assert PUBLIC_ROUTE_RULES["/layers/open/sepa-car"].value_basis == "none"


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
    assert "download" in detail or "csv" in detail or "ingest" in detail


def test_ngr_to_wgs84_parses_scotland_point():
    coords = ngr_to_wgs84("NS 95844 21321")
    assert coords is not None
    lng, lat = coords
    assert 55.4 < lat < 55.6
    assert -3.7 < lng < -3.5


def test_parse_car_csv_filters_car_water_rows(tmp_path: Path):
    path = tmp_path / "car.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Authorisation number",
                "Authorisation holder",
                "Authorisation location",
                "Authorisation level",
                "Authorisation status",
                "Regulatory area",
                "NGR",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Authorisation number": "CAR/L/1011412",
                "Authorisation holder": "Example Hydro",
                "Authorisation location": "Breadalbane",
                "Authorisation level": "CAR Complex Licence",
                "Authorisation status": "Granted",
                "Regulatory area": "Water",
                "NGR": "NN 12345 45678",
            }
        )
        writer.writerow(
            {
                "Authorisation number": "WML/123",
                "Authorisation holder": "Skip me",
                "Authorisation location": "Landfill",
                "Authorisation level": "Waste Management Licence",
                "Authorisation status": "Granted",
                "Regulatory area": "Waste",
                "NGR": "NS 10000 20000",
            }
        )
    rows = parse_car_csv(path)
    assert len(rows) == 1
    assert rows[0]["authorisation_no"] == "CAR/L/1011412"
    assert rows[0]["lng"] is not None


def test_hydro_bbox_after_fixture_load():
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
            cur.execute("TRUNCATE hydro_sites")
            cur.execute(
                """
                INSERT INTO hydro_sites (lic_no, site_name, geom, value_tier, publication_status)
                VALUES (
                  'CAR/L/TEST1',
                  'Fixture Hydro',
                  ST_SetSRID(ST_MakePoint(-4.25, 55.85), 4326),
                  'proxy',
                  'ok'
                )
                """
            )
        conn.commit()
    finally:
        conn.close()

    r = client.get("/layers/open/hydro", params=SCOTLAND_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["meta"]["ok"] is True
    assert body["meta"]["licence"] == "OGL-3.0"
    assert body["meta"]["value_tier"] == "proxy"
    assert body["meta"]["publication_status"] == "ok"
    assert "rent" not in (body["meta"].get("note") or "").lower() or "no £" in (
        body["meta"].get("note") or ""
    ).lower()
    assert any(
        f.get("properties", {}).get("lic_no") == "CAR/L/TEST1"
        for f in body["features"]
    )


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
                  authorisation_no, authorisation_level, regulatory_area,
                  geom, value_tier, publication_status
                ) VALUES (
                  'CAR/S/TEST1',
                  'CAR Simple Licence',
                  'Water',
                  ST_SetSRID(ST_MakePoint(-4.20, 55.90), 4326),
                  'proxy',
                  'download_only'
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
    assert body["meta"]["value_tier"] == "proxy"
    assert body["meta"]["publication_status"] == "download_only"
    assert "download" in (body["meta"].get("note") or "").lower()
    assert any(
        f.get("properties", {}).get("authorisation_no") == "CAR/S/TEST1"
        for f in body["features"]
    )


def test_downloads_list_hydro_and_car():
    r = client.get("/downloads")
    assert r.status_code == 200
    items = {row["id"]: row for row in r.json()["items"]}
    assert items["hydro_sites"]["licence"] == "OGL-3.0"
    assert items["sepa_car"]["licence"] == "OGL-3.0"
    assert "download" in (items["sepa_car"].get("note") or "").lower()
