"""ARCH-1a static pins P1–P10 and K2 catalog credits."""

from __future__ import annotations

import csv
import hashlib
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from layers.catalog_copy import (
    SCOTLAND_EXTENT_LAND_CREDIT,
    SCOTLAND_EXTENT_MARINE_CREDIT,
)

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
R36 = BACKEND / "certs" / "sectigo-public-server-auth-ca-dv-r36.pem"
R36_FINGERPRINT = (
    "8C:54:C3:34:B6:6B:A4:E4:26:77:2A:F4:A3:F9:13:6C:19:A1:AE:C7:29:FD:B2:8C:53:5C:07:A5:A4:EF:22:E0"
)

_TOKEN_LITERAL = re.compile(
    r"(?:token=(?![\*]{3}(?:&|\s|$))[0-9a-fA-F-]{8,})"
    r"|(?:" + "NMPI_WFS_TOKEN" + r"=\S+)"
)
_INSECURE = re.compile(r"verify\s*=\s*False|(?<!\w)-k(?!\w)|--insecure")
_BLANKET_EXCEPT = re.compile(r"except\s*(Exception|BaseException)?\s*:")
_WFS_FETCH = re.compile(
    r"msmap1\.atkinsgeospatial\.com|services-eu1\.arcgis\.com|NMPI_WFS_TOKEN\s*:"
)


def _tracked_files() -> list[Path]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=REPO, text=True)
    paths = [REPO / rel for rel in out.split("\0") if rel]
    # Also scan untracked ARCH-1 paths so local pre-commit mutations still bite.
    extra = [
        BACKEND / "etl" / "build_scotland_extent.py",
        BACKEND / "etl" / "run_layer.py",
        BACKEND / "layers" / "registry" / "loader.py",
        BACKEND / "etl" / "extent_sources.py",
        BACKEND / "etl" / "extent_geom.py",
    ]
    for path in extra:
        if path.is_file() and path not in paths:
            paths.append(path)
    return paths


