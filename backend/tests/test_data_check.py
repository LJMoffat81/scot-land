"""Runs scripts/data_check.py: the repo passes, and a Hutton-named file fails."""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(ROOT, "scripts", "data_check.py")


def run(args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


def test_repo_passes_data_check():
    r = run([ROOT, "--ref", "HEAD", "--base", "HEAD", "--json"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout)["result"] == "PASS"


def test_hutton_named_file_fails(tmp_path):
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(git[:3] + ["init", "-q"], check=True)
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "README.md").write_text("x\n")
    (tmp_path / "data" / "config").mkdir(parents=True)
    (tmp_path / "data" / "config" / "README.md").write_text("x\n")
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-qm", "base"], check=True)
    (tmp_path / "data" / "lca_test.geojson").write_text('{"type":"FeatureCollection","features":[]}')
    r = run([str(tmp_path), "--ref", "HEAD", "--base", "HEAD"])
    assert r.returncode == 1, r.stdout + r.stderr


def test_bad_checkout_exits_2(tmp_path):
    assert run([str(tmp_path / "missing")]).returncode == 2
