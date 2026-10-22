"""ARCH-2a-1 pins P-T1, P-T3, P-T6 and carry CA-1."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml
from _pytest.outcomes import Failed

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"

_PAID = re.compile(
    r"\b(boto|r2|s3)\b|R2_|S3_|amazonaws|cloudflarestorage",
    re.IGNORECASE,
)


def test_p_t1_no_paid_storage_adapter():
    targets = [
        *sorted((BACKEND / "tiles").glob("**/*")),
        BACKEND / "layers" / "storage.yaml",
        BACKEND / "layers" / "storage.schema.json",
        BACKEND / "api" / "tiles_routes.py",
    ]
    for path in targets:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        if _PAID.search(text):
            rel = path.relative_to(REPO).as_posix()
            pytest.fail(f"P-T1: paid storage adapter in {rel}")


def test_p_t3_tippecanoe_pin_match():
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    m_docker = re.search(r"git checkout ([0-9a-f]{40})", dockerfile)
    m_ci = re.search(r"TIPPECANOE_SHA:\s*([0-9a-f]{40})", ci) or re.search(
        r"tippecanoe-([0-9a-f]{40})", ci
    )
    if not m_docker or not m_ci or m_docker.group(1) != m_ci.group(1):
        pytest.fail("P-T3: tippecanoe pin mismatch")


def test_p_t6_no_unsafe_where():
    registry = BACKEND / "layers" / "registry"
    for path in sorted(registry.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        where = (data.get("source") or {}).get("where")
        if where is None:
            continue
        text = str(where)
        if ";" in text or "--" in text:
            pytest.fail(f"P-T6: unsafe where in registry {path.stem}")


def test_ca1_ci_fails_without_dsn(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("ARCH1_TEST_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    perf_path = Path(__file__).resolve().parent / "test_layers_perf_1.py"
    spec = importlib.util.spec_from_file_location(
        "test_layers_perf_1_ca1", perf_path
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    msg = "PERF: ARCH1_TEST_DSN / DATABASE_URL not set in CI"
    with pytest.raises(Failed, match=re.escape(msg) + "$"):
        mod._seed_oil_fields_clipped_table(monkeypatch)
