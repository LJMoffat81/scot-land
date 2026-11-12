"""EXTERNAL-UPTIME-1: offline pins for the external uptime helper and workflow.

Never calls the real site. HTTP cases use a local stub only.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / "scripts" / "ops" / "uptime-external.sh"
UPTIME_YML = REPO / ".github" / "workflows" / "uptime.yml"

TIME_LINE = re.compile(r"uptime-external: time_total=\d+(\.\d+)?s")
OK_LINE = "uptime-external: OK http_code=200 curl_exit=0"
PUBLIC_HEALTH = "https://scot-land.scot/backend/health"
_PROXY_KEYS = (
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
)


class _Script:
    def __init__(self, script: list[tuple[int, str]], delay: float) -> None:
        self.script = script
        self.delay = delay
        self.hits: list[str] = []


def _handler_class(state: _Script) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            state.hits.append(self.path)
            if state.delay:
                time.sleep(state.delay)
            idx = min(len(state.hits) - 1, len(state.script) - 1)
            status, body = state.script[idx]
            data = body.encode("ascii")
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if data:
                self.wfile.write(data)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    return Handler


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(HELPER), *args],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def _env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    for key in _PROXY_KEYS:
        env.pop(key, None)
    env.pop("GITHUB_STEP_SUMMARY", None)
    env["UPTIME_RETRIES"] = "0"
    env["UPTIME_MAX_TIME"] = "5"
    env["UPTIME_RETRY_DELAY"] = "1"
    env.update(overrides)
    return env


def _url(server: ThreadingHTTPServer) -> str:
    port = server.server_address[1]
    return f"http://127.0.0.1:{port}/backend/health"


def _workflow() -> tuple[str, dict, dict]:
    text = UPTIME_YML.read_text(encoding="utf-8")
    wf = yaml.safe_load(text)
    on = wf[True] if True in wf else wf["on"]
    return text, wf, on


@pytest.fixture
def health_stub():
    servers: list[ThreadingHTTPServer] = []

    def start(
        script: list[tuple[int, str]], delay: float = 0.0
    ) -> tuple[ThreadingHTTPServer, list[str]]:
        state = _Script(script, delay)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_class(state))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        return server, state.hits

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def test_p1_ok(health_stub):
    server, hits = health_stub([(200, '{"status":"ok","version":"x"}')])
    result = _run([_url(server)], _env())
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert lines[0] == OK_LINE
    assert TIME_LINE.fullmatch(lines[1])
    assert len(lines) == 2
    assert hits == ["/backend/health"]


def test_p2_retry_recovers(health_stub):
    server, hits = health_stub([(503, "x"), (200, '{"status":"ok"}')])
    result = _run([_url(server)], _env(UPTIME_RETRIES="2"))
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert lines[0] == OK_LINE
    assert len(hits) == 2


def test_p3_summary(health_stub, tmp_path):
    server, _hits = health_stub([(530, "error code: 1033")])
    url = _url(server)
    summary = tmp_path / "s.md"
    result = _run([url], _env(GITHUB_STEP_SUMMARY=str(summary)))
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    line1 = lines[0]
    line2 = lines[1]
    text = summary.read_text(encoding="utf-8") if summary.is_file() else ""
    assert text == f"### External uptime: {url}\n\n{line1}\n\n{line2}\n"


def test_n1_530(health_stub):
    server, hits = health_stub([(530, "error code: 1033")])
    result = _run([_url(server)], _env())
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert lines[0] == "uptime-external: FAIL http_code=530 curl_exit=0 reason=status"
    assert TIME_LINE.fullmatch(lines[1])
    assert len(hits) == 1


def test_n2_timeout(health_stub):
    server, _hits = health_stub([(200, '{"status":"ok"}')], delay=3)
    result = _run([_url(server)], _env(UPTIME_MAX_TIME="1"))
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert lines[0] == "uptime-external: FAIL http_code=000 curl_exit=28 reason=curl"


def test_n3_wrong_body(health_stub):
    server, _hits = health_stub([(200, "<html>ok</html>")])
    result = _run([_url(server)], _env())
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert lines[0] == "uptime-external: FAIL http_code=200 curl_exit=0 reason=body"


def test_n4_non_200_2xx(health_stub):
    server, _hits = health_stub([(204, "")])
    result = _run([_url(server)], _env())
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert lines[0] == "uptime-external: FAIL http_code=204 curl_exit=0 reason=status"


def test_n5_unreachable():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    url = f"http://127.0.0.1:{port}/backend/health"
    result = _run([url], _env())
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert lines[0] == "uptime-external: FAIL http_code=000 curl_exit=7 reason=curl"


def test_n6_empty_host():
    result = _run(["http:///backend/health"], _env())
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "uptime-external: invalid url: http:///backend/health\n"


def test_n7_missing_url():
    result = _run([], _env())
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "uptime-external: usage: uptime-external.sh <url>\n"


def test_n8_empty_url():
    result = _run([""], _env())
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "uptime-external: usage: uptime-external.sh <url>\n"


def test_w1_triggers():
    _text, _wf, on = _workflow()
    assert set(on) == {"schedule", "workflow_dispatch"}


def test_w2_cron():
    _text, _wf, on = _workflow()
    assert on["schedule"] == [{"cron": "17 * * * *"}]


def test_w3_permissions():
    _text, wf, _on = _workflow()
    assert wf["permissions"] == {"contents": "read"}


def test_w4_job():
    _text, wf, _on = _workflow()
    assert list(wf["jobs"]) == ["probe"]
    job = wf["jobs"]["probe"]
    name = job["name"]
    assert name == "External uptime (public health)"
    assert name not in {
        "Frontend typecheck and build",
        "Backend tests (PostGIS)",
        "Publishability guard",
        "Detect frontend changes",
        "Frontend Playwright e2e",
        "Frontend Playwright e2e (quarantine, non-blocking)",
    }
    assert job["timeout-minutes"] == 5


def test_w5_steps():
    _text, wf, _on = _workflow()
    steps = wf["jobs"]["probe"]["steps"]
    runs = [step["run"] for step in steps if "run" in step]
    uses = [step["uses"] for step in steps if "uses" in step]
    assert runs == [
        'bash scripts/ops/uptime-external.sh "https://scot-land.scot/backend/health"'
    ]
    assert uses == ["actions/checkout@v4"]
    assert PUBLIC_HEALTH in runs[0]


def test_w6_no_secrets():
    text, _wf, _on = _workflow()
    assert "secrets." not in text
    assert "GITHUB_TOKEN" not in text


def test_h1_helper_pins():
    raw = HELPER.read_bytes()
    text = raw.decode("ascii")
    assert "--max-time" in text
    assert "--retry " in text
    assert "--retry-connrefused" in text
    assert "--insecure" not in text
    assert " -k " not in text
    assert "--retry-all-errors" not in text
    assert "\u00a3" not in text
