"""DRC-TOL-1. SYNTHETIC labelled fixtures only. No price file is read.

The golden sha was recorded from build_v14_drc on the existing v1.4 DRC
fixtures at ee0fca249397e86eab4720309ad4817deef12105, before this tolerance.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

import pytest

from georgist import surface_costs as sc
from georgist import surface_rent as sr
from georgist.v14_primary_inputs import (
    DRC_REL_TOL,
    DepreciationMethodError,
    v14_depreciation,
    zone_drc_v14,
)
from georgist.v14_primary_inputs import math as primary_math
from scripts.build_v14_drc import drc_map_from_components
from scripts.build_v14_drc import main as build_v14_drc
from scripts.build_v14_drc_components import build_components, copy_pin_table, sha256_file

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v14_pr3a"
PRIMARY_INPUTS = (
    Path(__file__).resolve().parents[1] / "georgist" / "v14_primary_inputs.py"
)
# Byte-identical output of build_v14_drc on the v1.4 component fixtures at main.
GOLDEN_DRC_SHA256 = "7ca18fd527f18bcdb66bcb0b4df664451b5de992c2fd22af041ec13ce69fa939"
def _ok_central() -> sr.RebuildResult:
    """A no-age-mix zone that already satisfies the frozen remaining factor."""
    frozen = sr.no_age_mix_remaining_factor(v14_depreciation())
    rebuild = 1000.0
    return sr.RebuildResult(
        rebuild_new_gbp=rebuild,
        drc_gbp=rebuild * frozen,
        remaining_factor=frozen,
    )

MSG_V2 = (
    "DRC is not rebuild cost times remaining factor: "
    "drc=1000000.001 expected=1000000.0 rel_tol=1e-12"
)
MSG_V3_REFUSE = (
    "DRC is not rebuild cost times remaining factor: "
    "drc=1000000.0000019999 expected=1000000.0 rel_tol=1e-12"
)
MSG_V4 = (
    "DRC is not rebuild cost times remaining factor: "
    "drc=nan expected=1000000.0 rel_tol=1e-12"
)
MSG_V4A = (
    "DRC is not rebuild cost times remaining factor: "
    "drc=inf expected=1000000.0 rel_tol=1e-12"
)
MSG_V4B = (
    "DRC is not rebuild cost times remaining factor: "
    "drc=inf expected=inf rel_tol=1e-12"
)
MSG_V4C = (
    "DRC is not rebuild cost times remaining factor: "
    "drc=1000000.0 expected=nan rel_tol=1e-12"
)
MSG_V4D = (
    "DRC is not rebuild cost times remaining factor: "
    "drc=-inf expected=1000000.0 rel_tol=1e-12"
)


def _result(drc: float, rebuild: float, remaining: float) -> sr.RebuildResult:
    return sr.RebuildResult(
        rebuild_new_gbp=rebuild,
        drc_gbp=drc,
        remaining_factor=remaining,
    )


def _patch_rebuilds(monkeypatch: pytest.MonkeyPatch, by_code: dict[str, sr.RebuildResult]) -> None:
    def fake(**kwargs):
        central = by_code[kwargs["code"]]
        return {"central": central}

    monkeypatch.setattr(sc, "zone_cost_rebuilds", fake)
    monkeypatch.setattr("georgist.v14_primary_inputs.sc.zone_cost_rebuilds", fake)


def _call(code: str = "Z1") -> sr.RebuildResult:
    cfg = sr.load_config()
    return zone_drc_v14(
        code=code,
        epc_row=None,
        nrs2017_row=None,
        estate_row=None,
        cfg=cfg,
        band={},
        valuation_year=2025,
        defaults={},
    )


def _assert_refuses(monkeypatch: pytest.MonkeyPatch, central: sr.RebuildResult, message: str) -> None:
    _patch_rebuilds(monkeypatch, {"Z1": central})
    with pytest.raises(DepreciationMethodError) as raised:
        _call("Z1")
    assert str(raised.value) == message


def _assert_build_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bad: sr.RebuildResult,
) -> None:
    """Second zone refuses. No file, no writer call, no partial frame."""
    _patch_rebuilds(monkeypatch, {"ZOK": _ok_central(), "ZBAD": bad})
    writes = {"n": 0}

    def write(*_args, **_kwargs) -> None:
        writes["n"] += 1

    monkeypatch.setattr("scripts.build_v14_drc.write_drc_json", write)
    returned: list[dict] = []

    def wrapped(*args, **kwargs):
        result = drc_map_from_components(*args, **kwargs)
        returned.append(result)
        return result

    monkeypatch.setattr("scripts.build_v14_drc.drc_map_from_components", wrapped)
    components = tmp_path / "components.json"
    components.write_text(
        json.dumps(
            [
                {
                    "dz2011": "ZOK",
                    "label": "SYNTHETIC",
                    "epc_row": None,
                    "nrs2017_row": None,
                    "estate_row": None,
                },
                {
                    "dz2011": "ZBAD",
                    "label": "SYNTHETIC",
                    "epc_row": None,
                    "nrs2017_row": None,
                    "estate_row": None,
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "drc.json"
    code = build_v14_drc(["--drc-json", str(out), "--components", str(components)])
    assert code == 1
    assert not out.exists()
    assert writes["n"] == 0
    assert returned == []


def test_v1_near_equal_pair_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. The real-looking pair that exact equality refuses."""
    central = _result(124695.14520228098, 124695.145202281, 1.0)
    assert central.rebuild_new_gbp * central.remaining_factor == 124695.145202281
    _patch_rebuilds(monkeypatch, {"Z1": central})
    got = _call()
    assert got is central
    assert got.drc_gbp == 124695.14520228098


