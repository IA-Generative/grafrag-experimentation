# GraphRAG Indexing Benchmark v4

- Generated at: 2026-03-08T13:08:21.144628+01:00
- Commit: 26ca72c
- Runner: docker
- Docker container: grafrag-experimentation-bridge-1
- GraphRAG: 3.0.6
- LiteLLM: 1.82.0
- Optimized profile: v4 (`concurrent_requests: 48`, `summarize_descriptions.max_length: 300`)
- Reference runs taken from: benchmarks/results.json, benchmarks/results.v3.json

## Corpus

- Documents: 17
- Total size: 659262 bytes

## Runs

| Run | Method | Cache | Chunking | Chunks | LLM calls | Total time |
| --- | --- | --- | --- | ---: | ---: | ---: |
| baseline_cold (reference) | standard | cold | 1200/100 | 157 | 2437 | 1752.712s |
| optimized_v2_cold (reference) | standard | cold | 2200/64 | 84 | 1424 | 1189.072s |
| optimized_v3_cold (reference) | standard | cold | 2200/64 | 84 | 1420 | 1235.308s |
| optimized_v4_cold | standard | cold | 2200/64 | 84 | 1367 | 1208.441s |
| optimized_v4_warm | standard | warm | 2200/64 | 84 | 1367 | 248.337s |

## Key Comparisons

- v4 cold vs baseline cold: 544.271s (31.05%)
- v4 cold vs v2 cold: -19.369s (-1.63%)
- v4 cold vs v3 cold: 26.867s (2.17%)
- v4 warm vs v4 cold: 960.104s (79.45%)
- v4 warm vs v2 warm: 25.538s (9.32%)
- v4 warm vs v3 warm: 5.934s (2.33%)

## Structural Deltas

- vs baseline: chunks 157 -> 84, calls 2437 -> 1367, tokens 8126259 -> 3734956
- vs v2: chunks 84 -> 84, calls 1424 -> 1367, tokens 3694891 -> 3734956
- vs v3: chunks 84 -> 84, calls 1420 -> 1367, tokens 3691884 -> 3734956

## Hot Phases

- optimized_v4_cold: extract_graph: 775.954s, create_community_reports: 240.043s, generate_text_embeddings: 184.922s
- optimized_v4_warm: create_community_reports: 92.027s, generate_text_embeddings: 74.976s, extract_graph: 73.932s

## Notes

- The v4 run rolls back concurrency from 64 to 48 and trims `summarize_descriptions.max_length` from 350 to 300.
- The goal is to reduce the `extract_graph` tail observed on v3 without giving up the v2/v3 chunking and reporting gains.
- Baseline, v2, and v3 remain reference runs loaded from prior local measurements on the same corpus.
