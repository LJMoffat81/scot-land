#!/usr/bin/env bash
# Mandatory post-deploy smoke for Scot-LAND.
# Usage:
#   ./scripts/smoke.sh https://example.com
#   SITE_URL=https://app.example API_URL=https://api.example ./scripts/smoke.sh
# Exit non-zero when any check fails.

set -uo pipefail

SITE_URL="${SITE_URL:-${1:-}}"
API_URL="${API_URL:-${SITE_URL:-}}"

if [[ -z "${SITE_URL}" ]]; then
  echo "Usage: $0 <site-or-api-base-url>" >&2
  echo "   or: SITE_URL=... API_URL=... $0" >&2
  exit 2
fi

SITE_URL="${SITE_URL%/}"
API_URL="${API_URL%/}"

# Scotland-wide viewport so coastal/offshore layers can return features.
BBOX="south=54.6&west=-7.7&north=60.9&east=-0.7&max_features=80"

PASS=0
FAIL=0
ROWS=()

note_row() {
  local status="$1" name="$2" detail="$3"
  ROWS+=("$(printf '%-6s | %-40s | %s' "$status" "$name" "$detail")")
  if [[ "$status" == "PASS" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
  fi
}

http_code() {
  local url="$1"
  curl -sS -o /tmp/scot-land-smoke.body -w '%{http_code}' --max-time 45 "$url" 2>/tmp/scot-land-smoke.err || echo "000"
}

echo "Scot-LAND post-deploy smoke"
echo "  SITE_URL=${SITE_URL}"
echo "  API_URL=${API_URL}"
echo

code="$(http_code "${SITE_URL}/")"
if [[ "$code" == "200" ]]; then
  note_row PASS "site /" "HTTP ${code}"
else
  note_row FAIL "site /" "HTTP ${code} (want 200)"
fi

code="$(http_code "${API_URL}/health")"
if [[ "$code" == "200" ]]; then
  # HEALTH-TRIM / SW-037: public /health is status + version only.
  health_line="$(python3 - <<'PY' 2>/dev/null || true
import json
b = json.load(open("/tmp/scot-land-smoke.body", encoding="utf-8"))
print(f"{b.get('status') or ''}|{b.get('version') or ''}")
PY
)"
  status="${health_line%%|*}"
  version="${health_line#*|}"
  if [[ "$status" == "ok" && -n "$version" ]]; then
    note_row PASS "/health" "HTTP 200 status=${status} version=${version}"
  else
    note_row FAIL "/health" "HTTP 200 but status/version missing (got status=${status} version=${version})"
  fi
else
  note_row FAIL "/health" "HTTP ${code} (want 200)"
fi

code="$(http_code "${API_URL}/layers/catalog")"
if [[ "$code" != "200" ]]; then
  note_row FAIL "/layers/catalog" "HTTP ${code} (want 200)"
else
  note_row PASS "/layers/catalog" "HTTP 200"
  mapfile -t LAYER_SPECS < <(python3 - <<'PY'
import json
data = json.load(open("/tmp/scot-land-smoke.body", encoding="utf-8"))
for row in data.get("layers") or []:
    if not isinstance(row, dict):
        continue
    if (row.get("status") or "").lower() != "live":
        continue
    endpoint = (row.get("endpoint") or "").strip()
    if not endpoint.startswith("/"):
        continue
    if "{z}" in endpoint or "{x}" in endpoint:
        continue
    print(f"{row.get('id')}|{endpoint}")
PY
)
  for spec in "${LAYER_SPECS[@]:-}"; do
    [[ -z "${spec:-}" ]] && continue
    lid="${spec%%|*}"
    endpoint="${spec#*|}"
    if [[ "$endpoint" == *\?* ]]; then
      full="${API_URL}${endpoint}"
    else
      full="${API_URL}${endpoint}?${BBOX}"
    fi
    code="$(http_code "$full")"
    if [[ "$code" == "200" ]]; then
      feat_count="$(python3 - <<'PY'
import json
data = json.load(open("/tmp/scot-land-smoke.body", encoding="utf-8"))
feats = data.get("features")
print(len(feats) if isinstance(feats, list) else -1)
PY
)"
      if [[ "$feat_count" -gt 0 ]]; then
        note_row PASS "layer:${lid}" "HTTP 200 features=${feat_count}"
      elif [[ "$feat_count" -eq 0 ]]; then
        note_row FAIL "layer:${lid}" "HTTP 200 features=0 (want >0 or 503 not-yet-loaded)"
      else
        note_row PASS "layer:${lid}" "HTTP 200 (non-FeatureCollection OK)"
      fi
    elif [[ "$code" == "503" ]]; then
      detail="$(python3 - <<'PY'
import json
raw = open("/tmp/scot-land-smoke.body", encoding="utf-8").read()
try:
    data = json.loads(raw)
except Exception:
    print(raw[:120].replace("\n", " "))
    raise SystemExit
detail = data.get("detail") or (data.get("meta") or {}).get("error") or "not loaded"
print(str(detail)[:120].replace("\n", " "))
PY
)"
      note_row PASS "layer:${lid}" "HTTP 503 not-yet-loaded (${detail})"
    else
      note_row FAIL "layer:${lid}" "HTTP ${code} (want 200+features or 503 unload)"
    fi
  done
fi

echo
echo "STATUS | CHECK                                    | DETAIL"
echo "-------+------------------------------------------+----------------------------------------"
for row in "${ROWS[@]}"; do
  echo "$row"
done
echo
echo "Summary: PASS=${PASS} FAIL=${FAIL}"

if [[ "$FAIL" -gt 0 ]]; then
  echo "SMOKE FAILED" >&2
  exit 1
fi
echo "SMOKE PASSED"
exit 0