def test_v2_one_e_minus_9_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SYNTHETIC. Relative difference 1.0000000464974512e-09 refuses."""
    central = _result(1000000.001, 1000000.0, 1.0)
    _assert_refuses(monkeypatch, central, MSG_V2)
    _assert_build_writes_nothing(monkeypatch, tmp_path, central)


def test_v3_half_tolerance_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. Relative difference 5.00003807246435e-13 passes."""
    central = _result(1000000.0000005, 1000000.0, 1.0)
    assert central.rebuild_new_gbp * central.remaining_factor == 1000000.0
    _patch_rebuilds(monkeypatch, {"Z1": central})
    got = _call()
    assert got is central
    assert got.drc_gbp == 1000000.0000005


def test_v3_two_tolerance_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SYNTHETIC. Relative difference 1.9998988136609138e-12 refuses."""
    central = _result(1000000.0000019999, 1000000.0, 1.0)
    _assert_refuses(monkeypatch, central, MSG_V3_REFUSE)
    _assert_build_writes_nothing(monkeypatch, tmp_path, central)


def test_v4_nan_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SYNTHETIC. A NaN depreciated replacement cost refuses."""
    central = _result(float("nan"), 1000000.0, 1.0)
    _assert_refuses(monkeypatch, central, MSG_V4)
    _assert_build_writes_nothing(monkeypatch, tmp_path, central)


def test_v4a_inf_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SYNTHETIC. An infinite depreciated replacement cost refuses."""
    central = _result(float("inf"), 1000000.0, 1.0)
    _assert_refuses(monkeypatch, central, MSG_V4A)
    _assert_build_writes_nothing(monkeypatch, tmp_path, central)


def test_v4b_inf_pair_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SYNTHETIC. inf compared with inf is finite-checked before isclose."""
    central = _result(float("inf"), float("inf"), 1.0)
    _assert_refuses(monkeypatch, central, MSG_V4B)
    _assert_build_writes_nothing(monkeypatch, tmp_path, central)


def test_v4c_nan_rebuild_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SYNTHETIC. A NaN rebuild cost is truthy and refuses."""
    central = _result(1000000.0, float("nan"), 1.0)
    assert bool(central.rebuild_new_gbp) is True
    _assert_refuses(monkeypatch, central, MSG_V4C)
    _assert_build_writes_nothing(monkeypatch, tmp_path, central)


def test_v4d_negative_inf_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SYNTHETIC. Negative infinity refuses."""
    central = _result(float("-inf"), 1000000.0, 1.0)
    _assert_refuses(monkeypatch, central, MSG_V4D)
    _assert_build_writes_nothing(monkeypatch, tmp_path, central)


def test_v5_zero_rebuild_skips_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A zero rebuild cost skips the comparison."""
    central = _result(5.0, 0.0, 0.5)
    calls = {"n": 0}
    real = math.isclose

    def spy(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(primary_math, "isclose", spy)
    _patch_rebuilds(monkeypatch, {"Z1": central})
    got = _call()
    assert calls["n"] == 0
    assert got is central
    assert got.drc_gbp == 5.0
    assert got.rebuild_new_gbp == 0.0
    assert got.remaining_factor == 0.5


def test_v6_rel_tol_and_abs_tol_are_pinned() -> None:
    """The isclose call uses DRC_REL_TOL and abs_tol 0.0."""
    assert DRC_REL_TOL == 1e-12
    tree = ast.parse(PRIMARY_INPUTS.read_text(encoding="utf-8"))
    assigned = False
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "DRC_REL_TOL":
                assert isinstance(node.value, ast.Constant)
                assert node.value.value == 1e-12
                assigned = True
    assert assigned
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_isclose = (
            isinstance(func, ast.Attribute)
            and func.attr == "isclose"
            and isinstance(func.value, ast.Name)
            and func.value.id == "math"
        )
        if not is_isclose:
            continue
        kwargs = {keyword.arg: keyword.value for keyword in node.keywords}
        rel = kwargs["rel_tol"]
        abs_tol = kwargs["abs_tol"]
        assert isinstance(rel, ast.Name) and rel.id == "DRC_REL_TOL"
        assert isinstance(abs_tol, ast.Constant) and abs_tol.value == 0.0
        found = True
    assert found


def test_v7_existing_fixtures_keep_the_same_bytes(tmp_path: Path) -> None:
    """SYNTHETIC. Existing v1.4 DRC fixtures stay byte-identical."""
    paths = {
        "epc": FIXTURES / "epc.csv",
        "nrs2017": FIXTURES / "nrs2017.csv",
        "plot_bands": FIXTURES / "plot_bands.csv",
        "ur6": FIXTURES / "ur6.csv",
        "n25i": FIXTURES / "n25i.xlsx",
    }
    for path in paths.values():
        if path.suffix == ".csv":
            assert "SYNTHETIC" in path.read_text(encoding="utf-8")
    pins = copy_pin_table()
    for name, path in paths.items():
        pins[name] = sha256_file(path)
    records = build_components(paths, pins=pins)
    components = tmp_path / "components.json"
    components.write_text(json.dumps(records) + "\n", encoding="utf-8")
    out = tmp_path / "drc.json"
    code = build_v14_drc(["--drc-json", str(out), "--components", str(components)])
    assert code == 0
    blob = out.read_bytes()
    assert "£" not in blob.decode("utf-8")
    assert hashlib.sha256(blob).hexdigest() == GOLDEN_DRC_SHA256
