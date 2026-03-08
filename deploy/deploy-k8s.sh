#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

./deploy/prepare-k8s-env.sh

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"
sync_llm_env_aliases

: "${GRAPHRAG_INDEX_TIMEOUT_SECONDS:=3600}"
export GRAPHRAG_INDEX_TIMEOUT_SECONDS
: "${RUN_GRAPHRAG_INDEX_JOB:=false}"
export RUN_GRAPHRAG_INDEX_JOB

for dependency in kubectl docker envsubst curl; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    echo "Missing required dependency: $dependency" >&2
    exit 1
  fi
done

./deploy/build-images.sh
./deploy/push-images.sh
./deploy/prepare-registry-secrets.sh || true
./deploy/prepare-k8s-secrets.sh

mkdir -p k8s/rendered

RENDER_VARS='${BRIDGE_HOST} ${BRIDGE_TLS_SECRET_NAME} ${CORPUS_MANAGER_AUTH_REQUIRED} ${CORPUS_MANAGER_CLIENT_ID} ${CORPUS_MANAGER_HOST} ${CORPUS_MANAGER_TLS_SECRET_NAME} ${DRIVE_REPLICAS} ${GRAPHRAG_CACHE_S3_BUCKET} ${GRAPHRAG_CACHE_S3_ENABLED} ${GRAPHRAG_CACHE_S3_ENDPOINT_URL} ${GRAPHRAG_CACHE_S3_PREFIX} ${GRAPHRAG_CACHE_S3_REGION} ${GRAPHRAG_INDEX_TIMEOUT_SECONDS} ${GRAPHRAG_METHOD} ${GRAPHRAG_RESPONSE_TYPE} ${GRAPHRAG_TOP_K} ${GRAPH_VIEWER_AUTH_REQUIRED} ${GRAPH_VIEWER_CLIENT_ID} ${IMAGE_TAG} ${KEYCLOAK_ADMIN} ${KEYCLOAK_CLIENT_SECRET} ${KEYCLOAK_HOST} ${KEYCLOAK_REALM} ${KEYCLOAK_TLS_SECRET_NAME} ${LETSENCRYPT_EMAIL} ${NAMESPACE} ${OPENAI_EMBEDDING_MODEL} ${OPENAI_EMBEDDING_VECTOR_SIZE} ${OPENWEBUI_HOST} ${OPENWEBUI_IMAGE} ${PIPELINES_IMAGE} ${REGISTRY} ${SCW_LLM_BASE_URL} ${SCW_LLM_MODEL} ${SEARXNG_HOST} ${SEARXNG_IMAGE} ${SEARXNG_REPLICAS} ${SEARXNG_TLS_SECRET_NAME} ${TLS_SECRET_NAME} ${VALKEY_IMAGE}'

render_file() {
  local source_file="$1"
  local target_file="k8s/rendered/$(basename "$source_file")"
  envsubst "$RENDER_VARS" < "$source_file" > "$target_file"
}

