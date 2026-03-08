# GraphRAG Indexing Benchmark

- Generated at: 2026-03-08T10:25:32.366108+01:00
- Commit: 425c3c8
- Runner: docker (`grafrag-experimentation-bridge-1`)
- Host OS: macOS-26.3-arm64-arm-64bit
- Host Python: 3.11.3
- GraphRAG: 3.0.6
- LiteLLM: 1.82.0

## Corpus

- Documents: 17
- Total size: 638699 bytes

## Runs

| Run | Method | Cache | Chat model | Embedding model | Chunking | Chunks | LLM calls | Total time |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| baseline_cold_reconstructed | standard | cold* | gpt-oss-120b | bge-multilingual-gemma2 | 1200/100 | 157 | 2410 | 2061.491s |
| optimized_cold | standard | cold | mistral-small-3.2-24b-instruct-2506 | qwen3-embedding-8b | 1800/80 | 106 | 1712 | 1538.733s |
| optimized_warm | standard | warm | mistral-small-3.2-24b-instruct-2506 | qwen3-embedding-8b | 1800/80 | 106 | 1712 | 325.060s |

`cold*` = baseline reconstructed from a cold run that reached the last workflow plus a warm replay after forcing `TMPDIR=/tmp` inside the container.

## Before/After

- Baseline reconstructed cold: 2061.491s
- Optimized cold: 1538.733s
- Absolute gain: 522.758s
- Relative gain: 25.36%
- Optimized warm: 325.060s
- Warm vs optimized cold gain: 1213.673s (78.87%)

## Structural Impact

- Chunks: 157 -> 106 (-32.48%)
- Entities: 3513 -> 2073 (-40.99%)
- Relationships: 4950 -> 3920 (-20.81%)
- Community reports: 653 -> 337 (-48.39%)
- Observed LLM calls: 2410 -> 1712 (-28.96%)
- Observed tokens: 7868512 -> 4482375 (-43.03%)

## Proxy Cost

- Baseline cold proxy: $2.4353
- Optimized cold proxy: $0.8898
- Proxy gain: $1.5455 (63.46%)
- Caveat: token-price proxy only, not authoritative dedicated Managed Inference billing.

## Observations

- The dominant cold-cost drivers are still `extract_graph`, `summarize_descriptions`, and `create_community_reports`.
- The optimized profile kept `standard`, so the main tradeoff is lower graph density plus a smaller/faster chat model rather than the noisier `fast` method.
- The warm-cache replay is dramatically faster, but it is a different benchmark class from first-run latency.
- For the same corpus, the optimized profile cut chunks by about one third and total observed tokens by about 43%, which explains the time and cost deltas.

## Recommendations

- Use the optimized profile as the default local/CI indexing profile when you still need `standard` GraphRAG quality.
- Keep `fast` as a separate experiment only if you accept a noisier graph on French content.
- Next optimization targets to explore: increase `concurrent_requests` toward the documented Scaleway ceiling, reduce `community_reports` breadth if acceptable, and benchmark a more aggressive chunk size once retrieval quality has been checked.
