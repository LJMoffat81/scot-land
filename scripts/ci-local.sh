#!/usr/bin/env bash
# ARCH-2b-r3b — run the CI required jobs locally.
# Exits non-zero if any job fails. Prints a full summary at the end.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SUMMARY=()
FAIL=0

run_job() {
  local name="$1"
  shift
  echo ""
  echo "======== ci:local :: ${name} ========"
  local start end rc
  start=$(date +%s)
  set +e
  "$@"
  rc=$?
  set -e
  end=$(date +%s)
  local dur=$((end - start))
  if [[ $rc -eq 0 ]]; then
    SUMMARY+=("PASS  ${name}  (${dur}s)")
    echo "======== PASS ${name} (${dur}s) ========"
  else
    SUMMARY+=("FAIL  ${name}  (${dur}s) exit=${rc}")
    echo "======== FAIL ${name} (${dur}s) exit=${rc} ========"
    FAIL=1
  fi
  return 0
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ci:local: missing required command: $1" >&2
    exit 1
  }
}

need_cmd docker
need_cmd node
need_cmd npm
need_cmd python3

# P6 (and other pins) use origin/main...HEAD. Uncommitted frontend/backend
# edits are invisible to that diff — running before commit falsely greens P6.
if [[ -n "$(git -C "$ROOT" status --porcelain)" ]]; then
  echo "ci:local: working tree is dirty; commit (or stash) before running so HEAD matches what CI will test:" >&2
  git -C "$ROOT" status --porcelain >&2
  exit 1
fi

# --- tippecanoe (ARCH-2a pin; same as .github/workflows/ci.yml) ---
install_tippecanoe() {
  local TIPPECANOE_SHA=4f2621186acfec33b63ddf636f665623c0fef2dd
  local cache_dir="$HOME/.cache/tippecanoe-$TIPPECANOE_SHA"
  if ! command -v tippecanoe >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq build-essential libsqlite3-dev zlib1g-dev git
    if [[ ! -x "$cache_dir/tippecanoe" ]]; then
      rm -rf /tmp/tippecanoe-src
      git clone https://github.com/felt/tippecanoe.git /tmp/tippecanoe-src
      (cd /tmp/tippecanoe-src && git checkout "$TIPPECANOE_SHA" && make -j"$(nproc)")
      mkdir -p "$cache_dir"
      cp /tmp/tippecanoe-src/tippecanoe /tmp/tippecanoe-src/tippecanoe-decode /tmp/tippecanoe-src/tile-join "$cache_dir/"
    fi
    sudo cp "$cache_dir/tippecanoe" "$cache_dir/tippecanoe-decode" "$cache_dir/tile-join" /usr/local/bin/
  fi
  tippecanoe --version
}
run_job "tippecanoe" install_tippecanoe

# --- detect (paths gate, PR-style against origin/main) ---
run_job "detect" \
  bash -lc 'cd "'"$ROOT"'" && node frontend/scripts/ci-paths-gate.mjs --base origin/main'

# --- publishability ---
run_job "publishability" \
  bash -lc 'cd "'"$ROOT"'" && python3 scripts/check_publishable.py'

# --- backend PostGIS pytest (CI services: 17-3.5 suite + 16-3.4 ARCH1) ---
PG17_NAME="ci-local-postgis17"
PG16_NAME="ci-local-postgis16"
cleanup_pg() {
  docker rm -f "$PG17_NAME" "$PG16_NAME" >/dev/null 2>&1 || true
}
trap cleanup_pg EXIT

cleanup_pg
# Free host ports in case a prior run left listeners.
fuser -k 5432/tcp 5433/tcp 3100/tcp 3200/tcp 3201/tcp >/dev/null 2>&1 || true
sleep 1

docker run -d --name "$PG17_NAME" \
  -e POSTGRES_USER=wealth_ci \
  -e POSTGRES_PASSWORD=ci-throwaway-only \
  -e POSTGRES_DB=wealth_it \
  -p 5432:5432 \
  postgis/postgis:17-3.5 >/dev/null
docker run -d --name "$PG16_NAME" \
  -e POSTGRES_USER=arch1 \
  -e POSTGRES_PASSWORD=arch1 \
  -e POSTGRES_DB=arch1 \
  -p 5433:5432 \
  postgis/postgis:16-3.4 >/dev/null

wait_pg() {
  local cname="$1" user="$2" db="$3"
  local i
  for i in $(seq 1 90); do
    if docker exec "$cname" pg_isready -U "$user" -d "$db" >/dev/null 2>&1; then
      # Extra settle: avoid "database system is starting up/shutting down" races.
      if docker exec "$cname" psql -U "$user" -d "$db" -v ON_ERROR_STOP=1 -c "SELECT 1" >/dev/null 2>&1; then
        return 0
      fi
    fi
    sleep 1
  done
  echo "ci:local: timed out waiting for $cname" >&2
  return 1
}

