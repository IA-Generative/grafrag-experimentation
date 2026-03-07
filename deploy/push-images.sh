#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"
sync_llm_env_aliases

docker push "${REGISTRY}/grafrag-bridge:${IMAGE_TAG}"
echo "Pushed ${REGISTRY}/grafrag-bridge:${IMAGE_TAG}"
