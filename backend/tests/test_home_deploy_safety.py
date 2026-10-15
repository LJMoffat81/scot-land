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
    # Tunnel stays outside compose — a shared project up/down must never list it.
    assert "cloudflared" not in data["services"]
    assert set(data["services"]) == {"db", "api", "frontend"}


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


def test_deploy_home_records_last_good_before_pull():
    """HEAD must be written to last-good-sha before git pull runs."""
    text = DEPLOY_PS1.read_text(encoding="utf-8")
    assert "Write-LastGoodSha $prePullSha" in text
    assert "Recording HEAD as last-good before pull" in text
    assert "Save-LastGoodImages" in text
    assert "git pull origin main" in text
    # Order inside the -Pull block: record SHA, snapshot images, then pull.
    pull_if = text.find("if ($Pull)")
    assert pull_if >= 0
    write_idx = text.find("Write-LastGoodSha $prePullSha", pull_if)
    save_idx = text.find("Save-LastGoodImages", pull_if)
    pull_idx = text.find("git pull origin main", pull_if)
    assert write_idx > pull_if
    assert save_idx > write_idx
    assert pull_idx > save_idx


def test_deploy_home_rollback_resets_main_not_detached():
    """Rollback must checkout main then reset --hard; never detach onto the SHA."""
    text = DEPLOY_PS1.read_text(encoding="utf-8")
    compact = "".join(text.split()).lower()
    assert "git checkout --force main" in text.lower()
    assert "gitreset--hard$lastgood" in compact
    assert "not detached" in text.lower()
    # Forbidden: detached checkout of the SHA alone.
    assert "gitcheckout--force$lastgood" not in compact
    assert "gitcheckout$lastgood" not in compact


def test_deploy_home_rollback_retags_last_good_images_to_local():
    """On rollback, retag :last-good images to :local; do not rebuild to restore."""
    text = DEPLOY_PS1.read_text(encoding="utf-8")
    assert "scot-land-home-api:last-good" in text
    assert "scot-land-home-frontend:last-good" in text
    assert "scot-land-home-api:local" in text
    assert "scot-land-home-frontend:local" in text
    assert "Restore-LastGoodImages" in text
    assert "Save-LastGoodImages" in text
    assert "docker tag" in text
    # Rollback path must call retag and must not rebuild after retag for restore.
    rollback_start = text.find("function Invoke-Rollback")
    assert rollback_start >= 0
    rollback_fn = text[rollback_start:]
    next_fn = rollback_fn.find("\n# --- main")
    if next_fn < 0:
        next_fn = rollback_fn.find("\nfunction ", 1)
    rollback_body = rollback_fn[: next_fn if next_fn > 0 else len(rollback_fn)]
    assert "Restore-LastGoodImages" in rollback_body
    assert "up -d --no-build --no-deps api frontend" in rollback_body
    # Must not rebuild during rollback restore (retag is the restore).
    assert "Invoke-Compose -f $ComposePath build" not in rollback_body


def test_deploy_commands_never_stop_or_recreate_cloudflared():
    """Live compose ups must name api/frontend only; never full-stack or tunnel."""
    text = DEPLOY_PS1.read_text(encoding="utf-8")
    lower = text.lower()
    canary = yaml.safe_load(COMPOSE_CANARY.read_text(encoding="utf-8"))
    assert "cloudflared" not in canary["services"]

    # Forbidden: stop/kill tunnel, or recreate everything in the live project.
    assert "stop-process" not in lower
    assert "stop-service" not in lower
    assert "systemctl stop cloudflared" not in lower
    assert "--force-recreate" not in lower
    assert "invoke-compose -f $composepath down" not in lower
    # Bare full-project live up (no service names) would recreate every service.
    assert "Invoke-Compose -f $ComposePath up -d --no-build\n" not in text
    assert "Invoke-Compose -f $ComposePath up -d --build\n" not in text
    assert "Invoke-Compose -f $ComposePath up -d --build" not in text
    assert "Invoke-Compose -f $ComposePath build\n" not in text

    app_swap = "up -d --no-build --no-deps api frontend"
    assert app_swap in text
    assert text.count(app_swap) >= 2  # live swap + rollback restack
    assert "build api frontend" in text

    for line in text.splitlines():
        stripped = line.strip()
        if "Invoke-Compose" not in stripped:
            continue
        if "$CanaryPath" in stripped or "$CanaryProject" in stripped:
            continue
        if "up -d" in stripped:
            if stripped.endswith("up -d db") or " up -d db" in stripped:
                assert "cloudflared" not in stripped.lower()
                continue
            assert "--no-deps api frontend" in stripped, stripped
            assert "cloudflared" not in stripped.lower()
        if " build" in stripped:
            assert "api frontend" in stripped, stripped
            assert "cloudflared" not in stripped.lower()


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
    # Rollback contracts documented.
    assert "before" in doc.lower() and "pull" in doc.lower()
    assert "reset" in doc.lower() and "main" in doc.lower()
    assert ":last-good" in doc or "last-good" in doc
    assert ":local" in doc
    # Public surface: no £ figures in deploy docs.
    assert "£" not in doc
