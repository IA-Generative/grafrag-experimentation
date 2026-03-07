#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BRIDGE_BASE_URL="${BRIDGE_BASE_URL:-http://localhost:${BRIDGE_PORT:-8081}}"

echo "Generating the Wikipedia corpus"
python3 scripts/generate_medieval_wars_corpus.py --clean

echo "Checking bridge health"
curl -fsS "${BRIDGE_BASE_URL}/healthz" >/dev/null

echo "Triggering indexing"
./scripts/index_corpus.sh >/dev/null

response_file="$(mktemp)"
trap 'rm -f "${response_file}"' EXIT

echo "Running an end-to-end query"
curl -fsS -X POST "${BRIDGE_BASE_URL}/query" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Compare le traite de Bretigny et le traite de Troyes.","method":"global","top_k":6}' \
  >"${response_file}"

python3 - "${response_file}" <<'PY'
import json
import sys
from pathlib import Path

response_path = Path(sys.argv[1])
payload = json.loads(response_path.read_text(encoding="utf-8"))

answer = payload.get("answer", "")
citations = payload.get("citations", [])
engine_used = payload.get("engine_used", "")
warnings = payload.get("warnings", [])

if not answer.strip():
    raise SystemExit("Bridge answer is empty.")
if not citations:
    raise SystemExit("Bridge returned no citations.")

paths = " ".join(citation.get("path", "") for citation in citations).lower()
haystack = f"{answer.lower()} {paths}"
if "bretigny" not in haystack and "troyes" not in haystack:
    raise SystemExit(
        "The query did not surface expected treaty-specific material in the answer or citations."
    )

summary = {
    "engine_used": engine_used,
    "warnings": warnings,
    "citations": citations,
    "answer_preview": answer[:400],
}
print(json.dumps(summary, indent=2, ensure_ascii=False))
PY

echo "End-to-end test passed."
