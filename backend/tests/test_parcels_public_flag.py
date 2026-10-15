"""PARCELS_PUBLIC default-off: parcel tile + bbox routes 404."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TUNNEL_TEMPLATE = REPO_ROOT / "deploy" / "cloudflare" / "config.template.yml"

BBOX = {
    "south": 55.84,
    "west": -4.30,
    "north": 55.88,
    "east": -4.22,
}


@pytest.fixture(autouse=True)
def _parcels_public_off(monkeypatch):
    """Ensure the flag is unset for every test in this module (default off)."""
    monkeypatch.delenv("PARCELS_PUBLIC", raising=False)


def test_parcels_bbox_404_when_flag_off(client):
    r = client.get("/layers/parcels", params=BBOX)
    assert r.status_code == 404, r.text


def test_parcels_tile_404_when_flag_off(client):
    r = client.get("/layers/parcels/tiles/14/8045/5230")
    assert r.status_code == 404, r.text
    r_png = client.get("/layers/parcels/tiles/14/8045/5230.png")
    assert r_png.status_code == 404, r_png.text


def test_parcels_at_404_when_flag_off(client):
    r = client.get("/layers/parcels/at", params={"lat": 55.86, "lng": -4.25})
    assert r.status_code == 404, r.text


def test_parcels_bbox_not_404_when_flag_on(client, monkeypatch):
    monkeypatch.setenv("PARCELS_PUBLIC", "true")
    # May be 503 (unloaded) or 200 — must not be the flag 404.
    r = client.get("/layers/parcels", params=BBOX)
    assert r.status_code != 404, r.text


def test_tunnel_ingress_parcels_404_ahead_of_frontend():
    text = TUNNEL_TEMPLATE.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    ingress = data["ingress"]
    assert ingress[-1] == {"service": "http_status:404"}

    parcel_paths = {
        "^/backend/layers/parcels.*",
        "^/api/parcels.*",
    }
    hosts = {"scot-land.scot", "www.scot-land.scot"}
    parcel_rules = [
        r
        for r in ingress
        if r.get("path") in parcel_paths and r.get("service") == "http_status:404"
    ]
    assert len(parcel_rules) == 4, parcel_rules
    assert {r["hostname"] for r in parcel_rules} == hosts
    assert {r["path"] for r in parcel_rules} == parcel_paths

    # Parcel 404 rules must appear before the hostname → frontend rules.
    first_frontend = next(
        i
        for i, r in enumerate(ingress)
        if r.get("hostname") in hosts
        and r.get("service") == "http://localhost:3000"
        and "path" not in r
    )
    last_parcel = max(i for i, r in enumerate(ingress) if r in parcel_rules)
    assert last_parcel < first_frontend

    # Never expose Postgres / direct API :8000.
    for rule in ingress:
        svc = str(rule.get("service", ""))
        assert ":8000" not in svc
        assert "5432" not in svc
        assert "5433" not in svc
