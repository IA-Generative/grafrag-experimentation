#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

mkdir -p reports
: > reports/last-problems.txt
: > reports/last-fixes.txt

run_suite() {
  ./smoke-tests.sh
  ./integration-tests.sh
  ./penetration-tests.sh
}

if run_suite; then
  echo "No issues detected." > reports/last-problems.txt
  echo "No automatic fixes were needed." > reports/last-fixes.txt
  ./report.sh
  exit 0
fi

echo "Initial test suite failed." > reports/last-problems.txt

./deploy/prepare-env.sh >> reports/last-fixes.txt
./scripts/init_graphrag.sh >> reports/last-fixes.txt

if curl -fsS "${BRIDGE_BASE_URL:-http://localhost:${BRIDGE_PORT:-8081}}/healthz" >/dev/null 2>&1; then
  ./scripts/index_corpus.sh >> reports/last-fixes.txt
fi

run_suite
./report.sh

