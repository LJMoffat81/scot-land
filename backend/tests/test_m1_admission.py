"""M1 layer admission test (charter v2 §4): A1-A21. Synthetic fixtures only."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from layers.registry import loader
from layers.registry.admission import (
    CONTEXT_CAP,
    GRANDFATHERED_GAPS,
    AdmissionError,
    check_admission,
)
from layers.registry.loader import RegistryError, load_registry

REGISTRY = Path(__file__).resolve().parents[1] / "layers" / "registry"

EXPECTED_TAGS = {
    "ces-aquaculture": (["Q5"], "value_capture"),
    "councils": ([], "context"),
    "crown-estate-leases": (["Q5"], "value_capture"),
    "dz2022": ([], "context"),
    "hydro-sites": (["Q5"], "commons_rent"),
    "native-woodland": (["Q6"], "natural_capital"),
    "naturescot-designations": (["Q6"], "natural_capital"),
    "naturescot-sssi": (["Q6"], "natural_capital"),
    "nfi": (["Q6"], "natural_capital"),
    "oil-fields": (["Q5"], "commons_rent"),
    "pipelines": (["Q5"], "commons_rent"),
    "platforms": (["Q5"], "commons_rent"),
    "repd": (["Q5"], "commons_rent"),
    "repd-onshore-wind": (["Q5"], "commons_rent"),
    "scotland-extent": ([], "context"),
    "scotwind-intog": (["Q5"], "value_capture"),
    "sepa-car": (["Q5"], "commons_rent"),
    "sepa-flood": ([], "context"),
    "settlements-2022": ([], "context"),
}


def _copy(tmp_path: Path) -> Path:
    for src in REGISTRY.glob("*.yaml"):
        shutil.copy(src, tmp_path / src.name)
    return tmp_path


def _edit(d: Path, layer_id: str, **changes) -> None:
    path = d / f"{layer_id}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is _DROP:
            data.pop(key, None)
        else:
            data[key] = value
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _clone(d: Path, src_id: str, new_id: str, **changes) -> None:
    data = yaml.safe_load((d / f"{src_id}.yaml").read_text(encoding="utf-8"))
    data["id"] = new_id
    (d / f"{new_id}.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    _edit(d, new_id, **changes)


_DROP = object()


def _fails(d: Path, message: str) -> None:
    entries = load_registry(d)
    with pytest.raises(AdmissionError, match="^" + re.escape(message) + "$"):
        check_admission(entries)


def _value_pair(d: Path, **extra_a) -> None:
    _edit(d, "nfi", value_layer=True, net_of=["none"], overlaps_with=["native-woodland"], **extra_a)
    _edit(d, "native-woodland", value_layer=True, net_of=["none"], overlaps_with=["nfi"])


# --- A1-A2: committed registry -------------------------------------------------


def test_a1_committed_registry_admitted_and_tagged():
    entries = load_registry(REGISTRY)
    check_admission(entries)
    got = {
        eid: (e.raw["policy_question"], e.raw["shows"]) for eid, e in entries.items()
    }
    assert got == EXPECTED_TAGS
    assert all(e.raw["value_layer"] is False for e in entries.values())


def test_a2_grandfathered_gaps_are_exact():
    entries = load_registry(REGISTRY)
    with_gaps = {eid for eid, e in entries.items() if e.raw.get("admission_gaps")}
    assert with_gaps == GRANDFATHERED_GAPS


# --- A3-A7: required fields and questions --------------------------------------


@pytest.mark.parametrize("key", ["policy_question", "shows", "value_layer"])
def test_a3_required_field_missing(tmp_path, key):
    d = _copy(tmp_path)
    _edit(d, "repd", **{key: _DROP})
    _fails(d, f"ADMISSION: repd: $.{key}: required")


def test_a4_context_layer_with_question(tmp_path):
    d = _copy(tmp_path)
    _edit(d, "councils", policy_question=["Q1"])
    _fails(d, "ADMISSION: councils: $.policy_question: must be empty for a context layer")


def test_a5_value_question_empty(tmp_path):
    d = _copy(tmp_path)
    _edit(d, "repd", policy_question=[])
    _fails(d, "ADMISSION: repd: $.policy_question: name at least one of Q1-Q6")


@pytest.mark.parametrize(
    "key,value,msg",
    [
        ("policy_question", ["Q7"], "$.policy_question[0]: 'Q7' is not one of"),
        ("policy_question", "Q5", "$.policy_question: 'Q5' is not of type 'array'"),
        ("policy_question", ["Q5", "Q5"], "$.policy_question: ['Q5', 'Q5'] has non-unique elements"),
        ("shows", "rent", "$.shows: 'rent' is not one of"),
        ("shows", "", "$.shows: '' is not one of"),
        ("value_layer", "no", "$.value_layer: 'no' is not of type 'boolean'"),
        ("admission_gaps", [], "$.admission_gaps: [] should be non-empty"),
    ],
)
def test_a6_schema_rejects_bad_values(tmp_path, key, value, msg):
    d = _copy(tmp_path)
    _edit(d, "repd", **{key: value})
    with pytest.raises(RegistryError, match="^" + re.escape(f"REGISTRY: repd: {msg}")):
        load_registry(d)


# --- A7-A8: non-commercial licence tag -----------------------------------------


@pytest.mark.parametrize("value", [_DROP, False])
def test_a7_nsta_needs_non_commercial(tmp_path, value):
    d = _copy(tmp_path)
    _edit(d, "platforms", non_commercial=value)
    _fails(d, "ADMISSION: platforms: $.non_commercial: must be true for licence NSTA-OGL")


def test_a8_ogl_cannot_claim_non_commercial(tmp_path):
    d = _copy(tmp_path)
    _edit(d, "repd", non_commercial=True)
    _fails(d, "ADMISSION: repd: $.non_commercial: licence OGL-3.0 is not non-commercial")


# --- A9-A11: value layers, net_of, overlaps_with ------------------------------


@pytest.mark.parametrize("key", ["net_of", "overlaps_with"])
def test_a9_value_layer_needs_declarations(tmp_path, key):
    d = _copy(tmp_path)
    _value_pair(d)
    _edit(d, "nfi", **{key: _DROP})
    _fails(d, f"ADMISSION: nfi: $.{key}: required for a value layer")


@pytest.mark.parametrize("key,value", [("net_of", ["none"]), ("overlaps_with", [])])
def test_a10_declarations_only_on_value_layer(tmp_path, key, value):
    d = _copy(tmp_path)
    _edit(d, "repd", **{key: value})
    _fails(d, f"ADMISSION: repd: $.{key}: only allowed on a value layer")


def test_a11_context_cannot_be_value(tmp_path):
    d = _copy(tmp_path)
    _edit(d, "councils", value_layer=True, net_of=["none"], overlaps_with=[])
    _fails(d, "ADMISSION: councils: $.value_layer: a context layer cannot be a value layer")


def test_a12_valid_value_pair_admitted(tmp_path):
    d = _copy(tmp_path)
    _value_pair(d)
    check_admission(load_registry(d))


@pytest.mark.parametrize(
    "overlaps,msg",
    [
        (["nfi"], "ADMISSION: nfi: $.overlaps_with: lists itself"),
        (["no-such-layer"], "ADMISSION: nfi: $.overlaps_with: unknown layer no-such-layer"),
        (["repd"], "ADMISSION: nfi: $.overlaps_with: repd is not a value layer"),
    ],
)
def test_a13_overlaps_refs(tmp_path, overlaps, msg):
    d = _copy(tmp_path)
    _value_pair(d)
    _edit(d, "nfi", overlaps_with=overlaps)
    _edit(d, "native-woodland", overlaps_with=[])
    _fails(d, msg)


def test_a14_overlaps_must_be_symmetric(tmp_path):
    d = _copy(tmp_path)
    _value_pair(d)
    _edit(d, "native-woodland", overlaps_with=[])
    _fails(d, "ADMISSION: nfi: $.overlaps_with: native-woodland does not list nfi")


# --- A15-A16: no double counting ----------------------------------------------


@pytest.mark.parametrize("method", ["sum", "area_weighted", "pop_weighted"])
def test_a15_summing_overlapping_value_layers_refused(tmp_path, method):
    d = _copy(tmp_path)
    _value_pair(d)
    _clone(
        d,
        "repd",
        "zz-total",
        lineage={"derived_from": ["nfi", "native-woodland"], "method": method, "roll_up_to": []},
    )
    _fails(
        d,
        "ADMISSION: zz-total: $.lineage.derived_from: "
        "sums overlapping value layers nfi + native-woodland",
    )


@pytest.mark.parametrize(
    "method,overlap",
    [("mean", True), ("median_of_children", True), ("sum", False)],
)
def test_a16_double_count_guard_is_specific(tmp_path, method, overlap):
    d = _copy(tmp_path)
    _value_pair(d)
    if not overlap:
        _edit(d, "nfi", overlaps_with=[])
        _edit(d, "native-woodland", overlaps_with=[])
    _clone(
        d,
        "repd",
        "zz-total",
        lineage={"derived_from": ["nfi", "native-woodland"], "method": method, "roll_up_to": []},
    )
    check_admission(load_registry(d))


# --- A17-A19: vintage and grandfathered gaps ----------------------------------


@pytest.mark.parametrize("value", [_DROP, "   "])
def test_a17_vintage_required(tmp_path, value):
    d = _copy(tmp_path)
    _edit(d, "repd", vintage=value)
    _fails(d, "ADMISSION: repd: $.vintage: required (charter v2 §4.5)")


def test_a18_new_layer_cannot_declare_gaps(tmp_path):
    d = _copy(tmp_path)
    _edit(d, "repd", vintage=_DROP, admission_gaps=["vintage"])
    _fails(d, "ADMISSION: repd: $.admission_gaps: only pre-M1 layers may declare gaps")


def test_a19_stale_gap_refused(tmp_path):
    d = _copy(tmp_path)
    _edit(d, "councils", vintage="Boundary-Line 2026")
    _fails(d, "ADMISSION: councils: $.admission_gaps: stale gap 'vintage'")


# --- A20: context cap ----------------------------------------------------------


def test_a20_context_cap(tmp_path):
    d = _copy(tmp_path)
    ctx = dict(policy_question=[], shows="context")
    current = sum(1 for v in EXPECTED_TAGS.values() if v[1] == "context")
    for i in range(CONTEXT_CAP - current):
        _clone(d, "repd", f"zz-ctx-{i}", **ctx)
    check_admission(load_registry(d))
    _clone(d, "repd", "zz-ctx-over", **ctx)
    entries = load_registry(d)
    with pytest.raises(AdmissionError, match=r"^ADMISSION: context layers 7 > cap 6: "):
        check_admission(entries)


# --- A21-A22: wiring and clip parity -------------------------------------------


def test_a21_registry_runs_admission(monkeypatch, tmp_path):
    d = _copy(tmp_path)
    _edit(d, "repd", shows=_DROP)
    bad = load_registry(d)
    monkeypatch.setattr(loader, "_CACHE", None)
    monkeypatch.setattr(loader, "load_registry", lambda *a, **k: bad)
    with pytest.raises(AdmissionError, match=r"^ADMISSION: repd: \$\.shows: required$"):
        loader.registry()
    assert loader._CACHE is None


def test_a22_clip_enum_matches_pipeline_zones():
    from etl.run_layer import CLIP_ZONES

    schema = json.loads((REGISTRY / "schema.json").read_text(encoding="utf-8"))
    vector = set(schema["properties"]["clip"]["enum"]) - {"none"}
    assert vector == set(CLIP_ZONES)
    entries = load_registry(REGISTRY)
    for eid, e in entries.items():
        assert e.raw["clip"] in CLIP_ZONES, eid
