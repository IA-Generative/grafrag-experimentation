#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"
sync_llm_env_aliases

BUILD_PLATFORM="${DOCKER_BUILD_PLATFORM:-linux/amd64}"

docker buildx build \
  --platform "${BUILD_PLATFORM}" \
  --load \
  -t "${REGISTRY}/grafrag-bridge:${IMAGE_TAG}" \
  -f bridge/Dockerfile \
  .
echo "Built ${REGISTRY}/grafrag-bridge:${IMAGE_TAG}"
echo "Open WebUI and pipelines use upstream images: ${OPENWEBUI_IMAGE} and ${PIPELINES_IMAGE}"
