# GraphRAG Indexing Benchmark v6

- Generated at: 2026-03-08T17:57:32.155071+01:00
- Commit: 9e8e7c5
- Runner: docker
- Docker container: grafrag-experimentation-bridge-1
- GraphRAG: 3.0.6
- LiteLLM: 1.82.0
- Optimized profile: v6 (`fast`, `concurrent_requests: 40`, `summarize_descriptions.max_length: 300`, `community_reports.max_length: 900`, `community_reports.max_input_length: 4500`)
- Reference runs taken from: benchmarks/results.json, benchmarks/results.v4.json, benchmarks/results.v5.json

## Corpus

- Documents: 17
- Total size: 659262 bytes

## Runs

| Run | Method | Cache | Chunking | Chunks | Entities | Relationships | Community reports | LLM calls | Total time |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_cold (reference) | standard | cold | 1200/100 | 157 | 3653 | 5203 | 712 | 2437 | 1752.712s |
| optimized_v2_cold (reference) | standard | cold | 2200/64 | 84 | 1844 | 3472 | 300 | 1424 | 1189.072s |
| optimized_v4_cold (reference) | standard | cold | 2200/64 | 84 | 1777 | 3252 | 293 | 1367 | 1208.441s |
| optimized_v5_cold (reference) | standard | cold | 2200/64 | 84 | 1722 | 2704 | 259 | 1276 | 1977.432s |
| optimized_v6_cold | fast | cold | 2200/64 | 84 | 1305 | 93117 | 307 | 417 | 2691.599s |
| optimized_v6_warm | fast | warm | 2200/64 | 84 | 1305 | 93117 | 307 | 417 | 236.611s |

## Key Comparisons

- v6 cold vs baseline cold: -938.887s (-53.57%)
- v6 cold vs v2 cold: -1502.527s (-126.36%)
- v6 cold vs v4 cold: -1483.158s (-122.73%)
- v6 cold vs v5 cold: -714.167s (-36.12%)
- v6 warm vs v6 cold: 2454.988s (91.21%)
- v6 warm vs v2 warm: 37.264s (13.61%)
- v6 warm vs v4 warm: 11.726s (4.72%)
- v6 warm vs v5 warm: -7.895s (-3.45%)

## Structural Deltas

- vs baseline: chunks 157 -> 84, entities 3653 -> 1305, relationships 5203 -> 93117, community_reports 712 -> 307, calls 2437 -> 417
- vs v2: chunks 84 -> 84, entities 1844 -> 1305, relationships 3472 -> 93117, community_reports 300 -> 307, calls 1424 -> 417
- vs v4: chunks 84 -> 84, entities 1777 -> 1305, relationships 3252 -> 93117, community_reports 293 -> 307, calls 1367 -> 417
- vs v5: chunks 84 -> 84, entities 1722 -> 1305, relationships 2704 -> 93117, community_reports 259 -> 307, calls 1276 -> 417

## Hot Phases

- optimized_v6_cold: create_community_reports_text: 2419.096s, generate_text_embeddings: 141.020s, extract_graph_nlp: 83.034s
- optimized_v6_warm: create_community_reports_text: 116.929s, generate_text_embeddings: 65.981s, finalize_graph: 21.013s

## Notes

- The v6 run explicitly switches to `fast`; it is a speed-first profile, not a drop-in quality-equivalent replacement for the standard v2/v4 runs.
- The profile keeps the broader entity scope and tries to control the downstream budget by tightening community report size and input limits.
- The key question is whether the cold gain is strong enough to justify the expected loss in graph fidelity.
