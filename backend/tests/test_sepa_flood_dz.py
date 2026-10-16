"""SEPA-FLOOD-1: Data Zone shares from medium-likelihood Flood Maps v3.0."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import shape

from api.platform_routes import router
from etl.ingest_sepa_frm_v3 import (
    DZ2022_COUNT,
    DZ2022_SHA256,
    LicenceError,
    RejectedFloodSource,
    aggregate_directory,
    crs_from_geojson,
    load_replace,
    load_zones_postgis,
    main,
    reproject_to_bng,
    select_medium_layers,
)
from georgist.publication_rules import PUBLIC_ROUTE_RULES
from layers.flood_dz import ATTRIBUTION, PROPERTY_KEYS
from layers.layers_add_catalog import SEPA_NFRA_ATTRIBUTION

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sepa_frm_v3"
GLASGOW = "-4.30,55.84,-4.22,55.88"
DZ_SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [
            [-4.26, 55.85],
            [-4.24, 55.85],
            [-4.24, 55.87],
            [-4.26, 55.87],
            [-4.26, 55.85],
        ]
    ],
}


def test_half_coverage_fixture_is_50_and_0():
    rows = aggregate_directory(FIXTURES / "half")
    by_zone = {row["data_zone"]: row for row in rows}
    assert set(by_zone) == {"S01013482", "S01013483"}
    covered = by_zone["S01013482"]
    other = by_zone["S01013483"]
    assert covered["pct_area_river"] == 50
    assert other["pct_area_river"] == 0
    assert covered["pct_area_coastal"] == 0
    assert covered["pct_area_surface"] == 0
    assert other["pct_area_coastal"] == 0
    assert other["pct_area_surface"] == 0
    assert covered["source_version"] == "v3.0"
    for row in rows:
        assert set(row) == set(PROPERTY_KEYS)
        for key in ("pct_area_river", "pct_area_coastal", "pct_area_surface"):
            assert 0 <= row[key] <= 100


def test_climate_change_file_is_rejected():
    with pytest.raises(RejectedFloodSource):
        aggregate_directory(FIXTURES / "reject_cc")


def test_high_likelihood_file_is_rejected():
    with pytest.raises(RejectedFloodSource):
        aggregate_directory(FIXTURES / "reject_high")


def test_non_ogl_licence_aborts():
    with pytest.raises(LicenceError):
        aggregate_directory(FIXTURES / "bad_licence")


def test_bowtie_still_loads_expected_percent():
    """A self-intersecting bow-tie must not abort the load."""
    rows = aggregate_directory(FIXTURES / "bowtie")
    by_zone = {row["data_zone"]: row for row in rows}
    assert by_zone["S01013482"]["pct_area_river"] == 25
    assert by_zone["S01013483"]["pct_area_river"] == 0


def test_overlapping_polygons_are_100_not_more():
    rows = aggregate_directory(FIXTURES / "overlap")
    assert rows[0]["data_zone"] == "S01013482"
    assert rows[0]["pct_area_river"] == 100
    assert rows[0]["pct_area_coastal"] == 0
    assert rows[0]["pct_area_surface"] == 0


def test_river_flood_geojson_is_rejected():
    with pytest.raises(RejectedFloodSource):
        aggregate_directory(FIXTURES / "reject_flood")


def test_version_3_licence_is_accepted():
    rows = aggregate_directory(FIXTURES / "version_licence")
    by_zone = {row["data_zone"]: row for row in rows}
    assert by_zone["S01013482"]["pct_area_river"] == 50
    assert by_zone["S01013483"]["pct_area_river"] == 0


def test_file_crs_is_reprojected_to_27700():
    """EPSG:3857 coordinates must not be left unchanged just because they exceed 180."""
    rows = aggregate_directory(FIXTURES / "mercator_half")
    by_zone = {row["data_zone"]: row for row in rows}
    assert by_zone["S01013482"]["pct_area_river"] == 50
    assert by_zone["S01013483"]["pct_area_river"] == 0


def test_gpkg_is_refused(tmp_path: Path):
    (tmp_path / "LICENCE.txt").write_text(
        "Open Government Licence version 3.0\n", encoding="utf-8"
    )
    (tmp_path / "river_extent_m.gpkg").write_text("not-a-geojson", encoding="utf-8")
    (tmp_path / "dz.geojson").write_text(
        (FIXTURES / "half" / "dz.geojson").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(RejectedFloodSource):
        aggregate_directory(tmp_path)


def test_root_licence_does_not_cover_a_dataset_folder(tmp_path: Path):
    (tmp_path / "LICENCE.txt").write_text(
        "Open Government Licence 3.0\n", encoding="utf-8"
    )
    dataset = tmp_path / "river"
    dataset.mkdir()
    (dataset / "river_extent_m.geojson").write_text(
        (FIXTURES / "half" / "river_extent_m.geojson").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (dataset / "dz.geojson").write_text(
        (FIXTURES / "half" / "dz.geojson").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(LicenceError):
        aggregate_directory(tmp_path)


def test_ogl_v3_wording_is_accepted(tmp_path: Path):
    (tmp_path / "LICENCE.txt").write_text(
        "This product is licensed under the OGL v3.0.\n", encoding="utf-8"
    )
    (tmp_path / "river_extent_m.geojson").write_text(
        (FIXTURES / "half" / "river_extent_m.geojson").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "dz.geojson").write_text(
        (FIXTURES / "half" / "dz.geojson").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    rows = aggregate_directory(tmp_path)
    by_zone = {row["data_zone"]: row for row in rows}
    assert by_zone["S01013482"]["pct_area_river"] == 50


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_flood_dz_whitelist_and_zone_geometry(monkeypatch):
    monkeypatch.setenv("LAYER_SEPA_FLOOD_DZ_ENABLED", "true")
    monkeypatch.setattr("layers.flood_dz.is_loaded", lambda: True)

    def _rows(west, south, east, north):
        return [
            {
                "data_zone": "S01014567",
                "pct_area_river": 50,
                "pct_area_coastal": 0,
                "pct_area_surface": 100,
                "source_version": "v3.0",
                "geometry": DZ_SQUARE,
                "flood_geom": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                },
            }
        ]

    monkeypatch.setattr("layers.flood_dz.fetch_rows", _rows)
    response = _client().get(f"/layers/open/flood-dz?bbox={GLASGOW}&kind=river")
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["loaded"] is True
    assert len(body["features"]) == 1
    feature = body["features"][0]
    assert set(feature["properties"]) == set(PROPERTY_KEYS)
    assert "flood_geom" not in feature["properties"]
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["geometry"] == DZ_SQUARE
    for key in ("pct_area_river", "pct_area_coastal", "pct_area_surface"):
        assert isinstance(feature["properties"][key], int)
        assert 0 <= feature["properties"][key] <= 100
    assert "£" not in response.text


def test_flood_dz_empty_table_is_503(monkeypatch):
    monkeypatch.setenv("LAYER_SEPA_FLOOD_DZ_ENABLED", "true")
    monkeypatch.setattr("layers.flood_dz.is_loaded", lambda: False)
    response = _client().get(f"/layers/open/flood-dz?bbox={GLASGOW}&kind=surface")
    assert response.status_code == 503
    assert response.json()["detail"] == "SEPA flood Data Zone table is not loaded yet."


def test_flood_dz_stays_off_without_flag(monkeypatch):
    monkeypatch.delenv("LAYER_SEPA_FLOOD_DZ_ENABLED", raising=False)
    monkeypatch.setattr("layers.flood_dz.is_loaded", lambda: True)
    response = _client().get(f"/layers/open/flood-dz?bbox={GLASGOW}&kind=river")
    assert response.status_code == 503
    assert response.json()["detail"] == "SEPA flood Data Zone table is not loaded yet."


def test_loader_main_refuses_when_flag_off(monkeypatch):
    monkeypatch.delenv("LAYER_SEPA_FLOOD_DZ_ENABLED", raising=False)
    monkeypatch.setattr("sys.argv", ["ingest_sepa_frm_v3", "--replace"])
    with pytest.raises(SystemExit, match="LAYER_SEPA_FLOOD_DZ_ENABLED"):
        main()


def test_flood_dz_route_is_zone_level():
    rule = PUBLIC_ROUTE_RULES["/layers/open/flood-dz"]
    assert rule.geometry_level == "zone"
    assert rule.value_basis == "none"


SEPA_CREDIT = (
    "©SEPA 2025; this SEPA product is licensed under the "
    "Open Government Licence version 3.0."
)


def test_attribution_uses_sepa_wording():
    assert ATTRIBUTION == SEPA_CREDIT
    assert SEPA_NFRA_ATTRIBUTION == SEPA_CREDIT


def test_reproject_reads_file_crs_and_asserts_27700():
    payload = json.loads(
        (FIXTURES / "mercator_half" / "river_extent_m.geojson").read_text(encoding="utf-8")
    )
    crs = crs_from_geojson(payload)
    assert crs.to_epsg() == 3857
    geom = reproject_to_bng(shape(payload["features"][0]["geometry"]), crs)
    minx, miny, maxx, maxy = geom.bounds
    assert 0 < minx < 700_000
    assert 500_000 < miny < 1_300_000
    assert 0 < maxx < 700_000
    assert 500_000 < maxy < 1_300_000


def test_gdb_layers_require_extent_m():
    assert select_medium_layers(
        ["FRM_FH_RIVER_EXTENT_M", "FRM_FH_RIVER_EXTENT_M_CC", "river_flood"]
    ) == [("river", "FRM_FH_RIVER_EXTENT_M")]
    with pytest.raises(RejectedFloodSource):
        select_medium_layers(["FRM_FH_RIVER_EXTENT_H", "river_flood"])


def test_dz2022_sha_pin_matches_sources_yaml():
    sources = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "data" / "config" / "sources.yaml").read_text(
            encoding="utf-8"
        )
    )
    pinned = sources["data_zone_boundaries"]["vintages"][2022]["sha256"]
    assert DZ2022_SHA256 == pinned
    assert DZ2022_SHA256 == "421c648480c7d51e32934de9f1b9f6cbbf86c6d8d382aab30a7bb4d2049ef0ec"
    assert DZ2022_COUNT == 7392


class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self.conn = conn
        self._mode = ""

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, sql: str, params: object = None) -> None:
        self.conn.queries.append(sql)
        self._mode = "sha" if "dz_boundaries_meta" in sql else "zones"

    def fetchone(self) -> tuple[str]:
        return (self.conn.sha,)

    def fetchall(self) -> list[tuple[str, str, int]]:
        return self.conn.rows


class _Conn:
    def __init__(self, sha: str, rows: list[tuple[str, str, int]]) -> None:
        self.sha = sha
        self.rows = rows
        self.queries: list[str] = []
        self.closed = False

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def close(self) -> None:
        self.closed = True


def _square_rows(count: int, srid: int = 27700) -> list[tuple[str, str, int]]:
    geom = json.dumps(
        {
            "type": "Polygon",
            "coordinates": [[[250000, 660000], [250001, 660000], [250001, 660001], [250000, 660000]]],
        }
    )
    return [(f"S{i:08d}", geom, srid) for i in range(count)]


def test_zone_count_and_srid_are_asserted_before_write(monkeypatch):
    written: list[list] = []
    monkeypatch.setattr(
        "etl.ingest_sepa_frm_v3.floods_from_directory",
        lambda root: {"river": [], "coastal": [], "surface": []},
    )
    monkeypatch.setattr(
        "etl.ingest_sepa_frm_v3.connect",
        lambda: _Conn(DZ2022_SHA256, _square_rows(DZ2022_COUNT - 1)),
    )
    monkeypatch.setattr(
        "etl.ingest_sepa_frm_v3.write_rows",
        lambda conn, rows: written.append(rows) or len(rows),
    )
    with pytest.raises(SystemExit, match="7392"):
        load_replace(Path("."))
    assert written == []

    monkeypatch.setattr(
        "etl.ingest_sepa_frm_v3.connect",
        lambda: _Conn(DZ2022_SHA256, _square_rows(DZ2022_COUNT, srid=4326)),
    )
    with pytest.raises(SystemExit, match="27700"):
        load_replace(Path("."))
    assert written == []

    monkeypatch.setattr(
        "etl.ingest_sepa_frm_v3.connect",
        lambda: _Conn("0" * 64, _square_rows(DZ2022_COUNT)),
    )
    with pytest.raises(SystemExit, match="sha256"):
        load_replace(Path("."))
    assert written == []


def test_load_zones_postgis_accepts_pinned_7392():
    conn = _Conn(DZ2022_SHA256, _square_rows(DZ2022_COUNT))
    zones = load_zones_postgis(conn)
    assert len(zones) == 7392
    assert any("ST_SRID(geom) = 27700" in " ".join(sql.split()) or "ST_SRID(geom)" in sql for sql in conn.queries)
