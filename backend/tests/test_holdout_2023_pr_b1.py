"""HOLDOUT-2023-RUN PR-B1: DRC corners. SYNTHETIC fixtures only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from georgist import surface_rent as sr
from georgist.v14_primary_inputs import DepreciationMethodError, zone_drc_v14_corners
from scripts.build_v14_drc import main as build_v14_drc
from scripts.build_v14_drc_components import build_components, copy_pin_table, sha256_file

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v14_pr3a"
GOLDEN_DRC_SHA256 = "7ca18fd527f18bcdb66bcb0b4df664451b5de992c2fd22af041ec13ce69fa939"


def _components(tmp_path: Path) -> Path:
    paths = {
        "epc": FIXTURES / "epc.csv",
        "nrs2017": FIXTURES / "nrs2017.csv",
        "plot_bands": FIXTURES / "plot_bands.csv",
        "ur6": FIXTURES / "ur6.csv",
        "n25i": FIXTURES / "n25i.xlsx",
    }
    pins = copy_pin_table()
    for name, path in paths.items():
        pins[name] = sha256_file(path)
    out = tmp_path / "components.json"
    out.write_text(json.dumps(build_components(paths, pins=pins)) + "\n", encoding="utf-8")
    return out


def _run(tmp_path: Path) -> tuple[int, Path, Path]:
    drc = tmp_path / "drc.json"
    corners = tmp_path / "drc_corners.json"
    code = build_v14_drc(
        ["--drc-json", str(drc), "--components", str(_components(tmp_path)), "--corners-out", str(corners)]
    )
    return code, drc, corners


def test_corners_written_and_drc_json_unchanged(tmp_path: Path) -> None:
    code, drc, corners = _run(tmp_path)
    assert code == 0
    assert hashlib.sha256(drc.read_bytes()).hexdigest() == GOLDEN_DRC_SHA256
    central = json.loads(drc.read_text(encoding="utf-8"))
    payload = json.loads(corners.read_text(encoding="utf-8"))
    assert "P_H" in payload["note"] and "P_L" in payload["note"]
    assert set(payload["zones"]) == set(central)
    for zone, row in payload["zones"].items():
        assert set(row) == {"drc_low", "drc_central", "drc_high"}
        assert row["drc_central"] == central[zone]
        assert row["drc_low"] <= row["drc_central"] <= row["drc_high"]
    assert any(row["drc_low"] < row["drc_high"] for row in payload["zones"].values())
    assert "\u00a3" not in corners.read_text(encoding="utf-8")


def test_no_corners_flag_writes_no_corner_file(tmp_path: Path) -> None:
    drc = tmp_path / "drc.json"
    code = build_v14_drc(["--drc-json", str(drc), "--components", str(_components(tmp_path))])
    assert code == 0
    assert not (tmp_path / "drc_corners.json").exists()


def _result(drc: float) -> sr.RebuildResult:
    return sr.RebuildResult(rebuild_new_gbp=drc, drc_gbp=drc, remaining_factor=1.0)


def test_swapped_corners_refused_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(
        "scripts.build_v14_drc.zone_drc_v14_corners",
        lambda **_k: {"low": _result(3.0), "central": _result(2.0), "high": _result(1.0)},
    )
    code, _drc, corners = _run(tmp_path)
    assert code == 1
    assert not corners.exists()
    err = capsys.readouterr().err.strip()
    assert err.startswith("B1_DRC_CORNERS: REFUSED: order zone ")
    assert err.endswith(": expected low<=central<=high, got other")


def test_central_disagreeing_with_drc_json_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(
        "scripts.build_v14_drc.zone_drc_v14_corners",
        lambda **_k: {"low": _result(1.0), "central": _result(1.5), "high": _result(9e12)},
    )
    code, drc, corners = _run(tmp_path)
    assert code == 1
    assert not drc.exists() and not corners.exists()
    assert "expected equal to --drc-json, got different" in capsys.readouterr().err


def test_missing_corner_refused_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "georgist.v14_primary_inputs.sc.zone_cost_rebuilds",
        lambda **_k: {"central": _result(1.0), "high": _result(2.0)},
    )
    with pytest.raises(DepreciationMethodError) as raised:
        zone_drc_v14_corners(cfg=sr.load_config(), code="Z1")
    assert str(raised.value) == "DRC corners: expected low,central,high, got missing low"


def test_each_corner_passes_drc_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = sr.RebuildResult(rebuild_new_gbp=10.0, drc_gbp=11.0, remaining_factor=1.0)
    monkeypatch.setattr(
        "georgist.v14_primary_inputs.sc.zone_cost_rebuilds",
        lambda **_k: {"low": bad, "central": _result(1.0), "high": _result(2.0)},
    )
    with pytest.raises(DepreciationMethodError) as raised:
        zone_drc_v14_corners(cfg=sr.load_config(), code="Z1")
    assert str(raised.value).startswith("DRC is not rebuild cost times remaining factor")
