#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p graphrag/input graphrag/output

if [[ ! -f graphrag/input/sample-corpus.md ]]; then
  cp /dev/null graphrag/input/sample-corpus.md
fi

if [[ ! -f graphrag/output/index-manifest.json ]]; then
  python3 - <<'PY'
from pathlib import Path
import json

root = Path("graphrag")
documents = []
for path in sorted((root / "input").rglob("*")):
    if path.is_file():
        documents.append(
            {
                "path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
            }
        )
(root / "output").mkdir(parents=True, exist_ok=True)
(root / "output" / "index-manifest.json").write_text(
    json.dumps({"generated_by": "init-script", "documents": documents}, indent=2),
    encoding="utf-8",
)
PY
fi

echo "GraphRAG corpus directories are initialized."

