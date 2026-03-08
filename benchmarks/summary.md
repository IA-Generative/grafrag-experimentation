# GraphRAG Indexing Benchmark

- Generated at: 2026-03-08T10:49:35.110671+01:00
- Commit: 726ebc8
- Runner: docker
- Docker container: grafrag-experimentation-bridge-1
- Host OS: macOS-26.3-arm64-arm-64bit
- Host Python: 3.11.3
- GraphRAG: 3.0.6
- LiteLLM: 1.82.0

## Corpus

- Documents: 17
- Total size: 659262 bytes

## Model Preflight

- Baseline chat: gpt-oss-120b
- Baseline embedding: bge-multilingual-gemma2 (3584 dims)
- Optimized chat: mistral-small-3.2-24b-instruct-2506
- Optimized embedding: qwen3-embedding-8b (4096 dims)

## Runs

| Run | Method | Cache | Chat model | Embedding model | Chunking | Chunks | LLM calls | Total time |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| baseline_cold | standard | cold | gpt-oss-120b | bge-multilingual-gemma2 | 1200/100 | 157 | 2437 | 1752.712s |
| optimized_cold | standard | cold | mistral-small-3.2-24b-instruct-2506 | qwen3-embedding-8b | 2200/64 | 84 | 1424 | 1189.072s |
| optimized_warm | standard | warm | mistral-small-3.2-24b-instruct-2506 | qwen3-embedding-8b | 2200/64 | 84 | 1424 | 273.875s |

## Before/After

- Baseline cold: 1752.712s
- Optimized cold: 1189.072s
- Absolute gain: 563.640s
- Relative gain: 32.16%
- Optimized warm: 273.875s
- Warm vs optimized cold gain: 915.197s (76.97%)

## Hot Phases

- baseline_cold: extract_graph: 846.963s, create_community_reports: 577.003s, generate_text_embeddings: 319.030s
- optimized_cold: extract_graph: 713.967s, create_community_reports: 276.969s, generate_text_embeddings: 190.009s
- optimized_warm: create_community_reports: 103.959s, generate_text_embeddings: 83.995s, extract_graph: 77.951s

## Observations

- Cold runs were executed with GraphRAG cache enabled but empty; warm means the optimized cache was preserved while output artifacts were rebuilt.
- The optimized profile stays on `standard` by default, so the main tradeoff is model size plus larger chunks rather than the noisier `fast` graph extraction path.
- Baseline quality note: Reference run with standard indexing, baseline chunking, and the baseline chat/embedding models.
- Optimized quality note: Standard indexing kept, with more aggressive concurrency, larger chunks, shorter summaries, and leaner community reports to reduce cold latency. Expect a sparser graph and less detailed community reports than v1.
- Scaleway cache metrics exposed token counts and call volumes, but cost stayed at `0.0` in provider metrics, so no monetary estimate could be derived reliably.

## Recommendations

- Default to the optimized profile for local and CI indexing when standard GraphRAG quality is still required.
- Keep the warm-cache path for iterative corpus relaunches; it is a separate benchmark class and should not be compared directly to first-run latency.
- If you can accept lower graph fidelity on this French corpus, test `python3 scripts/benchmark_indexing.py --optimized-method fast` as a follow-up experiment.