run_job "backend-postgis-ready" \
  bash -c 'wait_pg(){ local cname="$1" user="$2" db="$3"; for i in $(seq 1 90); do
      if docker exec "$cname" pg_isready -U "$user" -d "$db" >/dev/null 2>&1 \
        && docker exec "$cname" psql -U "$user" -d "$db" -v ON_ERROR_STOP=1 -c "SELECT 1" >/dev/null 2>&1; then
        return 0
      fi
      sleep 1
    done
    echo "ci:local: timed out waiting for $cname" >&2
    return 1
  }
  wait_pg "'"$PG17_NAME"'" wealth_ci wealth_it && wait_pg "'"$PG16_NAME"'" arch1 arch1'

export DATABASE_URL="postgresql://wealth_ci:ci-throwaway-only@127.0.0.1:5432/wealth_it"
export WEALTH_TEST_DATABASE_URL="$DATABASE_URL"
export WEALTH_REQUIRE_POSTGIS="1"
export ARCH1_TEST_DSN="postgresql://arch1:arch1@127.0.0.1:5433/arch1"

# Exact backend pytest commands from .github/workflows/ci.yml (backend job).
run_job "backend-postgis-pytest" \
  bash -c 'cd "'"$ROOT"'/backend"
    if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python; else PY=python3; fi
    docker exec "'"$PG17_NAME"'" psql -U wealth_ci -d wealth_it -v ON_ERROR_STOP=1 \
      -c "CREATE EXTENSION IF NOT EXISTS postgis; SELECT postgis_version();"
    docker exec "'"$PG16_NAME"'" psql -U arch1 -d arch1 -v ON_ERROR_STOP=1 \
      -c "CREATE EXTENSION IF NOT EXISTS postgis; SELECT postgis_version();"
    # Valuation surface tests (ci.yml)
    "$PY" -m pytest -q -p no:cacheprovider -m "not real" tests/surface
    # Full backend suite (ci.yml)
    "$PY" -m pytest -q -p no:cacheprovider -rs -m "not real"'

# --- frontend job (parity with .github/workflows/ci.yml frontend:) ---
# Extract `- run: npm …` / `npx tsc` lines from the frontend job so new steps
# (e.g. test:tile-layer-factory) are picked up automatically; then npm run build.
run_job "frontend-job" \
  bash -c '
set -euo pipefail
cd "'"$ROOT"'/frontend"
npm ci
mapfile -t RUNS < <(
  python3 - <<"PY"
from pathlib import Path
text = Path("../.github/workflows/ci.yml").read_text()
start = text.index("\n  frontend:\n")
rest = text[start + 1 :]
end = rest.index("\n  e2e:\n")
block = rest[:end]
for line in block.splitlines():
    s = line.strip()
    if s.startswith("- run: npm ") or s.startswith("- run: npx tsc"):
        print(s[len("- run: "):])
PY
)
for cmd in "${RUNS[@]}"; do
  echo "+ $cmd"
  eval "$cmd"
done
if ! printf "%s\n" "${RUNS[@]}" | grep -qx "npm run build"; then
  echo "+ npm run build"
  npm run build
fi
'

# --- Deploy-home Pester (backend job) — skip locally when pwsh absent ---
if command -v pwsh >/dev/null 2>&1; then
  run_job "pester" \
    bash -c 'cd "'"$ROOT"'" && pwsh -NoProfile -Command \
      "Install-Module Pester -Force -SkipPublisherCheck -Scope CurrentUser -MinimumVersion 5.0.0; \
       Invoke-Pester -Path scripts/ops/tests/DeployHome.Tests.ps1 -CI -Output Detailed"'
else
  SUMMARY+=("SKIP  pester (no pwsh)")
  echo "======== SKIP pester (no pwsh) ========"
fi

# --- processed-data manifests (backend job) ---
run_job "processed-data-manifests" \
  bash -c 'cd "'"$ROOT"'/backend"
    if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python; else PY=python3; fi
    "$PY" -m etl.load_processed --check
    "$PY" -m etl.refresh_registry --check'

# --- both Playwright e2e projects with CI stubs + test:esri-key-build ---
# CI e2e job: playwright install, then test:esri-key-build (2 projects) + test:e2e:ci (chromium).
run_job "playwright-install" \
  bash -c 'cd "'"$ROOT"'/frontend" && npx playwright install --with-deps chromium'

run_job "test:esri-key-build" \
  bash -c 'cd "'"$ROOT"'/frontend" && npm run test:esri-key-resolver && npm run test:esri-key-build'

# Free Next ports before the CI e2e webServer bind.
fuser -k 3100/tcp >/dev/null 2>&1 || true
sleep 1

run_job "test:e2e:ci" \
  bash -c 'cd "'"$ROOT"'/frontend" && CI=true npm run test:e2e:ci -- --grep-invert @quarantine'

echo ""
echo "======== ci:local summary ========"
for line in "${SUMMARY[@]}"; do
  echo "$line"
done
echo "================================="

if [[ $FAIL -ne 0 ]]; then
  echo "ci:local: FAILED" >&2
  exit 1
fi
echo "ci:local: OK"
exit 0
