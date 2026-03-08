#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANEF_ROOT="${ANEF_ROOT:-${ROOT_DIR}/../anef-knowledge-assistant}"

if [[ ! -d "${ANEF_ROOT}" ]]; then
  printf 'anef repository missing: %s\n' "${ANEF_ROOT}" >&2
  exit 1
fi

export GRAFRAG_ROOT="${ROOT_DIR}"
export ANEF_ROOT

exec bash "${ANEF_ROOT}/scripts/redeploy_openwebui_stack.sh" "$@"
