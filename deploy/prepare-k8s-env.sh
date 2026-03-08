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

: "${GRAPHRAG_INDEX_TIMEOUT_SECONDS:=3600}"
export GRAPHRAG_INDEX_TIMEOUT_SECONDS

: "${RUN_GRAPHRAG_INDEX_JOB:=false}"
export RUN_GRAPHRAG_INDEX_JOB

: "${CORPUS_MANAGER_CLIENT_ID:=corpus-manager}"
export CORPUS_MANAGER_CLIENT_ID

: "${CORPUS_MANAGER_AUTH_REQUIRED:=true}"
export CORPUS_MANAGER_AUTH_REQUIRED

if [[ -z "${CORPUS_MANAGER_HOST:-}" && -n "${BASE_DOMAIN:-}" ]]; then
  CORPUS_MANAGER_HOST="corpus.${BASE_DOMAIN}"
fi
export CORPUS_MANAGER_HOST

: "${CORPUS_MANAGER_TLS_SECRET_NAME:=corpus-manager-tls}"
export CORPUS_MANAGER_TLS_SECRET_NAME

if [[ -z "${OPENAI_EMBEDDING_VECTOR_SIZE:-}" ]]; then
  case "${OPENAI_EMBEDDING_MODEL:-bge-multilingual-gemma2}" in
    qwen3-embedding-8b)
      OPENAI_EMBEDDING_VECTOR_SIZE=4096
      ;;
    *)
      OPENAI_EMBEDDING_VECTOR_SIZE=3584
      ;;
  esac
fi
export OPENAI_EMBEDDING_VECTOR_SIZE

required_vars=(
  NAMESPACE
  REGISTRY
  IMAGE_TAG
  OPENWEBUI_IMAGE
  PIPELINES_IMAGE
  SEARXNG_IMAGE
  VALKEY_IMAGE
  BRIDGE_HOST
  OPENWEBUI_HOST
  KEYCLOAK_HOST
  LETSENCRYPT_EMAIL
  KEYCLOAK_ADMIN
  SEARXNG_SECRET
  SCW_LLM_BASE_URL
  SCW_LLM_MODEL
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

if [[ -n "${SEARXNG_HOST:-}" && -z "${SEARXNG_TLS_SECRET_NAME:-}" ]]; then
  echo "Missing required variable: SEARXNG_TLS_SECRET_NAME" >&2
  exit 1
fi

if [[ "${GRAPHRAG_CACHE_S3_ENABLED:-false}" == "true" ]]; then
  if [[ -z "${GRAPHRAG_CACHE_S3_BUCKET:-}" ]]; then
    echo "Missing required variable: GRAPHRAG_CACHE_S3_BUCKET" >&2
    exit 1
  fi
fi

echo "Kubernetes environment variables look complete."
