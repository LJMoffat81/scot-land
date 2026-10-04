"""Each served export carries the engine stamp, equal to /health by default."""

import json

from fastapi.testclient import TestClient

from agr.batch import assess_points, batch_meta, write_csv, write_jsonl


def _patch_remote(monkeypatch) -> None:
    monkeypatch.setattr("layers.vdl.by_council_hectares", lambda: {})
    monkeypatch.setattr("layers.open_stats.by_council_hectares", lambda: {})
    monkeypatch.setattr("layers.council_metrics.by_council_hectares", lambda: {})
    monkeypatch.setattr("layers.open_stats._stats", lambda *args, **kwargs: [])
    monkeypatch.setattr("layers.platform.lookup_parcel_geojson", lambda lat, lng: None)
    monkeypatch.setattr(
        "layers.platform.vdl_at_point",
        lambda lat, lng: {"ok": True, "intersects": False},
    )
    monkeypatch.setattr(
        "layers.platform.public_land_at_point",
        lambda lat, lng: {"ok": True, "intersects": False, "holdings": []},
    )


def test_exports_carry_the_health_stamp(monkeypatch, tmp_path):
    from api.main_platform import app

    monkeypatch.delenv("W3W_API_KEY", raising=False)
    _patch_remote(monkeypatch)
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    stamp = health.json()["stamp"]

    def same(body: dict) -> None:
        assert body["stamp"] == stamp

    catalog = client.get("/api/catalog.json")
    assert catalog.status_code == 200
    same(catalog.json())

    registers = client.get("/api/registers.json")
    assert registers.status_code == 200
    same(registers.json())

    public = client.get("/api/public-land.json")
    assert public.status_code == 200
    same(public.json())

    vdl = client.get("/api/vdl.json")
    assert vdl.status_code == 200
    same(vdl.json())

    vdl_councils = client.get("/api/vdl-councils.json")
    assert vdl_councils.status_code == 200
    same(vdl_councils.json())

    roll = client.get("/api/roll.json")
    assert roll.status_code == 200
    same(roll.json())
    assert "councils" in roll.json()

    csv_resp = client.get("/api/roll.csv")
    assert csv_resp.status_code == 200
    csv_line, csv_rest = csv_resp.text.split("\n", 1)
    assert csv_line.startswith("# stamp: ")
    assert json.loads(csv_line.removeprefix("# stamp: ")) == stamp
    header = csv_rest.split("\n", 1)[0]
    assert "name" in header.split(",")
    assert not any(column.startswith("engine_") for column in header.split(","))

    place = client.get("/api/place.json", params={"lat": 55.9533, "lng": -3.1883})
    assert place.status_code == 200, place.text
    same(place.json())
    assert "plot_gbp" in place.json()["agr"]

    downloads = client.get("/downloads")
    assert downloads.status_code == 200
    same(downloads.json())
    assert downloads.json()["items"]

    report = client.get(
        "/assessment/report",
        params={
            "lat": 55.8642,
            "lng": -4.2518,
            "scenario": "full_agr",
            "include_sales_context": False,
        },
    )
    assert report.status_code == 200, report.text
    body = report.json()
    same(body)
    assert body["assessment"]["stamp"] == stamp
    md_line = body["markdown"].splitlines()[0]
    assert json.loads(md_line.removeprefix("# stamp: ")) == stamp

    markdown = client.get(
        "/assessment/report",
        params={
            "lat": 55.8642,
            "lng": -4.2518,
            "scenario": "full_agr",
            "include_sales_context": False,
            "format": "markdown",
        },
    )
    assert markdown.status_code == 200
    assert json.loads(markdown.text.splitlines()[0].removeprefix("# stamp: ")) == stamp

    councils = client.get("/layers/councils")
    assert councils.status_code == 200
    same(councils.json())
    assert councils.json()["type"] == "FeatureCollection"

    choropleth = client.get("/layers/councils-agr")
    assert choropleth.status_code == 200
    same(choropleth.json())

    rows = assess_points([(55.9533, -3.1883)])
    meta = batch_meta(rows, scenario="full_agr")
    assert meta["stamp"] == stamp
    assert meta["count"] == 1

    csv_path = tmp_path / "roll.csv"
    jsonl_path = tmp_path / "roll.jsonl"
    write_csv(rows, csv_path)
    write_jsonl(rows, jsonl_path)
    saved_csv = csv_path.read_text(encoding="utf-8")
    assert json.loads(saved_csv.splitlines()[0].removeprefix("# stamp: ")) == stamp
    assert saved_csv.splitlines()[1].split(",")[0] != "engine_version"
    assert "annual_ground_rent_gbp" in saved_csv.splitlines()[1]
    saved_lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert json.loads(saved_lines[0])["stamp"] == stamp
    figure_row = json.loads(saved_lines[1])
    assert "annual_ground_rent_gbp" in figure_row
    assert "stamp" not in figure_row
