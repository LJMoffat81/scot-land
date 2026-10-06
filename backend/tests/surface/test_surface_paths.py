"""CI safety: data locations come from env / gitignored local file / repo default; real-data tests skip when absent."""

from pathlib import Path

import pytest

from georgist import surface_paths as sp
from georgist import surface_rent as sr


def test_env_var_wins_and_default_is_repo_relative(monkeypatch, tmp_path):
    monkeypatch.setenv("SCOT_LAND_DATAZONES_DIR", str(tmp_path))
    assert sp.data_dir("datazones") == tmp_path
    assert sp.expand("{datazones_dir}/dwellings_by_year.csv") == f"{tmp_path}/dwellings_by_year.csv"
    monkeypatch.delenv("SCOT_LAND_DATAZONES_DIR")
    monkeypatch.setattr(sp, "LOCAL_OVERRIDE", tmp_path / "missing.yaml")
    assert sp.data_dir("datazones") == sp.REPO_ROOT / "data" / "external" / "datazones"
    with pytest.raises(KeyError):
        sp.data_dir("elsewhere")


def test_no_machine_paths_in_tracked_config():
    text = Path(sr.CONFIG_PATH).read_text(encoding="utf-8")
    assert "/workspace" not in text and "/home/" not in text


DZ = sp.data_dir("datazones") / "dwellings_by_year.csv"


@pytest.mark.skipif(not DZ.exists(), reason="local Data Zones data not present (CI)")
def test_real_datazones_dwellings_manifest_verifies():
    from georgist import surface_harvester as hv
    df = hv.load_dwelling_counts("datazones_ct_table", str(DZ), price_year=2025, vintage=2011)
    assert len(df) == 6976 and int(df["dwellings_total"].sum()) == 2_757_376