render_file cert-manager/clusterissuer-letsencrypt.yaml
for manifest in k8s/base/*.yaml; do
  manifest_name="$(basename "$manifest")"
  if [[ "$manifest_name" == "secret.example.yaml" || "$manifest_name" == "configmap-searxng.yaml" ]]; then
    continue
  fi
  if [[ "$manifest_name" == "ingress-searxng.yaml" && -z "${SEARXNG_HOST:-}" ]]; then
    continue
  fi
  render_file "$manifest"
done
python3 scripts/render_keycloak_realm.py \
  --source keycloak/realm-openwebui.k8s.json \
  --output k8s/rendered/realm-openwebui.json \
  --password-file keycloak/realm-passwords.local.json

kubectl apply -f k8s/rendered/namespace.yaml
kubectl apply -f k8s/rendered/clusterissuer-letsencrypt.yaml
kubectl apply -f k8s/rendered/pvc-graphrag.yaml
kubectl apply -f k8s/rendered/pvc-corpus-manager.yaml
kubectl apply -f k8s/rendered/configmap.yaml
kubectl apply -f k8s/rendered/configmap-drive-demo.yaml
python3 scripts/render_searxng_configmap.py "$NAMESPACE" > k8s/rendered/configmap-searxng.yaml
kubectl apply -f k8s/rendered/configmap-searxng.yaml
python3 scripts/render_pipelines_configmap.py "$NAMESPACE" > k8s/rendered/configmap-pipelines.yaml
kubectl apply -f k8s/rendered/configmap-pipelines.yaml

kubectl -n "$NAMESPACE" create configmap keycloak-realm \
  --from-file=realm-openwebui.json=k8s/rendered/realm-openwebui.json \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f k8s/rendered/deployment-bridge.yaml
kubectl apply -f k8s/rendered/service-bridge.yaml
kubectl apply -f k8s/rendered/deployment-corpus-manager.yaml
kubectl apply -f k8s/rendered/service-corpus-manager.yaml
kubectl apply -f k8s/rendered/deployment-corpus-worker.yaml
kubectl apply -f k8s/rendered/deployment-drive.yaml
kubectl apply -f k8s/rendered/service-drive.yaml
kubectl apply -f k8s/rendered/deployment-pipelines.yaml
kubectl apply -f k8s/rendered/service-pipelines.yaml
kubectl apply -f k8s/rendered/deployment-openwebui.yaml
kubectl apply -f k8s/rendered/service-openwebui.yaml
kubectl apply -f k8s/rendered/deployment-keycloak.yaml
kubectl apply -f k8s/rendered/service-keycloak.yaml
kubectl apply -f k8s/rendered/deployment-valkey.yaml
kubectl apply -f k8s/rendered/service-valkey.yaml
kubectl apply -f k8s/rendered/deployment-searxng.yaml
kubectl apply -f k8s/rendered/service-searxng.yaml
kubectl apply -f k8s/rendered/ingress-bridge.yaml
kubectl apply -f k8s/rendered/ingress-corpus-manager.yaml
kubectl apply -f k8s/rendered/ingress-openwebui.yaml
kubectl apply -f k8s/rendered/ingress-keycloak.yaml
if [[ -n "${SEARXNG_HOST:-}" ]]; then
  kubectl apply -f k8s/rendered/ingress-searxng.yaml
fi

kubectl -n "$NAMESPACE" wait --for=condition=available deployment/bridge --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/corpus-manager --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/corpus-worker --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/drive --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/pipelines --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/openwebui --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/keycloak --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/searxng --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/search-valkey --timeout=240s

if [[ "${RUN_GRAPHRAG_INDEX_JOB}" == "true" ]]; then
  kubectl -n "$NAMESPACE" delete job graphrag-index --ignore-not-found
  kubectl apply -f k8s/rendered/job-graphrag-index.yaml
  JOB_WAIT_TIMEOUT_SECONDS=$((GRAPHRAG_INDEX_TIMEOUT_SECONDS + 120))
  kubectl -n "$NAMESPACE" wait --for=condition=complete job/graphrag-index --timeout="${JOB_WAIT_TIMEOUT_SECONDS}s"
else
  echo "Skipping GraphRAG index job because RUN_GRAPHRAG_INDEX_JOB=${RUN_GRAPHRAG_INDEX_JOB}."
fi

kubectl -n "$NAMESPACE" port-forward service/bridge 18081:8081 >/tmp/grafrag-bridge-port-forward.log 2>&1 &
BRIDGE_FORWARD_PID=$!
kubectl -n "$NAMESPACE" port-forward service/openwebui 13000:80 >/tmp/grafrag-openwebui-port-forward.log 2>&1 &
OPENWEBUI_FORWARD_PID=$!

cleanup() {
  kill "${BRIDGE_FORWARD_PID}" "${OPENWEBUI_FORWARD_PID}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sleep 5

BRIDGE_BASE_URL=http://127.0.0.1:18081 OPENWEBUI_BASE_URL=http://127.0.0.1:13000 ./smoke-tests.sh
BRIDGE_BASE_URL=http://127.0.0.1:18081 OPENWEBUI_BASE_URL=http://127.0.0.1:13000 ./integration-tests.sh
BRIDGE_BASE_URL=http://127.0.0.1:18081 OPENWEBUI_BASE_URL=http://127.0.0.1:13000 ./penetration-tests.sh
BRIDGE_BASE_URL=http://127.0.0.1:18081 OPENWEBUI_BASE_URL=http://127.0.0.1:13000 ./report.sh

kubectl -n "$NAMESPACE" get pods,svc,ingress
