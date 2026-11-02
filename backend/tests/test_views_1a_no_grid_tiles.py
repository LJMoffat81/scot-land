"""VIEWS-1a: Scot-LAND estimates stop at Data Zone (G1-G5). Synthetic fixtures only."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml

from api import tiles_routes
from layers.registry.admission import SUB_DZ_GRID_RE, AdmissionError, check_admission
from layers.registry.loader import load_registry
from tiles import build

REGISTRY = Path(__file__).resolve().parents[1] / "layers" / "registry"
MSG = (
    "ADMISSION: {id}: $.{field}: Scot-LAND estimates stop at Data Zone; "
    "no 3 m grid or cell tiles"
)
GRID_IDS = ["grid3", "grid-3m", "cell-grid", "agr-cells", "squares", "square", "3m", "dz-3m"]
OK_IDS = ["councils", "dz2022", "griddle", "cellar", "sepa-nfra-grid", "squared-up", "m3"]


def _copy(tmp_path: Path) -> Path:
    for src in REGISTRY.glob("*.yaml"):
        shutil.copy(src, tmp_path / src.name)
    return tmp_path


def test_g1_committed_registry_has_no_grid_layer():
    entries = load_registry(REGISTRY)
    check_admission(entries)
    for eid, entry in entries.items():
        assert not SUB_DZ_GRID_RE.search(eid), eid
        table = (entry.raw.get("source") or {}).get("table") or ""
        assert not SUB_DZ_GRID_RE.search(table), table


@pytest.mark.parametrize("bad_id", GRID_IDS)
def test_g2_grid_id_refused(tmp_path, bad_id):
    d = _copy(tmp_path)
    (d / "councils.yaml").unlink()
    data = yaml.safe_load((REGISTRY / "councils.yaml").read_text(encoding="utf-8"))
    data["id"] = bad_id
    (d / f"{bad_id}.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    entries = load_registry(d)
    with pytest.raises(AdmissionError, match="^" + re.escape(MSG.format(id=bad_id, field="id")) + "$"):
        check_admission(entries)


@pytest.mark.parametrize("table", ["agr_grid3", "cell_grid", "scot_land_squares", "grid_3m_cells"])
def test_g3_grid_table_refused(tmp_path, table):
    d = _copy(tmp_path)
    data = yaml.safe_load((d / "crown-estate-leases.yaml").read_text(encoding="utf-8"))
    data["source"]["table"] = table
    (d / "crown-estate-leases.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    entries = load_registry(d)
    msg = MSG.format(id="crown-estate-leases", field="source.table")
    with pytest.raises(AdmissionError, match="^" + re.escape(msg) + "$"):
        check_admission(entries)


@pytest.mark.parametrize("name", OK_IDS)
def test_g4_pattern_not_overbroad(name):
    assert SUB_DZ_GRID_RE.search(name) is None


def test_g5_public_manifest_and_build_skip_grid(monkeypatch):
    synthetic = {
        "schema": 1,
        "tilesets": {
            "grid3": {"version": "v1"},
            "cell_grid": {"version": "v1"},
            "councils": {"version": "v1"},
        },
    }
    out = tiles_routes._public_manifest(synthetic)
    assert "grid3" not in out["tilesets"] and "cell_grid" not in out["tilesets"]
    built: list[str] = []
    monkeypatch.setattr(build, "build_tileset", lambda lid, **kw: built.append(lid) or lid)
    build.build_all(conn=object())
    assert built, "build_all built nothing"
    assert not [b for b in built if SUB_DZ_GRID_RE.search(b)]
