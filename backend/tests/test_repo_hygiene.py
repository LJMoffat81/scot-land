"""LAYERS-ADD-1 repo hygiene (L7, L8)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_l7_gitignore_covers_data_external():
    result = subprocess.run(
        ["git", "check-ignore", "data/external/x/y.gpkg"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_l7_no_tracked_files_under_data_external():
    result = subprocess.run(
        ["git", "ls-files", "data/external"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    assert not tracked, tracked


def test_l7_no_spatialhub_authkey_assignment_with_value():
    """Fail if a tracked file assigns a non-empty SPATIALHUB_AUTHKEY=… value."""
    pattern = re.compile(
        r"SPATIALHUB_AUTHKEY\s*=\s*['\"]?[A-Za-z0-9_\-]{16,}",
        re.I,
    )
    offenders: list[str] = []
    for path in (REPO / "backend").rglob("*.py"):
        if ".venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, offenders


def test_l8_manual_drop_module_has_no_network_or_terms_automation():
    text = (REPO / "backend" / "harvesters" / "manual_drop.py").read_text(
        encoding="utf-8"
    ).lower()
    for banned in (
        "import httpx",
        "import requests",
        "urllib.request",
        "spatialhub.scot",
        "authkey",
        "/login",
    ):
        assert banned not in text, banned
