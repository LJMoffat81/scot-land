"""Ingest NatureScot fixtures into PostGIS when a test database is available."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "data" / "fixtures" / "naturescot"


@pytest.fixture
def naturescot_db():
    url = (os.getenv("WEALTH_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        pytest.skip("No PostGIS test database configured")
    os.environ["DATABASE_URL"] = url
    import psycopg2

    from etl.ingest_naturescot import (
        connect,
        ensure_tables,
        load_designation_type,
        load_sssi,
    )

    conn = connect()
    ensure_tables(conn)
    yield conn, load_sssi, load_designation_type
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE naturescot_sssi;")
        cur.execute("TRUNCATE TABLE naturescot_designations;")
    conn.commit()
    conn.close()


def test_ingest_sssi_fixture(naturescot_db):
    conn, load_sssi, _ = naturescot_db
    n = load_sssi(FIXTURES / "sssi_sample.geojson", conn, replace=True)
    assert n == 1
    with conn.cursor() as cur:
        cur.execute("SELECT pa_code, name FROM naturescot_sssi")
        row = cur.fetchone()
    assert row[0] == "99001"
    assert "SSSI" in row[1] or "Peatland" in row[1]


def test_ingest_and_query_bbox(naturescot_db):
    conn, load_sssi, load_designation_type = naturescot_db
    load_sssi(FIXTURES / "sssi_sample.geojson", conn, replace=True)
    load_designation_type(
        FIXTURES / "spa_sample.geojson", conn, "spa", replace_type=True
    )

    from layers.naturescot import query_designations_bbox, query_sssi_bbox

    sssi = query_sssi_bbox(55.84, -4.30, 55.88, -4.22)
    assert sssi["meta"]["ok"] is True
    assert sssi["meta"]["licence"] == "OGL-3.0"
    assert len(sssi["features"]) == 1
    assert sssi["features"][0]["properties"]["designation_type"] == "sssi"

    des = query_designations_bbox(55.84, -4.30, 55.88, -4.22)
    assert des["meta"]["ok"] is True
    assert des["meta"]["licence"] == "OGL-3.0"
    assert len(des["features"]) == 1
    assert des["features"][0]["properties"]["designation_type"] == "spa"
