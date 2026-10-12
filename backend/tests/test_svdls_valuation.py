"""SVDLS valuation rules: best use − remediation; never zero; HLS owns overlap."""

from __future__ import annotations

from pathlib import Path

import yaml

from georgist.svdls_valuation import (
    annual_remediation_per_ha,
    load_config,
    previous_use_bucket,
    split_hectares_hls_owns_overlap,
    value_hls_overlap_handoff,
    value_svdls_site,
)
from layers.vdl import OUT_SR, query_bbox, query_point
from paths import CONFIG_DIR


def test_config_loads_from_data_config():
    cfg = load_config()
    assert cfg["use_basis"] == "best_permitted_use"
    assert cfg["source_id"] == "svdls"
    assert (CONFIG_DIR / "svdls_valuation.yaml").is_file()


def test_hls_owns_overlap_split():
    split = split_hectares_hls_owns_overlap(ha_register=10.0, ha_dup_hls=4.0)
    assert split.svdls_ha == 6.0
    assert split.hls_owned_ha == 4.0
    assert split.fully_owned_by_hls is False

    full = split_hectares_hls_owns_overlap(ha_register=3.0, ha_dup_hls=5.0)
    assert full.svdls_ha == 0.0
    assert full.hls_owned_ha == 3.0
    assert full.fully_owned_by_hls is True


def test_svdls_values_only_excl_hls_hectares():
    """Overlap must not be valued on the SVDLS layer (no double count)."""
    rent = 20_000.0  # £/ha/year
    full = value_svdls_site(
        ha_register=10.0,
        ha_dup_hls=0.0,
        rent_per_ha_gbp=rent,
        previous_use="unknown",
    )
    partial = value_svdls_site(
        ha_register=10.0,
        ha_dup_hls=4.0,
        rent_per_ha_gbp=rent,
        previous_use="unknown",
    )
    assert partial.valued_ha == 6.0
    assert partial.hls_owned_ha == 4.0
    assert "hls_owns_overlap" in partial.flags
    # Best-use scales with excl_hls only.
    assert partial.best_permitted_gbp == round(6.0 * rent, 2)
    assert partial.best_permitted_gbp < full.best_permitted_gbp
    # Overlap handoff equals valuing those hectares once on HLS.
    handoff = value_hls_overlap_handoff(
        ha_dup_hls=4.0,
        rent_per_ha_gbp=rent,
        previous_use="unknown",
    )
    assert handoff.valued_ha == 4.0
    assert handoff.best_permitted_gbp == round(4.0 * rent, 2)
    # SVDLS + HLS handoff covers the register without double-counting hectares.
    assert round(partial.valued_ha + handoff.valued_ha, 6) == 10.0


def test_never_zero_when_remediation_exceeds_best_use():
    cfg = load_config()
    # Force huge remediation so net would be negative without the floor.
    cfg = yaml.safe_load(Path(CONFIG_DIR / "svdls_valuation.yaml").read_text())
    cfg["remediation_gbp_per_ha_capital"] = {
        "default": 1_000_000_000,
        "by_previous_use": {"unknown": 1_000_000_000},
    }
    result = value_svdls_site(
        ha_register=2.0,
        ha_dup_hls=0.0,
        rent_per_ha_gbp=100.0,
        previous_use="unknown",
        config=cfg,
    )
    assert result.valued_ha == 2.0
    assert result.annual_rent_gbp > 0
    assert "remediation_floor_applied" in result.flags
    floor = 2.0 * float(cfg["never_zero"]["minimum_rent_gbp_per_ha_year"])
    assert result.annual_rent_gbp == round(floor, 2)


def test_best_permitted_minus_remediation_when_positive():
    cfg = load_config()
    cfg["remediation_gbp_per_ha_capital"] = {
        "default": 0,
        "by_previous_use": {"agriculture": 0},
    }
    cfg["land_yield"] = 0.05
    result = value_svdls_site(
        ha_register=1.0,
        ha_dup_hls=0.0,
        rent_per_ha_gbp=10_000.0,
        previous_use="Former agricultural land",
        config=cfg,
    )
    assert result.use_basis == "best_permitted_use"
    assert result.previous_use_bucket == "agriculture"
    assert result.best_permitted_gbp == 10_000.0
    assert result.remediation_gbp == 0.0
    assert result.annual_rent_gbp == 10_000.0


def test_previous_use_buckets_and_annual_remediation():
    assert previous_use_bucket("Former landfill tip") == "landfill"
    assert previous_use_bucket(None) == "unknown"
    annual = annual_remediation_per_ha("manufacturing works")
    cfg = load_config()
    capital = float(cfg["remediation_gbp_per_ha_capital"]["by_previous_use"]["manufacturing"])
    assert annual == capital * float(cfg["land_yield"])


def test_fully_hls_overlap_leaves_svdls_at_zero_with_flag():
    """Land is not left unvalued: HLS owns it; SVDLS reports zero + flag."""
    result = value_svdls_site(
        ha_register=1.5,
        ha_dup_hls=1.5,
        rent_per_ha_gbp=8_000.0,
        previous_use="residential",
    )
    assert result.annual_rent_gbp == 0.0
    assert result.valued_ha == 0.0
    assert "fully_owned_by_hls" in result.flags
    handoff = value_hls_overlap_handoff(
        ha_dup_hls=1.5,
        rent_per_ha_gbp=8_000.0,
        previous_use="residential",
    )
    assert handoff.annual_rent_gbp > 0
    assert handoff.valued_ha == 1.5


def test_arcgis_out_sr_still_4326(monkeypatch):
    """GIS note: FeatureServer queries must keep outSR=4326 after valuation work."""
    seen: list[dict] = []

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"type": "FeatureCollection", "features": []}

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def get(self, _url, params=None):
            seen.append(dict(params or {}))
            return _Resp()

    monkeypatch.setattr("layers.vdl._client", lambda: _Client())
    assert OUT_SR == 4326
    query_bbox(55.84, -4.30, 55.88, -4.22)
    query_point(55.86, -4.26)
    assert all(p.get("outSR") == 4326 for p in seen)
