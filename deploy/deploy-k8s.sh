#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

./deploy/prepare-k8s-env.sh

source "${ROOT_DIR}/scripts/load_env.sh"
load_dotenv_preserve_existing "${ROOT_DIR}/.env"
sync_llm_env_aliases

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

render_file() {
  local source_file="$1"
  local target_file="k8s/rendered/$(basename "$source_file")"
  envsubst < "$source_file" > "$target_file"
}

render_file cert-manager/clusterissuer-letsencrypt.yaml
for manifest in k8s/base/*.yaml; do
  if [[ "$(basename "$manifest")" == "secret.example.yaml" ]]; then
    continue
  fi
  render_file "$manifest"
done

kubectl apply -f k8s/rendered/namespace.yaml
kubectl apply -f k8s/rendered/clusterissuer-letsencrypt.yaml
kubectl apply -f k8s/rendered/pvc-graphrag.yaml
kubectl apply -f k8s/rendered/configmap.yaml
kubectl apply -f k8s/rendered/configmap-searxng.yaml
python3 scripts/render_pipelines_configmap.py "$NAMESPACE" > k8s/rendered/configmap-pipelines.yaml
kubectl apply -f k8s/rendered/configmap-pipelines.yaml

kubectl -n "$NAMESPACE" create configmap keycloak-realm \
  --from-file=realm-openwebui.json=keycloak/realm-openwebui.json \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f k8s/rendered/deployment-bridge.yaml
kubectl apply -f k8s/rendered/service-bridge.yaml
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
kubectl apply -f k8s/rendered/ingress-openwebui.yaml
kubectl apply -f k8s/rendered/ingress-keycloak.yaml
kubectl apply -f k8s/rendered/ingress-searxng.yaml

kubectl -n "$NAMESPACE" wait --for=condition=available deployment/bridge --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/pipelines --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/openwebui --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/keycloak --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/searxng --timeout=240s
kubectl -n "$NAMESPACE" wait --for=condition=available deployment/search-valkey --timeout=240s

kubectl -n "$NAMESPACE" delete job graphrag-index --ignore-not-found
kubectl apply -f k8s/rendered/job-graphrag-index.yaml
kubectl -n "$NAMESPACE" wait --for=condition=complete job/graphrag-index --timeout=300s

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
