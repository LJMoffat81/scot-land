"""SG Data Zone boundary loader: fixture CI path + loud count failures."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from etl import ingest_dz_boundaries as ingest

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "dz_boundaries_sample.geojson"
)

URL = os.getenv("WEALTH_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""

# Balfron Main Street ≈ OSGB36 easting/northing used in the fixture envelope.
BALFRON_LAT = 56.0715
BALFRON_LON = -4.3375


def test_fixture_geojson_exists_and_marks_synthetic():
    assert FIXTURE.is_file(), FIXTURE
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["type"] == "FeatureCollection"
    assert "27700" in payload["crs"]["properties"]["name"]
    codes = {f["properties"]["code"] for f in payload["features"]}
    assert "S01013010" in codes
    for feature in payload["features"]:
        assert feature["properties"].get("fixture") is True


def test_expected_national_counts_are_published_totals():
    assert ingest.EXPECTED_COUNTS == {2011: 6976, 2022: 7392}


def test_assert_count_fails_loudly_on_national_mismatch():
    with pytest.raises(ingest.IngestError, match="expected published count 6976"):
        ingest._assert_count(2011, 12, load_scope="production")
    with pytest.raises(ingest.IngestError, match="expected published count 7392"):
        ingest._assert_count(2022, 100, load_scope="production")


def test_refuse_download_into_data_external(tmp_path):
    bad = tmp_path / "data" / "external" / "dz" / "x.zip"
    bad.parent.mkdir(parents=True)
    # Resolve path that looks like repo data/external when nested under tmp.
    # The guard keys on "/data/external" in the resolved posix path.
    target = Path("/tmp/scot-land-data-external-guard/data/external/dz.zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ingest.IngestError, match="data/external"):
        ingest._refuse_external_write(target)


def test_iter_geojson_rows_reads_balfron_2011():
    rows = ingest.iter_geojson_rows(FIXTURE, 2011)
    codes = {code for code, _name, _geom in rows}
    assert "S01013010" in codes
    assert all(vintage_ok(code, 2011) for code in codes)


def vintage_ok(code: str, vintage: int) -> bool:
    from georgist.dz_lookup import vintage_for_code

    return vintage_for_code(code) == vintage


@pytest.mark.skipif(not URL, reason="DATABASE_URL / WEALTH_TEST_DATABASE_URL not set")
def test_fixture_load_writes_rows_meta_and_balfron_lookup(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    conn = ingest.connect()
    try:
        ingest.ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE dz_boundaries")
            cur.execute("TRUNCATE TABLE dz_boundaries_meta")
        conn.commit()
        loaded = ingest.load_fixture(conn, FIXTURE, replace=True)
        assert loaded[2011] == 2
        assert loaded[2022] == 1
        with conn.cursor() as cur:
            cur.execute(
                "SELECT vintage, row_count, load_scope, licence, "
                "length(sha256), source_url IS NOT NULL "
                "FROM dz_boundaries_meta ORDER BY vintage"
            )
            meta = cur.fetchall()
            assert meta == [
                (2011, 2, "fixture", "synthetic-test-only", 64, True),
                (2022, 1, "fixture", "synthetic-test-only", 64, True),
            ]
            cur.execute("SELECT ST_SRID(geom) FROM dz_boundaries LIMIT 1")
            assert cur.fetchone()[0] == 27700
        from georgist.dz_lookup import lookup_postgis

        hit = lookup_postgis(BALFRON_LAT, BALFRON_LON)
        assert hit.source == "postgis:dz_boundaries"
        # Default public grain is DZ2022 when both vintages hit.
        assert hit.to_dict()["code"] == "S01020380"
        assert hit.to_dict()["vintage"] == 2022
        assert hit.to_dict()["dz2022"]["code"] == "S01020380"
        assert hit.to_dict()["dz2011"]["code"] == "S01013010"
        assert hit.to_dict()["dz2011"]["name"] == "Balfron and Drymen - 02"
    finally:
        conn.close()


@pytest.mark.skipif(not URL, reason="DATABASE_URL / WEALTH_TEST_DATABASE_URL not set")
def test_cli_fixture_mode(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    assert ingest.main(["--fixture", "--replace"]) == 0
