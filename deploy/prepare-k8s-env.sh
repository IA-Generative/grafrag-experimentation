#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo ".env is missing. Run ./deploy/prepare-env.sh first." >&2
  exit 1
fi

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"
sync_llm_env_aliases

required_vars=(
  NAMESPACE
  REGISTRY
  IMAGE_TAG
  OPENWEBUI_IMAGE
  PIPELINES_IMAGE
  SEARXNG_IMAGE
  VALKEY_IMAGE
  OPENWEBUI_HOST
  KEYCLOAK_HOST
  SEARXNG_HOST
  SEARXNG_TLS_SECRET_NAME
  LETSENCRYPT_EMAIL
  KEYCLOAK_ADMIN
  SEARXNG_SECRET
  SCW_LLM_BASE_URL
  SCW_LLM_MODEL
  SEARXNG_OUTBOUND_PROXY_PAR_URL
  SEARXNG_OUTBOUND_PROXY_AMS_URL
  SEARXNG_OUTBOUND_PROXY_WAW_URL
)

missing=0
for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing required variable: ${var_name}" >&2
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  exit 1
fi

if [[ "${GRAPHRAG_CACHE_S3_ENABLED:-false}" == "true" ]]; then
  if [[ -z "${GRAPHRAG_CACHE_S3_BUCKET:-}" ]]; then
    echo "Missing required variable: GRAPHRAG_CACHE_S3_BUCKET" >&2
    exit 1
  fi
fi

echo "Kubernetes environment variables look complete."
