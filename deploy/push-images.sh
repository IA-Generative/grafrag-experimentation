#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"
sync_llm_env_aliases

if [[ "${DOCKER_BUILD_OUTPUT:-load}" == "push" ]]; then
  echo "Skipping docker push because build output already pushed ${REGISTRY}/grafrag-bridge:${IMAGE_TAG}"
  exit 0
fi

docker push "${REGISTRY}/grafrag-bridge:${IMAGE_TAG}"
echo "Pushed ${REGISTRY}/grafrag-bridge:${IMAGE_TAG}"
