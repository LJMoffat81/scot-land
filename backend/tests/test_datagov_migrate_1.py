"""DATAGOV-MIGRATE-1: statistics.gov.scot → data.gov.scot (synthetic, offline)."""

from __future__ import annotations

import ast
import json
import socket
import subprocess
import urllib.error
from pathlib import Path

import pytest

from agr.config import load_config
from agr.layers import _price_data, engine_stamp
from layers.layers_add2_catalog import sweep_entries
from sources_datagov import (
    DATAGOV_DZ_LOOKUP_2022,
    DATAGOV_EPC_DOMESTIC,
    DATAGOV_RPSP,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FETCH_PY = REPO_ROOT / "etl" / "datazones" / "fetch.py"

ALLOWLIST = {
    "data/processed/datazones/README.md",
    "data/processed/datazones/sources.md",
    "etl/datazones/README.md",
    "etl/datazones/sources.md",
    "data/processed/gis/README_dz_residential_land.md",
    "data/processed/gis/README_epc_dz_rollup.md",
    "backend/tests/test_datagov_migrate_1.py",
}

NEEDLE = b"statistics.gov.scot"


@pytest.fixture(autouse=True)
def _socket_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(self, *args, **kwargs):  # noqa: ANN001
        raise RuntimeError("network blocked in test_datagov_migrate_1")

    monkeypatch.setattr(socket.socket, "connect", blocked)


def _load_fetch():
    import importlib.util

    spec = importlib.util.spec_from_file_location("datazones_fetch", FETCH_PY)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_t1_statistics_gov_scot_allowlist() -> None:
    found: set[str] = set()
    listed = subprocess.check_output(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        text=True,
    ).splitlines()
    for rel in listed:
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\x00" in data:
            continue
        if NEEDLE in data.lower():
            found.add(rel.replace("\\", "/"))
    assert found == ALLOWLIST, (
        f"statistics.gov.scot paths mismatch; found={sorted(found)} "
        f"allowlist={sorted(ALLOWLIST)}"
    )


def test_t2_exact_urls() -> None:
    assert (
        DATAGOV_RPSP
        == "https://data.gov.scot/dataset/house_prices___residential_properties_sales_and_price"
    )
    assert (
        DATAGOV_EPC_DOMESTIC
        == "https://data.gov.scot/dataset/domestic_energy_performance_certificates___dataset_to_q1_2026"
    )
    assert DATAGOV_DZ_LOOKUP_2022 == "https://data.gov.scot/dataset/2022_data_zone_lookup"

    epc = next(row for row in sweep_entries() if row["layer_id"] == "epc_domestic")
    assert epc["source_url"] == DATAGOV_EPC_DOMESTIC

    assert _price_data()["source"] == (
        "RoS Residential Properties Sales and Price (data.gov.scot, OGL)"
    )

    stamp = engine_stamp(load_config())
    payload = json.dumps(stamp, sort_keys=True)
    assert "statistics.gov.scot" not in payload.lower()


def test_t3_unreachable_endpoint_raises_systemexit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fetch = _load_fetch()

    def boom(*args, **kwargs):  # noqa: ANN001
        raise urllib.error.URLError("synthetic")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", boom)
    monkeypatch.setattr(fetch.time, "sleep", lambda *_a, **_k: None)

    dest = tmp_path / "f"
    url = "https://data.gov.scot/dataset/x/resource/y/download"
    with pytest.raises(SystemExit) as raised:
        fetch.download(url, dest)
    assert str(raised.value) == (
        f"FAIL: could not download {url}: URLError"
    )
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()
    assert not dest.with_name(dest.name + ".tmp").exists()


def test_t4_no_blanket_catch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fetch = _load_fetch()

    def boom(*args, **kwargs):  # noqa: ANN001
        raise ValueError("synthetic")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", boom)
    monkeypatch.setattr(fetch.time, "sleep", lambda *_a, **_k: None)

    with pytest.raises(ValueError, match="synthetic"):
        fetch.download("https://data.gov.scot/dataset/x/resource/y/download", tmp_path / "f")

    tree = ast.parse(FETCH_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                raise AssertionError("bare except: found in fetch.py")
            if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                raise AssertionError("except Exception found in fetch.py")
            if isinstance(node.type, ast.Tuple):
                for elt in node.type.elts:
                    if isinstance(elt, ast.Name) and elt.id == "Exception":
                        raise AssertionError(
                            "except Exception found in fetch.py tuple"
                        )
