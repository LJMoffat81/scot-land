"""Crofting Register + common grazings — OGL tables, honest spatial gap."""

from __future__ import annotations

from layers.crofting import (
    catalog_common_grazings,
    catalog_crofting_register,
    crofting_payload,
    load_crofting_config,
    place_crofting,
)
from layers.platform import place_context, platform_catalog


def test_crofting_config_ogl_and_gaps():
    data = load_crofting_config()
    national = data["national"]
    assert national["licence"] == "OGL-3.0"
    assert "open-data" in national["open_data_url"]
    assert "crofts.ros.gov.uk" in national["ros_register_url"]
    assert "individuals" in data["not_ingested"]
    assert any("polygon" in g.lower() or "OGL" in g for g in data["gaps"])
    rejected = {row["id"] for row in data["rejected_alternatives"]}
    assert "spatial_hub_decrofted" in rejected


def test_crofting_payload_spatial_gap():
    payload = crofting_payload()
    assert payload["ok"] is True
    assert payload["licence"] == "OGL-3.0"
    assert payload["map_overlay"]["status"] == "gap"
    assert "RoS" in payload["spatial_gap"] or "polygon" in payload["spatial_gap"]
    assert "individuals" in payload["not_ingested"]
    assert payload["sources"]["holdings"]["postgis_table"] == "croft_holdings"
    assert payload["sources"]["grazings"]["postgis_table"] == "common_grazings"


def test_place_crofting_never_invents_geometry():
    card = place_crofting("S12000017")  # Highland
    assert card["status"] == "linked"
    assert card["on_this_point"] is None
    assert card["licence"] == "OGL-3.0"
    assert card["ros_register_url"]


def test_catalog_wires_crofting_and_grazings():
    reg = catalog_crofting_register()
    graz = catalog_common_grazings()
    assert reg["id"] == "crofting_register"
    assert reg["status"] == "linked"
    assert reg["licence"] == "OGL-3.0"
    assert "open-government-licence" in (reg.get("licence_url") or "")
    assert reg["endpoint"] == "/api/crofting.json"
    assert reg["lists_only"] is True
    assert reg["boundaries"] is False
    assert reg["ledger_role"] == "constraint"
    assert reg["ledger_row"] is None
    assert reg["ui_surface"] == "ledger"
    assert graz["id"] == "common_grazings"
    assert graz["status"] == "linked"
    assert graz["licence"] == "OGL-3.0"
    assert graz["lists_only"] is True
    assert graz["boundaries"] is False
    assert graz["ledger_role"] == "constraint"
    assert graz["ledger_row"] is None
    assert graz["ui_surface"] == "ledger"

    catalog = platform_catalog()
    ids = {row["id"] for row in catalog["layers"]}
    assert "crofting_register" in ids
    assert "common_grazings" in ids
    # Linked — must not break live-toggle drift (not status=live).
    live = {row["id"] for row in catalog["layers"] if row["status"] == "live"}
    assert "crofting_register" not in live
    assert "common_grazings" not in live

    place = place_context(57.48, -4.23, council_code="S12000017")
    assert place["crofting"]["status"] == "linked"
    assert place["crofting"]["on_this_point"] is None


def test_sources_yaml_crofting_lists_only_constraint():
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[2]
    sources = yaml.safe_load(
        (root / "data" / "config" / "sources.yaml").read_text(encoding="utf-8")
    )
    crofting = sources["crofting"]
    assert crofting["lists_only"] is True
    assert crofting["boundaries"] is False
    assert crofting["ledger_role"] == "constraint"
    assert crofting["ledger_row"] is None
    assert crofting["ui_surface"] == "ledger"
    assert "individuals" in crofting["not_ingested"]
    assert "open-government-licence" in crofting["licence_url"]


def test_api_crofting_json(client):
    response = client.get("/api/crofting.json")
    assert response.status_code == 200
    body = response.json()
    assert body["licence"] == "OGL-3.0"
    assert body["map_overlay"]["status"] == "gap"
    assert "open_data_url" in body


def test_downloads_lists_crofting(client):
    response = client.get("/downloads")
    assert response.status_code == 200
    items = response.json().get("items") or []
    ids = {item.get("id") for item in items}
    assert "crofting_register" in ids
    assert "common_grazings" in ids


def test_ingest_crofting_fixtures_into_postgis(monkeypatch):
    """CI / local PostGIS: fixture ingest must populate OGL tables."""
    import os

    import pytest

    url = os.getenv("WEALTH_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not url:
        pytest.skip("WEALTH_TEST_DATABASE_URL / DATABASE_URL not set")

    monkeypatch.setenv("DATABASE_URL", url)

    from etl.ingest_crofting import main as ingest_main
    from georgist import db

    assert ingest_main(["--from-fixtures"]) == 0
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM croft_holdings")
            holdings = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM common_grazings")
            grazings = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM croft_parishes")
            parishes = cur.fetchone()[0]
            cur.execute(
                "SELECT dataset, licence FROM crofting_ingest_meta ORDER BY dataset"
            )
            meta = cur.fetchall()
    finally:
        conn.close()
    assert holdings >= 1
    assert grazings >= 1
    assert parishes >= 1
    assert {row[0] for row in meta} >= {"parishes", "holdings", "grazings"}
    assert all(row[1] == "OGL-3.0" for row in meta)

    payload = crofting_payload()
    assert payload["postgis"]["loaded"] is True
    assert payload["postgis"]["counts"]["holdings"] == holdings
