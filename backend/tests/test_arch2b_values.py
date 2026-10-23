"""ARCH-2b values route (BV-1..BV-8) and build/registry pins (BM-1..BM-3)."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import ValidationError

from layers.registry.loader import LayerEntry, load_registry
from tiles.build import build_tileset

_HELPERS_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "arch2" / "helpers.py"
)
_spec = importlib.util.spec_from_file_location("arch2_helpers_values", _HELPERS_PATH)
assert _spec and _spec.loader
_helpers = importlib.util.module_from_spec(_spec)
sys.modules["arch2_helpers_values"] = _helpers
_spec.loader.exec_module(_helpers)

connect = _helpers.connect
make_entry = _helpers.make_entry
require_dsn = _helpers.require_dsn
seed_layer_table = _helpers.seed_layer_table
square = _helpers.square
write_storage_yaml = _helpers.write_storage_yaml

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
REGISTRY = BACKEND / "layers" / "registry"
SCHEMA_PATH = REGISTRY / "schema.json"

_DZ_STYLE = {
    "fill": {
        "fill-color": [
            "case",
            ["==", ["feature-state", "v"], None],
            "#d9d9d9",
            [
                "interpolate",
                ["linear"],
                ["feature-state", "v"],
                10,
                "#c6dbef",
                100,
                "#6baed6",
                500,
                "#2171b5",
                1500,
                "#08519c",
                3000,
                "#08306b",
            ],
        ],
        "fill-opacity": [
            "interpolate",
            ["linear"],
            ["zoom"],
            4.5,
            0,
            5,
            0.55,
            14,
            0.55,
            15,
            0.4,
        ],
    },
    "line": {
        "line-color": "#0b1e3a",
        "line-width": 1.05,
        "line-opacity": [
            "interpolate",
            ["linear"],
            ["zoom"],
            8.5,
            0,
            9.5,
            0.6,
        ],
    },
}
_DZ_LEGEND = [
    {"label": "10", "color": "#c6dbef"},
    {"label": "100", "color": "#6baed6"},
    {"label": "500", "color": "#2171b5"},
    {"label": "1500", "color": "#08519c"},
    {"label": "3000", "color": "#08306b"},
    {"label": "No value", "color": "#d9d9d9"},
]


@pytest.fixture
def conn():
    require_dsn()
    connection = connect()
    yield connection
    connection.close()


@pytest.fixture
def tiles_env(tmp_path, monkeypatch):
    tiles_dir = tmp_path / "tiles"
    tiles_dir.mkdir()
    (tiles_dir / ".tmp").mkdir()
    storage_yaml = write_storage_yaml(tmp_path / "storage.yaml", keep_versions=3)
    monkeypatch.setenv("TILES_DIR", str(tiles_dir))
    monkeypatch.setenv("ARCH1_TEST_DSN", require_dsn())
    import api.tiles_routes as tr

    with tr._reader_lock:
        for _key, (fh, _reader) in list(tr._reader_cache.items()):
            try:
                fh.close()
            except OSError:
                pass
        tr._reader_cache.clear()
    return {"dir": tiles_dir, "storage": storage_yaml}


def _dz_grid_features() -> list[dict]:
    feats: list[dict] = []
    for idx, code_n in enumerate(range(482, 491)):
        col, row = idx % 3, idx // 3
        x0 = 1000 + col * 1000
        y0 = 1000 + row * 1000
        code = f"S01013{code_n}"
        feats.append(
            {
                "id": code,
                "properties": {"name": f"DZ {code}"},
                "geometry": square(x0, y0, 1000),
            }
        )
    return feats


def _install_registry(monkeypatch, *entries: LayerEntry) -> None:
    mapping = {e.id: e for e in entries}
    monkeypatch.setattr("api.tiles_routes.registry", lambda: mapping)
    monkeypatch.setattr("tiles.build.registry", lambda: mapping)


def _synthetic_metrics(codes: dict[str, float]) -> dict:
    features = [
        {
            "type": "Feature",
            "geometry": None,
            "properties": {
                "code": code,
                "vintage": 2022,
                "population_density_per_km2": val,
                "simd_decile": 5,
            },
        }
        for code, val in codes.items()
    ]
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {"feature_count": len(features)},
    }


@pytest.fixture
def built_dz(conn, tiles_env, monkeypatch):
    entry = make_entry(
        "dz2022",
        title="Data Zones 2022",
        measure="pop_density",
        style=_DZ_STYLE,
        legend=_DZ_LEGEND,
    )
    _install_registry(monkeypatch, entry)
    seed_layer_table(
        conn,
        "dz2022",
        _dz_grid_features(),
        dataset_version="dz2022@2026-10-22-abcd1234",
        as_of="2026-10-22",
    )
    result = build_tileset(
        "dz2022", conn=conn, storage_path=tiles_env["storage"]
    )
    return {"entry": entry, "result": result, **tiles_env}


@pytest.fixture
def client(built_dz, monkeypatch):
    from api.main import ROUTER_STATUS, app

    assert ROUTER_STATUS.get("api.tiles_routes", {}).get("loaded") is True
    return TestClient(app)


@pytest.fixture
def values_codes():
    return {
        "S01013482": 12.5,
        "S01013483": 100.0,
        "S01013484": 225.1,
    }


def test_bv1_values_happy_path(client, built_dz, monkeypatch, values_codes):
    monkeypatch.setattr(
        "layers.dz_context.build_metrics_payload",
        lambda **_k: _synthetic_metrics(values_codes),
    )
    version = built_dz["result"]["version"]
    r = client.get(f"/v1/tiles/dz2022/{version}/values/pop_density.json")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "public, max-age=31536000, immutable"
    sha8 = version.rsplit(".", 1)[-1]
    assert r.headers.get("etag") == f'"{sha8}-values-pop_density"'
    assert r.json() == {
        "layer": "dz2022",
        "version": version,
        "measure": "pop_density",
        "values": values_codes,
    }


def test_bv2_if_none_match(client, built_dz, monkeypatch, values_codes):
    monkeypatch.setattr(
        "layers.dz_context.build_metrics_payload",
        lambda **_k: _synthetic_metrics(values_codes),
    )
    version = built_dz["result"]["version"]
    sha8 = version.rsplit(".", 1)[-1]
    etag = f'"{sha8}-values-pop_density"'
    r = client.get(
        f"/v1/tiles/dz2022/{version}/values/pop_density.json",
        headers={"If-None-Match": etag},
    )
    assert r.status_code == 304
    assert r.content == b""


def test_bv3_unknown_id(client, built_dz, monkeypatch, values_codes):
    monkeypatch.setattr(
        "layers.dz_context.build_metrics_payload",
        lambda **_k: _synthetic_metrics(values_codes),
    )
    version = built_dz["result"]["version"]
    r = client.get(f"/v1/tiles/nope/{version}/values/pop_density.json")
    assert r.status_code == 404
    assert r.json() == {"detail": "unknown tileset"}


def test_bv4_unknown_version(client, built_dz, monkeypatch, values_codes):
    monkeypatch.setattr(
        "layers.dz_context.build_metrics_payload",
        lambda **_k: _synthetic_metrics(values_codes),
    )
    r = client.get("/v1/tiles/dz2022/2026-10-22.deadbeef/values/pop_density.json")
    assert r.status_code == 404
    assert r.json() == {"detail": "unknown version"}


@pytest.mark.parametrize(
    "measure",
    [
        "simd_decile",
        "house_price_median_gbp",
        "average_price_gbp",
    ],
)
def test_bv5_unknown_measure(client, built_dz, monkeypatch, values_codes, measure):
    monkeypatch.setattr(
        "layers.dz_context.build_metrics_payload",
        lambda **_k: _synthetic_metrics(values_codes),
    )
    version = built_dz["result"]["version"]
    r = client.get(f"/v1/tiles/dz2022/{version}/values/{measure}.json")
    assert r.status_code == 404
    assert r.json() == {"detail": "unknown measure"}


def test_bv5_path_traversal_measure_rejected(client, built_dz, monkeypatch, values_codes):
    """``../x`` cannot reach the values route (ASGI path collapse) — 404 route miss."""
    monkeypatch.setattr(
        "layers.dz_context.build_metrics_payload",
        lambda **_k: _synthetic_metrics(values_codes),
    )
    version = built_dz["result"]["version"]
    r = client.get(f"/v1/tiles/dz2022/{version}/values/../x.json")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_bv5_empty_measure_route_miss(client, built_dz):
    version = built_dz["result"]["version"]
    r = client.get(f"/v1/tiles/dz2022/{version}/values/.json")
    assert r.status_code == 404


def test_bv6_values_unavailable_empty(client, built_dz, monkeypatch):
    monkeypatch.setattr(
        "layers.dz_context.build_metrics_payload",
        lambda **_k: {"type": "FeatureCollection", "features": []},
    )
    version = built_dz["result"]["version"]
    r = client.get(f"/v1/tiles/dz2022/{version}/values/pop_density.json")
    assert r.status_code == 404
    assert r.json() == {"detail": "values unavailable"}


def test_bv7_unparsable_metrics(client, built_dz, monkeypatch):
    def _boom(**_k):
        raise ValueError("bad number")

    monkeypatch.setattr("layers.dz_context.build_metrics_payload", _boom)
    version = built_dz["result"]["version"]
    r = client.get(f"/v1/tiles/dz2022/{version}/values/pop_density.json")
    assert r.status_code == 404
    assert r.json() == {"detail": "values unavailable"}


def test_bv8_no_gbp_keys(client, built_dz, monkeypatch, values_codes):
    monkeypatch.setattr(
        "layers.dz_context.build_metrics_payload",
        lambda **_k: _synthetic_metrics(values_codes),
    )
    version = built_dz["result"]["version"]
    for measure in ("pop_density",):
        r = client.get(f"/v1/tiles/dz2022/{version}/values/{measure}.json")
        assert r.status_code == 200
        body = r.json()
        blob = json.dumps(body)
        assert "_gbp" not in blob
        for key in body["values"]:
            assert not key.endswith("_gbp")
        assert "gbp" not in {k.lower() for k in body.keys()}


def test_bm1_build_writes_manifest_keys(built_dz):
    result = built_dz["result"]
    entry = built_dz["entry"]
    expected = {
        "title": entry.raw["title"],
        "geometry": entry.raw["geometry"],
        "style": entry.raw["style"],
        "legend": entry.raw["legend"],
        "measure": entry.raw["measure"],
        "source_layer": "dz2022",
    }
    got = {
        "title": result["title"],
        "geometry": result["geometry"],
        "style": result["style"],
        "legend": result["legend"],
        "measure": result["measure"],
        "source_layer": result["source_layer"],
    }
    assert got == expected
    manifest = json.loads((built_dz["dir"] / "manifest.json").read_text(encoding="utf-8"))
    row = manifest["tilesets"]["dz2022"]
    for key, val in expected.items():
        assert row[key] == val


def test_bm2_registry_measure_enum(tmp_path):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(schema)
    base = yaml.safe_load((REGISTRY / "dz2022.yaml").read_text(encoding="utf-8"))
    for bad in ("house_price", True, 1):
        entry = dict(base)
        entry["measure"] = bad
        with pytest.raises(ValidationError) as exc:
            validator.validate(entry)
        assert list(exc.value.absolute_path) == ["measure"] or "measure" in (
            list(exc.value.path) or []
        ) or "measure" in str(exc.value)


def test_bm3_registry_refuses_symbol_style(tmp_path):
    from layers.registry.loader import RegistryError

    base = yaml.safe_load((REGISTRY / "oil-fields.yaml").read_text(encoding="utf-8"))
    base["id"] = "sample-style"
    base["style"] = {
        "fill": {"fill-color": "#8a3b00"},
        "symbol": {"text-field": "x"},
    }
    (tmp_path / "sample-style.yaml").write_text(
        yaml.safe_dump(base, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(RegistryError, match=r"symbol|additional"):
        load_registry(tmp_path)