def _files_changed_vs_main() -> list[str]:
    # Needs fetch-depth 0 so origin/main is available.
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "origin/main"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        pytest.fail("P6: origin/main not available (shallow checkout)")
    # Unshallow if needed for a merge-base.
    subprocess.run(
        ["git", "fetch", "--unshallow", "origin"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "fetch", "origin", "main"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    diff = subprocess.check_output(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=REPO,
        text=True,
    )
    return [line for line in diff.splitlines() if line]


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
    targets = [
        BACKEND / "etl" / "build_scotland_extent.py",
        BACKEND / "etl" / "run_layer.py",
        BACKEND / "layers" / "registry" / "loader.py",
    ]
    for path in targets:
        if not path.is_file():
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
    assert "Sectigo Public Server Authentication CA DV R36" in subject
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


# Exact OPTIONAL_ROUTERS registration authorised by ARCH-2a_4ca4ba1c §5/§8.
# P6 still fails on any other change to backend/api/main.py.
_ARCH2A_TILES_ROUTER_LINE = '    ("api.tiles_routes", "router"),\n'

# Literal P6 exemptions for ARCH-2b-r3a harness files only (no globs).
_ARCH2B_R3A_FRONTEND_ALLOW = frozenset(
    [
        # ARCH-2b-r3a d555ca98 (A1)
        "frontend/e2e/ci/_fixtures.ts",
        # ARCH-2b-r3a d555ca98 (A1)
        "frontend/e2e/ci/arch2b-a1-g1.spec.ts",
        # ARCH-2b-r3a d555ca98 (A1)
        "frontend/e2e/ci/fixtures/tiles-manifest-empty.json",
        # ARCH-2b-r3a d555ca98 (A2)
        "frontend/e2e/build-key/esri-key-build.spec.ts",
        # ARCH-2b-r3a d555ca98 (A3′)
        "frontend/e2e/ci/sw-036-desktop-layout.spec.ts",
        # ARCH-2b-r3a d555ca98 (ci:local)
        "frontend/package.json",
    ]
)

# ARCH-2b-r3b 7fc93d8f — literal frontend allow-list (§7); unioned with r3a.
_ARCH2B_R3B_FRONTEND_ALLOW = frozenset(
    [
        # ARCH-2b-r3b 7fc93d8f
        "frontend/lib/tileLayerFactory.ts",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/scripts/test-tile-layer-factory.mjs",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/e2e/ci/arch2b-tiles.spec.ts",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/e2e/fixtures/arch2b/dz2022.mvt",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/e2e/fixtures/arch2b/oil-fields.mvt",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/e2e/fixtures/arch2b/platforms.mvt",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/e2e/fixtures/arch2b/pipelines.mvt",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/e2e/fixtures/arch2b/make_fixtures.py",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/components/ScotlandMap.tsx",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/lib/contextLayers.ts",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/app/backend/[...path]/route.ts",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/package.json",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/e2e/ci/layers-perf-1.spec.ts",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/e2e/ci/layers-perf-3.spec.ts",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/e2e/ci/layers-fix-1.spec.ts",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/scripts/test-proxy-null-body.mjs",
        # ARCH-2b-r3b 7fc93d8f
        "frontend/e2e/ci/_fixtures.ts",
    ]
)

# SRC-B §2a — literal P6 allow-list entry for built-up credit string site.
_SRC_B_FRONTEND_ALLOW = frozenset(
    [
        # SRC-B
        "frontend/lib/layerCatalog.ts",
    ]
)


def _assert_main_py_only_arch2a_tiles_registration() -> None:
    """HEAD main.py must equal origin/main plus exactly the ARCH-2a tiles line."""
    head = (BACKEND / "api" / "main.py").read_text(encoding="utf-8")
    base = subprocess.check_output(
        ["git", "show", "origin/main:backend/api/main.py"],
        cwd=REPO,
        text=True,
    )
    if head.count(_ARCH2A_TILES_ROUTER_LINE) != 1:
        pytest.fail("P6: forbidden file changed: backend/api/main.py")
    stripped = head.replace(_ARCH2A_TILES_ROUTER_LINE, "", 1)
    if stripped != base:
        pytest.fail("P6: forbidden file changed: backend/api/main.py")


def test_p6_no_forbidden_frontend_or_shallow():
    changed = _files_changed_vs_main()
    for rel in changed:
        if rel.startswith("frontend/"):
            if rel not in (
                _ARCH2B_R3A_FRONTEND_ALLOW
                | _ARCH2B_R3B_FRONTEND_ALLOW
                | _SRC_B_FRONTEND_ALLOW
            ):
                pytest.fail(f"P6: frontend file changed: {rel}")
            continue
        if rel in {"AGENTS.md", "backend/main.py"}:
            pytest.fail(f"P6: forbidden file changed: {rel}")
        if rel == "backend/api/main.py":
            _assert_main_py_only_arch2a_tiles_registration()


def test_p7_no_pound_in_changed_files():
    """Fail if this PR *introduces* a pound glyph (pre-existing main lines OK)."""
    pound = "\u00a3"  # do not embed the glyph in this file (P7 self-scan)
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "origin/main"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        pytest.fail("P6: origin/main not available (shallow checkout)")
    diff = subprocess.check_output(
        ["git", "diff", "-U0", "origin/main...HEAD"],
        cwd=REPO,
        text=True,
    )
    # Also include unstaged/untracked additions for local pre-commit runs.
    diff += subprocess.check_output(
        ["git", "diff", "-U0", "HEAD"],
        cwd=REPO,
        text=True,
    )
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++") and pound in line:
            pytest.fail(f"P7: {pound} in changed file")


def test_p8_workflow_does_not_fetch_wfs():
    workflow = REPO / ".github" / "workflows" / "ci.yml"
    text = workflow.read_text(encoding="utf-8")
    if _WFS_FETCH.search(text):
        pytest.fail("P8: workflow fetches WFS")
    if "NMPI_WFS_TOKEN" in text:
        pytest.fail("P8: workflow fetches WFS")


def test_p9_no_blanket_except():
    """P9 watches ARCH-1 pipeline modules; context_tiles only when this PR edits it."""
    watched = [
        BACKEND / "etl" / "run_layer.py",
        BACKEND / "etl" / "build_scotland_extent.py",
        BACKEND / "layers" / "registry" / "loader.py",
        # ARCH-2a P-T4 additions
        BACKEND / "tiles" / "build.py",
        BACKEND / "tiles" / "storage.py",
        BACKEND / "tiles" / "measure.py",
        BACKEND / "tiles" / "profiles.py",
        BACKEND / "etl" / "adapters" / "postgis_table.py",
        BACKEND / "api" / "tiles_routes.py",
        # SRC-A P9 add-only
        BACKEND / "etl" / "extent_sources.py",
        BACKEND / "etl" / "extent_geom.py",
    ]
    changed = set(_files_changed_vs_main())
    ctx = BACKEND / "spatial" / "context_tiles.py"
    if "backend/spatial/context_tiles.py" in changed and ctx.is_file():
        watched.append(ctx)

    for path in watched:
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if path.name == "context_tiles.py":
            # Only the fetch_context_geojson body is in scope (ARCH-1 §6 P9).
            start = next(
                (i for i, ln in enumerate(lines) if ln.startswith("def fetch_context_geojson")),
                None,
            )
            if start is None:
                continue
            end = start + 1
            while end < len(lines) and not (
                lines[end].startswith("def ") and end > start
            ):
                end += 1
            scan = list(enumerate(lines[start:end], start=start + 1))
        else:
            scan = list(enumerate(lines, start=1))
        for i, line in scan:
            if _BLANKET_EXCEPT.search(line):
                rel = path.relative_to(REPO).as_posix()
                pytest.fail(f"P9: blanket except in {rel}:{i}")


def test_p10_token_env_is_name_only():
    registry = BACKEND / "layers" / "registry"
    for path in sorted(registry.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        token_env = (data.get("source") or {}).get("token_env")
        if token_env is None:
            continue
        if not re.fullmatch(r"[A-Z_]+", str(token_env)):
            pytest.fail(f"P10: token value in registry {path.stem}")
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    if re.search(r"NMPI_WFS_TOKEN\s*:", workflow):
        pytest.fail("P10: token value in registry workflow")


def test_k2_catalog_credits():
    assert "Open Government Licence v3.0" in SCOTLAND_EXTENT_MARINE_CREDIT
    assert SCOTLAND_EXTENT_MARINE_CREDIT == (
        "Contains public sector information, licensed under the Open Government "
        "Licence v3.0, from UK Hydrographic Office."
    )
    assert SCOTLAND_EXTENT_LAND_CREDIT == (
        "Contains OS data © Crown copyright and database right 2026."
    )
    assert "Crown copyright" in SCOTLAND_EXTENT_LAND_CREDIT
