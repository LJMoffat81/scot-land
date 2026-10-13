"""Self-fetch RoS INSPIRE county zips: URL map, retry, shapefile load (mocked HTTP)."""

from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

import httpx
import pytest
import shapefile

from etl import ingest_inspire_parcels as ingest
from etl import inspire_counties as counties

URL = os.getenv("WEALTH_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""


def _synthetic_county_zip(code: str = "CLK") -> bytes:
    """Tiny BNG shapefile zip shaped like the RoS county product."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shp_path = root / f"{code}_bng"
        writer = shapefile.Writer(str(shp_path), shapeType=shapefile.POLYGON)
        writer.field("inspireid", "C", 40)
        writer.field("label", "C", 20)
        writer.field("nationalca", "C", 20)
        writer.field("county", "C", 3)
        # ~10 m square near Edinburgh in BNG
        x0, y0 = 325000.0, 673000.0
        ring = [
            [x0, y0],
            [x0 + 10, y0],
            [x0 + 10, y0 + 10],
            [x0, y0 + 10],
            [x0, y0],
        ]
        writer.poly([ring])
        writer.record(
            f"gb.ros.lr.SYN{code}001",
            f"SYN{code}001",
            f"SYN{code}001",
            code,
        )
        writer.close()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for ext in (".shp", ".shx", ".dbf"):
                path = Path(str(shp_path) + ext)
                zf.write(path, arcname=path.name)
        return buf.getvalue()


def test_registration_county_catalogue_has_33_and_pilot():
    assert len(counties.REGISTRATION_COUNTIES) == 33
    assert counties.resolve_codes(["edinburgh", "fife"]) == ["MID", "FFE"]
    assert counties.PILOT_CODES == ("MID", "FFE")
    assert counties.download_url("FFE").endswith("/FFE")


def test_download_retries_then_succeeds(tmp_path, monkeypatch):
    calls = {"n": 0}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def close(self):
            return None

        def get(self, url):
            calls["n"] += 1
            request = httpx.Request("GET", url)
            if calls["n"] < 3:
                return httpx.Response(503, request=request)
            body = _synthetic_county_zip("FFE")
            return httpx.Response(
                200,
                content=body,
                headers={"content-type": "application/zip"},
                request=request,
            )

    monkeypatch.setattr(ingest.httpx, "Client", FakeClient)
    dest = tmp_path / "FFE.zip"
    out = ingest.download_county_zip("FFE", dest, attempts=5, base_delay=0.01)
    assert out == dest
    assert dest.is_file()
    assert dest.read_bytes()[:2] == b"PK"
    assert calls["n"] == 3


def test_iter_county_rows_from_synthetic_zip(tmp_path):
    zip_path = tmp_path / "CLK.zip"
    zip_path.write_bytes(_synthetic_county_zip("CLK"))
    rows = list(ingest.iter_county_rows(zip_path, "CLK"))
    assert len(rows) == 1
    inspire_id, _national, _label, area_sqm, county, geojson = rows[0]
    assert inspire_id.startswith("gb.ros.lr.SYN")
    assert county == "CLK"
    assert area_sqm == pytest.approx(100.0, rel=0.05)
    payload = json.loads(geojson)
    assert payload["type"] in ("Polygon", "MultiPolygon")


def test_refuse_download_into_data_external(tmp_path):
    bad = tmp_path / "data" / "external" / "inspire"
    bad.mkdir(parents=True)
    with pytest.raises(SystemExit, match="data/external"):
        ingest.load_county_zips(
            ["FFE"],
            conn=None,  # type: ignore[arg-type]
            replace=True,
            work_dir=bad,
        )


@pytest.mark.skipif(not URL, reason="DATABASE_URL / WEALTH_TEST_DATABASE_URL not set")
def test_pilot_load_from_mocked_download(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", URL)

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def close(self):
            return None

        def get(self, url: str):
            code = url.rstrip("/").split("/")[-1]
            body = _synthetic_county_zip(code)
            return httpx.Response(
                200,
                content=body,
                headers={"content-type": "application/zip"},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(ingest.httpx, "Client", FakeClient)
    from layers import cadastral

    cadastral.parcel_source_meta.cache_clear()
    conn = ingest.connect()
    try:
        ingest.ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE inspire_parcels;")
            cur.execute("TRUNCATE TABLE inspire_parcels_meta;")
        conn.commit()
        work = tmp_path / "fetch"
        count, county_counts = ingest.load_county_zips(
            list(counties.PILOT_CODES),
            conn,
            replace=True,
            work_dir=work,
            attempts=2,
        )
        assert count == 2  # one synthetic parcel per county
        assert county_counts == {"MID": 1, "FFE": 1}
        ingest.write_load_meta(
            conn,
            count=count,
            vintage="2026-10-12",
            load_scope="pilot",
            licence="OGL-3.0",
            source_url="https://www.ros.gov.uk/open-data",
            input_path="pilot:MID,FFE",
            counties="MID,FFE",
            county_counts=county_counts,
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT county, COUNT(*) FROM inspire_parcels GROUP BY 1 ORDER BY 1"
            )
            got = dict(cur.fetchall())
            assert got == {"FFE": 1, "MID": 1}
            cur.execute(
                "SELECT value FROM inspire_parcels_meta WHERE key = 'load_scope'"
            )
            assert cur.fetchone()[0] == "pilot"
            cur.execute(
                "SELECT value FROM inspire_parcels_meta WHERE key = 'county_counts'"
            )
            assert json.loads(cur.fetchone()[0]) == {"FFE": 1, "MID": 1}
            cur.execute(
                "SELECT value FROM inspire_parcels_meta WHERE key = 'tagged'"
            )
            assert cur.fetchone()[0] == "live"
            cur.execute(
                "SELECT value FROM inspire_parcels_meta WHERE key = 'crs_source'"
            )
            assert cur.fetchone()[0] == "EPSG:27700"
    finally:
        conn.close()
