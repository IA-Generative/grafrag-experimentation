# GraphRAG Indexing Benchmark v3

- Generated at: 2026-03-08T12:15:54.995589+01:00
- Commit: beafc9a
- Runner: docker
- Docker container: grafrag-experimentation-bridge-1
- GraphRAG: 3.0.6
- LiteLLM: 1.82.0
- Optimized profile: v3 (`concurrent_requests: 64`)
- Reference baseline/v2 taken from: benchmarks/results.json

## Corpus

- Documents: 17
- Total size: 659262 bytes

## Runs

| Run | Method | Cache | Chunking | Chunks | LLM calls | Total time |
| --- | --- | --- | --- | ---: | ---: | ---: |
| baseline_cold (reference) | standard | cold | 1200/100 | 157 | 2437 | 1752.712s |
| optimized_v2_cold (reference) | standard | cold | 2200/64 | 84 | 1424 | 1189.072s |
| optimized_v3_cold | standard | cold | 2200/64 | 84 | 1420 | 1235.308s |
| optimized_v3_warm | standard | warm | 2200/64 | 84 | 1420 | 254.271s |

## Key Comparisons

- v3 cold vs baseline cold: 517.404s (29.52%)
- v3 cold vs v2 cold: -46.236s (-3.89%)
- v3 warm vs v3 cold: 981.037s (79.42%)
- v3 warm vs v2 warm: 19.604s (7.16%)

## Structural Deltas

- vs baseline: chunks 157 -> 84, calls 2437 -> 1420, tokens 8126259 -> 3691884
- vs v2: chunks 84 -> 84, calls 1424 -> 1420, tokens 3694891 -> 3691884

## Hot Phases

- optimized_v3_cold: extract_graph: 775.014s, create_community_reports: 273.007s, generate_text_embeddings: 178.041s
- optimized_v3_warm: create_community_reports: 94.999s, generate_text_embeddings: 76.954s, extract_graph: 74.022s

## Notes

- The v3 run reuses the same models, chunking, and report limits as v2; the main tested variable is `concurrent_requests: 64`.
- Baseline and v2 remain reference runs loaded from the latest benchmark on the same corpus rather than being recomputed in this faster v3 campaign.
- Watch the `extract_graph` tail latency in the artifact logs if the gain is weak: higher concurrency may compress average latency while leaving a heavy tail.
