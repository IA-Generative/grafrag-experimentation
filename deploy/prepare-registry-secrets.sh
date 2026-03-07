#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"
sync_llm_env_aliases

if [[ -z "${REGISTRY_SERVER:-}" || -z "${REGISTRY_USERNAME:-}" || -z "${REGISTRY_PASSWORD:-}" ]]; then
  echo "Registry credentials are incomplete. Skipping image pull secret creation."
  exit 0
fi

if [[ "${REGISTRY_USERNAME}" == "CHANGE_ME" || "${REGISTRY_PASSWORD}" == "CHANGE_ME" ]]; then
  echo "Registry credentials still use placeholders. Skipping image pull secret creation."
  exit 0
fi

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"

kubectl -n "$NAMESPACE" create secret docker-registry grafrag-registry \
  --docker-server="${REGISTRY_SERVER}" \
  --docker-username="${REGISTRY_USERNAME}" \
  --docker-password="${REGISTRY_PASSWORD}" \
  --docker-email="${REGISTRY_EMAIL:-ops@example.local}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Applied image pull secret grafrag-registry in namespace ${NAMESPACE}."
