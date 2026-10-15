"""HOME-TUNNEL step 2 contracts: tunnel template, compose bind, Worker, backups."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_HOME = REPO_ROOT / "docker-compose.home.yml"
TUNNEL_TEMPLATE = REPO_ROOT / "deploy" / "cloudflare" / "config.template.yml"
ACCESS_TEMPLATE = REPO_ROOT / "deploy" / "cloudflare" / "access.template.yml"
WORKER_SRC = (
    REPO_ROOT / "deploy" / "cloudflare" / "worker-offline" / "src" / "index.js"
)
WORKER_TEST = (
    REPO_ROOT
    / "deploy"
    / "cloudflare"
    / "worker-offline"
    / "offline-worker.test.mjs"
)
PG_DUMP_PS1 = REPO_ROOT / "scripts" / "ops" / "pg-dump-daily.ps1"
REGISTER_PG_DUMP = REPO_ROOT / "scripts" / "ops" / "register-pg-dump-task.ps1"
HOME_DEPLOY_DOC = REPO_ROOT / "docs" / "HOME_DEPLOY.md"
BACKEND_PROXY = (
    REPO_ROOT / "frontend" / "app" / "backend" / "[...path]" / "route.ts"
)
NEXT_CONFIG = REPO_ROOT / "frontend" / "next.config.ts"
PARCEL_TILES = (
    REPO_ROOT
    / "frontend"
    / "app"
    / "api"
    / "parcels"
    / "tiles"
    / "[z]"
    / "[x]"
    / "[y]"
    / "route.ts"
)
OFFLINE_MESSAGE = (
    "Scot-LAND is offline for a short while. Please try again later."
)


def test_compose_home_frontend_loopback_only():
    text = COMPOSE_HOME.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    ports = [str(p) for p in data["services"]["frontend"]["ports"]]
    assert any(
        "127.0.0.1:${HOME_FRONTEND_PORT:-3000}:3000" == p
        or (
            p.startswith("127.0.0.1:")
            and "3000" in p
            and "HOME_FRONTEND_PORT" in p
        )
        for p in ports
    ), ports
    # Exact compose line from the frozen ADD.
    assert '"127.0.0.1:${HOME_FRONTEND_PORT:-3000}:3000"' in text
    # Must not publish frontend on all interfaces (no bare host:port without 127.0.0.1).
    for p in ports:
        assert p.startswith("127.0.0.1:"), p


def test_tunnel_ingress_hostnames_to_frontend_only_then_404():
    text = TUNNEL_TEMPLATE.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["tunnel"] == "REPLACE_WITH_TUNNEL_ID"
    assert data["credentials-file"] == "REPLACE_WITH_CREDENTIALS_FILE"
    ingress = data["ingress"]
    # PARCELS-OFF: four path 404s (both hosts × two paths) ahead of front-end.
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

    frontend_rules = [
        r
        for r in ingress
        if r.get("hostname") in hosts
        and r.get("service") == "http://localhost:3000"
        and "path" not in r
    ]
    assert frontend_rules == [
        {"hostname": "scot-land.scot", "service": "http://localhost:3000"},
        {"hostname": "www.scot-land.scot", "service": "http://localhost:3000"},
    ]
    assert ingress[-1] == {"service": "http_status:404"}
    assert len(ingress) == 7  # 4 parcel 404 + 2 frontend + catch-all

    last_parcel = max(i for i, r in enumerate(ingress) if r in parcel_rules)
    first_frontend = min(i for i, r in enumerate(ingress) if r in frontend_rules)
    assert last_parcel < first_frontend

    # DROP any /api → :8000 service rule; Postgres never exposed (yaml values).
    # Path rules are only the PARCELS-OFF 404s above — never proxy to :8000.
    for rule in ingress:
        svc = str(rule.get("service", ""))
        assert ":8000" not in svc
        assert "5432" not in svc
        assert "5433" not in svc
        assert "postgres" not in svc.lower()
        if "path" in rule:
            assert rule["path"] in parcel_paths
            assert rule["service"] == "http_status:404"
    assert "REPLACE_WITH_" in text  # placeholders, no live secrets
    # Comment may mention :8000 as the dropped pattern; no ingress service uses it.
    assert not any(
        ":8000" in str(r.get("service", "")) for r in ingress
    )


def test_access_template_covers_admin_and_docs_admin():
    text = ACCESS_TEMPLATE.read_text(encoding="utf-8")
    assert "/admin" in text
    assert "/docs-admin" in text
    assert "scot-land.scot" in text
    assert "REPLACE_WITH_ALLOWED_EMAIL_DOMAIN" in text
    assert "£" not in text


def test_offline_worker_unit_with_mocked_failing_origin():
    assert WORKER_SRC.is_file()
    assert WORKER_TEST.is_file()
    src = WORKER_SRC.read_text(encoding="utf-8")
    assert OFFLINE_MESSAGE in src
    result = subprocess.run(
        ["node", "--test", str(WORKER_TEST)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def test_pg_dump_daily_keeps_fourteen_copies():
    text = PG_DUMP_PS1.read_text(encoding="utf-8")
    assert "[int]$Keep = 14" in text or "$Keep = 14" in text
    assert "pg_dump" in text
    assert "scot-land-" in text
    assert "Select-Object -Skip $Keep" in text
    reg = REGISTER_PG_DUMP.read_text(encoding="utf-8")
    assert "pg-dump-daily.ps1" in reg
    assert "Daily" in reg or "-Daily" in reg
    assert "Task Scheduler" in reg or "ScheduledTask" in reg


def test_home_deploy_doc_covers_tunnel_service_backup_and_cache():
    doc = HOME_DEPLOY_DOC.read_text(encoding="utf-8")
    assert "config.template.yml" in doc
    assert "Windows service" in doc or "cloudflared service" in doc.lower()
    assert "router" in doc.lower()
    assert "pg-dump-daily.ps1" in doc
    assert "14" in doc
    assert "/backend" in doc
    assert "max-age=300" in doc or "5 minutes" in doc
    assert OFFLINE_MESSAGE in doc
    assert "access.template.yml" in doc
    assert "£" not in doc
    # Spec: documented drop of any /api → :8000 ingress rule.
    assert "/api" in doc and ":8000" in doc
    assert re.search(r"(?i)no.*`?/api`?.*:8000|:8000.*`?/api`?", doc)


def test_backend_proxy_sets_five_minute_get_cache():
    text = BACKEND_PROXY.read_text(encoding="utf-8")
    assert "max-age=300" in text
    assert "GET" in text
    assert "no-store" in text


def test_static_and_tile_cache_headers_are_long():
    next_cfg = NEXT_CONFIG.read_text(encoding="utf-8")
    assert "max-age=31536000" in next_cfg or "max-age=86400" in next_cfg
    assert "/_next/static" in next_cfg
    tiles = PARCEL_TILES.read_text(encoding="utf-8")
    assert "max-age=86400" in tiles
