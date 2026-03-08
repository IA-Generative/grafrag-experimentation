#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"
sync_llm_env_aliases

BUILD_PLATFORM="${DOCKER_BUILD_PLATFORM:-linux/amd64}"
BUILD_OUTPUT="${DOCKER_BUILD_OUTPUT:-load}"

build_args=(
  --platform "${BUILD_PLATFORM}"
  -t "${REGISTRY}/grafrag-bridge:${IMAGE_TAG}"
  -f bridge/Dockerfile
  .
)

case "${BUILD_OUTPUT}" in
  load)
    build_args=(--load "${build_args[@]}")
    ;;
  push)
    build_args=(--push "${build_args[@]}")
    ;;
  *)
    echo "Unsupported DOCKER_BUILD_OUTPUT: ${BUILD_OUTPUT}. Expected load or push." >&2
    exit 1
    ;;
esac

docker buildx build "${build_args[@]}"
echo "Built ${REGISTRY}/grafrag-bridge:${IMAGE_TAG} with build output ${BUILD_OUTPUT}"
echo "Open WebUI and pipelines use upstream images: ${OPENWEBUI_IMAGE} and ${PIPELINES_IMAGE}"
