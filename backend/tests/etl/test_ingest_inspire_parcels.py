"""RoS INSPIRE Index Polygons loader: path guards + fixture ingest into PostGIS."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from etl import ingest_inspire_parcels as ingest

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "cadastral_index_polygons.geojson"
)

URL = os.getenv("WEALTH_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""


def test_fixture_geojson_exists_and_is_feature_collection():
    assert FIXTURE.is_file(), FIXTURE
    import json

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) >= 3
    counties = set()
    for feature in payload["features"]:
        props = feature["properties"]
        assert props.get("fixture") is True
        assert props.get("county")
        counties.add(props["county"])
        assert str(props.get("inspireid", "")).startswith("SYN-")
    assert "GLA" in counties
    assert "STG" in counties
    assert any(
        "BALFRON" in str(f["properties"].get("inspireid", "")).upper()
        for f in payload["features"]
    )


def test_inspire_id_prefers_inspireid_property():
    props = {"inspireid": "ABC", "id": "other"}
    feature = {"id": "feat-1", "properties": props}
    assert ingest._inspire_id(props, feature, 0) == "ABC"


def test_refuse_processed_path(tmp_path):
    bad = tmp_path / "data" / "processed" / "parcels.geojson"
    bad.parent.mkdir(parents=True)
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="data/processed"):
        ingest._assert_allowed_input(bad)


@pytest.mark.skipif(not URL, reason="DATABASE_URL / WEALTH_TEST_DATABASE_URL not set")
def test_fixture_load_writes_rows_and_meta(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    # Clear any cached source meta from other tests
    from layers import cadastral

    cadastral.parcel_source_meta.cache_clear()

    conn = ingest.connect()
    try:
        ingest.ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE inspire_parcels;")
            cur.execute("TRUNCATE TABLE inspire_parcels_meta;")
        conn.commit()
        count = ingest.load_geojson(FIXTURE, conn, replace=True)
        assert count == 3
        county_counts = ingest._county_counts_from_table(conn)
        ingest.write_load_meta(
            conn,
            count=count,
            vintage="2026-10-12",
            load_scope="fixture",
            licence="synthetic-test-only",
            source_url=str(FIXTURE),
            input_path=FIXTURE,
            county_counts=county_counts,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM inspire_parcels")
            assert cur.fetchone()[0] == 3
            cur.execute(
                "SELECT value FROM inspire_parcels_meta WHERE key = 'load_scope'"
            )
            assert cur.fetchone()[0] == "fixture"
            cur.execute(
                "SELECT value FROM inspire_parcels_meta WHERE key = 'county_counts'"
            )
            raw = cur.fetchone()[0]
            import json

            counts = json.loads(raw)
            assert counts.get("GLA") == 2
            assert counts.get("STG") == 1
            cur.execute(
                "SELECT value FROM inspire_parcels_meta WHERE key = 'harvest_year'"
            )
            assert cur.fetchone()[0] == "2026"
    finally:
        conn.close()
