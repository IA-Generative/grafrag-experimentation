#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${SEARXNG_LOCAL_BASE_URL:-http://localhost:${SEARXNG_LOCAL_PORT:-8083}}"
QUERY="${1:-guerre de cent ans}"
TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

if ! curl -fsS --get "${BASE_URL}/search" \
  --data-urlencode "q=${QUERY}" \
  --data-urlencode "format=json" \
  >"$TMP_FILE"; then
  CONTAINER_ID="$(docker compose --profile search ps -q searxng)"
  if [ -z "$CONTAINER_ID" ]; then
    echo "SearXNG n'est pas joignable sur ${BASE_URL} et aucun conteneur searxng n'a ete trouve." >&2
    exit 1
  fi
  docker exec -e SEARCH_QUERY="$QUERY" "$CONTAINER_ID" python -c "import json, os, urllib.parse, urllib.request; url='http://localhost:8080/search?' + urllib.parse.urlencode({'q': os.environ['SEARCH_QUERY'], 'format': 'json'}); print(json.dumps(json.load(urllib.request.urlopen(url, timeout=30)), ensure_ascii=False))" >"$TMP_FILE"
fi

python3 - "$TMP_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

results = payload.get("results") or []
print(f"results={len(results)}")
if results:
    first = results[0]
    print(f"title={first.get('title', '')}")
    print(f"url={first.get('url', '')}")
PY
