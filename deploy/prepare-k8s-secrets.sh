#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"
sync_llm_env_aliases

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"

kubectl -n "$NAMESPACE" create secret generic grafrag-secrets \
  --from-literal=SCW_SECRET_KEY_LLM="${SCW_SECRET_KEY_LLM:-CHANGE_ME}" \
  --from-literal=SCW_API_KEY="${SCW_API_KEY:-${SCW_SECRET_KEY_LLM:-CHANGE_ME}}" \
  --from-literal=PIPELINES_API_KEY="${PIPELINES_API_KEY:-CHANGE_ME}" \
  --from-literal=WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-CHANGE_ME}" \
  --from-literal=SEARXNG_SECRET="${SEARXNG_SECRET:-CHANGE_ME}" \
  --from-literal=KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-CHANGE_ME}" \
  --from-literal=KEYCLOAK_CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-CHANGE_ME}" \
  --from-literal=GRAPHRAG_CACHE_S3_ACCESS_KEY_ID="${GRAPHRAG_CACHE_S3_ACCESS_KEY_ID:-}" \
  --from-literal=GRAPHRAG_CACHE_S3_SECRET_ACCESS_KEY="${GRAPHRAG_CACHE_S3_SECRET_ACCESS_KEY:-}" \
  --from-literal=GRAPHRAG_CACHE_S3_SESSION_TOKEN="${GRAPHRAG_CACHE_S3_SESSION_TOKEN:-}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Applied Kubernetes secret grafrag-secrets in namespace ${NAMESPACE}."
