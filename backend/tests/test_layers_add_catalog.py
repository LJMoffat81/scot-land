"""LAYERS-ADD-1 catalog contract (L1–L4, L14) + licence addenda."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from layers.layer_flags import (
    FLAG_HLS,
    FLAG_LDP,
    FLAG_SEPA_FRM,
    GATED_FLAG_NAMES,
    derive_public,
    flag_enabled,
)
from layers.layers_add_catalog import (
    GATED_LAYER_IDS,
    LICENCE_STATUSES,
    REQUIRED_FIELDS,
    SG_ATTRIBUTION,
    TILE_PROPERTY_ALLOWLIST,
    flagged_layer_ids,
    layers_add_entries,
    public_layers_add_entries,
    tile_manifest,
    validate_entry,
    waiting_for_permission_rows,
)
from layers.platform import platform_catalog

REPO = Path(__file__).resolve().parents[2]
SIMD_UUID = "02866b0b-66e5-46ab-9b1c-d433dc3c2fae"


def test_l1_catalog_completeness():
    rows = layers_add_entries()
    assert rows, "ADD-1 catalog must not be empty"
    for row in rows:
        problems = validate_entry(row)
        assert not problems, f"{row['layer_id']}: {problems}"
        assert row["licence_status"] in LICENCE_STATUSES
        for field in REQUIRED_FIELDS:
            assert field in row


def test_l1_rejects_invalid_licence_status():
    row = dict(layers_add_entries()[0])
    row["licence_status"] = "open"
    row["public"] = True
    problems = validate_entry(row)
    assert any("licence_status" in p for p in problems)


def test_l2_public_derivation_matrix():
    for status in ("ogl", "confirmed", "unconfirmed", "open_other", "prohibited"):
        for flag_on in (False, True):
            got = derive_public(status, "LAYER_X_ENABLED", flag_on=flag_on)
            if status == "prohibited":
                assert got is False
            elif status in {"ogl", "confirmed", "open_other"}:
                assert got is flag_on
            else:
                assert got is False
    # No flag → public when licence allows.
    assert derive_public("ogl", None) is True
    assert derive_public("unconfirmed", None) is False


def test_l3_flags_default_off(monkeypatch):
    monkeypatch.delenv(FLAG_LDP, raising=False)
    monkeypatch.delenv(FLAG_HLS, raising=False)
    monkeypatch.delenv(FLAG_SEPA_FRM, raising=False)
    for name in GATED_FLAG_NAMES:
        assert flag_enabled(name) is False


def test_l3_prod_config_does_not_enable_flags():
    """No committed env/compose file may set LAYER_*_ENABLED=true."""
    patterns = (
        "LAYER_LDP_ENABLED=true",
        "LAYER_HLS_ENABLED=true",
        "LAYER_SEPA_FRM_MAPS_ENABLED=true",
    )
    roots = [REPO / "data" / "config", REPO / "backend"]
    offenders: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".yml", ".yaml", ".env", ".toml", ".json", ".md"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in patterns:
                if pat.lower() in text.lower():
                    offenders.append(f"{path}:{pat}")
    assert not offenders, offenders


def test_l4_gated_set_is_exact_after_licence_1a():
    assert flagged_layer_ids() == GATED_LAYER_IDS
    assert GATED_LAYER_IDS == frozenset(
        {"sepa_frm_maps", "ldp_allocations", "housing_land_supply"}
    )


def test_simd_uuid_is_gis_corrected_id():
    simd = next(
        r for r in layers_add_entries() if r["layer_id"] == "simd2020_domains"
    )
    assert SIMD_UUID in simd["source_url"]
    assert "4fb9-a9a9-7b3a0d6a6fe3" not in simd["source_url"]
    assert "Copyright Scottish Government, contains Ordnance Survey data" in (
        simd["attribution"]
    )


def test_sg_attribution_on_boundary_and_simd():
    needle = "Copyright Scottish Government, contains Ordnance Survey data"
    for layer_id in (
        "simd2020_domains",
        "dz2022_boundaries",
        "dz2011_boundaries",
    ):
        row = next(r for r in layers_add_entries() if r["layer_id"] == layer_id)
        assert needle in row["attribution"]
        assert SG_ATTRIBUTION.split("©")[0] in row["attribution"]


def test_listed_buildings_allowlist_category_and_hes_link_only():
    allow = TILE_PROPERTY_ALLOWLIST["hes_listed_buildings"]
    assert allow == frozenset({"category", "hes_link"})
    assert "DES_TITLE" not in allow
    assert "DES_REF" not in allow


def test_l5_tile_manifest_omits_flagged_ids(monkeypatch):
    monkeypatch.delenv(FLAG_LDP, raising=False)
    monkeypatch.delenv(FLAG_HLS, raising=False)
    manifest = tile_manifest()
    ids = {s["layer_id"] for s in manifest["sources"]}
    for gated in GATED_LAYER_IDS:
        assert gated not in ids
    assert "sepa_frm_maps" not in ids


def test_l6_platform_catalog_omits_flagged_when_off(monkeypatch):
    monkeypatch.delenv(FLAG_LDP, raising=False)
    monkeypatch.delenv(FLAG_HLS, raising=False)
    catalog = platform_catalog()
    ids = {row["id"] for row in catalog["layers"]}
    assert "ldp_allocations" not in ids
    assert "hla" not in ids
    add_ids = {row["layer_id"] for row in catalog["layers_add"]}
    assert "ldp_allocations" not in add_ids
    assert "housing_land_supply" not in add_ids
    assert "sepa_frm_maps" not in add_ids


def test_waiting_for_permission_is_ldp_and_hls():
    waiting = waiting_for_permission_rows()
    ids = {row["layer_id"] for row in waiting}
    assert ids == {"ldp_allocations", "housing_land_supply"}
    for row in waiting:
        assert row["status_label"] == "Waiting for permission to use the data"


def test_l14_v1_4_model_has_no_candidates_v15_import():
    georgist = REPO / "backend" / "georgist"
    agr = REPO / "backend" / "agr"
    offenders: list[str] = []
    for root in (georgist, agr):
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "candidates_v15" in text:
                offenders.append(str(path.relative_to(REPO)))
    assert not offenders, offenders


def test_public_layers_have_no_currency_fields():
    for row in public_layers_add_entries():
        blob = " ".join(str(v) for v in row.values())
        assert "£" not in blob
        assert "gbp" not in blob.lower() or "og" in blob.lower()


def test_manual_drop_harvesters_have_no_http_imports():
    path = REPO / "backend" / "harvesters" / "manual_drop.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in {"httpx", "requests", "urllib", "aiohttp"}
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in {
                "httpx",
                "requests",
                "urllib",
                "aiohttp",
            }
    text = path.read_text(encoding="utf-8").lower()
    for banned in ("spatialhub.scot", "authkey", "/login"):
        assert banned not in text


@pytest.mark.parametrize(
    "layer_id,flag",
    [
        ("ldp_allocations", FLAG_LDP),
        ("housing_land_supply", FLAG_HLS),
        ("sepa_frm_maps", FLAG_SEPA_FRM),
    ],
)
def test_flagged_layers_never_public_when_prohibited(layer_id, flag, monkeypatch):
    monkeypatch.setenv(flag, "true")
    row = next(r for r in layers_add_entries() if r["layer_id"] == layer_id)
    # Re-derive: prohibited stays non-public even with flag ON.
    assert derive_public(row["licence_status"], flag, flag_on=True) is False
