#!/usr/bin/env bash
# EXTERNAL-UPTIME-1: one curl of a public health URL, for the scheduled
# GitHub Actions workflow .github/workflows/uptime.yml. $0, no paid vendor.
# Pass rule (same as uptime-check.sh): curl exit 0 and HTTP 200; plus the
# body must contain "status":"ok". Exit 0 pass, 1 fail, 2 usage.
set -uo pipefail

if [[ $# -ne 1 || -z "${1}" ]]; then
  echo "uptime-external: usage: uptime-external.sh <url>" >&2
  exit 2
fi

url="${1}"
if [[ ! "${url}" =~ ^https?://[A-Za-z0-9.-]+(:[0-9]+)?(/.*)?$ ]]; then
  echo "uptime-external: invalid url: ${url}" >&2
  exit 2
fi
max_time="${UPTIME_MAX_TIME:-30}"
retries="${UPTIME_RETRIES:-2}"
retry_delay="${UPTIME_RETRY_DELAY:-10}"
body_file="$(mktemp)"
trap 'rm -f "${body_file}"' EXIT

meta="$(curl -sS -o "${body_file}" -w '%{http_code} %{time_total}' \
  --max-time "${max_time}" --retry "${retries}" --retry-delay "${retry_delay}" \
  --retry-connrefused "${url}" 2>/dev/null)"
curl_ec=$?
code="${meta%% *}"
time_total="${meta##* }"
[[ -n "${code}" ]] || code="000"
[[ -n "${time_total}" && "${meta}" == *" "* ]] || time_total="0"

if [[ "${curl_ec}" -ne 0 ]]; then
  reason="curl"
elif [[ "${code}" != "200" ]]; then
  reason="status"
elif ! grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' "${body_file}"; then
  reason="body"
else
  reason=""
fi

if [[ -z "${reason}" ]]; then
  line1="uptime-external: OK http_code=200 curl_exit=0"
  rc=0
else
  line1="uptime-external: FAIL http_code=${code} curl_exit=${curl_ec} reason=${reason}"
  rc=1
fi
line2="uptime-external: time_total=${time_total}s"
echo "${line1}"
echo "${line2}"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  printf '%s\n\n%s\n\n%s\n' "### External uptime: ${url}" "${line1}" "${line2}" >>"${GITHUB_STEP_SUMMARY}"
fi
exit "${rc}"
