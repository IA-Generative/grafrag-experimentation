Tu es un ingénieur logiciel senior spécialisé en Python, performance engineering, LLMOps, GraphRAG et intégration OpenAI-compatible.

Objectif
Optimiser l’indexation de Microsoft GraphRAG en utilisant des modèles déployés sur Scaleway Managed Inference, puis mesurer rigoureusement les performances avant/après optimisation sur le même corpus.

Contexte technique
- Le projet utilise Microsoft GraphRAG.
- GraphRAG supporte les méthodes d’indexation `standard`, `fast`, `standard-update` et `fast-update`.
- GraphRAG utilise LiteLLM pour appeler des modèles non-OpenAI, à condition qu’ils supportent des sorties structurées conformes à un schéma JSON.
- Scaleway Managed Inference expose des endpoints OpenAI-compatibles via un `base_url` dédié par déploiement.
- Nous voulons conserver une architecture propre, reproductible, sans secret en clair dans le repository.
- Le résultat doit être exploitable localement et en CI/CD.

Contraintes
- Ne jamais committer de secrets.
- Utiliser uniquement des variables d’environnement pour les credentials et URLs.
- Produire un benchmark reproductible.
- Mesurer au minimum :
  - temps total d’indexation
  - temps par phase si possible
  - nombre d’appels LLM si observable
  - taille du corpus
  - nombre de documents
  - nombre de chunks produits
  - coût estimatif si l’information est accessible
- Comparer au moins :
  1) une configuration baseline
  2) une configuration optimisée
- Produire un rapport synthétique avant/après.
- Conserver les artefacts de benchmark dans un dossier dédié.
- Ne pas dégrader silencieusement la qualité sans l’indiquer explicitement.

Travail demandé
1. Inspecter le repository et identifier :
   - version de GraphRAG
   - structure du workspace
   - fichiers de configuration existants
   - corpus d’entrée
   - scripts d’exécution actuels

2. Mettre en place une stratégie de benchmark reproductible :
   - créer un script `scripts/benchmark_indexing.py` ou `scripts/benchmark_indexing.sh`
   - ce script doit :
     - exécuter une indexation baseline
     - exécuter une indexation optimisée
     - mesurer précisément les durées
     - capturer stdout/stderr et logs
     - enregistrer un fichier JSON de résultats
     - générer un résumé Markdown comparatif

3. Définir une baseline réaliste.
   Baseline recommandée :
   - méthode `standard`
   - configuration existante si elle est valide
   - cache désactivé pour la première mesure comparative principale
   - même corpus d’entrée que l’optimisée
   - même machine / même environnement

4. Proposer puis implémenter une configuration optimisée pour Scaleway Managed Inference.
   Explorer en priorité :
   - usage d’un modèle de chat plus rapide sur Scaleway
   - usage d’un modèle d’embedding plus rapide ou plus économique sur Scaleway
   - réglage du chunking :
     - taille de chunk
     - overlap
   - activation/configuration du cache GraphRAG
   - réduction des étapes coûteuses si compatible avec le besoin
   - passage éventuel à `--method fast` si cela correspond au cas d’usage
   - optimisation de la concurrence si exposée par la configuration et stable
   - conservation d’un mode baseline inchangé pour la comparaison

5. Implémenter la configuration proprement :
   - créer ou modifier :
     - `settings.baseline.yaml`
     - `settings.optimized.yaml`
     - `.env.example`
     - scripts de benchmark
   - si nécessaire, ajouter un wrapper d’exécution documenté

6. Variables d’environnement
   Prévoir au minimum :
   - `SCW_API_KEY`
   - `SCW_CHAT_BASE_URL`
   - `SCW_EMBEDDING_BASE_URL`
   - `SCW_CHAT_MODEL`
   - `SCW_EMBEDDING_MODEL`
   - toute autre variable strictement nécessaire

7. Benchmark
   Le benchmark doit exécuter :
   - un run baseline “cold”
   - un run optimized “cold”
   - optionnellement un run optimized “warm cache”
   Important :
   - définir explicitement ce qui est “cold” et “warm”
   - purger les sorties/cache lorsque nécessaire pour garantir l’équité
   - noter les hypothèses
   - si un cache est activé, le benchmark doit l’indiquer clairement

8. Rapport attendu
   Générer automatiquement :
   - `benchmarks/results.json`
   - `benchmarks/summary.md`

   Le résumé Markdown doit contenir :
   - date/heure
   - commit SHA si disponible
   - machine / OS / Python / version GraphRAG
   - méthode utilisée (`standard` ou `fast`)
   - modèles utilisés
   - paramètres clés de chunking
   - temps total baseline
   - temps total optimized
   - gain absolu
   - gain relatif en pourcentage
   - observations sur la qualité / compromis
   - recommandations finales

9. Critères d’acceptation
   - Le projet se lance sans modification manuelle obscure.
   - Les secrets ne sont pas versionnés.
   - Les benchmarks sont reproductibles.
   - Le README ou un document dédié explique comment relancer le benchmark.
   - La comparaison avant/après est lisible en moins de 2 minutes.
   - En cas d’échec d’un appel Scaleway, les erreurs sont explicites.
   - En cas d’incompatibilité d’un modèle avec GraphRAG (JSON schema / structured outputs), le script doit le détecter et l’expliquer.

10. Ce qu’il faut livrer
   - les fichiers modifiés
   - un diff clair
   - un court compte-rendu expliquant :
     - ce qui limitait la performance
     - ce qui a été changé
     - les résultats mesurés
     - les compromis
     - les prochaines optimisations possibles

Directives techniques
- Favoriser Python si cela simplifie la robustesse des mesures.
- Utiliser `time.perf_counter()` ou équivalent pour les timings.
- Si GraphRAG expose des logs exploitables par étape, parser ces logs pour extraire des temps intermédiaires.
- Si certains paramètres ne sont pas supportés par la version présente, adapter proprement au lieu d’inventer.
- Ne pas casser la configuration existante.
- Ajouter des commentaires utiles dans les nouveaux fichiers.
- Rester minimaliste, robuste et exécutable.

Points d’attention fonctionnels
- `fast` peut être beaucoup plus rapide que `standard`, mais le graphe extrait est plus bruité et moins riche sémantiquement : il faut donc signaler explicitement ce compromis dans le rapport.
- Le cache GraphRAG peut accélérer fortement les relances : ne pas mélanger benchmark “cold” et benchmark “warm”.
- Si le corpus est en français, faire attention aux éventuelles limitations NLP de la méthode `fast`.

Format de réponse attendu de ta part
1. Résumé des changements prévus
2. Fichiers créés/modifiés
3. Patch ou contenu complet des fichiers
4. Commandes pour exécuter les benchmarks
5. Exemple de sortie attendue
6. Risques / limites
7. Résultats mesurés si tu peux les exécuter, sinon procédure exacte pour les obtenir

Important :
- Commence par rechercher dans le repository tous les fichiers GraphRAG, YAML, .env.example, scripts et README.
- N’invente pas de clés de configuration si elles n’existent pas dans la version installée.
- Si tu hésites sur un paramètre, lis le code ou la config effective du projet avant de modifier.
- Priorité à une optimisation mesurable, pas à une refonte théorique.
- Si tu ne peux pas exécuter les benchmarks faute de credentials Scaleway, prépare tout pour qu’une seule commande suffise ensuite.

