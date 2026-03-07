#!/usr/bin/env bash
set -euo pipefail

REPORT_DIR="reports"
mkdir -p "${REPORT_DIR}"
REPORT_FILE="${REPORT_DIR}/final-report.md"

BRIDGE_BASE_URL="${BRIDGE_BASE_URL:-http://localhost:${BRIDGE_PORT:-8081}}"
OPENWEBUI_BASE_URL="${OPENWEBUI_BASE_URL:-http://localhost:${OPENWEBUI_PORT:-3000}}"
KEYCLOAK_BASE_URL="${KEYCLOAK_BASE_URL:-http://localhost:${KEYCLOAK_PORT:-8082}}"

bridge_health="$(curl -ksS "${BRIDGE_BASE_URL}/healthz" 2>/dev/null || echo unavailable)"
openwebui_health_code="$(curl -ksS -L -o /dev/null -w '%{http_code}' "${OPENWEBUI_BASE_URL}" 2>/dev/null || echo unavailable)"
keycloak_health_code="$(curl -ksS -o /dev/null -w '%{http_code}' "${KEYCLOAK_BASE_URL}" 2>/dev/null || echo unavailable)"

problems="None recorded."
fixes="None recorded."

if [[ -f "${REPORT_DIR}/last-problems.txt" ]]; then
  problems="$(cat "${REPORT_DIR}/last-problems.txt")"
fi

if [[ -f "${REPORT_DIR}/last-fixes.txt" ]]; then
  fixes="$(cat "${REPORT_DIR}/last-fixes.txt")"
fi

cat > "${REPORT_FILE}" <<EOF
# grafrag-experimentation report

Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")

## Resultats des tests

- Smoke tests: voir execution shell courante
- Functional tests: voir execution shell courante
- Security tests: voir execution shell courante

## Services deployes

- Bridge: ${bridge_health}
- Open WebUI HTTP code: ${openwebui_health_code}
- Keycloak HTTP code: ${keycloak_health_code}

## URLs

- Open WebUI: ${OPENWEBUI_BASE_URL}
- Bridge API: ${BRIDGE_BASE_URL}
- Keycloak: ${KEYCLOAK_BASE_URL}

## Problemes detectes

${problems}

## Corrections appliquees

${fixes}
EOF

echo "Wrote ${REPORT_FILE}"

