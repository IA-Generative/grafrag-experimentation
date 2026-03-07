#!/usr/bin/env bash
set -euo pipefail

BRIDGE_BASE_URL="${BRIDGE_BASE_URL:-http://localhost:${BRIDGE_PORT:-8081}}"
OPENWEBUI_BASE_URL="${OPENWEBUI_BASE_URL:-http://localhost:${OPENWEBUI_PORT:-3000}}"
REPORT_DIR="reports"
mkdir -p "${REPORT_DIR}"

bridge_headers_file="$(mktemp)"
openwebui_headers_file="$(mktemp)"

cleanup() {
  rm -f "${bridge_headers_file}" "${openwebui_headers_file}"
}
trap cleanup EXIT

echo "Running basic endpoint checks"
bridge_health_code="$(curl -ksS -o /dev/null -w '%{http_code}' "${BRIDGE_BASE_URL}/healthz")"
openwebui_code="$(curl -ksS -L -o /dev/null -w '%{http_code}' "${OPENWEBUI_BASE_URL}")"
[[ "${bridge_health_code}" == "200" ]]
[[ "${openwebui_code}" =~ ^(200|302|307)$ ]]

echo "Capturing headers"
curl -ksS -D "${bridge_headers_file}" -o /dev/null "${BRIDGE_BASE_URL}/healthz"
curl -ksS -D "${openwebui_headers_file}" -o /dev/null "${OPENWEBUI_BASE_URL}"

echo "Testing trivial injection handling"
injection_code="$(curl -ksS -o /dev/null -w '%{http_code}' -X POST "${BRIDGE_BASE_URL}/query" \
  -H 'Content-Type: application/json' \
  -d '{"question":"'\'' OR 1=1; DROP TABLE graph; --"}')"
[[ "${injection_code}" =~ ^(200|422)$ ]]

echo "Testing obvious auth bypass path"
auth_api_code="$(curl -ksS -o /dev/null -w '%{http_code}' "${OPENWEBUI_BASE_URL}/api/v1/auths/")"
[[ "${auth_api_code}" =~ ^(401|403)$ ]]

echo "Testing port reachability"
if command -v nc >/dev/null 2>&1; then
  bridge_host="${BRIDGE_BASE_URL#*://}"
  bridge_host="${bridge_host%%/*}"
  bridge_name="${bridge_host%%:*}"
  bridge_port="${bridge_host##*:}"
  if [[ "${bridge_name}" == "${bridge_port}" ]]; then
    bridge_port="80"
  fi
  nc -z "${bridge_name}" "${bridge_port}"
fi

echo "Penetration smoke tests passed." | tee "${REPORT_DIR}/penetration-summary.txt"
