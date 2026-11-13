"""M1-CLOSE-1: fail-closed edges of the charter v2 §4 rule 6b fields. Synthetic fixtures only.

Every refusal asserts the full message, anchored at both ends, on a copy of the
committed registry with exactly one edit (or one synthetic value pair, which the
positive controls K1 and K7 prove is otherwise admitted). Schema refusals are
``RegistryError`` raised by ``load_registry`` and are asserted not to be
``AdmissionError``, which proves the admission code never ran.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml

from layers.registry.admission import AdmissionError, check_admission
from layers.registry.loader import RegistryError, load_registry

REGISTRY = Path(__file__).resolve().parents[1] / "layers" / "registry"
SLUG = "^[a-z0-9]+(-[a-z0-9]+)*$"
_DROP = object()


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
    (d / f"{new_id}.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    _edit(d, new_id, **changes)


def _value_pair(d: Path, overlap: bool = True) -> None:
    _edit(
        d,
        "nfi",
        value_layer=True,
        net_of=["none"],
        overlaps_with=["native-woodland"] if overlap else [],
    )
    _edit(
        d,
        "native-woodland",
        value_layer=True,
        net_of=["none"],
        overlaps_with=["nfi"] if overlap else [],
    )


def _schema_fails(d: Path, message: str) -> None:
    with pytest.raises(RegistryError, match="^" + re.escape(message) + "$") as info:
        load_registry(d)
    assert type(info.value) is RegistryError


def _admission_fails(d: Path, message: str) -> None:
    entries = load_registry(d)
    with pytest.raises(AdmissionError, match="^" + re.escape(message) + "$"):
        check_admission(entries)


# --- K1-K4: net_of ---------------------------------------------------------------


@pytest.mark.parametrize(
    "net_of",
    [["none"], ["zz-take-a"], ["zz-take-a", "zz-take-b"], ["zz2"]],
)
def test_k1_valid_net_of_admitted(tmp_path, net_of):
    d = _copy(tmp_path)
    _value_pair(d)
    _edit(d, "nfi", net_of=net_of)
    check_admission(load_registry(d))


@pytest.mark.parametrize(
    "item",
    ["", "   ", " none", "none ", "None", "zz take", "zz_take", "-zz", "zz-", "zz--take"],
)
def test_k2_net_of_item_must_be_a_slug(tmp_path, item):
    d = _copy(tmp_path)
    _value_pair(d)
    _edit(d, "nfi", net_of=[item])
    _schema_fails(d, f"REGISTRY: nfi: $.net_of[0]: {item!r} does not match {SLUG!r}")


@pytest.mark.parametrize(
    "net_of,msg",
    [
        ([], "$.net_of: [] should be non-empty"),
        (None, "$.net_of: None is not of type 'array'"),
        ("none", "$.net_of: 'none' is not of type 'array'"),
        (["zz-take-a", "zz-take-a"], "$.net_of: ['zz-take-a', 'zz-take-a'] has non-unique elements"),
    ],
)
def test_k3_net_of_shape(tmp_path, net_of, msg):
    d = _copy(tmp_path)
    _value_pair(d)
    _edit(d, "nfi", net_of=net_of)
    _schema_fails(d, f"REGISTRY: nfi: {msg}")


@pytest.mark.parametrize(
    "net_of",
    [["none", "zz-take-a"], ["zz-take-a", "none"], ["zz-take-a", "none", "zz-take-b"]],
)
def test_k4_net_of_none_stands_alone(tmp_path, net_of):
    d = _copy(tmp_path)
    _value_pair(d)
    _edit(d, "nfi", net_of=net_of)
    _admission_fails(d, "ADMISSION: nfi: $.net_of: 'none' cannot be combined with other entries")


# --- K5: overlaps_with shape -----------------------------------------------------


@pytest.mark.parametrize(
    "overlaps,msg",
    [
        ([""], "$.overlaps_with[0]: '' does not match '^[a-z0-9-]+$'"),
        (["   "], "$.overlaps_with[0]: '   ' does not match '^[a-z0-9-]+$'"),
        (["NFI"], "$.overlaps_with[0]: 'NFI' does not match '^[a-z0-9-]+$'"),
        (["native-woodland "], "$.overlaps_with[0]: 'native-woodland ' does not match '^[a-z0-9-]+$'"),
        (None, "$.overlaps_with: None is not of type 'array'"),
        ("native-woodland", "$.overlaps_with: 'native-woodland' is not of type 'array'"),
        (
            ["native-woodland", "native-woodland"],
            "$.overlaps_with: ['native-woodland', 'native-woodland'] has non-unique elements",
        ),
    ],
)
def test_k5_overlaps_with_shape(tmp_path, overlaps, msg):
    d = _copy(tmp_path)
    _value_pair(d)
    _edit(d, "nfi", overlaps_with=overlaps)
    _schema_fails(d, f"REGISTRY: nfi: {msg}")


# --- K6-K7: the same value layer summed twice ----------------------------------


@pytest.mark.parametrize("method", ["sum", "area_weighted", "pop_weighted"])
@pytest.mark.parametrize("overlap", [True, False])
def test_k6_summing_one_value_layer_twice_refused(tmp_path, method, overlap):
    d = _copy(tmp_path)
    _value_pair(d, overlap=overlap)
    _clone(
        d,
        "repd",
        "zz-total",
        lineage={"derived_from": ["nfi", "nfi"], "method": method, "roll_up_to": []},
    )
    _admission_fails(d, "ADMISSION: zz-total: $.lineage.derived_from: sums value layer nfi twice")


@pytest.mark.parametrize(
    "derived_from,method",
    [
        (["nfi", "nfi"], "mean"),
        (["nfi", "nfi"], "median_of_children"),
        (["repd", "repd"], "sum"),
        (["nfi"], "sum"),
    ],
)
def test_k7_double_parent_guard_is_specific(tmp_path, derived_from, method):
    d = _copy(tmp_path)
    _value_pair(d, overlap=False)
    _clone(
        d,
        "repd",
        "zz-total",
        lineage={"derived_from": derived_from, "method": method, "roll_up_to": []},
    )
    check_admission(load_registry(d))


# --- K8: unknown and mistyped rule 6b keys -------------------------------------


@pytest.mark.parametrize(
    "key", ["overlap_with", "overlaps", "netof", "net_off", "policy_questions", "value"]
)
def test_k8_unknown_key_refused(tmp_path, key):
    d = _copy(tmp_path)
    _edit(d, "repd", **{key: ["zz"]})
    _schema_fails(
        d, f"REGISTRY: repd: $: Additional properties are not allowed ({key!r} was unexpected)"
    )
