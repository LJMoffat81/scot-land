"""M1-VINTAGES: the 7 pre-M1 layers now declare vintage (V1-V5). Synthetic fixtures only."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml

from layers.registry.admission import GRANDFATHERED_GAPS, AdmissionError, check_admission
from layers.registry.loader import RegistryError, load_registry

REGISTRY = Path(__file__).resolve().parents[1] / "layers" / "registry"

EXPECTED_VINTAGES = {
    "councils": "OS Boundary-Line 2026-10",
    "dz2022": "ref 2022-03-20 (Census Day), published 2024-12-16",
    "oil-fields": "NSTA live feed, dataLastEditDate recorded at fetch",
    "pipelines": "NSTA infrastructure 2026-07-01",
    "platforms": "NSTA infrastructure 2026-07-01",
    "scotland-extent": (
        "UKHO limits (item modified 2026-05-28) + OS Boundary-Line 2026-10 + SI 1999/1126"
    ),
    "settlements-2022": "Census 2022 (published 2024-05-21)",
}
FORMER = sorted(EXPECTED_VINTAGES)


def _copy(tmp_path: Path) -> Path:
    for src in REGISTRY.glob("*.yaml"):
        shutil.copy(src, tmp_path / src.name)
    return tmp_path


def _edit(d: Path, layer_id: str, **changes) -> None:
    path = d / f"{layer_id}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _fails(d: Path, message: str) -> None:
    entries = load_registry(d)
    with pytest.raises(AdmissionError, match="^" + re.escape(message) + "$"):
        check_admission(entries)


def test_v1_grandfathered_gaps_empty():
    assert GRANDFATHERED_GAPS == frozenset()
    assert not set(FORMER) & GRANDFATHERED_GAPS


def test_v2_committed_vintages_exact_and_no_gaps():
    entries = load_registry(REGISTRY)
    check_admission(entries)
    assert {eid: entries[eid].raw.get("vintage") for eid in FORMER} == EXPECTED_VINTAGES
    assert {eid for eid, e in entries.items() if "admission_gaps" in e.raw} == set()
    assert all(
        isinstance(e.raw.get("vintage"), str) and e.raw["vintage"].strip()
        for e in entries.values()
    )
    assert not any("2026-01-07" in e.raw.get("vintage", "") for e in entries.values())


@pytest.mark.parametrize("layer_id", FORMER)
@pytest.mark.parametrize("value", [None, "   "])
def test_v3_blank_vintage_now_fails(tmp_path, layer_id, value):
    d = _copy(tmp_path)
    _edit(d, layer_id, vintage=value)
    _fails(d, f"ADMISSION: {layer_id}: $.vintage: required (charter v2 §4.5)")


@pytest.mark.parametrize("layer_id", FORMER)
def test_v4_empty_string_vintage_rejected_by_schema(tmp_path, layer_id):
    d = _copy(tmp_path)
    _edit(d, layer_id, vintage="")
    with pytest.raises(
        RegistryError,
        match="^" + re.escape(f"REGISTRY: {layer_id}: $.vintage: '' should be non-empty"),
    ):
        load_registry(d)


@pytest.mark.parametrize("layer_id", FORMER)
def test_v5_former_layer_cannot_redeclare_gap(tmp_path, layer_id):
    d = _copy(tmp_path)
    _edit(d, layer_id, vintage=None, admission_gaps=["vintage"])
    _fails(d, f"ADMISSION: {layer_id}: $.admission_gaps: only pre-M1 layers may declare gaps")
