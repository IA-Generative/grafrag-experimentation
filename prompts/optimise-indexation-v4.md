Tu es un ingénieur logiciel senior spécialisé en Python, performance engineering, LLMOps, GraphRAG et intégration OpenAI-compatible.

Objectif
Réaliser une quatrième itération d’optimisation de l’indexation GraphRAG en ciblant explicitement le point faible observé sur la v3 : la queue de latence du workflow `extract_graph`, qui a rendu la v3 plus lente que la v2 en cold run.

Etat actuel à respecter
- Le benchmark reproductible existe dans `scripts/benchmark_indexing.py`.
- Les profils existants sont :
  - `graphrag/settings.baseline.yaml`
  - `graphrag/settings.optimized.yaml`
  - `graphrag/settings.optimized.v2.yaml`
  - `graphrag/settings.optimized.v3.yaml`
  - `graphrag/settings.optimized.v4.yaml`
- Les artefacts déjà présents sont :
  - `benchmarks/results.json`
  - `benchmarks/summary.md`
  - `benchmarks/results.v3.json`
  - `benchmarks/summary.v3.md`

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

Lecture des itérations précédentes
- La v2 est le meilleur profil `standard` cold mesuré jusqu’ici.
- La v3, avec `concurrent_requests: 64`, est légèrement meilleure en warm, mais plus lente en cold que la v2 :
  - `+46.236 s` de régression cold
  - `-19.604 s` de gain warm
- La v3 n’a donc pas validé l’idée d’une montée forte de concurrence comme profil par défaut.

Point faible principal à corriger
- La queue de latence dans `extract_graph`.
- Le cold v3 est dominé par un `extract_graph` plus lent que la v2 :
  - v2 `extract_graph`: `713.967 s`
  - v3 `extract_graph`: `775.014 s`

Hypothèse v4
La v4 doit chercher un meilleur compromis que la v3 en :
1. réduisant la concurrence pour sortir de la zone de saturation probable
2. allégeant légèrement la fin du workflow `extract_graph` via des descriptions plus courtes

Profil v4 à tester
- `concurrent_requests: 48`
- même modèles que v2/v3
- même chunking que v2/v3 :
  - `2200/64`
- même contraintes sur `community_reports` que v2/v3
- `summarize_descriptions.max_length: 300`

Intention technique
- `48` est un compromis entre :
  - v2 à `40`, plus rapide en cold
  - v3 à `64`, meilleure en warm mais plus lente en cold
- la réduction de `summarize_descriptions.max_length` vise à raccourcir une partie du workflow `extract_graph` sans retoucher brutalement la structure du graphe

Travail demandé
1. Vérifier les résultats v2 et v3 déjà mesurés.
2. Exécuter la v4 localement.
3. Comparer explicitement :
   - v4 cold vs baseline cold
   - v4 cold vs v2 cold
   - v4 cold vs v3 cold
   - v4 warm vs v2 warm
   - v4 warm vs v3 warm
4. Regarder en priorité :
   - le temps de `extract_graph`
   - le temps total cold
   - la stabilité de la queue de latence
5. Conclure honnêtement :
   - garder v2
   - promouvoir v4
   - ou préparer une v5

Point d’attention
- Ne pas confondre amélioration warm et amélioration cold.
- Si la v4 ne bat pas la v2 en cold, il faut le dire clairement.
- Si la v4 améliore seulement légèrement le warm, cela ne suffit pas à en faire le nouveau défaut si l’objectif principal est la première indexation.

Commandes attendues
- benchmark v4 standard :
  - `python3 scripts/benchmark_indexing.py --optimized-profile v4`

Critère de réussite
Quelqu’un qui arrive ensuite dans le repository doit comprendre :
- pourquoi la v4 existe
- pourquoi la v3 n’a pas été retenue comme défaut
- quelle hypothèse exacte la v4 teste
- si la v4 corrige réellement ou non la régression cold de la v3

Resultat mesure localement
- `optimized_v4_cold`: `1208.441 s`
- `optimized_v4_warm`: `248.337 s`

Comparaisons cles
- vs baseline cold (`1752.712 s`) :
  - `+544.271 s`
  - `-31.05 %`
- vs v2 cold (`1189.072 s`) :
  - `-19.369 s`
  - `+1.63 %` plus lent que la v2
- vs v3 cold (`1235.308 s`) :
  - `+26.867 s`
  - `-2.17 %`
- vs v2 warm (`273.875 s`) :
  - `+25.538 s`
  - `-9.32 %`
- vs v3 warm (`254.271 s`) :
  - `+5.934 s`
  - `-2.33 %`

Lecture technique
- La v4 ameliore la v3 en temps total cold, mais ne reprend pas la premiere place a la v2.
- Le gain principal v4 ne vient pas d'une vraie correction de `extract_graph`.
- `extract_graph` reste pratiquement au niveau v3 et plus lent que v2 :
  - v2 `extract_graph`: `713.967 s`
  - v3 `extract_graph`: `775.014 s`
  - v4 `extract_graph`: `775.954 s`
- La v4 gagne surtout sur `create_community_reports` :
  - v2 `create_community_reports`: `276.969 s`
  - v3 `create_community_reports`: `273.007 s`
  - v4 `create_community_reports`: `240.043 s`
- La reduction de `summarize_descriptions.max_length` a bien reduit le cout de `summarize_descriptions`, mais n'a pas suffi a faire baisser le temps global de `extract_graph`.

Conclusion
- Garder la v2 comme profil `standard` cold par defaut.
- Considerer la v4 comme la meilleure variante `warm` observee jusqu'ici.
- Ne pas presenter la v4 comme correction definitive de la queue de latence `extract_graph`.
- La suite logique est une v5 qui cible directement `extract_graph` plutot que d'esperer un gain lateral via `community_reports`.
