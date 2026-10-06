"""scripts/check_publishable.py: the public-repo guard catches what it must, passes clean data."""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[2] / "scripts" / "check_publishable.py"


def _guard():
    spec = importlib.util.spec_from_file_location("check_publishable", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _repo(tmp_path, files: dict[str, str]):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", "."], check=True)


def _problems(tmp_path):
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        g = _guard()
        return g.check(g.tracked())
    finally:
        os.chdir(cwd)


def test_clean_repo_passes(tmp_path):
    _repo(tmp_path, {
        "data/processed/x/manifest.csv": "file,publish_level\nok.csv,public_zone\n",
        "data/processed/x/ok.csv": "code,vintage,streetlight_share,n_res_uprn,share_res_uprn_in_parcels,"
                                   "res_uprn_exceeds_dwellings\nS01006506,2011,0.1,3,0.5,False\n",
        "etl/gis/build_dz_detached_plot_bands.py": "# code may name it\n",
    })
    assert _problems(tmp_path) == []


@pytest.mark.parametrize("files, needle", [
    ({"data/processed/x/manifest.csv": "file,publish_level\ns.csv,internal\n",
      "data/processed/x/s.csv": "code\n"}, "publish_level=internal"),
    ({"etl/gis/raw/download.zip": "x"}, "raw/ folder"),
    ({"data/processed/x/a.csv": "\ufeffcode,Postcode\n"}, "Postcode"),
    ({"data/processed/x/a.csv": "id,UPRN\n"}, "UPRN"),
    ({"data/processed/x/a.tsv": "id\taddress_line1\n"}, "address_line1"),
    ({"data/spatial_hub/parcels.txt": "x"}, "Spatial Hub"),
    ({"data/processed/gis/svdls_sites.gpkg": "x"}, "GeoPackage"),
    ({"data/processed/gis/hls_sites.gpkg": "x"}, "GeoPackage"),
    ({"data/processed/gis/internal/dz_svdls_rollup_with_inspire.csv": "code\n"}, "internal/ folder"),
    ({"data/processed/gis/dz_svdls_rollup_with_inspire.csv": "code\n"}, "INSPIRE"),
    ({"data/processed/gis/manifest.csv": "file,publish_level\ndz_detached_plot_bands.csv,internal\n",
      "data/processed/gis/dz_detached_plot_bands.csv": "code,vintage\n"}, "publish_level=internal"),
    ({"data/processed/gis/dz_detached_plot_bands.csv": "code,vintage\n"}, "plot-band"),  # even unlisted
    ({"frontend/public/tiles/parcels.pmtiles": "x"}, "tile"),
    ({"data/processed/gis/parcel_outlines.geojson": "{}"}, "parcel"),
    ({"data/processed/x/a.csv": "code,res_uprn\n"}, "res_uprn"),
])
def test_guard_fails(tmp_path, files, needle):
    problems = _problems(tmp_path) if _repo(tmp_path, files) is None else None
    assert any(needle in p for p in problems), problems


def test_this_repo_passes():
    root = GUARD.parents[1]
    if not (root / ".git").exists():
        pytest.skip("not a git checkout")
    r = subprocess.run(["python3", str(GUARD)], cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
