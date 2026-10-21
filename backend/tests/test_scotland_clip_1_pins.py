"""Static pins for SCOTLAND-CLIP-1a (P1–P4, P6, P7)."""

from __future__ import annotations

import csv
import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
EXTENT_GLOB = "scotland_extent.*"
R36 = BACKEND / "certs" / "sectigo-public-server-auth-ca-dv-r36.pem"
R36_FINGERPRINT = (
    "8C:54:C3:34:B6:6B:A4:E4:26:77:2A:F4:A3:F9:13:6C:19:A1:AE:C7:29:FD:B2:8C:53:5C:07:A5:A4:EF:22:E0"
)

# Built from parts so this file does not itself contain a token assignment literal.
_TOKEN_LITERAL = re.compile(
    r"(?:token=(?![\*]{3}(?:&|\s|$))[0-9a-fA-F-]{8,})"
    r"|(?:" + "NMPI_WFS_TOKEN" + r"=\S+)"
)
_INSECURE = re.compile(r"verify\s*=\s*False|\s-k\s|--insecure")
_FRONTEND_CLIP = re.compile(
    r"scotland_extent|turf|bboxClip|booleanPointInPolygon", re.IGNORECASE
)


def _tracked_files() -> list[Path]:
    out = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=REPO, text=True
    )
    return [REPO / rel for rel in out.split("\0") if rel]


def _base_branch_name() -> str:
    return (os.environ.get("GITHUB_BASE_REF") or "main").strip() or "main"


def _unshallow_if_needed() -> None:
    """Actions backend checkout defaults to fetch-depth 1 (shallow)."""
    shallow = REPO / ".git" / "shallow"
    if not shallow.is_file():
        return
    subprocess.check_call(
        ["git", "fetch", "--unshallow", "--no-tags", "origin"],
        cwd=REPO,
    )


def _ensure_origin_main() -> str:
    """Return ``origin/<base>`` with enough history for a three-dot merge-base."""
    base_branch = _base_branch_name()
    ref = f"origin/{base_branch}"
    _unshallow_if_needed()
    # Full (non-depth) fetch so merge-base(origin/<base>, HEAD) can resolve.
    subprocess.check_call(
        [
            "git",
            "fetch",
            "--no-tags",
            "origin",
            f"+{base_branch}:refs/remotes/origin/{base_branch}",
        ],
        cwd=REPO,
    )
    merge = subprocess.run(
        ["git", "merge-base", ref, "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if merge.returncode != 0:
        # Rare: still disconnected after unshallow — deepen until merge-base exists.
        for _ in range(40):
            subprocess.check_call(
                ["git", "fetch", "--deepen=50", "--no-tags", "origin"],
                cwd=REPO,
            )
            merge = subprocess.run(
                ["git", "merge-base", ref, "HEAD"],
                cwd=REPO,
                capture_output=True,
                text=True,
            )
            if merge.returncode == 0:
                break
        else:
            raise RuntimeError(
                f"P6/P7: no merge-base between {ref} and HEAD after deepen"
            )
    return ref


def _files_changed_vs_main() -> list[str]:
    """Files introduced on this branch vs main (three-dot; CI-shallow safe)."""
    ref = _ensure_origin_main()
    out = subprocess.check_output(
        ["git", "diff", "--name-only", f"{ref}...HEAD"],
        cwd=REPO,
        text=True,
    )
    return [line for line in out.splitlines() if line]


def test_p1_no_token_literal():
    for path in _tracked_files():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        if _TOKEN_LITERAL.search(text):
            rel = path.relative_to(REPO).as_posix()
            pytest.fail(f"P1: token literal in {rel}")


def test_p2_no_insecure_tls():
    roots = [BACKEND / "etl", BACKEND / "spatial"]
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".sh", ".md"}:
                continue
            text = path.read_text(encoding="utf-8")
            if _INSECURE.search(text):
                rel = path.relative_to(REPO).as_posix()
                pytest.fail(f"P2: insecure TLS in {rel}")


def test_p3_r36_fingerprint():
    assert R36.is_file()
    subject = subprocess.check_output(
        ["openssl", "x509", "-in", str(R36), "-noout", "-subject"], text=True
    )
    fp = subprocess.check_output(
        ["openssl", "x509", "-in", str(R36), "-noout", "-fingerprint", "-sha256"],
        text=True,
    )
    assert "CN = Sectigo Public Server Authentication CA DV R36" in subject or (
        "CN=Sectigo Public Server Authentication CA DV R36" in subject
    )
    got = fp.strip().split("=", 1)[-1].strip().upper()
    if got != R36_FINGERPRINT:
        pytest.fail("P3: R36 fingerprint mismatch")


def test_p4_one_extent_matches_manifest():
    matches = [
        p
        for p in _tracked_files()
        if p.name.startswith("scotland_extent.")
        and p.suffix in {".geojson", ".fgb", ".json"}
    ]
    # Also accept untracked during local runs before git add.
    if not matches:
        matches = list((REPO / "data" / "processed" / "gis").glob("scotland_extent.*"))
    assert len(matches) == 1, f"P4: expected one scotland_extent.* got {matches}"
    path = matches[0]
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = REPO / "data" / "processed" / "gis" / "manifest.csv"
    rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
    row = next((r for r in rows if (r.get("file") or "") == path.name), None)
    assert row is not None, f"P4: no manifest row for {path.name}"
    if (row.get("sha256") or "").lower() != actual:
        pytest.fail("P4: extent sha256 != manifest")


def test_p6_no_frontend_clip():
    frontend = REPO / "frontend"
    if not frontend.is_dir():
        return
    for path in frontend.rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _FRONTEND_CLIP.search(text):
            pytest.fail(f"P6: frontend clip helper in {path.relative_to(REPO)}")
    # No frontend file changed vs main.
    for line in _files_changed_vs_main():
        if line.startswith("frontend/"):
            pytest.fail(f"P6: frontend file changed: {line}")


def test_p7_no_pound_in_changed_files():
    # Pound sign built from codepoint so this pin file does not itself contain it.
    pound = chr(0x00A3)
    for rel in _files_changed_vs_main():
        path = REPO / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if pound in text:
            pytest.fail(f"P7: {pound} in changed file {rel}")
