#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"
sync_llm_env_aliases

BRIDGE_BASE_URL="${BRIDGE_BASE_URL:-http://localhost:${BRIDGE_PORT:-8081}}"

if curl -fsS "${BRIDGE_BASE_URL}/healthz" >/dev/null 2>&1; then
  curl -fsS -X POST "${BRIDGE_BASE_URL}/index" -H 'Content-Type: application/json' -d '{"rebuild": true}'
  echo
  exit 0
fi

if command -v graphrag >/dev/null 2>&1; then
  graphrag index --root "${ROOT_DIR}/graphrag"
  exit 0
fi

./scripts/init_graphrag.sh
echo "Bridge and GraphRAG CLI are unavailable. Generated the fallback manifest instead."
