"""Engine layers keep today's figures and only add a stamp."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from agr.config import load_config
from agr.engine import calculate_square_agr
from agr.layers import (
    ENGINE_VERSION,
    LayerConfigError,
    engine_stamp,
    load_layers,
    split_config,
    validate_layers,
)
from agr.overrides import merge_config_overrides
from api.main import app
from spatial.grid import snap_to_w3w_grid
from spatial.parcels import CadastralParcel

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SQUARE_PATH = FIXTURES / "engine_snapshot_main.json"
POSTCODE_PATH = FIXTURES / "postcode_snapshot_main.json"
LAYERS_PATH = ROOT / "data" / "config" / "layers.yaml"

FROZEN_SHA256 = {
    "data/config/agr.yaml": "139c3e510dc37587a9c1956a100bd5864e4119f67c39255213751cdca98bd31f",
    "data/config/sources.yaml": "0ba74307691bd20ca16c62f2386e446c78c57b1bf6efd9c9c0821cc0f330a84a",
    "data/processed/councils.json": "62a09c8ac892d75a5634ad6ad95d4f2b08c177663241af0ed2dfd3713b6aeb07",
    "backend/agr/valuation.py": "6da672ffece81960fd10be81c130ee965febae036fefc51ff2df18682bd8144a",
    "backend/agr/engine.py": "238a2d855d39eeb7a281b1b454748b8e0f6f083c8a2b0204774e4ddd4f2827a3",
    "backend/agr/scenarios.py": "0f125e9c550cb30941c3370aff18fec243c0ba47dc46e7b19203da67a9d1ebff",
}

READ_SECTIONS = {
    "valuer_roll",
    "valuation",
    "despeculation",
    "per_square",
    "land_use_values_gbp_per_ha_2009",
    "site_share",
    "scenarios",
}


class TrackingDict(dict):
    def __init__(self, data: dict, prefix: str, reads: set[str]):
        super().__init__(data)
        self._prefix = prefix
        self._reads = reads

    def _mark(self, key, value):
        path = f"{self._prefix}.{key}" if self._prefix else str(key)
        self._reads.add(path)
        if isinstance(value, dict) and not isinstance(value, TrackingDict):
            return TrackingDict(value, path, self._reads)
        return value

    def __getitem__(self, key):
        return self._mark(key, super().__getitem__(key))

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return default


def _listed_paths() -> set[str]:
    spec = yaml.safe_load(LAYERS_PATH.read_text(encoding="utf-8"))
    paths = set(spec["valuation"]["keys"])
    paths.update(spec["policy"]["keys"])
    paths.update(spec["policy"].get("applied_by_valuation") or [])
    mirrors = spec.get("mirrors") or {}
    paths.update(str(key) for key in mirrors)
    paths.update(str(value) for value in mirrors.values())
    return paths


def _covered(path: str, listed: set[str]) -> bool:
    for item in listed:
        if path == item or path.startswith(item + ".") or item.startswith(path + "."):
            return True
    return False


def _in_section(path: str) -> bool:
    root = path.split(".", 1)[0]
    return root in READ_SECTIONS


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _same_number(key: str, old, new) -> bool:
    if "per_sqm" in key:
        return old == new
    # Re-snapping a stored cell can move a coordinate by a fraction of a millimetre.
    if key in {"lat", "lng", "south", "west", "north", "east"}:
        return abs(float(old) - float(new)) < 1e-5
    return round(float(old), 2) == round(float(new), 2)


def _compare(old, new, path: str, errors: list[str]) -> None:
    if isinstance(old, dict):
        if not isinstance(new, dict):
            errors.append(f"{path} type changed")
            return
        missing = set(old) - set(new)
        extra = set(new) - set(old) - {"stamp"}
        for key in sorted(missing):
            errors.append(f"{path}.{key} removed")
        for key in sorted(extra):
            errors.append(f"{path}.{key} added")
        for key in sorted(set(old) & set(new)):
            _compare(old[key], new[key], f"{path}.{key}", errors)
        return
    if isinstance(old, list):
        if not isinstance(new, list) or len(old) != len(new):
            errors.append(f"{path} list changed")
            return
        for index, (left, right) in enumerate(zip(old, new)):
            _compare(left, right, f"{path}[{index}]", errors)
        return
    if _is_number(old) or _is_number(new):
        key = path.rsplit(".", 1)[-1]
        if not _is_number(old) or not _is_number(new) or not _same_number(key, old, new):
            errors.append(f"{path}: {old!r} != {new!r}")
        return
    if old != new:
        errors.append(f"{path}: {old!r} != {new!r}")


def _assert_stamp(stamp: dict) -> None:
    assert stamp["engine_version"] == ENGINE_VERSION
    for side in ("valuation", "policy"):
        assert stamp[side]["version"]
        assert len(stamp[side]["inputs_hash"]) == 12
        int(stamp[side]["inputs_hash"], 16)
    assert len(stamp["config"]["agr_yaml_sha256"]) == 12
    assert len(stamp["config"]["layers_yaml_sha256"]) == 12
    assert stamp["data"]["councils_generated_at"]
    assert stamp["data"]["hpi_period"]
    assert stamp["commit"]
    assert stamp["commit"] != "unknown"
    assert isinstance(stamp["sensitivity_overrides"], dict)


def _parcel_from(response: dict) -> CadastralParcel | None:
    feature = response.get("parcel")
    agr = response.get("agr") or {}
    if feature is None and agr.get("parcel_id") is None and agr.get("parcel_area_sqm") is None:
        return None
    props = (feature or {}).get("properties") or {}
    area = agr.get("parcel_area_sqm")
    if area is None:
        area = props.get("area_sqm") or 0
    return CadastralParcel(
        inspire_id=str(props.get("inspire_id") or ""),
        label=str(props.get("label") or agr.get("parcel_id") or ""),
        national_reference=str(props.get("national_reference") or ""),
        area_sqm=float(area),
        county=props.get("county"),
        geometry=(feature or {}).get("geometry"),
    )


def _install_parcel(monkeypatch, holder: dict) -> None:
    monkeypatch.setattr("agr.engine.lookup_parcel", lambda lat, lng: holder["parcel"])
    monkeypatch.setattr("api.main.lookup_parcel_geojson", lambda lat, lng: holder["feature"])


def _square_again(client: TestClient, response: dict, holder: dict) -> dict:
    square = response["square"]
    holder["parcel"] = _parcel_from(response)
    holder["feature"] = response.get("parcel")
    fresh = client.get(
        "/square",
        params={"lat": square["lat"], "lng": square["lng"], "scenario": "full_agr"},
    )
    assert fresh.status_code == 200, fresh.text
    return fresh.json()


def test_snapshot_matches_frozen_figures(monkeypatch):
    monkeypatch.delenv("W3W_API_KEY", raising=False)
    squares = json.loads(SQUARE_PATH.read_text(encoding="utf-8"))
    postcodes = json.loads(POSTCODE_PATH.read_text(encoding="utf-8"))
    assert len(squares["points"]) == 36
    holder: dict = {"parcel": None, "feature": None}
    _install_parcel(monkeypatch, holder)
    client = TestClient(app)
    errors: list[str] = []
    for point in squares["points"]:
        fresh = _square_again(client, point["response"], holder)
        _compare(point["response"], fresh, point.get("name") or point.get("code") or "point", errors)
        _assert_stamp(fresh["agr"]["stamp"])
    for postcode, response in postcodes["postcodes"].items():
        fresh = _square_again(client, response, holder)
        without_postcode = {key: value for key, value in response.items() if key != "postcode"}
        _compare(without_postcode, fresh, postcode, errors)
        _assert_stamp(fresh["agr"]["stamp"])
    assert not errors, "\n".join(errors[:30])


def test_frozen_files_match_main_bytes():
    import hashlib

    for rel, digest in FROZEN_SHA256.items():
        data = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest, rel


def test_every_read_config_key_is_mapped():
    councils = json.loads((ROOT / "data" / "processed" / "councils.json").read_text(encoding="utf-8"))
    reads: set[str] = set()
    config = TrackingDict(copy.deepcopy(load_config()), "", reads)
    assert len(councils["councils"]) == 32
    for council in councils["councils"]:
        centroid = council["centroid"]
        square = snap_to_w3w_grid(float(centroid["lat"]), float(centroid["lng"]))
        calculate_square_agr(square, scenario="full_agr", config=config)
    listed = _listed_paths()
    missing = sorted(path for path in reads if _in_section(path) and not _covered(path, listed))
    assert not missing, missing


def test_mirrors_agree_and_a_disagreement_raises():
    config = load_config()
    assert config["valuation"]["yield_rate"] == config["valuer_roll"]["yield_rate"]
    assert config["valuation"]["typical_dwelling_sqm"] == config["valuer_roll"]["typical_dwelling_sqm"]
    load_layers(config)

    bad = copy.deepcopy(config)
    bad["valuation"]["yield_rate"] = 0.09
    with pytest.raises(LayerConfigError):
        load_layers(bad)


def test_a_key_mapped_twice_raises():
    spec = yaml.safe_load(LAYERS_PATH.read_text(encoding="utf-8"))
    spec["policy"]["keys"] = [*spec["policy"]["keys"], "valuer_roll.yield_rate"]
    with pytest.raises(LayerConfigError):
        validate_layers(spec, load_config())


def test_stamp_hashes_follow_the_layer_that_changed():
    base = load_config()
    policy_changed = merge_config_overrides(base, urban_speculation_discount=0.6)
    yield_changed = merge_config_overrides(base, yield_rate=0.04)
    original = engine_stamp(base)
    policy = engine_stamp(policy_changed)
    valuation = engine_stamp(yield_changed)

    assert policy["policy"]["inputs_hash"] != original["policy"]["inputs_hash"]
    assert policy["valuation"]["inputs_hash"] == original["valuation"]["inputs_hash"]
    assert valuation["valuation"]["inputs_hash"] != original["valuation"]["inputs_hash"]
    assert valuation["policy"]["inputs_hash"] == original["policy"]["inputs_hash"]
    assert policy["sensitivity_overrides"]["urban_speculation_discount"] == 0.6
    assert valuation["sensitivity_overrides"]["yield_rate"] == 0.04
    valuation_inputs, policy_inputs = split_config(policy_changed)
    assert "urban_speculation_discount" not in json.dumps(valuation_inputs)
    assert policy_inputs["despeculation"]["urban_speculation_discount"] == 0.6


def test_square_postcode_health_and_layer_carry_a_stamp(monkeypatch):
    monkeypatch.delenv("W3W_API_KEY", raising=False)
    holder = {"parcel": None, "feature": None}
    _install_parcel(monkeypatch, holder)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    _assert_stamp(health.json()["stamp"])

    square = client.get("/square", params={"lat": 55.8642, "lng": -4.2518, "scenario": "full_agr"})
    assert square.status_code == 200
    _assert_stamp(square.json()["agr"]["stamp"])

    report = client.get(
        "/assessment/report",
        params={"lat": 55.8642, "lng": -4.2518, "scenario": "full_agr", "include_sales_context": False},
    )
    assert report.status_code == 200, report.text
    body = report.json()
    _assert_stamp(body["assessment"]["stamp"])
    _assert_stamp(body["stamp"])
    assert body["stamp"] == body["assessment"]["stamp"]
    assert body["markdown"].splitlines()[0].startswith("# stamp: ")

    layer = client.get("/layers/councils-agr")
    assert layer.status_code == 200
    _assert_stamp(layer.json()["stamp"])

    class _Response:
        status_code = 200

        def json(self):
            return {
                "result": {
                    "postcode": "G1 1BL",
                    "latitude": 55.8642,
                    "longitude": -4.2518,
                    "parish": None,
                    "admin_district": "Glasgow City",
                    "country": "Scotland",
                }
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return _Response()

    monkeypatch.setattr("api.main.httpx.Client", _Client)
    postcode = client.get("/postcode/G1 1BL", params={"scenario": "full_agr"})
    assert postcode.status_code == 200, postcode.text
    body = postcode.json()
    _assert_stamp(body["agr"]["stamp"])
    assert body["postcode"]["postcode"] == "G1 1BL"


def test_stamp_commit_uses_the_full_sha_when_git_commit_is_set(monkeypatch):
    from agr.layers import _commit_ids

    sha = "a" * 40
    monkeypatch.setenv("GIT_COMMIT", sha)
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    _commit_ids.cache_clear()
    stamp = engine_stamp(load_config())
    assert stamp["commit"] == sha[:7]
    assert stamp["commit_full"] == sha
    health = TestClient(app).get("/health")
    assert health.status_code == 200
    assert health.json()["stamp"]["commit"] == sha[:7]
    assert health.json()["stamp"]["commit_full"] == sha
    _commit_ids.cache_clear()


def test_stamp_commit_is_dev_unknown_without_a_sha_or_git(monkeypatch):
    import subprocess

    from agr.layers import _commit_ids

    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "unknown")

    def _no_git(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "no git")

    monkeypatch.setattr("agr.layers.subprocess.run", _no_git)
    _commit_ids.cache_clear()
    stamp = engine_stamp(load_config())
    assert stamp["commit"] == "dev-unknown"
    assert stamp["commit_full"] == "dev-unknown"
    _commit_ids.cache_clear()
