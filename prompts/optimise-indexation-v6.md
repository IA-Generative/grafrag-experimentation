Tu es un ingénieur logiciel senior spécialisé en Python, performance engineering, LLMOps, GraphRAG et intégration OpenAI-compatible.

Objectif
Réaliser une sixième itération d’optimisation de l’indexation GraphRAG en assumant un changement de classe de compromis : viser la vitesse cold via `fast`, tout en réduisant explicitement le coût de `community_reports`.

Etat actuel a respecter
- Le benchmark reproductible existe dans `scripts/benchmark_indexing.py`.
- Les profils existants sont :
  - `graphrag/settings.baseline.yaml`
  - `graphrag/settings.optimized.yaml`
  - `graphrag/settings.optimized.v2.yaml`
  - `graphrag/settings.optimized.v3.yaml`
  - `graphrag/settings.optimized.v4.yaml`
  - `graphrag/settings.optimized.v5.yaml`
  - `graphrag/settings.optimized.v6.yaml`
- Les artefacts déjà présents sont :
  - `benchmarks/results.json`
  - `benchmarks/summary.md`
  - `benchmarks/results.v4.json`
  - `benchmarks/summary.v4.md`
  - `benchmarks/results.v5.json`
  - `benchmarks/summary.v5.md`

Connaissance capitalisee
- La v2 reste le meilleur profil `standard` cold :
  - `1189.072 s`
- La v4 reste un bon profil `standard` warm :
  - cold `1208.441 s`
  - warm `248.337 s`
- La v5 a echoue en cold mais a donne le meilleur warm :
  - cold `1977.432 s`
  - warm `228.716 s`
- La v5 a montre qu’un gain structurel local peut deplacer le cout vers `community_reports`.

Hypothese v6
La v6 doit changer de strategie :
1. revenir au scope d’entites large des v2/v4 :
  - `organization`
  - `person`
  - `geo`
  - `event`
2. garder le chunking efficace :
  - `2200/64`
3. garder des descriptions courtes :
  - `summarize_descriptions.max_length: 300`
4. serrer davantage les rapports de communaute :
  - `community_reports.max_length: 900`
  - `community_reports.max_input_length: 4500`
5. executer le benchmark en methode :
  - `fast`

Intention technique
- `fast` doit attaquer directement le cout de `extract_graph`.
- Le serrage de `community_reports` doit eviter qu’un gain en amont soit reperdu en aval.
- Cette v6 n’est pas comparable qualitativement a la v2 ou la v4 comme un simple detail de tuning : elle assume une baisse de fidelite de graphe pour mesurer un plafond de vitesse pragmatique.

Travail demande
1. Verifier les resultats v2, v4 et v5 deja mesures.
2. Executer la v6 localement avec `--optimized-method fast`.
3. Comparer explicitement :
   - v6 cold vs baseline cold
   - v6 cold vs v2 cold
   - v6 cold vs v4 cold
   - v6 cold vs v5 cold
   - v6 warm vs v2 warm
   - v6 warm vs v4 warm
   - v6 warm vs v5 warm
4. Regarder en priorite :
   - `extract_graph`
   - `create_community_reports`
   - la baisse de structure produite
   - le compromis de fidelite induit par `fast`
5. Conclure honnêtement si la v6 peut devenir :
   - un profil `speed-first`
   - ou seulement un benchmark de borne basse

Point d’attention
- Ne pas presenter la v6 comme remplacement direct de la v2 sans signaler le changement de methode.
- Si la v6 est plus rapide mais qualitativement plus faible, il faut le dire explicitement.

Commandes attendues
- benchmark v6 fast :
  - `python3 scripts/benchmark_indexing.py --optimized-profile v6 --optimized-method fast`

Critere de reussite
Quelqu’un qui arrive ensuite dans le repository doit comprendre :
- pourquoi la v6 existe
- pourquoi la v5 ne suffisait pas
- quel compromis `community_reports / fast` est teste
- si la v6 est un vrai profil operational ou seulement un profil `speed-first`

Resultat mesure localement
- Commit de depart :
  - `9e8e7c5`
- Commande executee :
  - `python3 scripts/benchmark_indexing.py --optimized-profile v6 --optimized-method fast`
- Resultats :
  - v6 cold : `2691.599 s`
  - v6 warm : `236.611 s`

Comparaisons clefs
- v6 cold vs baseline cold :
  - `-938.887 s` soit `-53.57%`
- v6 cold vs v2 cold :
  - `-1502.527 s` soit `-126.36%`
- v6 cold vs v4 cold :
  - `-1483.158 s` soit `-122.73%`
- v6 cold vs v5 cold :
  - `-714.167 s` soit `-36.12%`
- v6 warm vs v2 warm :
  - `+37.264 s` soit `+13.61%`
- v6 warm vs v4 warm :
  - `+11.726 s` soit `+4.72%`
- v6 warm vs v5 warm :
  - `-7.895 s` soit `-3.45%`

Lecture technique
- `fast` a bien reduit le cout d’extraction amont :
  - `extract_graph_nlp: 83.034 s` en cold
- En revanche, la structure produite a explose en densite relationnelle :
  - `93117` relations
- Cette explosion a deplace le goulot principal vers :
  - `create_community_reports_text: 2419.096 s`
- La v6 reduit fortement les appels LLM :
  - `417`
- Mais ce gain ne compense pas le cout aval induit par le graphe plus dense.

Conclusion
- La v6 echoue comme profil `speed-first` cold operationnel.
- Elle reste interessante comme preuve de comportement :
  - `fast` peut accelerer l’extraction
  - mais peut aussi densifier fortement le graphe et faire exploser `community_reports`
- La v6 est donc a conserver comme benchmark exploratoire, pas comme nouveau profil par defaut.
- La suite logique est une v7 ciblee sur :
  - la reduction ou le plafonnement des relations
  - ou une simplification plus radicale de `community_reports` en mode `fast`
