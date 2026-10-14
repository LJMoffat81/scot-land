"""CES aquaculture seabed leases (catalog, routes, PostGIS; no £ rent)."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2
import pytest
from fastapi.testclient import TestClient

from api.main import app
from etl.ingest_ces_aquaculture import CES_ATTRIBUTION, _rows_from_features
from layers.ces_aquaculture import OGL_V3_URL, source_meta
from layers.platform import platform_catalog

client = TestClient(app)

# West coast aquaculture bbox (Argyll / Inner Hebrides).
SCOTLAND_BBOX = {
    "south": 55.5,
    "west": -6.5,
    "north": 57.5,
    "east": -4.5,
    "max_features": 40,
}

SCHEMA_SQL = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "schema"
    / "021_ces_aquaculture_leases.sql"
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


def test_catalog_lists_ces_aquaculture_ogl_market_no_rent():
    row = next(r for r in platform_catalog()["layers"] if r["id"] == "ces_aquaculture")
    assert row["status"] == "live"
    assert row["endpoint"] == "/layers/open/ces-aquaculture"
    assert row["licence"] == "OGL-3.0"
    assert row["licence_url"] == OGL_V3_URL
    assert OGL_URL in (row.get("licence_url") or "")
    assert "crown-estate-scotland" in (row.get("source_url") or "")
    assert row["value_tier"] == "market"
    assert row["adds_to_surface_rent"] is False
    assert row.get("ledger_role") == "ledger-row"
    assert row.get("ledger_row") == "5"
    assert row.get("ui_surface") == "ledger"
    desc = row.get("description") or ""
    assert "No £" in desc or "no £" in desc
    assert "surface rent" in desc.lower()
    assert "ledger row 5" in desc.lower()


def test_source_meta_attribution_and_licence_url():
    meta = source_meta()
    assert meta["licence_url"] == OGL_V3_URL
    assert meta["attribution"] == CES_ATTRIBUTION
    assert meta["value_tier"] == "market"
    assert meta["adds_to_surface_rent"] is False


def test_publication_rules_declare_ces_aquaculture_route():
    from georgist.publication_rules import PUBLIC_ROUTE_RULES

    assert "/layers/open/ces-aquaculture" in PUBLIC_ROUTE_RULES
    assert PUBLIC_ROUTE_RULES["/layers/open/ces-aquaculture"].value_basis == "none"


def _truncate_table() -> None:
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
            cur.execute("TRUNCATE ces_aquaculture_leases")
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def test_open_ces_aquaculture_503_when_unloaded():
    _truncate_table()
    r = client.get("/layers/open/ces-aquaculture", params=SCOTLAND_BBOX)
    assert r.status_code == 503
    detail = r.json().get("detail", "").lower()
    assert "aquaculture" in detail or "ces" in detail
    assert "ingest" in detail


def test_ingest_rows_tag_market_and_ces_attribution():
    features = [
        {
            "properties": {
                "OBJECTID": 1,
                "Site_ID": "A-001",
                "Lease_Description": "Example finfish lease",
                "Property_Classification": "Aquaculture",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-5.5, 56.4],
                        [-5.49, 56.4],
                        [-5.49, 56.41],
                        [-5.5, 56.41],
                        [-5.5, 56.4],
                    ]
                ],
            },
        },
        {
            "properties": {"OBJECTID": 2, "Site_ID": "skip-no-geom"},
            "geometry": None,
        },
    ]
    rows = _rows_from_features(features, {})
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "ces-aqua:A-001"
    assert row["value_tier"] == "market"
    assert row["publication_status"] == "ok"
    assert row["licence_url"] == OGL_V3_URL
    assert row["attribution"] == CES_ATTRIBUTION
    assert "rent" not in row
    assert "gbp" not in {k.lower() for k in row}


def test_ces_aquaculture_bbox_after_fixture_load():
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
            cur.execute("TRUNCATE ces_aquaculture_leases")
            cur.execute(
                """
                INSERT INTO ces_aquaculture_leases (
                  id, site_id, lease_description, property_classification,
                  value_tier, publication_status, unpublished_reason, geom,
                  licence, licence_url, attribution, source_url, retrieved_at
                ) VALUES (
                  'ces-aqua:TEST1', 'TEST1', 'Fixture aquaculture lease',
                  'Aquaculture', 'market', 'ok', NULL,
                  ST_Multi(ST_SetSRID(ST_GeomFromText(
                    'POLYGON((-5.5 56.4, -5.49 56.4, -5.49 56.41, -5.5 56.41, -5.5 56.4))'
                  ), 4326)),
                  'OGL-3.0', %s, %s,
                  'https://crown-estate-scotland-spatial-hub-coregis.hub.arcgis.com/',
                  CURRENT_DATE
                )
                """,
                (OGL_V3_URL, CES_ATTRIBUTION),
            )
            cur.execute(
                """
                INSERT INTO ces_aquaculture_leases (
                  id, site_id, lease_description, property_classification,
                  value_tier, publication_status, unpublished_reason, geom,
                  licence, licence_url, attribution, source_url, retrieved_at
                ) VALUES (
                  'ces-aqua:BLOCKED', 'BLOCKED', 'Blocked thin row',
                  'Aquaculture', 'shadow', 'blocked', 'thin fixture',
                  ST_Multi(ST_SetSRID(ST_GeomFromText(
                    'POLYGON((-5.48 56.4, -5.47 56.4, -5.47 56.41, -5.48 56.41, -5.48 56.4))'
                  ), 4326)),
                  'OGL-3.0', %s, %s,
                  'https://crown-estate-scotland-spatial-hub-coregis.hub.arcgis.com/',
                  CURRENT_DATE
                )
                """,
                (OGL_V3_URL, CES_ATTRIBUTION),
            )
        conn.commit()
    finally:
        conn.close()

    r = client.get("/layers/open/ces-aquaculture", params=SCOTLAND_BBOX)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["meta"]["ok"] is True
    assert body["meta"]["adds_to_surface_rent"] is False
    assert body["meta"]["value_tier"] == "market"
    assert body["meta"]["licence_url"] == OGL_V3_URL
    assert body["meta"]["attribution"] == CES_ATTRIBUTION
    ids = {f["properties"]["id"] for f in body["features"]}
    assert "ces-aqua:TEST1" in ids
    assert "ces-aqua:BLOCKED" not in ids
    blob = str(body).lower()
    assert "annual_rent" not in blob
    assert "measured_rent" not in blob
    assert "lease_fee" not in blob
    assert "option_fee" not in blob
    assert "gbp" not in blob or "no £" in str(body).lower()
    for feat in body["features"]:
        props = feat["properties"]
        assert props.get("adds_to_surface_rent") is False
        assert props.get("value_tier") == "market"
        assert "annual_rent" not in props
        assert "fee" not in {k.lower() for k in props}
        assert "gbp" not in {k.lower() for k in props}
