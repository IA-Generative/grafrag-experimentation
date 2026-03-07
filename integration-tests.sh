#!/usr/bin/env bash
set -euo pipefail

PYTEST_BIN="${PYTEST_BIN:-}"
if [[ -z "${PYTEST_BIN}" ]]; then
  if command -v pytest >/dev/null 2>&1; then
    PYTEST_BIN="pytest"
  elif [[ -x .venv/bin/pytest ]]; then
    PYTEST_BIN=".venv/bin/pytest"
  else
    echo "pytest is not installed. Install requirements-dev.txt first." >&2
    exit 1
  fi
fi

BRIDGE_BASE_URL="${BRIDGE_BASE_URL:-http://localhost:${BRIDGE_PORT:-8081}}"
OPENWEBUI_BASE_URL="${OPENWEBUI_BASE_URL:-http://localhost:${OPENWEBUI_PORT:-3000}}"

BRIDGE_BASE_URL="${BRIDGE_BASE_URL}" OPENWEBUI_BASE_URL="${OPENWEBUI_BASE_URL}" \
  "${PYTEST_BIN}" tests/functional

