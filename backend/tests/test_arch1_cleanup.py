"""ARCH-1a cleanup coverage folded into 1b when budget allows."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
import yaml

from etl.build_scotland_extent import ExtentError, load_only
from layers.registry.loader import RegistryError, load_registry

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "arch1"


def _dsn() -> str:
    dsn = os.environ.get("ARCH1_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("ARCH1_TEST_DSN not set")
    return dsn


def test_clip_extent_file_not_geojson(monkeypatch, tmp_path):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    dest = tmp_path / "scotland_extent.27700.geojson"
    body = b"this is not json {{{"
    dest.write_bytes(body)
    sha = hashlib.sha256(body).hexdigest()
    (tmp_path / "manifest.csv").write_text(
        f"file,sha256\nscotland_extent.27700.geojson,{sha}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "etl.build_scotland_extent.MANIFEST_PATH", tmp_path / "manifest.csv"
    )
    with pytest.raises(ExtentError, match=r"CLIP: extent file not GeoJSON:"):
        load_only(dest)


def test_registry_empty_yaml(tmp_path):
    (tmp_path / "sample.yaml").write_text("", encoding="utf-8")
    with pytest.raises(RegistryError, match=r"REGISTRY: sample:"):
        load_registry(tmp_path)


def test_registry_invalid_yaml(tmp_path):
    (tmp_path / "sample.yaml").write_text(
        "id: [unterminated\n", encoding="utf-8"
    )
    with pytest.raises((RegistryError, yaml.YAMLError)):
        load_registry(tmp_path)


def test_registry_bool_and_float_values(tmp_path):
    # Bool where a string is required, float where an int enum/const is required.
    data = {
        "id": "sample",
        "title": True,  # bool instead of string
        "geography": "scotland",
        "clip": "sea",
        "unit": "none",
        "licence": "NSTA-OGL",
        "attribution": "Test",
        "source": {
            "type": "arcgis",
            "url": "https://example.com/FeatureServer/0/query",
            "where": "1=1",
        },
        "geometry": "polygon",
        "refresh": {"cron": "0 4 * * 1", "max_mb": 10.5, "max_s": 60},
        "serve": {
            "mode": "geojson",
            "simplify_m": 0,
            "precision_dp": 6.5,  # float not int
            "max_mb": 15,
        },
        "zoom": {"min": 0, "max": 14, "low_zoom": "simplify"},
        "style": {},
        "legend": [],
        "lineage": {
            "derived_from": [],
            "method": "source",
            "roll_up_to": [],
        },
    }
    (tmp_path / "sample.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(RegistryError, match=r"REGISTRY: sample:"):
        load_registry(tmp_path)
