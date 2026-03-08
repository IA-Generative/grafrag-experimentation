# GraphRAG Indexing Benchmark v5

- Generated at: 2026-03-08T14:45:28.605747+01:00
- Commit: 5d25c66
- Runner: docker
- Docker container: grafrag-experimentation-bridge-1
- GraphRAG: 3.0.6
- LiteLLM: 1.82.0
- Optimized profile: v5 (`concurrent_requests: 40`, `summarize_descriptions.max_length: 300`, `entity_types: [person, geo, event]`)
- Reference runs taken from: benchmarks/results.json, benchmarks/results.v3.json, benchmarks/results.v4.json

## Corpus

- Documents: 17
- Total size: 659262 bytes

## Runs

| Run | Method | Cache | Chunking | Chunks | Entities | Relationships | LLM calls | Total time |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| baseline_cold (reference) | standard | cold | 1200/100 | 157 | 3653 | 5203 | 2437 | 1752.712s |
| optimized_v2_cold (reference) | standard | cold | 2200/64 | 84 | 1844 | 3472 | 1424 | 1189.072s |
| optimized_v3_cold (reference) | standard | cold | 2200/64 | 84 | 1788 | 3274 | 1420 | 1235.308s |
| optimized_v4_cold (reference) | standard | cold | 2200/64 | 84 | 1777 | 3252 | 1367 | 1208.441s |
| optimized_v5_cold | standard | cold | 2200/64 | 84 | 1722 | 2704 | 1276 | 1977.432s |
| optimized_v5_warm | standard | warm | 2200/64 | 84 | 1722 | 2704 | 1276 | 228.716s |

## Key Comparisons

- v5 cold vs baseline cold: -224.720s (-12.82%)
- v5 cold vs v2 cold: -788.360s (-66.30%)
- v5 cold vs v3 cold: -742.124s (-60.08%)
- v5 cold vs v4 cold: -768.991s (-63.63%)
- v5 warm vs v5 cold: 1748.716s (88.43%)
- v5 warm vs v2 warm: 45.159s (16.49%)
- v5 warm vs v3 warm: 25.555s (10.05%)
- v5 warm vs v4 warm: 19.621s (7.90%)

## Structural Deltas

- vs baseline: chunks 157 -> 84, entities 3653 -> 1722, relationships 5203 -> 2704, community_reports 712 -> 259, calls 2437 -> 1276
- vs v2: chunks 84 -> 84, entities 1844 -> 1722, relationships 3472 -> 2704, community_reports 300 -> 259, calls 1424 -> 1276
- vs v4: chunks 84 -> 84, entities 1777 -> 1722, relationships 3252 -> 2704, community_reports 293 -> 259, calls 1367 -> 1276

## Hot Phases

- optimized_v5_cold: extract_graph: 996.071s, create_community_reports: 796.930s, generate_text_embeddings: 175.051s
- optimized_v5_warm: create_community_reports: 81.029s, generate_text_embeddings: 70.963s, extract_graph: 68.944s

## Notes

- The v5 run keeps the v2 cold-oriented concurrency target and the v4 shorter descriptions, but narrows entity extraction to `person`, `geo`, and `event`.
- This is a corpus-aware profile for the current medieval-wars benchmark corpus, not a generic GraphRAG default.
- The main tradeoff to inspect is whether the extract_graph gain justifies losing organization coverage.
