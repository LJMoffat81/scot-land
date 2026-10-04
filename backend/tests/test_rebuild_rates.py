"""Rebuild rates stay labelled, and the old flat-rate fallback is gone."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from agr.config import load_config
from agr.valuation import _blended_rebuild_per_m2
from datasources.rebuild import blended_rebuild_per_m2

ROOT = Path(__file__).resolve().parents[2]
RATE_PATHS = (
    "valuer_roll.rebuild.house_gbp_per_m2",
    "valuer_roll.rebuild.flat_gbp_per_m2",
)
SOURCE_FILES = (
    ROOT / "backend" / "agr" / "valuation.py",
    ROOT / "backend" / "datasources" / "rebuild.py",
)


def setup_function():
    load_config.cache_clear()


def test_both_rates_are_labelled_assumptions():
    config = yaml.safe_load((ROOT / "data" / "config" / "agr.yaml").read_text(encoding="utf-8"))
    meta = config["_meta"]
    for path in RATE_PATHS:
        entry = meta[path]
        assert entry["label"] == "ASSUMPTION"
        assert entry["status"] == "unsourced, temporary"


def test_fallback_rate_is_gone_from_source():
    for path in SOURCE_FILES:
        text = path.read_text(encoding="utf-8")
        assert "2300" not in text


def test_missing_flat_rate_raises():
    config = copy.deepcopy(load_config())
    del config["valuer_roll"]["rebuild"]["flat_gbp_per_m2"]
    with pytest.raises(KeyError, match="flat_gbp_per_m2"):
        _blended_rebuild_per_m2(config)
    with pytest.raises(KeyError, match="flat_gbp_per_m2"):
        blended_rebuild_per_m2(config)
