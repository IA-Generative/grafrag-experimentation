Tu es un ingénieur logiciel senior spécialisé en Python, performance engineering, LLMOps, GraphRAG et intégration OpenAI-compatible.

Objectif
Réaliser une cinquième itération d’optimisation de l’indexation GraphRAG en ciblant enfin directement `extract_graph`, qui reste le principal goulet d’étranglement cold malgré les v2, v3 et v4.

Etat actuel à respecter
- Le benchmark reproductible existe dans `scripts/benchmark_indexing.py`.
- Les profils existants sont :
  - `graphrag/settings.baseline.yaml`
  - `graphrag/settings.optimized.yaml`
  - `graphrag/settings.optimized.v2.yaml`
  - `graphrag/settings.optimized.v3.yaml`
  - `graphrag/settings.optimized.v4.yaml`
  - `graphrag/settings.optimized.v5.yaml`
- Les artefacts déjà présents sont :
  - `benchmarks/results.json`
  - `benchmarks/summary.md`
  - `benchmarks/results.v3.json`
  - `benchmarks/summary.v3.md`
  - `benchmarks/results.v4.json`
  - `benchmarks/summary.v4.md`

Connaissance capitalisée
- Baseline cold :
  - `1752.712 s`
- Optimized v2 cold :
  - `1189.072 s`
- Optimized v2 warm :
  - `273.875 s`
- Optimized v3 cold :
  - `1235.308 s`
- Optimized v3 warm :
  - `254.271 s`
- Optimized v4 cold :
  - `1208.441 s`
- Optimized v4 warm :
  - `248.337 s`

Lecture des itérations précédentes
- La v2 reste le meilleur profil `standard` cold.
- La v3 a montré qu’une forte montée de concurrence n’améliore pas le cold sur ce corpus.
- La v4 a amélioré le warm et réduit le coût de `create_community_reports`, mais n’a pas réellement amélioré `extract_graph` :
  - v2 `extract_graph`: `713.967 s`
  - v3 `extract_graph`: `775.014 s`
  - v4 `extract_graph`: `775.954 s`

Point faible principal a corriger
- `extract_graph` reste trop cher.
- Les itérations v3 et v4 n’ont pas réduit ce temps malgré des ajustements de concurrence et de longueur de résumés.

Hypothese v5
La v5 doit tester un levier plus direct et plus sémantique :
1. revenir à la stabilité cold de la v2 avec `concurrent_requests: 40`
2. garder les descriptions plus courtes de la v4 avec `summarize_descriptions.max_length: 300`
3. réduire le travail de `extract_graph` en restreignant `entity_types` à :
  - `person`
  - `geo`
  - `event`

Justification technique
- Le corpus benchmarké est majoritairement centré sur les guerres médiévales, leurs acteurs et leurs lieux.
- Le type `organization` génère aussi du bruit depuis les documents techniques du repo présents dans le corpus.
- La v5 assume explicitement un graphe plus orienté histoire/personnes/lieux/événements, avec moins d’institutions et moins de bruit infra.

Profil v5 a tester
- `concurrent_requests: 40`
- chunking inchangé :
  - `2200/64`
- `summarize_descriptions.max_length: 300`
- `community_reports.max_length: 1200`
- `community_reports.max_input_length: 6000`
- `extract_graph.entity_types: [person, geo, event]`

Travail demande
1. Vérifier les résultats v2, v3 et v4 déjà mesurés.
2. Exécuter la v5 localement.
3. Comparer explicitement :
   - v5 cold vs baseline cold
   - v5 cold vs v2 cold
   - v5 cold vs v3 cold
   - v5 cold vs v4 cold
   - v5 warm vs v2 warm
   - v5 warm vs v3 warm
   - v5 warm vs v4 warm
4. Regarder en priorité :
   - `extract_graph`
   - le volume d’entités
   - le volume de relations
   - la perte éventuelle sur les entités `organization`
5. Conclure honnêtement si la réduction du scope sémantique vaut le gain de temps.

Point d’attention
- Cette v5 n’est pas un profil générique universel.
- Elle est volontairement orientée par le corpus courant.
- Si elle accélère vraiment `extract_graph`, il faudra la présenter comme un profil corpus-specifique, pas comme une vérité globale.

Commandes attendues
- benchmark v5 standard :
  - `python3 scripts/benchmark_indexing.py --optimized-profile v5`

Critere de reussite
Quelqu’un qui arrive ensuite dans le repository doit comprendre :
- pourquoi la v5 existe
- pourquoi la v4 ne suffisait pas
- quel compromis sémantique exact la v5 assume
- si la baisse du coût `extract_graph` justifie la perte de couverture `organization`

Resultat mesure localement
- `optimized_v5_cold`: `1977.432 s`
- `optimized_v5_warm`: `228.716 s`

Comparaisons cles
- vs baseline cold (`1752.712 s`) :
  - `-224.720 s`
  - `+12.82 %` plus lent que la baseline
- vs v2 cold (`1189.072 s`) :
  - `-788.360 s`
  - `+66.30 %` plus lent que la v2
- vs v3 cold (`1235.308 s`) :
  - `-742.124 s`
  - `+60.08 %`
- vs v4 cold (`1208.441 s`) :
  - `-768.991 s`
  - `+63.63 %`
- vs v2 warm (`273.875 s`) :
  - `+45.159 s`
  - `-16.49 %`
- vs v3 warm (`254.271 s`) :
  - `+25.555 s`
  - `-10.05 %`
- vs v4 warm (`248.337 s`) :
  - `+19.621 s`
  - `-7.90 %`

Lecture technique
- La v5 reduit bien la structure produite :
  - entites `1844 -> 1722` vs v2
  - relations `3472 -> 2704` vs v2
  - `community_reports` `300 -> 259` vs v2
  - appels LLM `1424 -> 1276` vs v2
- Mais elle echoue nettement en cold.
- `extract_graph` devient encore plus lent :
  - v2 `extract_graph`: `713.967 s`
  - v4 `extract_graph`: `775.954 s`
  - v5 `extract_graph`: `996.071 s`
- Le vrai effondrement cold vient aussi de `create_community_reports` :
  - v2 `create_community_reports`: `276.969 s`
  - v4 `create_community_reports`: `240.043 s`
  - v5 `create_community_reports`: `796.930 s`
- Pourtant la v5 genere moins de rapports et moins de tokens de `community_reporting` :
  - v4 `community_reporting`: `1371939` tokens, `4399.083 s` compute, `293` requetes
  - v5 `community_reporting`: `1207529` tokens, `5932.891 s` compute, `259` requetes
- Conclusion probable : en retirant `organization`, la v5 fusionne le graphe en communautes moins nombreuses mais plus lourdes, avec une queue de latence plus severe sur les rapports de communaute.
- `summarize_descriptions` n'aide pas non plus :
  - v4 `296173` tokens, `1290.811 s` compute
  - v5 `281609` tokens, `2000.456 s` compute

Conclusion
- La v5 est un echec comme profil cold.
- La v5 devient en revanche le meilleur profil warm mesure jusqu'ici.
- Il ne faut pas promouvoir la v5 comme profil par defaut.
- La lecon utile est negative mais claire : reduire le scope sémantique de `extract_graph` ne suffit pas, et peut deplacer le cout vers `community_reports`.
- La suite logique est une v6 qui traite explicitement :
  - soit la generation de `community_reports`
  - soit une strategie `fast` mesuree a part
  - soit un profil corpus-specifique separe qui isole vraiment les documents techniques parasites du corpus benchmarke
