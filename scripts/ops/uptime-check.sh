#!/usr/bin/env bash
# Free / self-hosted uptime probe for the public home origin.
# Hits https://scot-land.scot/backend/health; appends failures to .deploy/uptime.log.
# $0/month — use cron or the systemd timer units beside this script.
#
#   */5 * * * * /path/to/scot-land/scripts/ops/uptime-check.sh
#   systemctl --user enable --now scot-land-uptime.timer

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_DIR="${ROOT}/.deploy"
LOG_FILE="${DEPLOY_DIR}/uptime.log"
HEALTH_URL="${SCOT_LAND_HEALTH_URL:-https://scot-land.scot/backend/health}"
TIMEOUT_SEC="${SCOT_LAND_HEALTH_TIMEOUT:-30}"
LOG_SUCCESS="${SCOT_LAND_UPTIME_LOG_SUCCESS:-0}"

mkdir -p "${DEPLOY_DIR}"

ts="$(date '+%Y-%m-%d %H:%M:%S')"

set +e
code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time "${TIMEOUT_SEC}" "${HEALTH_URL}")"
curl_ec=$?
set -e

if [[ "${curl_ec}" -eq 0 && "${code}" == "200" ]]; then
  if [[ "${LOG_SUCCESS}" == "1" ]]; then
    echo "${ts} [INFO] OK ${HEALTH_URL} HTTP ${code}" >>"${LOG_FILE}"
  fi
  exit 0
fi

echo "${ts} [ERROR] FAIL ${HEALTH_URL} HTTP ${code:-0} curl_exit=${curl_ec}" >>"${LOG_FILE}"
exit 1
