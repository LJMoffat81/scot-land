"""Contracts for safe home auto-deploy (health-gated swap, tunnel, uptime)."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_HOME = REPO_ROOT / "docker-compose.home.yml"
COMPOSE_CANARY = REPO_ROOT / "docker-compose.home.canary.yml"
DEPLOY_PS1 = REPO_ROOT / "scripts" / "ops" / "deploy-home.ps1"
REBUILD_PS1 = REPO_ROOT / "scripts" / "ops" / "rebuild-home.ps1"
UPTIME_PS1 = REPO_ROOT / "scripts" / "ops" / "uptime-check.ps1"
UPTIME_SH = REPO_ROOT / "scripts" / "ops" / "uptime-check.sh"
UPTIME_TIMER = REPO_ROOT / "scripts" / "ops" / "scot-land-uptime.timer"
HOME_DEPLOY_DOC = REPO_ROOT / "docs" / "HOME_DEPLOY.md"
GITIGNORE = REPO_ROOT / ".gitignore"

PUBLIC_HEALTH = "https://scot-land.scot/backend/health"


def test_compose_home_publishes_named_images_for_canary_reuse():
    text = COMPOSE_HOME.read_text(encoding="utf-8")
    assert "image: scot-land-home-api:local" in text
    assert "image: scot-land-home-frontend:local" in text
    data = yaml.safe_load(text)
    assert data["services"]["api"]["image"] == "scot-land-home-api:local"
    assert data["services"]["frontend"]["image"] == "scot-land-home-frontend:local"


def test_canary_compose_uses_alternate_loopback_ports_not_live():
    text = COMPOSE_CANARY.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert "db" not in data["services"]
    api_ports = data["services"]["api"]["ports"]
    fe_ports = data["services"]["frontend"]["ports"]
    assert any("8001" in str(p) for p in api_ports)
    assert any("3001" in str(p) for p in fe_ports)
    # Must not bind the live public origin ports.
    joined = " ".join(str(p) for p in api_ports + fe_ports)
    assert ":8000:8000" not in joined.replace(" ", "")
    assert "3000:3000" not in joined.replace(" ", "")
    assert "host.docker.internal" in text
    assert data["services"]["api"]["image"] == "scot-land-home-api:local"
    assert data["services"]["frontend"]["image"] == "scot-land-home-frontend:local"


def test_deploy_home_script_health_gates_and_never_stops_tunnel():
    text = DEPLOY_PS1.read_text(encoding="utf-8")
    lower = text.lower()
    assert "never stop" in lower
    assert "cloudflared" in lower
    assert "last-good-sha" in text
    assert "/backend/health" in text
    assert "canary" in lower
    assert "rollback" in lower
    assert "restacklive" in text.replace(" ", "").lower()
    # Must not stop the tunnel process/service.
    assert "stop-process" not in lower
    assert "stop-service" not in lower
    assert "systemctl stop cloudflared" not in lower


def test_rebuild_home_delegates_to_deploy_home():
    text = REBUILD_PS1.read_text(encoding="utf-8")
    assert "deploy-home.ps1" in text


def test_uptime_check_hits_public_backend_health_every_five_minutes():
    ps1 = UPTIME_PS1.read_text(encoding="utf-8")
    sh = UPTIME_SH.read_text(encoding="utf-8")
    timer = UPTIME_TIMER.read_text(encoding="utf-8")
    assert PUBLIC_HEALTH in ps1
    assert PUBLIC_HEALTH in sh
    assert "uptime.log" in ps1
    assert "uptime.log" in sh
    assert "OnUnitActiveSec=5min" in timer
    assert "paid" not in ps1.lower() or "no paid" in ps1.lower()


def test_home_deploy_doc_and_gitignore_cover_state_dir():
    doc = HOME_DEPLOY_DOC.read_text(encoding="utf-8")
    ignore = GITIGNORE.read_text(encoding="utf-8")
    assert "deploy-home.ps1" in doc
    assert "last-good-sha" in doc
    assert "cloudflared" in doc.lower()
    assert "530" in doc or "1033" in doc
    assert ".deploy/" in ignore
    # Public surface: no £ figures in deploy docs.
    assert "£" not in doc
