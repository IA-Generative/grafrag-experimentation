Tu es un ingénieur logiciel senior spécialisé en Python, performance engineering, LLMOps, GraphRAG et intégration OpenAI-compatible.

Objectif
Réaliser une troisième itération d’optimisation de l’indexation GraphRAG en gardant la méthode `standard`, mais en testant une montée franche de concurrence côté endpoint pour voir si le goulot principal devient la saturation ou si un nouveau gain de latence cold est encore possible.

Etat actuel à respecter
- Le benchmark reproductible existe dans `scripts/benchmark_indexing.py`.
- Les profils existants sont :
  - `graphrag/settings.baseline.yaml`
  - `graphrag/settings.optimized.yaml`
  - `graphrag/settings.optimized.v2.yaml`
  - `graphrag/settings.optimized.v3.yaml`
- Les derniers résultats connus sont dans `benchmarks/results.json` et `benchmarks/summary.md`.

Connaissance capitalisée avant la v3
- Baseline cold mesurée localement :
  - `1752.712 s`
  - `157` chunks
  - `2437` appels LLM observés
  - `8126259` tokens observés
- Optimized v2 cold :
  - `1189.072 s`
  - `84` chunks
  - `1424` appels LLM observés
  - `3694891` tokens observés
- Optimized v2 warm :
  - `273.875 s`
- Gain v2 cold vs baseline :
  - `563.640 s`
  - `32.16 %`
- Gain v2 warm vs v2 cold :
  - `915.197 s`
  - `76.97 %`

Lecture de la v2
- La v2 a déjà fortement compressé le pipeline :
  - chunks `157 -> 84`
  - appels LLM `2437 -> 1424`
  - tokens `8126259 -> 3694891`
- Les phases dominantes restent :
  - `extract_graph`
  - `create_community_reports`
  - `generate_text_embeddings`
- La prochaine hypothèse la plus propre à tester est la montée de `concurrent_requests`, sans remodifier en même temps le chunking ou les longueurs de résumés.

Hypothèse v3
La v3 doit garder le profil sémantique de la v2, mais pousser `concurrent_requests` à une valeur >= `64` sans dépasser `80`.

Choix demandé
- Profil principal à valider : `concurrent_requests: 64`
- Ne pas dépasser `80`
- Ne pas basculer par défaut en `fast`
- Ne pas modifier silencieusement le modèle de chat, le modèle d’embedding, le chunking, ni les contraintes de résumé par rapport à la v2

Ce qu’il faut mesurer
1. temps cold v3
2. temps warm v3
3. comparaison v3 vs v2
4. comparaison v3 vs baseline
5. évolution des :
   - chunks
   - appels LLM
   - tokens
   - entités
   - relations
   - communautés
   - community reports
6. stabilité :
   - erreurs
   - retries
   - symptômes de throttling
   - éventuelle dégradation de la queue de latence

Point d’attention majeur
Une hausse de concurrence peut améliorer la latence globale si l’endpoint absorbe la charge, mais peut aussi :
- ne rien changer
- dégrader la queue de latence
- créer plus de variance entre chunks
- provoquer du throttling ou des délais erratiques

Travail demandé
1. Vérifier l’état réel du repository.
2. Vérifier les derniers résultats v2.
3. Exécuter une campagne v3 locale.
4. Produire un compte-rendu honnête :
   - si la v3 gagne, quantifier le gain
   - si la v3 ne gagne pas, le dire clairement
   - si la v3 devient instable, le dire clairement
5. Proposer ensuite :
   - soit de garder la v3
   - soit de revenir à la v2
   - soit de préparer une v4 ciblant une autre piste

Commandes attendues
- benchmark v3 standard :
  - `python3 scripts/benchmark_indexing.py --optimized-profile v3`
- test séparé `fast` uniquement si besoin :
  - `python3 scripts/benchmark_indexing.py --optimized-profile v3 --optimized-method fast`

Critère de réussite
Quelqu’un qui arrive ensuite dans le repository doit comprendre immédiatement :
- pourquoi la v3 existe
- ce qu’elle change par rapport à la v2
- quelle plage de concurrence a été testée
- si la montée à `64+` est utile ou non

Résultats v3 déjà mesurés localement le 2026-03-08
- Profil testé :
  - `concurrent_requests: 64`
  - même modèles, chunking et contraintes de résumé que la v2
- Optimized v3 cold :
  - `1235.308 s`
  - `84` chunks
  - `1420` appels LLM observés
  - `3691884` tokens observés
- Optimized v3 warm :
  - `254.271 s`
- v3 cold vs baseline cold :
  - `517.404 s`
  - `29.52 %`
- v3 cold vs v2 cold :
  - `-46.236 s`
  - `-3.89 %`
  - donc la v3 est plus lente que la v2 en cold
- v3 warm vs v2 warm :
  - `19.604 s`
  - `7.16 %`
  - donc la v3 est légèrement meilleure en warm

Lecture honnête du test
- Monter à `64` n’a pas cassé le pipeline.
- Monter à `64` n’a pas amélioré le cold run par rapport à la v2.
- Le gain warm existe, mais il ne compense pas la régression cold si l’objectif principal reste la première indexation.
- Le point faible principal observé est la queue de latence dans `extract_graph`.

Conclusion recommandée
- Garder la v2 comme profil `standard` par défaut.
- Considérer la v3 comme un profil expérimental utile seulement si l’usage privilégie fortement les relances warm.
- Si une v4 est tentée, éviter d’augmenter encore la concurrence par défaut sans traiter d’abord la variance de `extract_graph`.
